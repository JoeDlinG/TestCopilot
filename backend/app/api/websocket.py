"""WebSocket endpoints for real-time communication."""
import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.com_logger import com_logger

logger = logging.getLogger(__name__)

router = APIRouter()

# Connection pools
_execution_connections: Dict[str, set] = {}  # execution_id -> set of websockets
_device_connections: Dict[str, set] = {}  # device_id -> set of websockets

# Background receive tasks per device WebSocket connection
_receive_tasks: Dict[str, asyncio.Task] = {}


async def broadcast_execution_update(execution_id: str, message: Dict[str, Any]):
    """Broadcast execution status update to all connected clients."""
    if execution_id in _execution_connections:
        dead = set()
        for ws in _execution_connections[execution_id]:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        _execution_connections[execution_id] -= dead


async def broadcast_device_update(device_id: str, message: Dict[str, Any]):
    """Broadcast device status update to all connected clients."""
    if device_id in _device_connections:
        dead = set()
        for ws in _device_connections[device_id]:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        _device_connections[device_id] -= dead


def _get_device_interface(device_id: str):
    """Get the active communication interface for a device."""
    try:
        from app.services.device_service import _active_connections
        return _active_connections.get(device_id)
    except ImportError:
        return None


async def _receive_loop(device_id: str, websocket: WebSocket, interval_ms: int):
    """Background task that continuously polls device for unsolicited data."""
    task_id = f"{device_id}_{id(websocket)}"
    logger.info(f"Starting receive loop for {device_id} (task: {task_id})")
    try:
        while True:
            interface = _get_device_interface(device_id)
            if interface is None:
                await websocket.send_json({
                    "type": "device_disconnected",
                    "message": "Device connection lost",
                    "timestamp": datetime.utcnow().isoformat(),
                })
                break

            try:
                data = await interface.receive(timeout=0.1)
                if data:
                    ts = datetime.utcnow().isoformat()
                    com_logger.log_received(device_id, data, timestamp=ts)
                    await websocket.send_json({
                        "type": "device_data",
                        "data": data,
                        "timestamp": ts,
                    })
            except asyncio.TimeoutError:
                pass
            except Exception as e:
                logger.debug(f"Receive loop transient error for {device_id}: {e}")
                # Continue polling despite transient errors

            await asyncio.sleep(interval_ms / 1000.0)
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected during receive loop for {device_id}")
    except Exception as e:
        logger.error(f"Receive loop fatal error for {device_id}: {e}")
        try:
            await websocket.send_json({
                "type": "receive_error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            })
        except Exception:
            pass
    finally:
        _receive_tasks.pop(task_id, None)
        logger.info(f"Receive loop stopped for {device_id} (task: {task_id})")


def _stop_receive_task(device_id: str, websocket: WebSocket):
    """Stop the background receive task for a WebSocket connection."""
    task_id = f"{device_id}_{id(websocket)}"
    task = _receive_tasks.pop(task_id, None)
    if task and not task.done():
        task.cancel()
        logger.info(f"Cancelled receive task for {device_id}")


@router.websocket("/ws/executions/{execution_id}")
async def execution_websocket(websocket: WebSocket, execution_id: str):
    """WebSocket for real-time execution monitoring."""
    await websocket.accept()

    if execution_id not in _execution_connections:
        _execution_connections[execution_id] = set()
    _execution_connections[execution_id].add(websocket)

    try:
        # Send initial connection confirmation
        await websocket.send_json({
            "type": "connected",
            "execution_id": execution_id,
            "message": "Connected to execution monitor",
        })

        # Keep connection alive, listen for client messages
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                msg_type = msg.get("type", "")

                if msg_type == "ping":
                    await websocket.send_json({"type": "pong"})
                elif msg_type == "subscribe":
                    sub_id = msg.get("execution_id", execution_id)
                    if sub_id not in _execution_connections:
                        _execution_connections[sub_id] = set()
                    _execution_connections[sub_id].add(websocket)
                elif msg_type == "unsubscribe":
                    sub_id = msg.get("execution_id", execution_id)
                    if sub_id in _execution_connections:
                        _execution_connections[sub_id].discard(websocket)

            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid JSON",
                })

    except WebSocketDisconnect:
        logger.info(f"Execution WS disconnected: {execution_id}")
    finally:
        if execution_id in _execution_connections:
            _execution_connections[execution_id].discard(websocket)


