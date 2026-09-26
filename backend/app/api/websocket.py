"""WebSocket endpoints for real-time communication."""
import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.database import async_session
from app.models.models import CommunicationLog, LogDirection, LogStatus
from app.services.com_logger import com_logger

logger = logging.getLogger(__name__)

router = APIRouter()

# Connection pools
_execution_connections: Dict[str, set] = {}  # execution_id -> set of websockets
_device_connections: Dict[str, set] = {}  # device_id -> set of websockets


def _get_device_interface(device_id: str):
    """Get the active communication interface for a device."""
    try:
        from app.services.device_service import _active_connections
        return _active_connections.get(device_id)
    except ImportError:
        return None


async def _safe_receive(interface, timeout: float = 0.1):
    """Receive data from an interface.

    Plugin-based interfaces (e.g. PeakCAN) may not accept a ``timeout`` kwarg,
    so fall back to calling ``receive()`` without arguments.
    """
    try:
        return await interface.receive(timeout=timeout)
    except TypeError:
        return await interface.receive()


async def _log_rx_to_db(device_id: str, protocol: str, data: Any, timestamp: str):
    """Persist an unsolicited received message to the communication_logs table."""
    try:
        raw = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
        raw_hex = None
        raw_size = None
        if isinstance(data, dict):
            raw_hex = data.get("data") or data.get("hex")
            if isinstance(raw_hex, list):
                raw_hex = "".join(f"{b:02X}" for b in raw_hex)
            raw_size = data.get("dlc") or data.get("size")
            if raw_hex is not None and raw_size is None and isinstance(raw_hex, str):
                raw_size = len(raw_hex.replace(" ", "")) // 2
        async with async_session() as db:
            db.add(CommunicationLog(
                timestamp=datetime.fromisoformat(timestamp),
                device_id=device_id,
                direction=LogDirection.RECEIVED.value,
                protocol=protocol,
                raw_data=raw,
                raw_data_hex=raw_hex,
                raw_data_size=raw_size,
                status=LogStatus.SUCCESS.value,
            ))
            await db.commit()
    except Exception as e:
        logger.debug(f"Failed to persist received log for {device_id}: {e}")


# Global per-device receive monitors, independent of any WebSocket.
# Started when a device connects and stopped when it disconnects, so that
# ALL traffic of every connected device is captured, persisted and shown in
# the communication terminal even without manually clicking "start listening".
_device_monitor_tasks: Dict[str, asyncio.Task] = {}
_device_protocols: Dict[str, str] = {}


async def _device_monitor_loop(device_id: str, protocol: str, interval_ms: int = 100):
    """Continuously poll a connected device and broadcast/persist all traffic."""
    logger.info(f"Starting device monitor for {device_id}")
    try:
        while True:
            interface = _get_device_interface(device_id)
            if interface is None:
                logger.info(f"Device monitor: {device_id} disconnected, stopping")
                break

            # Never poll while a command/response exchange is in flight:
            # reading concurrently would steal the reply bytes.
            try:
                from app.services.device_service import _command_in_flight
                if _command_in_flight.get(device_id):
                    await asyncio.sleep(interval_ms / 1000.0)
                    continue
            except Exception:
                pass

            try:
                data = await _safe_receive(interface, timeout=0.1)
                if data:
                    ts = datetime.utcnow().isoformat()
                    com_logger.log_received(device_id, data, timestamp=ts)
                    await _log_rx_to_db(device_id, protocol, data, ts)
                    await broadcast_device_update(device_id, {
                        "type": "device_data",
                        "data": data,
                        "timestamp": ts,
                    })
            except asyncio.TimeoutError:
                pass
            except Exception as e:
                logger.debug(f"Device monitor transient error for {device_id}: {e}")
            await asyncio.sleep(interval_ms / 1000.0)
    finally:
        _device_monitor_tasks.pop(device_id, None)
        logger.info(f"Device monitor stopped for {device_id}")


def start_device_monitor(device_id: str, protocol: str = "unknown"):
    """Start the global receive monitor for a connected device (idempotent)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return
    if protocol and protocol != "unknown":
        _device_protocols[device_id] = protocol
    existing = _device_monitor_tasks.get(device_id)
    if existing and not existing.done():
        return
    task = asyncio.create_task(
        _device_monitor_loop(device_id, _device_protocols.get(device_id, protocol))
    )
    _device_monitor_tasks[device_id] = task
    logger.info(f"Device monitor started for {device_id}")


def stop_device_monitor(device_id: str):
    """Stop the global receive monitor for a device."""
    task = _device_monitor_tasks.pop(device_id, None)
    if task and not task.done():
        task.cancel()
        logger.info(f"Device monitor stopped for {device_id}")


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
                    # The device-level monitor is started automatically when the
                    # device connects; ensure it is running, then acknowledge.
                    start_device_monitor(device_id)
                    interval_ms = msg.get("interval_ms", 200)
                    await websocket.send_json({
                        "type": "receive_started",
                        "interval_ms": interval_ms,
                        "timestamp": datetime.utcnow().isoformat(),
                    })

                elif msg_type == "stop_receive":
                    stop_device_monitor(device_id)
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
