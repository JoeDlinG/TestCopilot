"""Device connection and communication service.

Uses the communication layer abstraction for SCPI/CAN/Serial/Ethernet.
"""
from __future__ import annotations
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.models.models import Device, CommunicationLog, DeviceStatus, LogDirection, LogStatus
from app.schemas.schemas import DeviceCreate, DeviceUpdate
from app.communication import (
    create_interface,
    CommunicationInterface,
)
from app.services.plugin_service import plugin_service
from app.services.com_logger import com_logger
from app.services.program_logger import get_execution_log
from app.api.websocket import (
    start_device_monitor,
    stop_device_monitor,
    broadcast_device_update,
)
from app.core.timeutils import utc_now

# Protocols handled natively by the communication layer (not by plugins).
_STANDARD_PROTOCOLS = {"scpi", "gpib", "can", "serial", "ethernet", "usb"}

logger = logging.getLogger(__name__)

# In-memory device connections
_active_connections: Dict[str, CommunicationInterface] = {}

# Devices with a command/response exchange currently in flight. The global
# device monitor skips polling these so it can never consume reply bytes.
_command_in_flight: Dict[str, bool] = {}


class DeviceService:
    """Service for managing test device connections."""

    async def reset_stale_connections(self, db: AsyncSession):
        """Reset all devices with 'connected' status to 'disconnected' on startup.

        _active_connections is in-memory and lost on restart, but DB state
        persists. This prevents stale 'connected' state after service restart.
        """
        try:
            await db.execute(
                update(Device)
                .where(Device.status == DeviceStatus.CONNECTED.value)
                .values(
                    status=DeviceStatus.DISCONNECTED.value,
                    disconnected_at=utc_now(),
                )
            )
            await db.commit()
            logger.info("Reset stale device connections on startup")
        except Exception as e:
            logger.warning(f"Failed to reset stale connections: {e}")

    def _parse_json_field(self, value: Any) -> Any:
        """Parse a JSON string field from DB, or return as-is if already parsed."""
        if value is None:
            return None
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
        return value

    def _to_json_field(self, value: Any) -> Optional[str]:
        """Convert a value to JSON string for DB storage."""
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False)

    def _model_to_response(self, device: Device) -> dict:
        """Convert Device model to response dict with parsed JSON fields."""
        return {
            "id": device.id,
            "name": device.name,
            "type": device.type,
            "protocol": device.protocol,
            "connection_type": device.connection_type,
            "visa_address": device.visa_address,
            "can_channel": device.can_channel,
            "serial_port": device.serial_port,
            "ip_address": device.ip_address,
            "port": device.port,
            "status": device.status,
            "config": self._parse_json_field(device.config),
            "metadata": self._parse_json_field(device.extra_meta),
            "connected_at": device.connected_at,
            "disconnected_at": device.disconnected_at,
            "last_seen": device.last_seen,
            "created_at": device.created_at,
        }

    def _get_address(self, device: Device) -> str:
        """Get the appropriate address for the device based on protocol."""
        if device.protocol in ("scpi", "gpib"):
            return device.visa_address or ""
        elif device.protocol == "can":
            return device.can_channel or ""
        elif device.protocol == "serial":
            return device.serial_port or ""
        elif device.protocol == "ethernet":
            return device.ip_address or ""
        elif device.protocol == "usb":
            # For USB protocol, address is not a single string;
            # VID/PID come from config
            return ""
        return ""

    def _get_connect_config(self, device: Device, config: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Build config dict for connection, merging device info with user-supplied config.

        The device's stored config (JSON) is always used as the base so that
        plugin devices (e.g. created via "add device from plugin") keep their
        port/baudrate/board_id defaults; user-supplied config overrides it.
        """
        merged = {}
        existing = self._parse_json_field(device.config)
        if isinstance(existing, dict):
            merged.update(existing)
        if config:
            merged.update(config)
        return merged if merged else None

    async def create_device(self, db: AsyncSession, data: DeviceCreate) -> Device:
        device = Device(
            name=data.name,
            type=data.type,
            protocol=data.protocol,
            connection_type=data.connection_type,
            visa_address=data.visa_address,
            can_channel=data.can_channel,
            serial_port=data.serial_port,
            ip_address=data.ip_address,
            port=data.port,
            config=self._to_json_field(data.config),
            extra_meta=self._to_json_field(data.extra_meta),
        )
        db.add(device)
        await db.commit()
        await db.refresh(device)
        return device

    async def get_device(self, db: AsyncSession, device_id: str) -> Optional[Device]:
        result = await db.execute(select(Device).where(Device.id == device_id))
        return result.scalar_one_or_none()

    async def list_devices(
        self,
        db: AsyncSession,
        device_type: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[List[Device], int]:
        query = select(Device)
        count_query = select(Device)

        if device_type:
            query = query.where(Device.type == device_type)
            count_query = count_query.where(Device.type == device_type)
        if status:
            query = query.where(Device.status == status)
            count_query = count_query.where(Device.status == status)

        # Count
        count_result = await db.execute(count_query)
        total = len(count_result.scalars().all())

        # Paginate
        query = query.order_by(Device.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await db.execute(query)
        devices = result.scalars().all()

        return devices, total

    async def update_device(self, db: AsyncSession, device_id: str, data: DeviceUpdate) -> Optional[Device]:
        device = await self.get_device(db, device_id)
        if not device:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if key in ("config", "metadata") and value is not None:
                setattr(device, key, self._to_json_field(value))
            elif value is not None:
                setattr(device, key, value)

        device.updated_at = utc_now()
        await db.commit()
        await db.refresh(device)
        return device

    async def delete_device(self, db: AsyncSession, device_id: str) -> bool:
        device = await self.get_device(db, device_id)
        if not device:
            return False
        if device.status == DeviceStatus.CONNECTED.value:
            await self.disconnect_device(db, device_id)
        await db.delete(device)
        await db.commit()
        return True

    async def connect_device(
        self, db: AsyncSession, device_id: str, config: Optional[Dict[str, Any]] = None
    ) -> dict:
        device = await self.get_device(db, device_id)
        if not device:
            raise ValueError(f"Device {device_id} not found")

        try:
            # Build merged config
            merged_config = self._get_connect_config(device, config)

            # Create communication interface. Custom protocols are handled by
            # an installed + enabled plugin (matched on protocol_name).
            if device.protocol in _STANDARD_PROTOCOLS:
                interface = create_interface(
                    protocol=device.protocol,
                    address=self._get_address(device),
                    port=device.port,
                    config=merged_config,
                )
                await interface.connect()
            else:
                plugin_class = await plugin_service.get_plugin_class_by_protocol(
                    db, device.protocol
                )
                if plugin_class is None:
                    raise ValueError(
                        f"未找到协议 '{device.protocol}' 对应的已启用插件。"
                        "请先在「插件管理」中安装并启用对应插件。"
                    )
                interface = plugin_class()
                await interface.connect(merged_config or {})
            _active_connections[device.id] = interface

            # Start the global receive monitor so ALL device traffic is captured
            # (persisted to DB + pushed to the terminal) automatically.
            start_device_monitor(device.id, protocol=device.protocol or "unknown")

            device.status = DeviceStatus.CONNECTED.value
            device.connected_at = utc_now()
            device.last_seen = utc_now()
            if config:
                existing_config = self._parse_json_field(device.config) or {}
                existing_config.update(config)
                device.config = self._to_json_field(existing_config)

            await db.commit()
            return {"status": "connected", "device_id": device_id}
        except Exception as e:
            logger.error(f"Failed to connect device {device_id}: {e}")
            raise

    async def disconnect_device(self, db: AsyncSession, device_id: str) -> dict:
        device = await self.get_device(db, device_id)
        if not device:
            raise ValueError(f"Device {device_id} not found")

        interface = _active_connections.pop(device.id, None)
        if interface:
            try:
                await interface.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting {device_id}: {e}")

        # Stop the global receive monitor for this device
        stop_device_monitor(device_id)

        device.status = DeviceStatus.DISCONNECTED.value
        device.disconnected_at = utc_now()
        await db.commit()
        return {"status": "disconnected", "device_id": device_id}

    async def send_command(
        self,
        db: AsyncSession,
        device_id: str,
        command: str,
        execution_id: Optional[str] = None,
        step_result_id: Optional[str] = None,
    ) -> dict:
        device = await self.get_device(db, device_id)
        if not device or device.status != DeviceStatus.CONNECTED.value:
            raise ValueError(f"Device {device_id} is not connected")

        interface = _active_connections.get(device.id)
        if not interface:
            # Stale DB state: mark device as disconnected
            device.status = DeviceStatus.DISCONNECTED.value
            device.disconnected_at = utc_now()
            await db.commit()
            raise ValueError(f"No active connection for device {device_id}. Please reconnect the device.")

        start_time = utc_now()

        # Log sent command to file
        com_logger.log_sent(device_id, command, timestamp=start_time.isoformat())
        # Mirror into the per-execution communication log (logs/executions/<id>/)
        if execution_id:
            _el = get_execution_log(execution_id)
            if _el:
                _el.communication(device_id, "SEND", str(command))

        # Push the sent command to the communication terminal in real time
        await broadcast_device_update(device_id, {
            "type": "command_sent",
            "command": command,
            "timestamp": start_time.isoformat(),
        })

        # Normalize command to a persistable string (CAN sends may be dicts)
        cmd_raw = command if isinstance(command, str) else (
            json.dumps(command, ensure_ascii=False) if isinstance(command, (dict, list)) else str(command)
        )
        cmd_hex = command.encode().hex() if isinstance(command, str) else None
        cmd_size = len(command.encode()) if isinstance(command, str) else 0

        # Log sent command
        sent_log = CommunicationLog(
            device_id=device_id,
            execution_id=execution_id,
            step_result_id=step_result_id,
            direction=LogDirection.SENT.value,
            protocol=device.protocol,
            raw_data=cmd_raw,
            raw_data_hex=cmd_hex,
            raw_data_size=cmd_size,
            status=LogStatus.SUCCESS.value,
        )
        db.add(sent_log)
        await db.commit()

        _command_in_flight[device_id] = True
        try:
            # Execute command
            response = await interface.send(command)
            duration_ms = int((utc_now() - start_time).total_seconds() * 1000)

            # Log received response to file
            com_logger.log_received(device_id, response)
            if execution_id:
                _el = get_execution_log(execution_id)
                if _el:
                    _el.communication(device_id, "RECV", str(response))

            # Push the received response to the communication terminal in real time
            recv_ts = utc_now().isoformat()
            await broadcast_device_update(device_id, {
                "type": "command_response",
                "command": command,
                "response": response,
                "duration_ms": duration_ms,
                "timestamp": recv_ts,
            })

            # Update sent log with timing
            sent_log.duration_ms = duration_ms

            # Normalize response to a persistable string (CAN responses are dicts)
            resp_raw = response if isinstance(response, str) else (
                json.dumps(response, ensure_ascii=False) if isinstance(response, (dict, list)) else str(response)
            )
            resp_hex = None
            resp_size = 0
            if isinstance(response, dict):
                resp_hex = response.get("data") if isinstance(response.get("data"), str) else None
                d = response.get("dlc")
                resp_size = d if isinstance(d, int) else (
                    len(resp_hex.replace(" ", "")) // 2 if resp_hex else 0
                )
            elif isinstance(response, str):
                resp_hex = response.encode().hex()
                resp_size = len(response.encode())

            # Log received response
            recv_log = CommunicationLog(
                device_id=device_id,
                execution_id=execution_id,
                step_result_id=step_result_id,
                direction=LogDirection.RECEIVED.value,
                protocol=device.protocol,
                raw_data=resp_raw,
                raw_data_hex=resp_hex,
                raw_data_size=resp_size,
                status=LogStatus.SUCCESS.value,
                duration_ms=duration_ms,
                response_log_id=sent_log.id,
            )
            db.add(recv_log)

            device.last_seen = utc_now()
            await db.commit()

            return {
                "device_id": device_id,
                "command": command,
                "response": response,
                "duration_ms": duration_ms,
            }
        except Exception as e:
            # Log error to file
            com_logger.log_error(device_id, str(e), command=command)

            # Log error
            sent_log.status = LogStatus.ERROR.value
            sent_log.error_message = str(e)
            await db.commit()

            # Auto-cleanup broken connection
            _active_connections.pop(device_id, None)
            device.status = DeviceStatus.DISCONNECTED.value
            device.disconnected_at = utc_now()
            await db.commit()
            logger.warning(f"Connection to {device_id} broken, auto-disconnected: {e}")

            raise ConnectionError(f"Communication error with device {device.name}: {e}") from e
        finally:
            _command_in_flight.pop(device_id, None)

    async def get_active_connections(self) -> List[str]:
        """Get list of currently connected device IDs."""
        return list(_active_connections.keys())


device_service = DeviceService()