@router.websocket("/ws/devices/{device_id}")
async def device_websocket(websocket: WebSocket, device_id: str):
    """WebSocket for real-time device communication terminal.

    Supports:
    - command: Execute a command on the device and return the response
    - start_receive: Start background polling for unsolicited device data
    - stop_receive: Stop background polling
    - ping: Keep-alive
    """
    await websocket.accept()

    if device_id not in _device_connections:
        _device_connections[device_id] = set()
    _device_connections[device_id].add(websocket)

    # Check if device has an active connection
    interface = _get_device_interface(device_id)
    if interface is None:
        await websocket.send_json({
            "type": "error",
            "message": f"Device {device_id} is not connected. Please connect it first in Device Management.",
        })
        # Don't close - user might connect the device later
    else:
        com_logger.log_system(device_id, "WebSocket terminal connected")
        await websocket.send_json({
            "type": "connected",
            "device_id": device_id,
            "message": "Connected to device terminal",
            "timestamp": datetime.utcnow().isoformat(),
        })

    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                msg_type = msg.get("type", "")

                if msg_type == "ping":
                    await websocket.send_json({"type": "pong"})

                elif msg_type == "command":
                    command = msg.get("command", "")
                    if not command:
                        await websocket.send_json({
                            "type": "command_error",
                            "command": "",
                            "error": "Empty command",
                        })
                        continue

                    # Get the interface (may have changed since connection)
                    interface = _get_device_interface(device_id)
                    if interface is None:
                        await websocket.send_json({
                            "type": "command_error",
                            "command": command,
                            "error": "Device not connected. Please connect it first.",
                        })
                        continue

                    start_time = datetime.utcnow()
                    send_ts = start_time.isoformat()
                    # Log the sent command
                    com_logger.log_sent(device_id, command, timestamp=send_ts)

                    try:
                        response = await interface.send(command)
                        duration_ms = int(
                            (datetime.utcnow() - start_time).total_seconds() * 1000
                        )
                        recv_ts = datetime.utcnow().isoformat()
                        # Log the received response
                        com_logger.log_received(device_id, response, timestamp=recv_ts)
                        await websocket.send_json({
                            "type": "command_response",
                            "command": command,
                            "response": response,
                            "duration_ms": duration_ms,
                            "timestamp": recv_ts,
                        })
                    except Exception as e:
                        logger.error(f"Command error for {device_id}: {e}")
                        com_logger.log_error(device_id, str(e), command=command)
                        await websocket.send_json({
                            "type": "command_error",
                            "command": command,
                            "error": str(e),
                            "timestamp": datetime.utcnow().isoformat(),
                        })

                elif msg_type == "start_receive":
                    # Stop any existing receive task for this WS
                    _stop_receive_task(device_id, websocket)

                    interval_ms = msg.get("interval_ms", 200)
                    task_id = f"{device_id}_{id(websocket)}"
                    task = asyncio.create_task(
                        _receive_loop(device_id, websocket, interval_ms)
                    )
                    _receive_tasks[task_id] = task
                    await websocket.send_json({
                        "type": "receive_started",
                        "interval_ms": interval_ms,
                        "timestamp": datetime.utcnow().isoformat(),
                    })

                elif msg_type == "stop_receive":
                    _stop_receive_task(device_id, websocket)
                    await websocket.send_json({
                        "type": "receive_stopped",
                        "timestamp": datetime.utcnow().isoformat(),
                    })

                elif msg_type == "command_ack":
                    # Legacy compatibility: just acknowledge
                    await websocket.send_json({
                        "type": "command_ack",
                        "command": msg.get("command", ""),
                        "message": "Use type=command for actual command execution",
                    })

            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})

    except WebSocketDisconnect:
        logger.info(f"Device WS disconnected: {device_id}")
    finally:
        if device_id in _device_connections:
            _device_connections[device_id].discard(websocket)
        # Clean up receive task
        _stop_receive_task(device_id, websocket)
