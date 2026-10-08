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

Connecting tries every plausible interface/channel candidate in order (UP
SocketCAN interfaces first on Linux, detected PCAN channels, then the platform
default) and reports the reason for each failed attempt, so a bare OS error can
never reach the UI. Send ``{"action": "diagnose"}`` for an environment report and
``{"action": "scan"}`` for the detected channel list — both work while
disconnected.

Install this plugin via 插件管理 → 安装插件, then add a device to connect.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from app.services.plugin_service import BaseProtocolPlugin

logger = logging.getLogger(__name__)


class PeakCANPlugin(BaseProtocolPlugin):
    """PEAK-System PCAN-USB / PCAN-USB FD protocol plugin."""

    plugin_name = "PeakCAN USB"
    protocol_name = "peakcan"
    version = "1.1.0"

    # ------------------------------------------------------------------ #
    # Constants
    # ------------------------------------------------------------------ #
    _STANDARD_BITRATES = [100000, 125000, 250000, 500000, 800000, 1000000]
    _IFACE_OPTIONS = ["socketcan", "pcan", "auto"]

    #: Channel names that only make sense for SocketCAN (``can0``, ``vcan0``, ...).
    _SOCKETCAN_CHANNEL_RE = re.compile(r"^(v?can)\d+$", re.IGNORECASE)
    #: ``WSAEAFNOSUPPORT`` — raised by Windows when an AF_CAN socket is created.
    _WSAEAFNOSUPPORT = 10047
    #: USB vendor id of PEAK-System adapters (PCAN-USB, PCAN-USB FD, ...).
    _PEAK_USB_VENDOR = 0x0C72

    def __init__(self):
        self._connected = False
        self._bus = None           # can.Bus instance
        self._notifier = None      # can.Notifier for async receive
        self._listener = None      # Buffered listener for rx messages
        self._config: Dict[str, Any] = {}
        self._active_channel: str = ""
        self._active_interface: str = "auto"
        self._is_fd: bool = False
        self._last_error: str = ""       # last connection failure (for the UI)
        self._attempts: List[str] = []   # per-candidate failure report
        # Periodic (cyclic) transmissions: key -> python-can CyclicSendTask.
        self._periodic: Dict[str, Any] = {}
        self._periodic_auto_stop: Dict[str, "asyncio.Task"] = {}

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
        interface = (config.get("interface") or "auto").strip() or "auto"
        channel = (config.get("channel") or "").strip()
        bitrate = int(config.get("bitrate", 500000))
        fd_enabled = bool(config.get("fd", False))
        data_bitrate = int(config.get("data_bitrate", bitrate))
        f_clock = config.get("f_clock_mhz", None)

        # Ordered (interface, channel) candidates — best guess first, so a
        # connectable combination is found instead of blindly trying one.
        candidates = self._candidate_list(interface, channel, can)

        self._config = config
        self._is_fd = fd_enabled
        self._last_error = ""
        self._attempts = []

        for iface, ch in candidates:
            bus_kwargs: Dict[str, Any] = {
                "interface": iface,
                "channel": ch,
                "bitrate": bitrate,
                "state": can.bus.BusState.ACTIVE,
            }
            if iface == "socketcan" and bool(config.get("loopback", False)):
                # Self-test mode: our own frames are echoed back even when nobody
                # else sits on the bus, so the whole software path can be
                # verified without a peer device.
                bus_kwargs["local_loopback"] = True
                bus_kwargs["receive_own_messages"] = True

            if fd_enabled:
                bus_kwargs["fd"] = True
                if data_bitrate != bitrate:
                    bus_kwargs["data_bitrate"] = data_bitrate
                if f_clock is not None:
                    bus_kwargs["f_clock_mhz"] = int(f_clock)

            try:
                self._bus = can.interface.Bus(**bus_kwargs)
            except Exception as e:  # noqa: BLE001 — never leak a raw OS error
                self._bus = None
                reason = self._explain(e, iface)
                self._attempts.append(f"{iface}/{ch}: {reason}")
                logger.warning(f"PeakCAN: cannot open {iface}/{ch} — {reason}")
                continue

            # Success — remember which combination actually worked.
            self._active_interface = iface
            self._active_channel = str(ch)
            self._listener = can.BufferedReader()
            self._notifier = can.Notifier(self._bus, [self._listener])
            self._connected = True
            if self._attempts:
                logger.info(
                    f"PeakCAN connected after {len(self._attempts)} failed attempt(s): "
                    f"{iface}/{ch}"
                )
            mode = "CAN FD" if fd_enabled else "CAN"
            logger.info(
                f"PeakCAN connected: interface={iface}, channel={ch}, "
                f"mode={mode}, bitrate={bitrate}"
                + (f", data_bitrate={data_bitrate}" if fd_enabled and data_bitrate != bitrate else "")
            )
            return True

        self._connected = False
        self._bus = None
        self._active_interface = interface
        self._active_channel = channel
        details = "\n".join(f"  - {a}" for a in self._attempts) or "  - （无可用候选）"
        self._last_error = (
            f"PeakCAN 连接失败，已依次尝试 {len(candidates)} 个接口/通道组合：\n"
            f"{details}\n{self._platform_hint()}"
        )
        raise ConnectionError(self._last_error)

    @staticmethod
    def _is_windows() -> bool:
        """True when running on Windows, where SocketCAN is unavailable."""
        import sys
        return sys.platform.startswith("win")

    @classmethod
    def _auto_detect(cls, interface: str, channel: str, can_module) -> tuple:
        """Backward-compatible helper: return the highest-priority candidate.

        Platform-aware: SocketCAN depends on the Linux kernel CAN subsystem
        (``/sys/class/net`` + AF_CAN) and does not exist on Windows. Previously
        the fallback defaulted to ``socketcan`` + ``can0`` on every platform,
        so Windows users hit ``WinError 10047`` ("An address incompatible with
        the requested protocol was used") instead of a meaningful error.
        """
        candidates = cls._candidate_list(interface, channel, can_module)
        if not candidates:
            raise ConnectionError(
                "未找到可用的 CAN 接口/通道，请检查驱动与硬件连接。\n"
                + cls._platform_hint()
            )
        return candidates[0]

    @classmethod
    def _candidate_list(
        cls, interface: str, channel: str, can_module
    ) -> List[Tuple[str, str]]:
        """Ordered ``(interface, channel)`` pairs to try, most likely first.

        SocketCAN is Linux-only, so it is never a candidate on Windows — the
        old ``auto`` fallback picked ``socketcan``/``can0`` on every platform,
        which surfaced as ``WinError 10047`` instead of a usable message.
        """
        windows = cls._is_windows()
        interface = (interface or "auto").strip().lower()
        channel = (channel or "").strip()

        # SocketCAN is Linux-only: reject an explicit request on Windows with an
        # actionable message rather than letting python-can fail with 10047.
        if windows and interface == "socketcan":
            raise ConnectionError(
                "SocketCAN 仅适用于 Linux（依赖内核 AF_CAN 子系统），Windows 上不可用。"
                "请在 Windows 上使用 'pcan' 接口，并确认已安装 PEAK PCAN-Basic 驱动"
                "（https://www.peak-system.com/quick/PCANDriver）。"
            )
        if windows and channel and cls._SOCKETCAN_CHANNEL_RE.match(channel):
            raise ConnectionError(
                f"通道 '{channel}' 是 SocketCAN 名称，仅 Linux 可用。"
                "Windows 上请使用 PEAK 通道名（如 PCAN_USBBUS1）并选择 'pcan' 接口。"
            )

        candidates: List[Tuple[str, str]] = []

        def add(iface: str, ch: str) -> None:
            if iface and ch and (iface, ch) not in candidates:
                candidates.append((iface, ch))

        # An explicitly requested interface is used as-is (channel auto-filled).
        if interface != "auto":
            add(interface, channel or cls._default_channel(interface, windows))
            return candidates

        # 1) An explicit channel wins — guess which driver owns it.
        if channel:
            if not windows and cls._SOCKETCAN_CHANNEL_RE.match(channel):
                add("socketcan", channel)
            else:
                add("pcan", channel)
                if not windows:
                    add("socketcan", channel)

        # 2) Auto-detected SocketCAN interfaces (Linux only), UP ones first.
        if not windows:
            for ch in cls._socketcan_channels(only_up=True):
                add("socketcan", ch)
            for ch in cls._socketcan_channels():
                add("socketcan", ch)

        # 3) Auto-detected PCAN chardev / PCAN-Basic channels.
        for ch in cls._pcan_channels(can_module):
            add("pcan", ch)

        # 4) Platform default, as the last resort (never socketcan on Windows).
        if windows:
            add("pcan", "PCAN_USBBUS1")
        else:
            add("socketcan", "can0")
            add("pcan", "PCAN_USBBUS1")

        return candidates

    @classmethod
    def _default_channel(cls, interface: str, windows: Optional[bool] = None) -> str:
        """Default channel name for a driver interface."""
        if interface == "socketcan":
            return "can0"
        if interface == "pcan":
            return "PCAN_USBBUS1"
        if windows is None:
            windows = cls._is_windows()
        return "PCAN_USBBUS1" if windows else "can0"

    @staticmethod
    def _pcan_channels(can_module) -> List[str]:
        """Channels reported by the PCAN-Basic / chardev driver."""
        try:
            configs = can_module.detect_available_configs(interfaces=["pcan"])
        except Exception as e:
            logger.debug(f"PCAN channel detection failed: {e}")
            return []
        channels: List[str] = []
        for cfg in configs or []:
            ch = cfg.get("channel") if isinstance(cfg, dict) else None
            ch = str(ch if ch is not None else cfg)
            if ch and ch not in channels:
                channels.append(ch)
        return channels

    @classmethod
    def _socketcan_channels(cls, only_up: bool = False) -> List[str]:
        """Available SocketCAN interfaces (Linux only, always empty on Windows).

        With ``only_up=True`` interfaces whose ``operstate`` is ``down`` are
        skipped: they exist but cannot carry traffic, which is the usual reason
        a "can0 exists" connection still fails.
        """
        if cls._is_windows():
            return []
        import glob
        names: List[str] = []
        try:
            for path in glob.glob("/sys/class/net/*/type"):
                try:
                    with open(path) as f:
                        if f.read().strip() != "280":  # ARPHRD_CAN = 280
                            continue
                except OSError:
                    continue
                name = path.split("/")[4]
                if only_up and cls._operstate(name) in ("down", "lowerlayerdown"):
                    continue
                names.append(name)
            names.sort(key=lambda n: (not n.startswith("can"), n))
        except Exception as e:
            logger.debug(f"SocketCAN scan failed: {e}")
        return names

    @staticmethod
    def _operstate(name: str) -> str:
        """Read ``/sys/class/net/<name>/operstate`` ('' when unavailable)."""
        try:
            with open(f"/sys/class/net/{name}/operstate") as f:
                return f.read().strip().lower()
        except OSError:
            return ""

    @staticmethod
    def _bus_state(channel: str) -> Optional[Dict[str, Any]]:
        """Read the SocketCAN controller state (``ip -details link show``).

        Returns e.g. ``{"state": "ERROR-PASSIVE", "tx": 128, "rx": 0,
        "bitrate": 500000}`` or ``None`` when unavailable (Windows, missing
        ``ip``, unknown channel). This is the single most useful signal when
        frames silently do not reach anyone.
        """
        if not channel or PeakCANPlugin._is_windows():
            return None
        try:
            out = subprocess.run(
                ["ip", "-details", "link", "show", channel],
                capture_output=True, text=True, timeout=3,
            )
            stdout = out.stdout or ""
        except Exception as e:
            logger.debug(f"cannot read bus state for {channel}: {e}")
            return None
        m = re.search(r"can state (\S+)(?: \(berr-counter tx (\d+) rx (\d+))?", stdout)
        if not m:
            return None
        state: Dict[str, Any] = {
            "state": m.group(1),
            "tx": int(m.group(2) or 0),
            "rx": int(m.group(3) or 0),
        }
        b = re.search(r"bitrate (\d+)", stdout)
        if b:
            state["bitrate"] = int(b.group(1))
        return state

    @staticmethod
    def _bus_hint(state: Optional[Dict[str, Any]], channel: str = "") -> str:
        """Explain a controller state in terms of what to do about it."""
        if not state:
            return ""
        name = (state.get("state") or "").upper()
        tx, rx = state.get("tx", 0), state.get("rx", 0)
        ch = channel or "can0"
        reset = f"`sudo ip link set {ch} down && sudo ip link set {ch} up type can bitrate {state.get('bitrate', 500000)}`"
        if name == "BUS-OFF":
            return (
                f"总线已 BUS-OFF（tx={tx} rx={rx}）：控制器停止发送。"
                f"按 {reset} 复位后重试；若仍复现，检查对端是否上电、"
                "波特率是否一致、总线两端是否各有一个 120Ω 终端电阻。"
            )
        if name == "ERROR-PASSIVE":
            return (
                f"总线处于 ERROR-PASSIVE（tx={tx} rx={rx}）：发出的帧没有节点应答，"
                "请确认①对端已上电且波特率相同②总线两端各有 120Ω 终端电阻③CAN_H/CAN_L 未接反。"
                f"排查后按 {reset} 复位。"
            )
        if name == "ERROR-ACTIVE" and (tx or rx):
            return (
                f"总线 ERROR-ACTIVE 但已有错误计数（tx={tx} rx={rx}），"
                "可能存在波特率偏差或瞬时干扰，建议关注后续是否升级为 ERROR-PASSIVE。"
            )
        if name == "ERROR-ACTIVE":
            return "总线状态正常（ERROR-ACTIVE，无错误计数），可以收发。"
        return ""

    @staticmethod
    def _error_frame_desc(msg: "can.Message") -> str:
        """Decode a Linux CAN error frame into readable Chinese.

        Error frames are enabled by default in python-can, so a bus with nobody
        answering shows up as an ordinary-looking frame with a tiny id — this
        makes the actual reason obvious instead of confusing.
        """
        # The class mask is delivered in the arbitration id for SFF error frames.
        cls_mask = int(msg.arbitration_id) & 0x7FF
        data = bytes(msg.data or b"")
        parts: List[str] = []
        _CLASSES = (
            (0x01, "发送超时"),
            (0x02, "仲裁丢失"),
            (0x04, "控制器状态变化"),
            (0x08, "协议违规"),
            (0x10, "收发器状态变化"),
            (0x20, "无 ACK：发出的帧没有节点应答"),
            (0x40, "总线关闭 BUS-OFF"),
            (0x80, "总线错误"),
            (0x100, "控制器已重启"),
        )
        for bit, text in _CLASSES:
            if cls_mask & bit:
                parts.append(text)
        if cls_mask & 0x04 and len(data) > 1:
            ctrl = data[1]
            for bit, text in (
                (0x01, "接收缓冲溢出"),
                (0x02, "发送缓冲溢出"),
                (0x04, "接收计数告警"),
                (0x08, "发送计数告警"),
                (0x10, "接收 ERROR-PASSIVE"),
                (0x20, "发送 ERROR-PASSIVE"),
                (0x40, "恢复到 ERROR-ACTIVE"),
            ):
                if ctrl & bit:
                    parts.append(text)
        if not parts:
            parts.append("未知错误类型")
        return "；".join(parts)

    @classmethod
    def _list_socketcan_channels(cls) -> list:
        """Backward-compatible alias for :meth:`_socketcan_channels`."""
        return cls._socketcan_channels()

    @classmethod
    def _explain(cls, exc: Exception, interface: str) -> str:
        """Turn a driver exception into an actionable, human-readable reason."""
        msg = str(exc) or exc.__class__.__name__
        low = msg.lower()
        if (
            str(cls._WSAEAFNOSUPPORT) in msg
            or "address incompatible" in low
            or "协议不兼容" in msg
        ):
            return (
                f"{msg} → Windows 不支持 SocketCAN（AF_CAN），"
                "请安装 PEAK PCAN-Basic 驱动并改用 interface='pcan'"
            )
        if "can0" in msg and ("no such device" in low or "network is down" in low):
            return (
                f"{msg} → 接口未启动，执行 "
                "`sudo ip link set can0 up type can bitrate 500000`"
            )
        if interface == "pcan" and ("dll" in low or "找不到" in msg or "not found" in low):
            return f"{msg} → 未找到 PCAN-Basic 驱动库，请先安装 PEAK PCAN-Basic"
        return msg

    @classmethod
    def _usb_hint(cls) -> str:
        """Report what the USB bus says about a plugged-in PEAK adapter.

        The most common real-world failure is "adapter is plugged in but no CAN
        interface exists", which is precisely what this detects: the hardware is
        there, the kernel ``peak_usb`` module just is not loaded.
        """
        try:
            import usb.core
        except Exception:
            return ""
        found: List[str] = []
        try:
            for dev in usb.core.find(find_all=True, idVendor=cls._PEAK_USB_VENDOR):
                pid = getattr(dev, "idProduct", 0)
                found.append(f"{cls._PEAK_USB_VENDOR:04X}:{pid:04X}")
        except Exception as e:
            logger.debug(f"USB enumeration failed: {e}")
            return ""
        if not found:
            return (
                "USB 总线上没有检测到 PEAK-System 设备（厂商 0C72）："
                "请确认 PCAN-USB 已插入且供电正常（可用 `lsusb | grep -i peak` 复核）。"
            )
        return (
            f"USB 总线上已检测到 PEAK-System 设备 {'、'.join(sorted(set(found)))}，"
            "但没有可用的 CAN 接口 —— 通常只是内核模块没加载："
            "`sudo modprobe peak_usb && sudo ip link set can0 up type can bitrate 500000`。"
        )

    @classmethod
    def _platform_hint(cls) -> str:
        """Actionable platform-specific hint appended to connection failures."""
        if cls._is_windows():
            return (
                "Windows 提示：SocketCAN 不可用，请安装 PEAK PCAN-Basic 驱动"
                "（https://www.peak-system.com/quick/PCANDriver），接口选 'pcan'，"
                "通道常用 PCAN_USBBUS1；可用 {\"action\": \"diagnose\"} 查看检测结果。"
            )
        base = (
            "Linux 提示：SocketCAN 需要一个处于 UP 状态的内核 CAN 接口 —— "
            "`sudo modprobe peak_usb && sudo ip link set can0 up type can bitrate 500000` 即可启用；"
            "或安装 PEAK PCAN-Basic（chardev）后使用 interface='pcan'。"
            "可用 {\"action\": \"diagnose\"} 查看检测结果。"
        )
        detail = cls._usb_hint()
        return f"{detail}\n{base}" if detail else base

    async def disconnect(self) -> bool:
        try:
            # Stop any periodic transmission before tearing the bus down.
            await self._stop_periodic({}, quiet=True)
        except Exception as e:
            logger.warning(f"Error stopping PeakCAN periodic sends: {e}")
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

        A dict may also carry an ``action`` that does not touch the bus:
        ``scan`` / ``status`` (channel listing), ``diagnose`` (environment
        report), ``receive`` (read one buffered message). These work while
        disconnected, which makes them usable for troubleshooting.

        The documented JSON command syntax (``'{"action": "scan"}'``,
        ``'{"arbitration_id": 291, "data": [...]}'``) arrives as a *string*
        from the UI/terminal, so JSON object strings are normalized to dicts
        here — otherwise they would be parsed as a CAN ``id#data`` string.
        """
        # Recognise python-can pseudo-code typed in the terminal (e.g.
        # ``bus.send_periodic(can.Message(arbitration_id=0x20, ...), 0.2)`` or
        # ``bus.send(can.Message(...))``) and rewrite it to the JSON command the
        # plugin actually understands. Without this the string falls through to
        # ``_parse_can_string`` and dies with "Invalid CAN string format".
        if isinstance(data, str):
            translated = self._translate_python_can(data)
            if translated is not None:
                return await self.send(translated)

        if isinstance(data, str) and data.strip().startswith("{"):
            try:
                parsed = json.loads(data)
            except (json.JSONDecodeError, ValueError):
                parsed = None
            if isinstance(parsed, dict):
                return await self.send(parsed)

        if isinstance(data, dict) and data.get("action"):
            return await self._handle_action(data)

        if not self._connected or self._bus is None:
            raise ConnectionError(
                "PeakCAN is not connected"
                + (f"（上次连接失败：{self._last_error}）" if self._last_error else "")
            )

        msg = self._build_message(data)

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

    def _build_message(self, data: Any) -> Any:
        """Turn a send payload (dict / ``id#data`` string / Message) into a
        :class:`can.Message`, shared by single-shot and periodic sends."""
        import can

        if isinstance(data, str):
            # Parse a string formatted as "can_id#hex_data" e.g. "123#11223344AABBCCDD"
            return self._parse_can_string(data)
        if isinstance(data, can.Message):
            return data
        if isinstance(data, dict):
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

            return can.Message(**msg_kwargs)
        raise ValueError(f"Unsupported send payload type: {type(data)}")

    # ------------------------------------------------------------------ #
    # python-can pseudo-code translation (terminal / stray AI steps)
    # ------------------------------------------------------------------ #
    # A user (or a generated step) may type ``bus.send_periodic(can.Message(...), 0.2)``
    # or ``bus.send(can.Message(...))`` into the debug terminal. The plugin only
    # speaks JSON dicts and ``id#data`` strings, so we recognise the call here
    # and rewrite it to the equivalent JSON command — otherwise it falls through
    # to ``_parse_can_string`` and dies with "Invalid CAN string format".
    _PYCAN_CALL_RE = re.compile(
        r"^\s*(?:(?:bus|self\._bus)\s*\.\s*)?"
        r"(?P<fn>send_periodic|send_cyclic|cyclic_send|send|recv|receive|can\.Message|Message)"
        r"\s*\(",
        re.IGNORECASE,
    )

    @staticmethod
    def _balanced_paren(text: str, open_idx: int) -> str:
        """Return the substring inside the ``(`` at ``open_idx`` (through its
        matching ``)``)."""
        depth = 0
        for i in range(open_idx, len(text)):
            ch = text[i]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return text[open_idx + 1 : i]
        return text[open_idx + 1 :]

    @classmethod
    def _parse_message_kwargs(cls, args: str) -> Dict[str, Any]:
        """Parse ``can.Message(...)`` kwargs into a JSON command dict."""
        out: Dict[str, Any] = {}

        m = re.search(r"arbitration_id\s*=\s*(0x[0-9A-Fa-f]+|\d+)", args, re.IGNORECASE)
        if m:
            tok = m.group(1)
            out["arbitration_id"] = int(tok, 16) if tok.lower().startswith("0x") else int(tok)

        data: Optional[List[int]] = None
        m = re.search(r"data\s*=\s*\[([^\]]*)\]", args, re.IGNORECASE)
        if m:
            data = [
                int(x, 16) if x.lower().startswith("0x") else int(x)
                for x in re.findall(r"0x[0-9A-Fa-f]+|\d+", m.group(1))
            ]
        else:
            m = re.search(r"data\s*=\s*bytes\s*\(\s*\[([^\]]*)\]\s*\)", args, re.IGNORECASE)
            if m:
                data = [
                    int(x, 16) if x.lower().startswith("0x") else int(x)
                    for x in re.findall(r"0x[0-9A-Fa-f]+|\d+", m.group(1))
                ]
        if data is not None:
            out["data"] = data

        for flag in ("is_extended_id", "is_fd", "is_remote_frame"):
            m = re.search(flag + r"\s*=\s*(True|False|true|false|1|0)", args, re.IGNORECASE)
            if m:
                out[flag] = m.group(1).lower() in ("true", "1")

        m = re.search(r"dlc\s*=\s*(\d+)", args, re.IGNORECASE)
        if m:
            out["dlc"] = int(m.group(1))
        return out

    @classmethod
    def _translate_python_can(cls, text: str) -> Optional[Dict[str, Any]]:
        """Translate python-can pseudo-code into a JSON command dict (or ``None``).

        Covers:
          * ``bus.send_periodic(can.Message(...), 0.2)`` → ``send_periodic``
            (``period_ms`` = the seconds argument × 1000)
          * ``bus.send(can.Message(...))`` / ``can.Message(...)`` → single send
          * ``bus.recv(timeout=2.0)`` → ``receive``
        """
        if not isinstance(text, str):
            return None
        s = text.strip()
        m = cls._PYCAN_CALL_RE.match(s)
        if not m:
            return None
        fn = m.group("fn").lower()
        open_idx = m.end() - 1  # index of the opening '('
        args = cls._balanced_paren(s, open_idx)

        if fn in ("recv", "receive"):
            tm = re.search(r"timeout\s*=\s*([0-9.]+)", args, re.IGNORECASE)
            return {"action": "receive", "timeout": float(tm.group(1)) if tm else 0.05}

        # Locate can.Message(...) if it is wrapped by a bus.* call.
        msg_args = args
        msg_open: Optional[int] = None
        msg_m = re.search(r"can\.Message\s*\(", args, re.IGNORECASE)
        if msg_m:
            msg_open = msg_m.end() - 1
            msg_args = cls._balanced_paren(args, msg_open)

        cmd = cls._parse_message_kwargs(msg_args)
        if fn in ("can.message", "message"):
            return cmd or None

        if fn in ("send_periodic", "send_cyclic", "cyclic_send"):
            cmd["action"] = "send_periodic"
            period: Optional[float] = None
            if msg_open is not None:
                # The seconds argument sits after can.Message(...) closes.
                after_msg = args[msg_open + len(msg_args) + 2 :]
                pm = re.search(r"([0-9]*\.?[0-9]+)", after_msg)
                if pm:
                    period = float(pm.group(1))
            if period is None:
                raise ValueError(
                    "send_periodic 需要周期参数（秒），例如 bus.send_periodic(msg, 0.2)"
                )
            cmd["period_ms"] = period * 1000.0
            return cmd

        # Plain single send.
        if "arbitration_id" not in cmd:
            return None
        return cmd

    # ------------------------------------------------------------------ #
    # Periodic / cyclic transmission
    # ------------------------------------------------------------------ #
    # The period is a *parameter* of each command, never a fixed value — a
    # test case decides its own cadence via ``period_ms``.

    def _periodic_key(self, data: dict) -> str:
        return str(data.get("key") or data.get("tag") or data.get("arbitration_id") or "default")

    async def _send_periodic(self, data: dict) -> dict:
        """Start sending ``data`` every ``period_ms`` milliseconds.

        Extra keys:
          * ``period_ms`` (float, required) — interval, in milliseconds
          * ``count``     (int, optional)    — stop automatically after N frames
          * ``key``       (str, optional)    — handle used by ``stop_periodic``
        """
        import can

        if not self._connected or self._bus is None:
            raise ConnectionError("PeakCAN is not connected")

        period_ms = float(data.get("period_ms") or data.get("period") or 0)
        if period_ms <= 0:
            raise ValueError("周期发送需要正的 period_ms 参数（例如 period_ms: 200）")
        period = period_ms / 1000.0

        msg = self._build_message(data)
        task = self._bus.send_periodic(msg, period)
        key = self._periodic_key(data)
        # stop any previous transmission on the same key first
        await self._stop_periodic({"key": key}, quiet=True)
        self._periodic[key] = task

        count = data.get("count")
        if count:
            delay = period * max(1, int(count))
            try:
                self._periodic_auto_stop[key] = asyncio.create_task(
                    self._auto_stop_periodic(key, delay)
                )
            except RuntimeError:
                pass  # no running loop (e.g. sync test) — leave it running

        logger.info(
            "PeakCAN periodic send started: id=0x%X period=%.1fms count=%s",
            msg.arbitration_id, period_ms, count or "∞",
        )
        return {
            "status": "periodic_started",
            "key": key,
            "arbitration_id": msg.arbitration_id,
            "is_extended_id": msg.is_extended_id,
            "is_fd": getattr(msg, "is_fd", False),
            "period_ms": period_ms,
            "count": count,
        }

    async def _auto_stop_periodic(self, key: str, delay: float) -> None:
        await asyncio.sleep(delay)
        await self._stop_periodic({"key": key}, quiet=True)

    async def _stop_periodic(self, data: dict, quiet: bool = False) -> dict:
        """Stop one (by ``key``) or all periodic transmissions."""
        stopped: List[str] = []
        key = str(data.get("key") or data.get("tag") or "")

        if key:
            task = self._periodic.pop(key, None)
            auto = self._periodic_auto_stop.pop(key, None)
            if auto and not auto.done():
                auto.cancel()
            if task is not None:
                task.stop()
                stopped.append(key)
        else:
            for k, task in list(self._periodic.items()):
                task.stop()
                stopped.append(k)
            self._periodic.clear()
            for auto in self._periodic_auto_stop.values():
                if not auto.done():
                    auto.cancel()
            self._periodic_auto_stop.clear()

        if not quiet:
            logger.info("PeakCAN periodic send stopped: %s", stopped or "none")
        return {"status": "periodic_stopped", "keys": stopped}

    async def receive(self, timeout: float = 0.05, skip_error_frames: Optional[bool] = None) -> Any:
        """Read one buffered CAN message (non-blocking).

        By default error frames are *skipped*: python-can enables them, so a bus
        where nobody answers would otherwise surface as a bogus "response" with
        a tiny id. Pass ``skip_error_frames=False`` (or set it in the device
        config) to inspect them — then every entry carries an ``error_desc``.
        """
        if not self._connected or self._listener is None:
            raise ConnectionError("PeakCAN is not connected")

        if skip_error_frames is None:
            skip_error_frames = bool(self._config.get("skip_error_frames", True))

        deadline = time.monotonic() + max(float(timeout or 0.0), 0.0)
        while True:
            remaining = max(deadline - time.monotonic(), 0.0)
            try:
                msg = self._listener.get_message(timeout=remaining)
            except Exception:
                msg = None
            if msg is None:
                return None
            if skip_error_frames and msg.is_error_frame:
                logger.debug("PeakCAN: skipped error frame — %s", self._error_frame_desc(msg))
                if time.monotonic() >= deadline:
                    return None
                continue
            # In normal (non-loopback) mode, never surface our own TX frame that
            # the kernel echoed back — otherwise the sent message shows up in our
            # OWN terminal instead of the peer's, which reads as "the peer never
            # received it". ``is_rx`` is False for looped-back own frames.
            if (
                not bool(self._config.get("loopback", False))
                and getattr(msg, "is_rx", True) is False
            ):
                logger.debug("PeakCAN: skipped self-echo frame id=0x%X", msg.arbitration_id)
                if time.monotonic() >= deadline:
                    return None
                continue
            return self._msg_to_dict(msg)

    async def _handle_action(self, data: dict) -> Any:
        """Dispatch a dict payload's ``action`` without sending a CAN frame."""
        action = str(data.get("action") or "").strip().lower()
        if action in ("diagnose", "diagnostics"):
            return self.diagnose()
        if action in ("scan", "status", "list_channels"):
            return self.get_status()
        if action == "receive":
            return await self.receive(timeout=float(data.get("timeout", 0.05)))
        if action in ("send_periodic", "send_cyclic", "cyclic_send"):
            return await self._send_periodic(data)
        if action in ("stop_periodic", "stop_cyclic"):
            return await self._stop_periodic(data)
        if action in ("send", "send_can", "send_canfd", "send_message"):
            data.pop("action", None)  # fall through to the normal message path
            return await self.send(data)
        raise ValueError(
            f"未知的 PeakCAN action: '{action}'（可用：send / send_periodic / "
            f"stop_periodic / receive / scan / diagnose）"
        )

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
            "platform": sys.platform,
            "is_windows": self._is_windows(),
            "last_error": self._last_error or None,
        }

        # Append available channels from both interfaces
        try:
            import can
            status["available_pcan_channels"] = self._pcan_channels(can)
        except Exception:
            status["available_pcan_channels"] = []
        status["available_socketcan_channels"] = self._socketcan_channels()
        status["available_socketcan_up_channels"] = self._socketcan_channels(only_up=True)

        # Controller state — the fastest way to see why nothing gets through.
        channel = self._active_channel or (
            (self._config or {}).get("channel") or "" if self._config else ""
        )
        bus_state = self._bus_state(channel) if not sys.platform.startswith("win") else None
        status["bus_state"] = bus_state
        status["bus_hint"] = self._bus_hint(bus_state, channel)

        return status

    def diagnose(self) -> dict:
        """Environment report for troubleshooting a failed connection.

        Safe to call while disconnected (``{"action": "diagnose"}``).
        """
        info: Dict[str, Any] = self.get_status()
        try:
            import can
            info["python_can_version"] = getattr(can, "__version__", None)
            info["candidate_order"] = [
                f"{iface}/{ch}"
                for iface, ch in self._candidate_list(
                    (self._config or {}).get("interface") or "auto",
                    (self._config or {}).get("channel") or "",
                    can,
                )
            ]
        except Exception as e:
            info["python_can_version"] = None
            info["candidate_order"] = []
            info["candidate_error"] = str(e)
        info["last_attempts"] = list(self._attempts)
        info["hint"] = self._platform_hint()
        return info

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
                "loopback": {
                    "type": "boolean",
                    "title": "自发自收自检 (loopback)",
                    "default": False,
                    "description": "自检用：发出的帧会被内核回环给自己，即使总线上没有其他节点也能收到 —— 用于验证驱动/插件链路是否正常",
                },
                "skip_error_frames": {
                    "type": "boolean",
                    "title": "接收时跳过错误帧",
                    "default": True,
                    "description": "错误帧（无人应答/总线告警）不会被当成正常响应；需要排查总线时设为 false，返回会带 error_desc 说明",
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
                "description": "列出所有可用的 PCAN / SocketCAN 通道（无需先连接）",
                "parameters": [],
            },
            {
                "name": "diagnose",
                "syntax": '{"action": "diagnose"}',
                "description": "输出连接环境诊断（python-can 版本、候选接口顺序、驱动提示）",
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
        out = {
            "arbitration_id": msg.arbitration_id,
            "is_extended_id": msg.is_extended_id,
            "is_remote_frame": msg.is_remote_frame,
            "is_fd": getattr(msg, "is_fd", False),
            "is_error_frame": msg.is_error_frame,
            "is_rx": getattr(msg, "is_rx", True),  # False = 自己发出的回环帧
            "dlc": msg.dlc,
            "data": msg.data.hex(),
            "timestamp": getattr(msg, "timestamp", None),
        }
        if msg.is_error_frame:
            out["error_desc"] = PeakCANPlugin._error_frame_desc(msg)
        return out
