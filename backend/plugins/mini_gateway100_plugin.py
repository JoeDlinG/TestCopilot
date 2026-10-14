"""Mini Gateway 100 protocol plugin for AITestLab.

Implements the UART / USB-C command protocol described in
"Mini Gateway 100 - User Manual v1.5".

Protocol summary (from the manual)
----------------------------------
* Every command starts with ``@`` and ends with ``;`` and carries the board ID
  and the command plus its parameters in order::

      @<ID>_<COMMAND>=<PARAMETERS>;

* The board replies with a header (timestamp + size) then a ``#`` framed body::

      [yy/mm/dd,hh:mm:ss.msec,size]#<ID>_<COMMAND>=<RESULT>;

* Commands are request/response: a new command may only be sent after the
  reply to the previous one has been received (1.5 s timeout on the device).

Transports
----------
The board exposes the same protocol on two physical links, selected with the
``transport`` config key:

* ``serial``   — USB-C CDC virtual COM port (default, unchanged behaviour)
* ``ethernet`` — raw TCP socket, default ``192.168.0.120:6025``

Per the user's decisions:
* The RS-232 external power-supply ON/OFF command (``PSU``) is intentionally
  NOT implemented (no application scenario yet).
* The USB-C host port baud rate defaults to 115200 but is user selectable.
* The board ID is configurable and defaults to 11.

Install via the plugin management UI (插件管理), then add the device through
the plugin ("添加设备").
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

from app.services.plugin_service import BaseProtocolPlugin


logger = logging.getLogger(__name__)


def _default_port() -> str:
    """Return a sensible default serial device path for the current OS."""
    return "COM3" if os.name == "nt" else "/dev/ttyACM0"


# The Mini Gateway 100 speaks the very same request/response protocol over its
# USB-C CDC port and over its Ethernet port — only the transport differs, so a
# single plugin covers both.
TRANSPORTS = ("serial", "ethernet")
DEFAULT_ETH_HOST = "192.168.0.120"
DEFAULT_ETH_PORT = 6025

# Standard protocols handled by the communication layer (not plugins).
_STANDARD_PROTOCOLS = {"scpi", "gpib", "can", "serial", "ethernet", "usb"}


class MiniGateway100Plugin(BaseProtocolPlugin):
    """Mini Gateway 100 custom protocol plugin."""

    plugin_name = "Mini Gateway 100"
    protocol_name = "mini_gateway100"
    version = "1.0.0"

    def __init__(self):
        self._connected = False
        self._transport = "serial"   # "serial" | "ethernet"
        self._serial = None          # pyserial.Serial instance (transport=serial)
        self._reader = None          # asyncio.StreamReader (transport=ethernet)
        self._writer = None          # asyncio.StreamWriter (transport=ethernet)
        self._board_id = 11
        self._config: Dict[str, Any] = {}
        # Serialises access to the single serial port so that background
        # polling (unsolicited frames) can never steal the bytes of a
        # command/response exchange. Created lazily (Python 3.8 binds asyncio
        # primitives to the running loop at creation time).
        self._io_lock = None

    def _get_lock(self) -> "asyncio.Lock":
        if self._io_lock is None:
            self._io_lock = asyncio.Lock()
        return self._io_lock

    # ------------------------------------------------------------------ #
    # Connection management
    # ------------------------------------------------------------------ #
    @property
    def _endpoint_label(self) -> str:
        """Human readable endpoint description used in logs and errors."""
        if self._transport == "ethernet":
            return f"{self._config.get('host', DEFAULT_ETH_HOST)}:{self._config.get('tcp_port', DEFAULT_ETH_PORT)}"
        return str(self._config.get("port") or _default_port())

    def _require_connection(self) -> None:
        if not self._connected:
            raise ConnectionError("Mini Gateway 100 is not connected")
        if self._transport == "ethernet":
            if self._writer is None or self._reader is None:
                raise ConnectionError("Mini Gateway 100 Ethernet link is not open")
        elif self._serial is None:
            raise ConnectionError("Mini Gateway 100 serial port is not open")

    # ---- transport primitives ------------------------------------------ #

    async def _write_frame(self, payload: str) -> None:
        """Send one terminated frame on whichever transport is active."""
        data = (payload + "\r\n").encode()
        if self._transport == "ethernet":
            self._writer.write(data)
            await self._writer.drain()
        else:
            self._serial.write(data)

    async def _flush_input(self) -> None:
        """Drop stale inbound bytes before a request/response exchange."""
        if self._transport == "ethernet":
            # Best effort: anything already buffered belongs to a previous,
            # already-consumed exchange (e.g. unsolicited frames).
            while True:
                try:
                    extra = await asyncio.wait_for(self._reader.read(4096), timeout=0.02)
                except asyncio.TimeoutError:
                    break
                if not extra:
                    break
        elif self._serial is not None:
            self._serial.reset_input_buffer()

    async def _read_frame(self, timeout: float) -> bytes:
        """Read one response frame terminated by ``;``.

        Returns whatever arrived (possibly empty) when *timeout* elapses, so a
        slow/absent reply surfaces as an empty frame rather than hanging.
        """
        if self._transport == "ethernet":
            loop = asyncio.get_event_loop()
            deadline = loop.time() + max(0.01, timeout)
            buf = bytearray()
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break
                try:
                    chunk = await asyncio.wait_for(
                        self._reader.read(4096), timeout=remaining
                    )
                except asyncio.TimeoutError:
                    break
                if not chunk:
                    break
                buf += chunk
                if b";" in chunk:
                    end = buf.index(b";") + 1
                    return bytes(buf[:end])
            return bytes(buf)

        # Serial: pyserial has its own read timeout, so a plain loop suffices.
        old_timeout = self._serial.timeout
        self._serial.timeout = max(0.01, timeout)
        try:
            buf = bytearray()
            while True:
                chunk = self._serial.read(1)
                if not chunk:
                    break
                buf += chunk
                if chunk == b";":
                    break
            return bytes(buf)
        finally:
            self._serial.timeout = old_timeout

    # ---- connection lifecycle ------------------------------------------- #

    async def connect(self, config: dict) -> bool:
        """Open a connection to the Mini Gateway 100.

        ``config`` keys:
          * ``transport``  — ``"serial"`` (default) or ``"ethernet"``
          * serial branch: ``port`` / ``baudrate``
          * ethernet branch: ``host`` (default ``192.168.0.120``) /
            ``tcp_port`` (default ``6025``)
          * common: ``board_id`` (default 11), ``timeout`` (default 2.0 s)
        """
        config = config or {}
        transport = str(config.get("transport") or "serial").strip().lower()
        if transport not in TRANSPORTS:
            raise ValueError(
                f"不支持的连接方式 '{transport}'，可选：{' / '.join(TRANSPORTS)}"
            )

        self._config = config
        self._transport = transport
        self._board_id = int(config.get("board_id", 11))

        if transport == "ethernet":
            await self._connect_ethernet(config)
        else:
            await self._connect_serial(config)

        self._connected = True
        logger.info(
            f"Mini Gateway 100 connected via {transport}: "
            f"{self._endpoint_label}, board_id={self._board_id}"
        )
        return True

    async def _connect_serial(self, config: Dict[str, Any]) -> None:
        try:
            import serial
        except ImportError as e:
            raise RuntimeError(
                "pyserial is not installed. Install with: pip install pyserial"
            ) from e

        port = config.get("port")
        if not port:
            raise ValueError("Missing 'port' in plugin config (serial device path)")

        self._serial = serial.Serial(
            port=port,
            baudrate=int(config.get("baudrate", 115200)),
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=float(config.get("timeout", 2.0)),
        )

    async def _connect_ethernet(self, config: Dict[str, Any]) -> None:
        host = str(config.get("host") or DEFAULT_ETH_HOST).strip()
        try:
            tcp_port = int(config.get("tcp_port") or DEFAULT_ETH_PORT)
        except (TypeError, ValueError) as e:
            raise ValueError(f"以太网端口号无效：{config.get('tcp_port')!r}") from e

        connect_timeout = float(config.get("connect_timeout", 5.0))
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(host, tcp_port),
                timeout=connect_timeout,
            )
        except asyncio.TimeoutError as e:
            raise ConnectionError(
                f"连接 Mini Gateway 100 超时（{host}:{tcp_port}，{connect_timeout}s）。"
                "请确认设备已上电、网线已接好，且 IP 与端口配置正确。"
            ) from e
        except OSError as e:
            raise ConnectionError(
                f"无法通过以太网连接 Mini Gateway 100（{host}:{tcp_port}）：{e}。"
                "请确认设备已上电、IP 可达且端口未被占用。"
            ) from e
        # Normalise so later lookups (and the endpoint label) see the resolved
        # values instead of whatever was left blank.
        self._config["host"] = host
        self._config["tcp_port"] = tcp_port

    async def disconnect(self) -> bool:
        if self._serial is not None:
            try:
                if self._serial.is_open:
                    self._serial.close()
            except Exception as e:
                logger.warning(f"Error closing Mini Gateway 100 serial port: {e}")
        self._serial = None

        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception as e:
                logger.warning(f"Error closing Mini Gateway 100 Ethernet link: {e}")
        self._writer = None
        self._reader = None

        self._connected = False
        return True

    # ------------------------------------------------------------------ #
    # Command building / response parsing
    # ------------------------------------------------------------------ #
    def _build_command(self, command: str, parameters: Optional[Any] = None) -> str:
        """Build a protocol command string from a command name and params."""
        cmd = command.upper()
        if parameters is None or parameters == "" or parameters == []:
            return f"@{self._board_id}_{cmd};"
        if isinstance(parameters, dict):
            param_str = ",".join(str(v) for v in parameters.values())
        elif isinstance(parameters, (list, tuple)):
            param_str = ",".join(str(p) for p in parameters)
        else:
            param_str = str(parameters)
        return f"@{self._board_id}_{cmd}={param_str};"

    @staticmethod
    def _parse_response(raw: str) -> str:
        """Extract the RESULT portion from a ``#<ID>_<CMD>=<RESULT>;`` reply.

        Some commands (e.g. HELLO) reply without a ``=`` separator, meaning an
        empty payload / simple acknowledgement — in that case we return "".
        """
        if not raw:
            return raw
        body = raw.split("#", 1)[1] if "#" in raw else raw
        body = body.strip()
        if "=" in body:
            result = body.split("=", 1)[1]
        else:
            result = ""
        if result.endswith(";"):
            result = result[:-1]
        return result.strip()

    # ------------------------------------------------------------------ #
    # Transport
    # ------------------------------------------------------------------ #
    async def send(self, data: Any) -> Any:
        """Send a command and return the parsed result string.

        ``data`` may be:
          * a raw protocol string (e.g. ``"@11_SYSID=;"``) — forwarded as-is, or
          * a dict ``{"command": "SYSID", "parameters": [...]}`` — formatted.
        """
        self._require_connection()

        if isinstance(data, dict):
            command = data.get("command")
            if not command:
                raise ValueError("Missing 'command' in payload")
            raw_cmd = self._build_command(command, data.get("parameters"))
        elif isinstance(data, str):
            # Raw passthrough: if it already looks like a protocol frame, send
            # as-is; otherwise treat the whole string as a command name.
            if data.lstrip().startswith("@"):
                raw_cmd = data if data.rstrip().endswith(";") else data.rstrip() + ";"
            else:
                raw_cmd = self._build_command(data.strip())
        else:
            raise ValueError(f"Unsupported send payload: {type(data)}")

        # Serialise with background polling so responses are never consumed
        # by a concurrent read.
        async with self._get_lock():
            try:
                await self._flush_input()
                await self._write_frame(raw_cmd)

                # Read until the terminating ';' (response has no newline).
                reply = await self._read_frame(float(self._config.get("timeout", 2.0)))

                raw_response = reply.decode(errors="replace").strip()
                logger.debug(f"MG100 TX: {raw_cmd!r}  RX: {raw_response!r}")
                return self._parse_response(raw_response)
            except Exception as e:
                logger.error(f"Mini Gateway 100 send error: {e}")
                raise

    async def receive(self, timeout: float = 0.05) -> Any:
        """Read one unsolicited frame (terminated by ';').

        Uses a short read timeout so an idle poll returns quickly and never
        delays a pending command; access is serialised with :meth:`send`.
        """
        self._require_connection()

        async with self._get_lock():
            frame = await self._read_frame(max(0.01, min(float(timeout), 0.2)))

        raw = frame.decode(errors="replace").strip()
        if not raw:
            return None
        return self._parse_response(raw)

    # ------------------------------------------------------------------ #
    # Plugin metadata for the UI
    # ------------------------------------------------------------------ #
    def get_config_schema(self) -> dict:
        # NOTE: there is deliberately no top-level ``required`` list — which
        # fields are mandatory depends on ``transport``, and that is enforced
        # in :meth:`connect` with a user-friendly message.
        return {
            "type": "object",
            "properties": {
                "transport": {
                    "type": "string",
                    "title": "连接方式",
                    "default": "serial",
                    "enum": list(TRANSPORTS),
                    "description": "serial=USB-C CDC 串口；ethernet=以太网 TCP",
                },
                "port": {
                    "type": "string",
                    "title": "串口号 / 设备路径",
                    "default": _default_port(),
                    "description": "transport=serial 时使用。Mini Gateway 100 USB-C CDC 串口设备路径",
                },
                "baudrate": {
                    "type": "integer",
                    "title": "波特率",
                    "default": 115200,
                    "enum": [
                        9600, 19200, 38400, 57600,
                        115200, 230400, 460800, 921600,
                    ],
                },
                "host": {
                    "type": "string",
                    "title": "IP 地址",
                    "default": DEFAULT_ETH_HOST,
                    "description": f"transport=ethernet 时使用。出厂默认 {DEFAULT_ETH_HOST}",
                },
                "tcp_port": {
                    "type": "integer",
                    "title": "TCP 端口号",
                    "default": DEFAULT_ETH_PORT,
                    "minimum": 1,
                    "maximum": 65535,
                    "description": f"transport=ethernet 时使用。默认 {DEFAULT_ETH_PORT}",
                },
                "connect_timeout": {
                    "type": "number",
                    "title": "以太网连接超时 (秒)",
                    "default": 5.0,
                    "minimum": 0.5,
                    "maximum": 60,
                    "description": "transport=ethernet 时建立 TCP 连接的最长等待时间",
                },
                "board_id": {
                    "type": "integer",
                    "title": "板卡 ID",
                    "default": 11,
                    "minimum": 0,
                    "maximum": 99,
                },
                "timeout": {
                    "type": "number",
                    "title": "读取超时 (秒)",
                    "default": 2.0,
                    "minimum": 0.2,
                    "maximum": 30,
                },
            },
        }

    def get_device_template(self) -> dict:
        """Template used by the backend to create a Device from this plugin."""
        schema = self.get_config_schema()
        defaults = {
            k: v.get("default")
            for k, v in schema["properties"].items()
            if "default" in v
        }
        return {
            "name": "Mini Gateway 100",
            "type": "gateway",
            "protocol": self.protocol_name,
            "connection_type": "usb",
            "config": defaults,
        }

    def get_commands(self) -> List[Dict[str, Any]]:
        """Command descriptors for UI help / auto-completion."""
        return [
            {"name": "HELLO", "syntax": "@<ID>_HELLO;",
             "description": "与板卡握手，确认通信正常", "parameters": []},
            {"name": "SYSID", "syntax": "@<ID>_SYSID;",
             "description": "获取设备软件版本 / 系统 ID", "parameters": []},
            {"name": "PSUV", "syntax": "@<ID>_PSUV=<voltage>;",
             "description": "设置 RS-232 外接电源的输出电压 (V)",
             "parameters": [{"name": "voltage", "type": "number"}]},
            {"name": "PSUC", "syntax": "@<ID>_PSUC=<current>;",
             "description": "设置 RS-232 外接电源的输出电流限制 (A)",
             "parameters": [{"name": "current", "type": "number"}]},
            {"name": "PSDV", "syntax": "@<ID>_PSDV;",
             "description": "读取 RS-232 外接电源的输出电压反馈", "parameters": []},
            {"name": "PSDC", "syntax": "@<ID>_PSDC;",
             "description": "读取 RS-232 外接电源的输出电流反馈", "parameters": []},
            {"name": "ETH", "syntax": "@<ID>_ETH=<TYPE>,<value>; 或 @<ID>_ETH;",
             "description": "设置/读取以太网 IP (SOURCE/MASK/GATEWAY)",
             "parameters": [{"name": "TYPE", "type": "string"},
                            {"name": "value", "type": "string"}]},
            {"name": "RTC", "syntax": "@<ID>_RTC=SET,<Y>,<M>,<D>,<WD>,<h>,<m>,<s>; 或 @<ID>_RTC=GET;",
             "description": "设置/读取实时时钟",
             "parameters": [{"name": "mode", "type": "string"}]},
            {"name": "STORAGE", "syntax": "@<ID>_STORAGE=<op>;",
             "description": "管理 SD 卡 (DLSTART/DLSTOP/...)",
             "parameters": [{"name": "op", "type": "string"}]},
            {"name": "SETDIG", "syntax": "@<ID>_SETDIG=<channel>;",
             "description": "将指定数字输出置高",
             "parameters": [{"name": "channel", "type": "integer"}]},
            {"name": "CLRDIG", "syntax": "@<ID>_CLRDIG=<channel>;",
             "description": "将指定数字输出置低",
             "parameters": [{"name": "channel", "type": "integer"}]},
            {"name": "GETDIG", "syntax": "@<ID>_GETDIG=<channel>;",
             "description": "读取指定数字输入状态",
             "parameters": [{"name": "channel", "type": "integer"}]},
            {"name": "CALBRT", "syntax": "@<ID>_CALBRT=VIN,<ch>,<FS|OF>,<value>;",
             "description": "校准模拟输入 (VIN) / 输出 (VOUT) 的 Scale/Offset",
             "parameters": [{"name": "type", "type": "string"},
                            {"name": "channel", "type": "integer"},
                            {"name": "parameter", "type": "string"},
                            {"name": "value", "type": "number"}]},
            {"name": "GETVOLT", "syntax": "@<ID>_GETVOLT=<channel>;",
             "description": "读取模拟输入通道电压",
             "parameters": [{"name": "channel", "type": "integer"}]},
            {"name": "SETVOLT", "syntax": "@<ID>_SETVOLT=<channel>,<voltage>;",
             "description": "设置模拟输出通道电压",
             "parameters": [{"name": "channel", "type": "integer"},
                            {"name": "voltage", "type": "number"}]},
            {"name": "OPEN", "syntax": "@<ID>_OPEN=R<ch1>[,R<ch2>...];",
             "description": "断开一个或多个继电器 (1-96)",
             "parameters": [{"name": "channels", "type": "string"}]},
            {"name": "CLOSE", "syntax": "@<ID>_CLOSE=R<ch1>[,R<ch2>...];",
             "description": "闭合一个或多个继电器 (1-96)",
             "parameters": [{"name": "channels", "type": "string"}]},
            {"name": "CONFIG", "syntax": "@<ID>_CONFIG=CAN<ch>,BAUDRATE,<baud>; 或 @<ID>_CONFIG=CAN<ch>,<dir>,<alias>,<IDtype>,<ID>;",
             "description": "配置 CAN 总线波特率 / 消息 ID（波特率只支持 10K/20K/33.3K/40K/83.3K/100K/125K/250K/500K/1000K(1M)，大写 K；ID 用大写 0X 前缀；配置前需先 TSTOP）",
             "parameters": [{"name": "args", "type": "string"}]},
            {"name": "TSTRT", "syntax": "@<ID>_TSTRT;",
             "description": "验证并启动当前配置", "parameters": []},
            {"name": "TSTOP", "syntax": "@<ID>_TSTOP;",
             "description": "复位当前配置", "parameters": []},
            {"name": "MSGTX", "syntax": "@<ID>_MSGTX=CAN<ch>,<alias>,<message>;",
             "description": "在指定 CAN 通道发送消息（alias 需先配置为 TX；message 必须以大写 0X 开头，最长 8 字节）",
             "parameters": [{"name": "channel", "type": "string"},
                            {"name": "alias", "type": "string"},
                            {"name": "message", "type": "string"}]},
            {"name": "MSGRX", "syntax": "@<ID>_MSGRX=CAN<ch>,<alias>,<size>;",
             "description": "在指定 CAN 通道接收消息（alias 需先配置为 RX；返回空数据 0X 表示未收到报文）",
             "parameters": [{"name": "channel", "type": "string"},
                            {"name": "alias", "type": "string"},
                            {"name": "size", "type": "integer"}]},
            {"name": "PROCESS", "syntax": "@<ID>_PROCESS=<id>,DEFINE,<granularity>,<totalsteps>; / @<ID>_PROCESS=<id>,<step>,<command>; / @<ID>_PROCESS=<id>,END|START|STOP|DELETE|DEFINE;",
             "description": "实时进程（定时/周期执行）：周期 = granularity x totalsteps；动作命令不带 @11_ 前缀与结尾 ;，step 取 1..totalsteps-1",
             "parameters": [{"name": "id", "type": "integer"},
                            {"name": "args", "type": "string"}]},
            {"name": "SYNCHRO", "syntax": "@<ID>_SYNCHRO=<OUT|IN>,<START|STOP>; 或 @<ID>_SYNCHRO=<OUT|IN>;",
             "description": "硬件同步：OUT 主模式 / IN 从模式；START 启用、STOP 禁用（注意：V1.4.8 固件实测无应答，暂不可用）",
             "parameters": [{"name": "mode", "type": "string"},
                            {"name": "state", "type": "string"}]},
        ]

    def get_status(self) -> dict:
        return {
            "name": self.plugin_name,
            "protocol": self.protocol_name,
            "version": self.version,
            "connected": self._connected,
            "board_id": self._board_id,
            "transport": self._transport,
            "endpoint": self._endpoint_label if self._connected else None,
        }
