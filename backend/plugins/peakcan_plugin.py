"""
PeakCAN USB Protocol Plugin for AITestLab.

Connects to a PEAK-System PCAN-USB (or PCAN-USB FD) adapter via the
python-can library.

Supports two driver interfaces (auto-detected):
- **socketcan**: Uses the Linux kernel ``peak_usb`` module (``can0``, ``can1``, ...).
  Built into modern kernels; just ``sudo modprobe peak_usb``.
- **pcan**: Uses the PEAK chardev driver (``/dev/pcan*``).
  Requires the PCAN-Basic API from https://www.peak-system.com/linux/

Capabilities:
- Standard CAN 2.0A/B (up to 8 bytes)
- CAN FD (up to 64 bytes, requires PCAN-USB FD or PCAN-USB Pro FD hardware)
- Hardware auto-detection
- Configurable bitrate / data_bitrate

Prerequisites:
  Linux   Option A (recommended): ``sudo modprobe peak_usb``  → uses SocketCAN (can0)
          Option B: install the chardev driver from https://www.peak-system.com/linux/
  Windows Install the PEAK **PCAN-Basic** driver and use the ``pcan`` interface
          (``PCAN_USBBUS1``). SocketCAN is Linux-only and is never auto-selected
          on Windows (it previously surfaced as ``WinError 10047``).

Install this plugin via 插件管理 → 安装插件, then add a device to connect.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.services.plugin_service import BaseProtocolPlugin

logger = logging.getLogger(__name__)


class PeakCANPlugin(BaseProtocolPlugin):
    """PEAK-System PCAN-USB / PCAN-USB FD protocol plugin."""

    plugin_name = "PeakCAN USB"
    protocol_name = "peakcan"
    version = "1.0.0"

    # ------------------------------------------------------------------ #
    # Constants
    # ------------------------------------------------------------------ #
    _STANDARD_BITRATES = [100000, 125000, 250000, 500000, 800000, 1000000]
    _IFACE_OPTIONS = ["socketcan", "pcan", "auto"]

    def __init__(self):
        self._connected = False
        self._bus = None           # can.Bus instance
        self._notifier = None      # can.Notifier for async receive
        self._listener = None      # Buffered listener for rx messages
        self._config: Dict[str, Any] = {}
        self._active_channel: str = ""
        self._active_interface: str = "auto"
        self._is_fd: bool = False

    # ------------------------------------------------------------------ #
    # Connection management
    # ------------------------------------------------------------------ #
    async def connect(self, config: dict) -> bool:
        """Open the PCAN-USB channel via socketcan or pcan.

        ``config`` keys:
          * ``interface``  — ``socketcan``, ``pcan``, or ``auto`` (default auto-detect)
          * ``channel``    — for socketcan: ``can0`` / ``can1``; for pcan: ``PCAN_USBBUS1`` / ``0``
          * ``bitrate``    — arbitration bitrate (default 500000)
          * ``fd``         — enable CAN FD mode (default False)
          * ``data_bitrate`` — FD data-phase bitrate (defaults to bitrate)
          * ``f_clock_mhz``  — clock frequency in MHz (auto-detect by default)
        """
        try:
            import can
        except ImportError as e:
            raise RuntimeError(
                "python-can is not installed. Install with: pip install python-can"
            ) from e

        config = config or {}
        interface = config.get("interface", "auto")
        channel = config.get("channel", "")
        bitrate = int(config.get("bitrate", 500000))
        fd_enabled = bool(config.get("fd", False))
        data_bitrate = int(config.get("data_bitrate", bitrate))
        f_clock = config.get("f_clock_mhz", None)

        # --- Auto-detect the best interface + channel ---
        interface, channel = self._auto_detect(interface, channel, can)

        self._config = config
        self._active_channel = str(channel)
        self._active_interface = interface
        self._is_fd = fd_enabled

        bus_kwargs: Dict[str, Any] = {
            "interface": interface,
            "channel": channel,
            "bitrate": bitrate,
            "state": can.bus.BusState.ACTIVE,
        }

        if fd_enabled:
            bus_kwargs["fd"] = True
            if data_bitrate != bitrate:
                bus_kwargs["data_bitrate"] = data_bitrate
            if f_clock is not None:
                bus_kwargs["f_clock_mhz"] = int(f_clock)

        try:
            self._bus = can.interface.Bus(**bus_kwargs)

            # Set up buffered listener for captured messages
            self._listener = can.BufferedReader()
            self._notifier = can.Notifier(self._bus, [self._listener])

            self._connected = True
            mode = "CAN FD" if fd_enabled else "CAN"
            logger.info(
                f"PeakCAN connected: interface={interface}, channel={channel}, "
                f"mode={mode}, bitrate={bitrate}"
                + (f", data_bitrate={data_bitrate}" if fd_enabled and data_bitrate != bitrate else "")
            )
            return True
        except can.exceptions.CanError as e:
            self._connected = False
            self._bus = None
            hint = ""
            if interface == "pcan" and self._is_windows():
                hint = (
                    " Windows 下请确认已安装 PEAK PCAN-Basic 驱动"
                    "（https://www.peak-system.com/quick/PCANDriver）且 PCAN-USB 已插入；"
                    "接口请选 'pcan'，通道常用 PCAN_USBBUS1。"
                )
            raise ConnectionError(
                f"Failed to open CAN channel {channel} via {interface}: {e}.{hint}"
            ) from e

    @staticmethod
    def _is_windows() -> bool:
        """True when running on Windows, where SocketCAN is unavailable."""
        import sys
        return sys.platform.startswith("win")

    @staticmethod
    def _auto_detect(interface: str, channel: str, can_module) -> tuple:
        """Resolve the interface and channel, auto-detecting if needed.

        Platform-aware: SocketCAN depends on the Linux kernel CAN subsystem
        (``/sys/class/net`` + AF_CAN) and does not exist on Windows. Previously
        the fallback defaulted to ``socketcan`` + ``can0`` on every platform,
        so Windows users hit ``WinError 10047`` ("An address incompatible with
        the requested protocol was used") instead of a meaningful error.

        Returns ``(interface, channel)``.
        """
        windows = PeakCANPlugin._is_windows()

        # SocketCAN is Linux-only: reject an explicit request on Windows with an
        # actionable message rather than letting python-can fail with 10047.
        if windows and interface == "socketcan":
            raise ConnectionError(
                "SocketCAN 仅适用于 Linux（依赖内核 AF_CAN 子系统），Windows 上不可用。"
                "请在 Windows 上使用 'pcan' 接口，并确认已安装 PEAK PCAN-Basic 驱动"
                "（https://www.peak-system.com/quick/PCANDriver）。"
            )

        # If both are explicitly set, trust the user
        if interface != "auto" and channel:
            return interface, channel

        # Try socketcan first (most common on Linux with kernel drivers)
        if not windows and interface in ("auto", "socketcan"):
            socket_channels = PeakCANPlugin._list_socketcan_channels()
            if socket_channels:
                ch = channel or socket_channels[0]
                return "socketcan", ch

        # Try pcan (PEAK PCAN-Basic / chardev driver) — primary option on Windows
        if interface in ("auto", "pcan"):
            try:
                configs = can_module.detect_available_configs(interfaces=["pcan"])
                if configs:
                    pcan_channels = [c.get("channel", str(c)) for c in configs]
                    ch = channel if channel in pcan_channels else pcan_channels[0]
                    return "pcan", str(ch)
            except Exception:
                pass

        # Fallback: platform-aware default (never socketcan on Windows).
        if interface != "auto":
            iface = interface
        else:
            iface = "pcan" if windows else "socketcan"
        ch = channel or ("PCAN_USBBUS1" if iface == "pcan" else "can0")
        return iface, ch

    @staticmethod
    def _list_socketcan_channels() -> list:
        """Return a list of available SocketCAN interface names (e.g. ['can0']).

        Always empty on Windows: there is no ``/sys/class/net`` and no AF_CAN.
        """
        import os
        import glob
        if PeakCANPlugin._is_windows():
            return []
        names = []
        try:
            # Check /sys/class/net for CAN interfaces
            for path in glob.glob("/sys/class/net/*/type"):
                with open(path) as f:
                    if f.read().strip() == "280":  # ARPHRD_CAN = 280
                        names.append(path.split("/")[4])
            names.sort()
        except Exception:
            pass
        return names

    async def disconnect(self) -> bool:
        try:
            if self._notifier:
                self._notifier.stop()
                self._notifier = None
            if self._bus:
                self._bus.shutdown()
                self._bus = None
        except Exception as e:
            logger.warning(f"Error during PeakCAN disconnect: {e}")

        self._connected = False
        self._listener = None
        return True

    # ------------------------------------------------------------------ #
    # Transport
    # ------------------------------------------------------------------ #
    async def send(self, data: Any) -> Any:
        """Send a CAN message.

        ``data`` may be a dict with:
          * ``arbitration_id`` — CAN ID (hex int or str)
          * ``data`` — list of bytes / hex str
          * ``is_extended_id`` — use 29-bit ID (default False)
          * ``is_fd`` — send as CAN FD frame (default: follow bus mode)
          * ``is_remote_frame`` — send a remote frame (default False)
          * ``dlc`` — optional data length code (auto-computed normally)

        Or a raw string like ``"123#11223344AABBCCDD"``.
        """
        if not self._connected or self._bus is None:
            raise ConnectionError("PeakCAN is not connected")

        try:
            import can
        except ImportError:
            raise RuntimeError("python-can is not installed")

        if isinstance(data, str):
            # Parse a string formatted as "can_id#hex_data" e.g. "123#11223344AABBCCDD"
            msg = self._parse_can_string(data)
        elif isinstance(data, dict):
            msg_kwargs: Dict[str, Any] = {
                "arbitration_id": self._resolve_int(data.get("arbitration_id", 0)),
                "is_extended_id": bool(data.get("is_extended_id", False)),
                "is_remote_frame": bool(data.get("is_remote_frame", False)),
            }

            raw_data = data.get("data", [])
            if isinstance(raw_data, str):
                raw_data = bytes.fromhex(raw_data.replace(" ", ""))
            elif isinstance(raw_data, list):
                raw_data = bytes(bytearray(raw_data))
            msg_kwargs["data"] = raw_data

            if "dlc" in data:
                msg_kwargs["dlc"] = int(data["dlc"])

            # FD flag: use explicit if given, otherwise inherit bus mode
            if "is_fd" in data:
                msg_kwargs["is_fd"] = bool(data["is_fd"])
            elif self._is_fd:
                msg_kwargs["is_fd"] = True

            msg = can.Message(**msg_kwargs)
        elif isinstance(data, can.Message):
            msg = data
        else:
            raise ValueError(f"Unsupported send payload type: {type(data)}")

        try:
            self._bus.send(msg)
            logger.debug(f"PeakCAN TX: id=0x{msg.arbitration_id:X}, data={msg.data.hex()}")
            return {
                "status": "sent",
                "arbitration_id": msg.arbitration_id,
                "is_extended_id": msg.is_extended_id,
                "is_fd": getattr(msg, "is_fd", False),
                "data": msg.data.hex(),
            }
        except can.exceptions.CanError as e:
            raise RuntimeError(f"PeakCAN send error: {e}") from e

    async def receive(self, timeout: float = 0.05) -> Any:
        """Read one buffered CAN message (non-blocking)."""
        if not self._connected or self._listener is None:
            raise ConnectionError("PeakCAN is not connected")

        try:
            msg = self._listener.get_message(timeout=timeout)
        except Exception:
            msg = None

        if msg is None:
            return None

        return self._msg_to_dict(msg)

    # ------------------------------------------------------------------ #
    # Hardware detection (custom extension)
    # ------------------------------------------------------------------ #
    def get_status(self) -> dict:
        status: Dict[str, Any] = {
            "name": self.plugin_name,
            "protocol": self.protocol_name,
            "version": self.version,
            "connected": self._connected,
            "channel": self._active_channel,
            "interface": self._active_interface,
            "mode": "CAN FD" if self._is_fd else "CAN",
        }

        # Append available channels from both interfaces
        try:
            import can
            # PCAN chardev channels
            pcan_configs = can.detect_available_configs(interfaces=["pcan"])
            pcan_channels = [c.get("channel", str(c)) for c in pcan_configs]
            # SocketCAN channels
            socket_channels = self._list_socketcan_channels()
            status["available_pcan_channels"] = pcan_channels
            status["available_socketcan_channels"] = socket_channels
        except Exception:
            status["available_pcan_channels"] = []
            status["available_socketcan_channels"] = []

        return status

    # ------------------------------------------------------------------ #
    # Plugin metadata
    # ------------------------------------------------------------------ #
    def get_config_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "interface": {
                    "type": "string",
                    "title": "驱动接口",
                    "default": "auto",
                    "enum": self._IFACE_OPTIONS,
                    "description": "auto = 自动检测; socketcan = 内核 peak_usb 模块; pcan = PCAN-Basic chardev 驱动",
                },
                "channel": {
                    "type": "string",
                    "title": "CAN 通道",
                    "default": "",
                    "description": "socketcan: can0/can1; pcan: PCAN_USBBUS1 或 0（留空自动选择）",
                    "examples": ["can0", "PCAN_USBBUS1", "0"],
                },
                "bitrate": {
                    "type": "integer",
                    "title": "CAN 波特率 (bps)",
                    "default": 500000,
                    "enum": self._STANDARD_BITRATES,
                    "description": "CAN 仲裁域波特率",
                },
                "fd": {
                    "type": "boolean",
                    "title": "启用 CAN FD",
                    "default": False,
                    "description": "使用 CAN FD 模式（硬件需支持，如 PCAN-USB FD）",
                },
                "data_bitrate": {
                    "type": "integer",
                    "title": "CAN FD 数据域波特率 (bps)",
                    "default": 2000000,
                    "description": "仅 CAN FD 模式生效，与 bitrate 相同则不单独设定",
                },
                "f_clock_mhz": {
                    "type": "integer",
                    "title": "时钟频率 (MHz)",
                    "description": "通常自动检测，仅在特殊硬件上手动指定（如 80）",
                },
            },
            "required": [],
        }

    def get_device_template(self) -> dict:
        schema = self.get_config_schema()
        defaults = {
            k: v.get("default")
            for k, v in schema["properties"].items()
            if "default" in v
        }
        return {
            "name": "PeakCAN USB",
            "type": "other",
            "protocol": self.protocol_name,
            "connection_type": "usb",
            "config": defaults,
        }

    def get_commands(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "scan",
                "syntax": '{"action": "scan"}',
                "description": "扫描并列出所有可用的 PCAN 通道",
                "parameters": [],
            },
            {
                "name": "send_can",
                "syntax": '{"arbitration_id": 0x123, "data": [0x11, 0x22, ...]}',
                "description": "发送一条标准 CAN 消息（最大 8 字节）",
                "parameters": [
                    {"name": "arbitration_id", "type": "integer"},
                    {"name": "data", "type": "array"},
                    {"name": "is_extended_id", "type": "boolean"},
                ],
            },
            {
                "name": "send_canfd",
                "syntax": '{"arbitration_id": 0x100, "data": [0, 1, 2, ...], "is_fd": true}',
                "description": "发送一条 CAN FD 消息（最大 64 字节）",
                "parameters": [
                    {"name": "arbitration_id", "type": "integer"},
                    {"name": "data", "type": "array"},
                    {"name": "is_fd", "type": "boolean"},
                ],
            },
            {
                "name": "receive",
                "syntax": '{"action": "receive"}',
                "description": "读取一条 CAN 总线上的消息",
                "parameters": [],
            },
        ]

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _resolve_int(value: Any) -> int:
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            return int(value, 16 if value.lower().startswith("0x") else 10)
        return int(value)

    @staticmethod
    def _parse_can_string(raw: str) -> "can.Message":
        """Parse a CAN message string like ``"123#11223344AABBCCDD"``."""
        import can

        raw = raw.strip()
        if "#" not in raw:
            raise ValueError(
                f"Invalid CAN string format: '{raw}'. "
                f"Expected 'can_id#hex_data' e.g. '123#11223344AABBCCDD'"
            )
        id_part, data_part = raw.split("#", 1)

        is_extended = False
        if id_part.endswith("x"):
            is_extended = True
            id_part = id_part[:-1]

        arbitration_id = int(id_part, 16)

        if data_part.upper() == "R":
            return can.Message(
                arbitration_id=arbitration_id,
                is_extended_id=is_extended,
                is_remote_frame=True,
                dlc=0,
            )

        data_bytes = bytes.fromhex(data_part.replace(" ", ""))
        return can.Message(
            arbitration_id=arbitration_id,
            is_extended_id=is_extended,
            data=data_bytes,
        )

    @staticmethod
    def _msg_to_dict(msg: "can.Message") -> dict:
        return {
            "arbitration_id": msg.arbitration_id,
            "is_extended_id": msg.is_extended_id,
            "is_remote_frame": msg.is_remote_frame,
            "is_fd": getattr(msg, "is_fd", False),
            "is_error_frame": msg.is_error_frame,
            "dlc": msg.dlc,
            "data": msg.data.hex(),
            "timestamp": getattr(msg, "timestamp", None),
        }
