"""Shared SCPI transport for programmable DC power supplies.

Four brand plugins (ITECH, TDK-Lambda, Chroma, Keysight) differ only in their
command dialect and factory defaults. The physical transport -- RS-232 / RS-485
serial and LAN raw TCP socket -- is identical, so it lives here once.

Design constraints taken from the existing plugins:

* ``run_blocking`` for every pyserial call (never block the event loop).
* ``transport`` is written by ``apply_plugin_transport`` (issue #11 regression:
  without a binding the UI can never switch a plugin from serial to LAN).
* ``send`` raises ``ValueError`` for command/semantic errors and
  ``ConnectionError``/``OSError`` for transport errors. ``device_service`` uses
  that distinction to avoid dropping a healthy device on a bad command
  (issue #33).
* ``port`` has a placeholder but NO default: a hard-coded /dev/tty* used to be
  persisted into every new device (AST guard in Test/test_mgw100_connect.py).
* ``receive`` must return immediately: the global monitor polls every 100 ms.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from app.core.blocking import run_blocking

__all__ = ["ScpiPowerTransport", "default_serial_port"]

#: Aliases accepted for ``config["transport"]``. Users coming from the generic
#: interface dialog supply ``serial`` / ``ethernet``; manuals say RS-232/RS-485
#: and LAN, so those spellings are accepted too.
_SERIAL_ALIASES = frozenset({"serial", "rs232", "rs-232", "rs485", "rs-485", "com"})
_LAN_ALIASES = frozenset({"ethernet", "lan", "tcp", "tcpip", "socket"})

#: Commands whose ``{value}`` must be a finite number.
_NUMERIC_ACTIONS = frozenset({
    "set_voltage", "set_current", "set_ovp", "set_ocp",
    "set_voltage_slew", "set_current_slew",
})

_COMMAND_DESCRIPTIONS: Dict[str, str] = {
    "idn": "读取仪器识别字串（厂商 / 型号 / 序列号 / 固件）",
    "reset": "恢复出厂设置（IEEE 488.2 *RST）",
    "clear_status": "清除状态与错误队列（IEEE 488.2 *CLS）",
    "system_error": "读取并弹出下一条仪器错误",
    "set_voltage": "设定输出电压（V）",
    "get_voltage": "回读电压设定值（V）",
    "set_current": "设定输出电流（A）",
    "get_current": "回读电流设定值（A）",
    "output_on": "打开输出",
    "output_off": "关闭输出",
    "get_output": "查询输出开关状态",
    "measure_voltage": "实测输出电压（V）",
    "measure_current": "实测输出电流（A）",
    "measure_power": "实测输出功率（W）",
    "set_ovp": "设定过压保护阈值（V）",
    "set_ocp": "设定过流保护阈值（A）",
    "get_status": "读取状态/保护寄存器",
    "select_channel": "选择输出通道（多通道机型）",
    "set_voltage_slew": "设定电压爬升率",
    "set_current_slew": "设定电流爬升率",
}


def default_serial_port() -> str:
    """Platform-appropriate placeholder (never persisted as a default)."""
    return "COM3" if os.name == "nt" else "/dev/ttyUSB0"


class ScpiPowerTransport:
    """Mixin implementing serial + LAN SCPI I/O for a power-supply plugin.

    A concrete plugin subclasses this mixin together with ``BaseProtocolPlugin``
    and supplies ``COMMAND_MAP`` plus a handful of brand defaults. It is *not*
    itself a plugin (``plugin_service`` only collects BaseProtocolPlugin
    subclasses), so it can safely live in ``app/services``.
    """

    BRAND: str = "GENERIC"
    IDN_EXPECT: Tuple[str, ...] = ()
    DEFAULT_LAN_PORT: int = 5025
    DEFAULT_BAUDRATE: int = 9600
    BAUD_RATES: List[int] = [4800, 9600, 19200, 38400, 57600, 115200]
    COMMAND_MAP: Dict[str, str] = {}
    #: Commands that need a ``{channel}`` placeholder (multi-output models).
    SUPPORTS_CHANNELS: bool = False

    def __init__(self) -> None:
        self._connected = False
        self._transport = "serial"
        self._config: Dict[str, Any] = {}
        self._serial = None                 # pyserial.Serial
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._lock: Optional[asyncio.Lock] = None
        self._idn: str = ""

    # ------------------------------------------------------------------ #
    # small helpers
    # ------------------------------------------------------------------ #
    def _get_lock(self) -> asyncio.Lock:
        # Created lazily so it binds to the running loop, not import time.
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    @staticmethod
    def _normalise_transport(value: Any) -> str:
        text = str(value or "serial").strip().lower()
        if text in _SERIAL_ALIASES:
            return "serial"
        if text in _LAN_ALIASES:
            return "ethernet"
        raise ConnectionError(
            f"不支持的连接方式 {value!r}（可选 serial / RS232 / RS485 / ethernet / LAN）"
        )

    @staticmethod
    def _is_query(command: str) -> bool:
        """SCPI queries put '?' on the header, which may not end the message."""
        head = command.strip().split(" ", 1)[0]
        return head.endswith("?") or command.rstrip().endswith("?")

    @staticmethod
    def _stringify(value: Any) -> str:
        if isinstance(value, bool):
            return "ON" if value else "OFF"
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)

    @property
    def _termination(self) -> str:
        raw = self._config.get("termination", "\n")
        if raw in ("CR", "cr", "\\r"):
            return "\r"
        if raw in ("CRLF", "crlf", "\\r\\n"):
            return "\r\n"
        return "\n"

    def format_command(self, action: str, value: Any = None,
                       channel: Any = None, **kwargs: Any) -> str:
        """Render one high-level action into a brand-specific SCPI string."""
        template = self.COMMAND_MAP.get(action)
        if template is None:
            raise ValueError(
                f"未知命令 {action!r}；可用: {', '.join(sorted(self.COMMAND_MAP))}"
            )
        fields: Dict[str, Any] = dict(kwargs)
        fields.setdefault("channel", channel)
        if "{value}" in template:
            if value is None:
                raise ValueError(f"命令 {action!r} 缺少 value 参数")
            if action in _NUMERIC_ACTIONS:
                try:
                    number = float(value)
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"{action} 需要数值，收到 {value!r}") from exc
                if not math.isfinite(number):
                    raise ValueError(f"{action} 不接受 NaN / Infinity")
                fields["value"] = self._stringify(value)
            else:
                fields["value"] = self._stringify(value)
        if "{channel}" in template:
            if channel in (None, ""):
                channel = self._config.get("channel", "OUT1")
            fields["channel"] = self._stringify(channel)
        try:
            return template.format(**fields).strip()
        except (KeyError, IndexError) as exc:
            raise ValueError(f"命令 {action!r} 参数不完整: {exc}") from exc

    def _parse_payload(self, data: Any) -> Tuple[str, bool]:
        """Return (SCPI command, force_query). Raises ValueError on bad input."""
        if isinstance(data, bytes):
            data = data.decode("utf-8", "replace")
        if isinstance(data, str):
            text = data.strip()
            if text.startswith("{"):
                try:
                    parsed = json.loads(text)
                except (ValueError, TypeError):
                    parsed = None
                if isinstance(parsed, dict):
                    data = parsed
                else:
                    return text, False
            else:
                return text, False
        if not isinstance(data, dict):
            raise ValueError(f"不支持的命令类型 {type(data).__name__}（应为字符串或字典）")

        force_query = bool(data.get("query"))
        if data.get("action"):
            value = data.get("value")
            if value is None and data.get("parameters"):
                params = data["parameters"]
                if isinstance(params, (list, tuple)) and params:
                    value = params[0]
            command = self.format_command(
                str(data["action"]), value=value,
                channel=data.get("channel"), **{
                    k: v for k, v in data.items()
                    if k not in ("action", "value", "parameters", "channel", "query", "command")
                },
            )
            return command, force_query
        command = str(data.get("command") or "").strip()
        if not command:
            raise ValueError("命令字典缺少 command / action 字段")
        value = data.get("value")
        if value is None:
            params = data.get("parameters")
            if isinstance(params, (list, tuple)) and params:
                value = params[0]
        if value is not None and not self._is_query(command) and "{value}" not in command:
            command = f"{command} {self._stringify(value)}"
        return command, force_query

    # ------------------------------------------------------------------ #
    # transport primitives (serial + LAN)
    # ------------------------------------------------------------------ #
    async def _write_line(self, command: str) -> None:
        payload = (command + self._termination).encode(
            str(self._config.get("encoding", "ascii")), "replace"
        )
        if self._transport == "ethernet":
            if self._writer is None:
                raise ConnectionError("LAN 连接已断开")
            self._writer.write(payload)
            await self._writer.drain()
        else:
            if self._serial is None:
                raise ConnectionError("串口连接已断开")
            await run_blocking(self._serial.write, payload)

    async def _flush_input(self) -> None:
        """Discard stale bytes so a late reply cannot be mistaken for this one."""
        if self._transport == "ethernet":
            if self._reader is None:
                return
            try:
                await asyncio.wait_for(self._reader.read(4096), 0.01)
            except (asyncio.TimeoutError, OSError):
                pass
        elif self._serial is not None:
            try:
                await run_blocking(self._serial.reset_input_buffer)
            except (OSError, AttributeError):
                pass

    def _serial_readline_sync(self, timeout: float) -> bytes:
        old = self._serial.timeout
        self._serial.timeout = max(0.01, timeout)
        try:
            return self._serial.readline()
        finally:
            self._serial.timeout = old

    async def _read_line(self, timeout: float) -> str:
        try:
            if self._transport == "ethernet":
                if self._reader is None:
                    raise ConnectionError("LAN 连接已断开")
                raw = await asyncio.wait_for(self._reader.readline(), timeout=timeout)
            else:
                raw = await run_blocking(self._serial_readline_sync, timeout)
        except asyncio.TimeoutError as exc:
            raise ConnectionError(
                f"{self.BRAND} 电源在 {timeout:g}s 内无应答（检查接线 / 波特率 / 设备是否远程模式）"
            ) from exc
        if not raw:
            raise ConnectionError(f"{self.BRAND} 电源无应答，连接可能已断开")
        return raw.decode(str(self._config.get("encoding", "ascii")), "replace").strip()

    async def _connect_serial(self, config: Dict[str, Any]) -> None:
        try:
            import serial  # pyserial is an optional runtime dependency
        except ImportError as exc:
            raise ConnectionError("缺少 pyserial，请执行 pip install pyserial") from exc

        port = str(config.get("port") or config.get("serial_port") or "").strip()
        if not port:
            raise ConnectionError("串口号未配置：请在「配置接口」填写实际 COM 口或 /dev/ttyUSB*")
        if os.name == "nt":
            if not re.match(r"^COM\d{1,3}$", port, re.IGNORECASE):
                raise ConnectionError(f"Windows 串口名应形如 COM3，收到 {port!r}")
        elif not os.path.exists(port):
            raise ConnectionError(f"串口设备不存在: {port}")

        baudrate = int(config.get("baudrate") or self.DEFAULT_BAUDRATE)
        # "配置接口" writes the INTERFACE_SPECS names (data_bits / stop_bits)
        # into config, while the plugin template ships the driver-level names
        # (bytesize / stopbits). Prefer the UI value when both are present,
        # otherwise the template's 8N1 silently overrides what the user set.
        data_bits = int(config.get("data_bits") or config.get("bytesize") or 8)
        parity = str(config.get("parity") or "N")[:1].upper()
        stop_bits = float(config.get("stop_bits") or config.get("stopbits") or 1)
        parity_map = {
            "N": getattr(serial, "PARITY_NONE", "N"),
            "E": getattr(serial, "PARITY_EVEN", "E"),
            "O": getattr(serial, "PARITY_ODD", "O"),
        }
        stop_map = {
            1: getattr(serial, "STOPBITS_ONE", 1),
            1.5: getattr(serial, "STOPBITS_ONE_POINT_FIVE", 1.5),
            2: getattr(serial, "STOPBITS_TWO", 2),
        }
        if parity not in parity_map or stop_bits not in stop_map:
            raise ConnectionError(f"串口参数无效: parity={parity!r}, stopbits={stop_bits!r}")
        timeout = float(config.get("timeout") or 2.0)
        self._serial = await run_blocking(
            lambda: serial.Serial(
                port=port, baudrate=baudrate,
                bytesize=getattr(serial, "EIGHTBITS", 8) if data_bits == 8 else data_bits,
                parity=parity_map[parity], stopbits=stop_map[stop_bits],
                timeout=timeout, write_timeout=timeout,
            )
        )
        self._config["port"] = port

    async def _connect_lan(self, config: Dict[str, Any]) -> None:
        host = str(config.get("host") or config.get("ip_address") or "").strip()
        if not host:
            raise ConnectionError("LAN 连接方式缺少 IP 地址：请在「配置接口」填写电源 IP")
        try:
            tcp_port = int(config.get("tcp_port") or config.get("port") or self.DEFAULT_LAN_PORT)
        except (TypeError, ValueError) as exc:
            raise ConnectionError(f"LAN 端口无效: {config.get('tcp_port')!r}") from exc
        connect_timeout = float(config.get("connect_timeout") or 5.0)
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(host, tcp_port), timeout=connect_timeout
            )
        except (OSError, asyncio.TimeoutError) as exc:
            raise ConnectionError(
                f"无法连接 {host}:{tcp_port}（检查网线 / IP / LAN 端口，{self.BRAND} 默认 {self.DEFAULT_LAN_PORT}）: {exc}"
            ) from exc
        self._config.update(host=host, tcp_port=tcp_port)

    # ------------------------------------------------------------------ #
    # BaseProtocolPlugin contract
    # ------------------------------------------------------------------ #
    async def connect(self, config: dict) -> bool:
        await self.disconnect()
        cfg = dict(config or {})
        transport = self._normalise_transport(cfg.get("transport"))
        self._config, self._transport = cfg, transport
        try:
            if transport == "ethernet":
                await self._connect_lan(cfg)
            else:
                await self._connect_serial(cfg)
            self._connected = True
            if cfg.get("probe_idn", True):
                # Identification is best-effort: some supplies need a front
                # panel REMOTE switch before they answer any query.
                try:
                    self._idn = str(await self.send("*IDN?"))
                except Exception:
                    self._idn = ""
            return True
        except Exception as exc:
            await self.disconnect()
            if isinstance(exc, ConnectionError):
                raise
            raise ConnectionError(f"连接 {self.BRAND} 电源失败: {exc}") from exc

    async def disconnect(self) -> bool:
        if self._serial is not None:
            try:
                await run_blocking(self._serial.close)
            except Exception:
                pass
        self._serial = None
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
        self._writer = self._reader = None
        self._connected = False
        return True

    async def send(self, data: Any) -> Any:
        """Send a SCPI command; return the reply for queries, 'OK' otherwise.

        Accepts a raw SCPI string, a JSON string, or a dict with either
        ``command``/``value``/``query`` or a high-level ``action``.
        """
        if not self._connected:
            raise ConnectionError(f"{self.BRAND} 电源未连接")
        command, force_query = self._parse_payload(data)   # ValueError: semantic error
        if not command:
            return ""
        query = force_query or self._is_query(command)
        timeout = float(self._config.get("timeout") or 2.0)
        async with self._get_lock():
            try:
                await self._flush_input()
                await self._write_line(command)
                if query:
                    return await self._read_line(timeout)
                return str(self._config.get("write_ack", "OK"))
            except ValueError:
                raise
            except (OSError, asyncio.TimeoutError, RuntimeError) as exc:
                # Transport failures must reach device_service as ConnectionError
                # so the device is marked disconnected; do NOT catch ValueError.
                raise ConnectionError(f"{self.BRAND} 电源通信失败: {exc}") from exc

    async def receive(self, timeout: float = 0.05) -> Any:
        """Power supplies have no unsolicited traffic; monitor polls harmlessly."""
        return None

    # ------------------------------------------------------------------ #
    # metadata
    # ------------------------------------------------------------------ #
    def get_config_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "transport": {
                    "type": "string", "title": "连接方式", "default": "serial",
                    "enum": ["serial", "ethernet"],
                    "help": "serial = RS-232 / RS-485 串口；ethernet = LAN TCP socket",
                },
                "port": {
                    "type": "string", "title": "串口号",
                    "placeholder": default_serial_port(),
                    "help": "RS-232/RS-485 实际端口，勿使用示例值",
                },
                "baudrate": {
                    "type": "integer", "title": "波特率",
                    "default": self.DEFAULT_BAUDRATE, "enum": self.BAUD_RATES,
                },
                "bytesize": {"type": "integer", "title": "数据位", "default": 8},
                "parity": {
                    "type": "string", "title": "校验位", "default": "N",
                    "enum": ["N", "E", "O"],
                },
                "stopbits": {"type": "number", "title": "停止位", "default": 1},
                "rs485": {
                    "type": "boolean", "title": "RS-485 电气接口", "default": False,
                    "help": "串口参数相同；半双工/多机地址由转换器或设备面板设置",
                },
                "host": {
                    "type": "string", "title": "IP 地址（LAN）",
                    "placeholder": "192.168.1.100",
                },
                "tcp_port": {
                    "type": "integer", "title": "TCP 端口（LAN）",
                    "default": self.DEFAULT_LAN_PORT,
                },
                "connect_timeout": {"type": "number", "title": "连接超时（s）", "default": 5.0},
                "timeout": {"type": "number", "title": "读取超时（s）", "default": 2.0},
                "termination": {
                    "type": "string", "title": "命令结束符", "default": "LF",
                    "enum": ["LF", "CR", "CRLF"],
                },
                "probe_idn": {"type": "boolean", "title": "连接后读取 *IDN?", "default": True},
                # Private signature keys: not in INTERFACE_SPECS nor in
                # GENERIC_DRIVER_CONFIG_KEYS, so plugin pollution repair works.
                "brand_key": {"type": "string", "title": "品牌标识", "default": self.BRAND},
                "idn_expect": {
                    "type": "string", "title": "*IDN? 期望厂商字段",
                    "default": "|".join(self.IDN_EXPECT),
                },
            },
        }

    def get_device_template(self) -> dict:
        props = self.get_config_schema()["properties"]
        config = {k: v["default"] for k, v in props.items() if "default" in v}
        return {
            "name": getattr(self, "plugin_name", f"{self.BRAND} 可编程直流电源"),
            "type": "power_supply",
            "protocol": getattr(self, "protocol_name", ""),
            "connection_type": "serial",
            "config": config,
        }

    def get_commands(self) -> list:
        out = []
        for action, syntax in sorted(self.COMMAND_MAP.items()):
            out.append({
                "name": action,
                "syntax": syntax,
                "description": _COMMAND_DESCRIPTIONS.get(action, action),
                "parameters": ["value"] if "{value}" in syntax else [],
            })
        return out

    def get_status(self) -> dict:
        return {
            "name": getattr(self, "plugin_name", self.BRAND),
            "protocol": getattr(self, "protocol_name", ""),
            "version": getattr(self, "version", ""),
            "connected": self._connected,
            "transport": self._transport if self._connected else None,
            "idn": self._idn,
        }
