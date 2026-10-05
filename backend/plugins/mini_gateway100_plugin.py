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

# Standard protocols handled by the communication layer (not plugins).
_STANDARD_PROTOCOLS = {"scpi", "gpib", "can", "serial", "ethernet", "usb"}


class MiniGateway100Plugin(BaseProtocolPlugin):
    """Mini Gateway 100 custom protocol plugin."""

    plugin_name = "Mini Gateway 100"
    protocol_name = "mini_gateway100"
    version = "1.0.0"

    def __init__(self):
        self._connected = False
        self._serial = None  # pyserial.Serial instance
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
    async def connect(self, config: dict) -> bool:
        """Open the serial (USB-C CDC) connection to the Mini Gateway 100.

        ``config`` keys:
          * ``port``      — serial device path, e.g. ``/dev/ttyACM0`` (required)
          * ``baudrate``  — default 115200, user selectable
          * ``board_id``  — board ID, default 11
          * ``timeout``   — read timeout in seconds, default 2.0
        """
        try:
            import serial
        except ImportError as e:
            raise RuntimeError(
                "pyserial is not installed. Install with: pip install pyserial"
            ) from e

        config = config or {}
        port = config.get("port")
        if not port:
            raise ValueError("Missing 'port' in plugin config (serial device path)")

        self._config = config
        self._board_id = int(config.get("board_id", 11))
        baudrate = int(config.get("baudrate", 115200))
        timeout = float(config.get("timeout", 2.0))

        self._serial = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=timeout,
        )
        self._connected = True
        logger.info(
            f"Mini Gateway 100 connected: {port} @ {baudrate} baud, board_id={self._board_id}"
        )
        return True

    async def disconnect(self) -> bool:
        if self._serial and self._serial.is_open:
            try:
                self._serial.close()
            except Exception as e:
                logger.warning(f"Error closing Mini Gateway 100 serial port: {e}")
        self._serial = None
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
        if not self._connected or self._serial is None:
            raise ConnectionError("Mini Gateway 100 is not connected")

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
                self._serial.reset_input_buffer()
                self._serial.write((raw_cmd + "\r\n").encode())

                # Read until the terminating ';' (response has no newline).
                buf = bytearray()
                while True:
                    chunk = self._serial.read(1)
                    if not chunk:
                        break
                    buf += chunk
                    if chunk == b";":
                        break

                raw_response = bytes(buf).decode(errors="replace").strip()
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
        if not self._connected or self._serial is None:
            raise ConnectionError("Mini Gateway 100 is not connected")

        async with self._get_lock():
            old_timeout = self._serial.timeout
            self._serial.timeout = max(0.01, min(float(timeout), 0.2))
            try:
                buf = bytearray()
                while True:
                    chunk = self._serial.read(1)
                    if not chunk:
                        break
                    buf += chunk
                    if chunk == b";":
                        break
            finally:
                self._serial.timeout = old_timeout

        raw = bytes(buf).decode(errors="replace").strip()
        if not raw:
            return None
        return self._parse_response(raw)

    # ------------------------------------------------------------------ #
    # Plugin metadata for the UI
    # ------------------------------------------------------------------ #
    def get_config_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "port": {
                    "type": "string",
                    "title": "串口号 / 设备路径",
                    "default": _default_port(),
                    "description": "Mini Gateway 100 USB-C CDC 串口设备路径",
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
            "required": ["port"],
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
        }
