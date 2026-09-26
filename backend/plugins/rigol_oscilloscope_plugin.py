"""RIGOL oscilloscope plugin — SCPI over LAN (raw TCP), USB-TMC or VISA.

Supports the RIGOL (普源精电) digital oscilloscope family (DS1000Z-E,
DS1000Z, MSO5000, ...) by speaking standard SCPI commands.

Transports
  * ``tcpip``  — raw TCP socket, port 5555 (no VISA / driver needed)  ← recommended
  * ``usbtmc`` — Linux USB-TMC character device, e.g. ``/dev/usbtmc0``
  * ``visa``   — any VISA resource string (requires ``pyvisa``)

Blocking socket/file IO is always executed in a worker thread so the FastAPI
event loop is never blocked.
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
import select
import socket
import struct
from typing import Any, Dict, List, Optional

from app.services.plugin_service import BaseProtocolPlugin

logger = logging.getLogger(__name__)

TRANSPORTS = ("tcpip", "usbtmc", "visa")

#: ``:WAVeform:PREamble?`` field order (see RIGOL programming guide)
PREAMBLE_KEYS = (
    "format", "type", "points", "count",
    "xincrement", "xorigin", "xreference",
    "yincrement", "yorigin", "yreference",
)


class RigolOscilloscopePlugin(BaseProtocolPlugin):
    """Control a RIGOL digital oscilloscope with SCPI commands."""

    plugin_name = "RIGOL 示波器"
    protocol_name = "rigol_oscilloscope"
    version = "1.0.0"

    def __init__(self) -> None:
        self._connected = False
        self._transport = "tcpip"
        self._sock: Optional[socket.socket] = None
        self._fd: Optional[int] = None
        self._visa: Any = None
        self._timeout = 2.0
        self._config: Dict[str, Any] = {}
        self._idn: Optional[str] = None
        self._buf = bytearray()

    # ------------------------------------------------------------------ #
    # Blocking primitives (always called through run_in_executor)
    # ------------------------------------------------------------------ #
    def _blk_write(self, payload: bytes) -> None:
        if self._transport == "tcpip":
            if self._sock is None:
                raise ConnectionError("socket 未建立")
            self._sock.sendall(payload)
        elif self._transport == "usbtmc":
            if self._fd is None:
                raise ConnectionError("USB-TMC 设备未打开")
            os.write(self._fd, payload)
        else:
            if self._visa is None:
                raise ConnectionError("VISA 资源未打开")
            self._visa.write_raw(payload)

    def _blk_read_some(self, size: int = 4096) -> bytes:
        if self._transport == "tcpip":
            if self._sock is None:
                raise ConnectionError("socket 未建立")
            return self._sock.recv(size)
        if self._transport == "usbtmc":
            if self._fd is None:
                raise ConnectionError("USB-TMC 设备未打开")
            return os.read(self._fd, size)
        if self._visa is None:
            raise ConnectionError("VISA 资源未打开")
        return bytes(self._visa.read_bytes(1))

    def _blk_drain(self, grace: float = 0.05) -> int:
        """Drop stale bytes sitting in the input queue.

        A previous operation may have left an answer behind (an aborted read,
        an unexpected device message). Without this the next query would read
        yesterdays response and every following command shifts by one.
        """
        dropped = len(self._buf)
        self._buf = bytearray()
        try:
            if self._transport == "tcpip":
                if self._sock is None:
                    return dropped
                self._sock.settimeout(grace)
                try:
                    while True:
                        chunk = self._sock.recv(65536)
                        if not chunk:
                            break
                        dropped += len(chunk)
                except (socket.timeout, TimeoutError, BlockingIOError, OSError):
                    pass
                finally:
                    self._sock.settimeout(self._timeout)
            elif self._transport == "usbtmc":
                if self._fd is None:
                    return dropped
                while True:
                    ready, _, _ = select.select([self._fd], [], [], grace)
                    if not ready:
                        break
                    chunk = os.read(self._fd, 65536)
                    if not chunk:
                        break
                    dropped += len(chunk)
            else:
                if self._visa is None:
                    return dropped
                old = getattr(self._visa, "timeout", None)
                try:
                    self._visa.timeout = max(1, int(grace * 1000))
                    while True:
                        try:
                            chunk = self._visa.read_raw(4096)
                        except Exception:  # noqa: BLE001 - timeout ends the drain
                            break
                        if not chunk:
                            break
                        dropped += len(chunk)
                finally:
                    if old is not None:
                        self._visa.timeout = old
        except Exception as exc:  # pragma: no cover - draining is best effort
            logger.debug(f"RIGOL 清空接收缓冲失败: {exc}")
        return dropped

    def _take(self, n: int) -> bytes:
        """Return exactly ``n`` bytes (buffered)."""
        while len(self._buf) < n:
            chunk = self._blk_read_some(65536)
            if not chunk:
                raise IOError("示波器连接已关闭（数据未读完）")
            self._buf.extend(chunk)
        data = bytes(self._buf[:n])
        del self._buf[:n]
        return data

    def _take_line(self) -> bytes:
        """Return one line without the trailing newline."""
        while b"\n" not in self._buf:
            chunk = self._blk_read_some()
            if not chunk:
                break
            self._buf.extend(chunk)
        idx = self._buf.find(b"\n")
        if idx < 0:
            line = bytes(self._buf)
            del self._buf[:]
        else:
            line = bytes(self._buf[:idx])
            del self._buf[:idx + 1]
        return line.rstrip(b"\r")

    def _take_block(self) -> bytes:
        """Read an IEEE 488.2 definite-length block: ``#<N><len><data>``."""
        head = self._take(1)
        if head != b"#":
            # plain text answer (small ASCii transfers, error text, ...)
            return (head + self._take_line()).strip()
        digits = self._take(1).decode("ascii", "replace")
        if not digits.isdigit():
            raise IOError(f"块数据头解析失败: #{digits!r}")
        length = int(self._take(int(digits)).decode("ascii", "replace"))
        data = self._take(length)
        try:
            self._take(1)  # trailing terminator
        except Exception:  # pragma: no cover - device may not send one
            pass
        return data

    # ------------------------------------------------------------------ #
    # Async helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _run(fn, *args):
        loop = asyncio.get_running_loop()
        return loop.run_in_executor(None, fn, *args)

    @staticmethod
    def _is_query(cmd: str) -> bool:
        """Is this SCPI command a query?

        The ``?`` belongs to the **command keyword**, not to the whole string:
        ``:MEASure:ITEM? VPP,CHANnel1`` is a query even though it does not end
        with ``?``.
        """
        head = cmd.strip().split(" ", 1)[0]
        return head.endswith("?")

    async def _write(self, cmd: str) -> None:
        payload = cmd.strip().encode("ascii", "replace") + b"\n"
        await self._run(self._blk_write, payload)

    async def _query(self, cmd: str) -> str:
        await self._run(self._blk_drain)   # never read a stale answer
        await self._write(cmd)
        raw = await self._run(self._take_line)
        return raw.decode("utf-8", "replace").strip()

    async def write(self, cmd: str) -> None:
        """Send a SCPI command without waiting for an answer."""
        if not self._connected:
            raise ConnectionError("RIGOL 示波器未连接")
        await self._write(cmd)

    async def query(self, cmd: str) -> str:
        """Send a SCPI query and return the ASCII answer."""
        if not self._connected:
            raise ConnectionError("RIGOL 示波器未连接")
        return await self._query(cmd)

    # ------------------------------------------------------------------ #
    # Waveform
    # ------------------------------------------------------------------ #
    @staticmethod
    def _parse_preamble(text: str) -> Dict[str, float]:
        parts = [p.strip() for p in text.split(",")]
        if len(parts) < len(PREAMBLE_KEYS):
            raise IOError(f":WAVeform:PREamble? 返回异常: {text!r}")
        out: Dict[str, float] = {}
        for key, val in zip(PREAMBLE_KEYS, parts[:len(PREAMBLE_KEYS)]):
            try:
                out[key] = float(val)
            except ValueError as exc:
                raise IOError(f":WAVeform:PREamble? 字段 {key} 非数值: {val!r}") from exc
        return out

    @staticmethod
    def _to_volts(payload: bytes, fmt: int, pre: Dict[str, float]) -> List[float]:
        """Convert raw waveform bytes to voltages: (raw - yref) * yinc + yorg."""
        if fmt == 2:  # ASCii
            text = payload.decode("ascii", "replace").strip().rstrip(",")
            raw = [float(x) for x in text.split(",") if x.strip()]
        elif fmt == 1:  # WORD — big endian, signed
            usable = len(payload) - (len(payload) % 2)
            raw = list(struct.unpack(f">{usable // 2}h", payload[:usable])) if usable else []
        else:  # BYTE — unsigned
            raw = list(struct.unpack(f">{len(payload)}B", payload)) if payload else []
        yinc = pre["yincrement"]
        yorg = pre["yorigin"]
        yref = pre["yreference"]
        return [(v - yref) * yinc + yorg for v in raw]

    def _blk_read_waveform(
        self, channel: str, mode: str, fmt: str,
        start: Optional[int], stop: Optional[int],
    ) -> Dict[str, Any]:
        self._blk_drain()
        self._blk_write(f":WAVeform:SOURce {channel}\n".encode())
        self._blk_write(f":WAVeform:MODE {mode}\n".encode())
        self._blk_write(f":WAVeform:FORMat {fmt}\n".encode())
        if start is not None:
            self._blk_write(f":WAVeform:STARt {int(start)}\n".encode())
        if stop is not None:
            self._blk_write(f":WAVeform:STOP {int(stop)}\n".encode())

        self._blk_write(b":WAVeform:PREamble?\n")
        pre = self._parse_preamble(self._take_line().decode("utf-8", "replace"))
        self._blk_write(b":WAVeform:DATA?\n")
        payload = self._take_block()
        fmt_code = int(pre["format"])
        volts = self._to_volts(payload, fmt_code, pre)
        return {"preamble": pre, "volts": volts, "raw_bytes": len(payload)}

    async def read_waveform(
        self,
        channel: str = "CHANnel1",
        mode: str = "NORMal",
        fmt: str = "ASCii",
        include_data: bool = False,
        start: Optional[int] = None,
        stop: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Acquire a waveform and return statistics (+ optionally the samples).

        ``volt = (raw - yreference) * yincrement + yorigin``
        """
        if not self._connected:
            raise ConnectionError("RIGOL 示波器未连接")
        result = await self._run(
            self._blk_read_waveform, channel, mode, fmt, start, stop
        )
        pre = result["preamble"]
        volts: List[float] = result["volts"]

        stats: Dict[str, Any] = {
            "status": "ok",
            "channel": channel,
            "mode": mode,
            "format": fmt,
            "points": len(volts),
            "raw_bytes": result["raw_bytes"],
            "xincrement": pre["xincrement"],
            "xorigin": pre["xorigin"],
            "xreference": pre["xreference"],
            "yincrement": pre["yincrement"],
            "yorigin": pre["yorigin"],
            "yreference": pre["yreference"],
        }
        if volts:
            vmax = max(volts)
            vmin = min(volts)
            n = len(volts)
            stats.update({
                "vmax": vmax,
                "vmin": vmin,
                "vpp": vmax - vmin,
                "vavg": sum(volts) / n,
                "vrms": math.sqrt(sum(v * v for v in volts) / n),
                "period_s": round(pre["xincrement"] * n, 12),
                "frequency_hz": (
                    round(1.0 / (pre["xincrement"] * n), 6)
                    if pre["xincrement"] > 0 and n else None
                ),
            })
        if include_data:
            stats["data"] = volts
        return stats

    # ------------------------------------------------------------------ #
    # Screenshot
    # ------------------------------------------------------------------ #
    def _blk_screenshot(self, path: str) -> Dict[str, Any]:
        self._blk_drain()
        self._blk_write(b":DISPlay:DATA?\n")
        payload = self._take_block()
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(payload)
        return {"status": "ok", "path": path, "bytes": len(payload)}

    async def screenshot(self, path: str = "/tmp/aitestlab_rigol/screen.png") -> Dict[str, Any]:
        """Grab the screen as a PNG (``:DISPlay:DATA?``) and save it to ``path``."""
        if not self._connected:
            raise ConnectionError("RIGOL 示波器未连接")
        return await self._run(self._blk_screenshot, path)

    # ------------------------------------------------------------------ #
    # BaseProtocolPlugin interface
    # ------------------------------------------------------------------ #
    async def connect(self, config: dict) -> bool:
        transport = str((config or {}).get("transport") or "tcpip").strip().lower()
        if transport not in TRANSPORTS:
            raise ConnectionError(
                f"不支持的连接方式 {transport!r}，可选: {', '.join(TRANSPORTS)}"
            )
        self._timeout = float((config or {}).get("timeout") or 2.0)
        self._config = dict(config or {})
        self._buf = bytearray()

        try:
            if transport == "tcpip":
                host = config.get("host")
                port = int(config.get("port") or 5555)
                if not host:
                    raise ConnectionError("LAN 连接方式缺少 host")

                def _open_tcp() -> socket.socket:
                    sock = socket.create_connection((host, port), timeout=self._timeout)
                    sock.settimeout(self._timeout)
                    return sock

                self._sock = await self._run(_open_tcp)

            elif transport == "usbtmc":
                device = config.get("device") or "/dev/usbtmc0"
                if not os.path.exists(device):
                    raise ConnectionError(f"USB-TMC 设备不存在: {device}")
                self._fd = await self._run(os.open, device, os.O_RDWR)

            else:
                resource = config.get("resource")
                if not resource:
                    raise ConnectionError("VISA 连接方式缺少 resource")

                def _open_visa():
                    try:
                        import pyvisa  # noqa: PLC0415
                    except ImportError as exc:  # pragma: no cover
                        raise ConnectionError(
                            "未安装 pyvisa，请执行 pip install pyvisa"
                        ) from exc
                    rm = pyvisa.ResourceManager()
                    inst = rm.open_resource(resource)
                    inst.timeout = int(self._timeout * 1000)
                    return inst

                self._visa = await self._run(_open_visa)

            self._transport = transport
            self._connected = True
            self._buf = bytearray()

            # sanity check + auto detect model
            try:
                self._idn = await self._query("*IDN?")
            except Exception as exc:  # pragma: no cover - device quirks
                logger.warning(f"RIGOL *IDN? 查询失败: {exc}")
                self._idn = None
            return True

        except Exception as exc:
            await self._safe_close()
            self._connected = False
            raise ConnectionError(f"连接 RIGOL 示波器失败: {exc}")

    async def _safe_close(self) -> None:
        for closer in (self._close_sock, self._close_fd, self._close_visa):
            try:
                await closer()
            except Exception:  # pragma: no cover
                pass

    async def _close_sock(self) -> None:
        if self._sock is not None:
            sock, self._sock = self._sock, None
            await self._run(sock.close)

    async def _close_fd(self) -> None:
        if self._fd is not None:
            fd, self._fd = self._fd, None
            await self._run(os.close, fd)

    async def _close_visa(self) -> None:
        if self._visa is not None:
            visa, self._visa = self._visa, None
            await self._run(visa.close)

    async def disconnect(self) -> bool:
        await self._safe_close()
        self._connected = False
        self._buf = bytearray()
        return True

    async def send(self, data: Any) -> Any:
        """Send a SCPI command / action.

        ``data`` may be:
          * a raw SCPI string — ``"*IDN?"``, ``":CHANnel1:SCALe 1"``,
          * ``{"command": ":CHANnel1:SCALe", "value": 1}``
          * ``{"command": ":CHANnel1:SCALe?", "query": true}``
          * ``{"action": "waveform", "channel": "CHANnel1"}``
          * ``{"action": "screenshot", "path": "/tmp/s.png"}``
        """
        if not self._connected:
            raise ConnectionError("RIGOL 示波器未连接")

        if isinstance(data, (bytes, bytearray)):
            data = bytes(data).decode("utf-8", "replace")

        if isinstance(data, str):
            cmd = data.strip()
            if not cmd:
                return ""
            if self._is_query(cmd):
                return await self._query(cmd)
            await self._write(cmd)
            return "OK"

        if not isinstance(data, dict):
            raise ValueError(f"无法识别的命令格式: {type(data).__name__}")

        action = str(data.get("action") or "").strip().lower()
        if action == "waveform":
            return await self.read_waveform(
                channel=data.get("channel") or "CHANnel1",
                mode=data.get("mode") or "NORMal",
                fmt=data.get("format") or "ASCii",
                include_data=bool(data.get("include_data")),
                start=data.get("start"),
                stop=data.get("stop"),
            )
        if action in ("screenshot", "screen", "capture"):
            return await self.screenshot(
                data.get("path") or "/tmp/aitestlab_rigol/screen.png"
            )
        if action in ("idn", "identify"):
            return await self._query("*IDN?")
        if action in ("reset", "rst"):
            await self._write("*RST")
            return "OK"
        if action in ("autoscale", "auto"):
            await self._write(":AUToscale")
            return "OK"
        if action in ("run", "start"):
            await self._write(":RUN")
            return "OK"
        if action == "stop":
            await self._write(":STOP")
            return "OK"
        if action == "single":
            await self._write(":SINGle")
            return "OK"
        if action in ("measure", "meas"):
            item = data.get("item") or data.get("type")
            channel = data.get("channel") or data.get("source") or "CHANnel1"
            if not item:
                raise ValueError("measure 动作缺少 item（如 VPP / FREQuency）")
            await self._write(f":MEASure:ITEM {item},{channel}")
            return await self._query(f":MEASure:ITEM? {item},{channel}")
        if action == "error":
            return await self._query(":SYSTem:ERRor?")

        cmd = str(data.get("command") or data.get("scpi") or "").strip()
        if not cmd:
            raise ValueError("命令缺少 command 字段")
        value = data.get("value", data.get("parameter"))
        if value is not None and not self._is_query(cmd):
            cmd = f"{cmd} {value}"
        if data.get("query") or self._is_query(cmd):
            return await self._query(cmd)
        await self._write(cmd)
        return "OK"

    async def receive(self) -> Any:
        """Read unsolicited data (non-blocking); ``None`` when nothing pending."""
        if not self._connected:
            raise ConnectionError("RIGOL 示波器未连接")

        def _blk() -> Optional[str]:
            try:
                if not self._buf:
                    if self._transport == "tcpip":
                        self._sock.settimeout(0.05)
                        try:
                            chunk = self._sock.recv(4096)
                        finally:
                            self._sock.settimeout(self._timeout)
                    elif self._transport == "usbtmc":
                        ready, _, _ = select.select([self._fd], [], [], 0.05)
                        if not ready:
                            return None
                        chunk = os.read(self._fd, 4096)
                    else:
                        return None  # VISA 无可靠的非阻塞读取
                    if not chunk:
                        return None
                    self._buf.extend(chunk)
                line = self._take_line()
            except (BlockingIOError, socket.timeout, TimeoutError):
                return None
            except Exception as exc:
                logger.warning(f"RIGOL receive 失败: {exc}")
                return None
            text = line.decode("utf-8", "replace").strip()
            return text or None

        return await self._run(_blk)

    # ------------------------------------------------------------------ #
    # Metadata for the UI
    # ------------------------------------------------------------------ #
    def get_config_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "transport": {
                    "type": "string",
                    "title": "连接方式",
                    "default": "tcpip",
                    "enum": list(TRANSPORTS),
                    "description": "tcpip=LAN 直连(5555) / usbtmc=USB-TMC 字符设备 / visa=VISA 资源串",
                },
                "host": {
                    "type": "string",
                    "title": "仪器 IP（LAN）",
                    "default": "192.168.1.10",
                    "description": "transport=tcpip 时使用",
                },
                "port": {
                    "type": "integer",
                    "title": "端口（LAN）",
                    "default": 5555,
                    "description": "RIGOL 示波器 SCPI RAW 端口默认 5555",
                },
                "device": {
                    "type": "string",
                    "title": "USB-TMC 设备路径",
                    "default": "/dev/usbtmc0",
                    "description": "transport=usbtmc 时使用",
                },
                "resource": {
                    "type": "string",
                    "title": "VISA 资源串",
                    "default": "USB0::0x1AB1::0x04CE::INSTR",
                    "description": "transport=visa 时使用，需已安装 pyvisa",
                },
                "timeout": {
                    "type": "number",
                    "title": "读取超时（秒）",
                    "default": 2.0,
                    "minimum": 0.2,
                    "maximum": 30,
                },
            },
            "required": ["transport"],
        }

    def get_status(self) -> dict:
        return {
            "name": self.plugin_name,
            "protocol": self.protocol_name,
            "version": self.version,
            "connected": self._connected,
            "transport": self._transport if self._connected else None,
            "idn": self._idn,
            "host": self._config.get("host"),
            "port": self._config.get("port"),
            "device": self._config.get("device"),
            "resource": self._config.get("resource"),
            "timeout": self._timeout,
        }

    def get_device_template(self) -> dict:
        schema = self.get_config_schema()
        defaults = {
            k: v.get("default")
            for k, v in schema["properties"].items()
            if "default" in v
        }
        return {
            "name": "RIGOL 示波器",
            "type": "oscilloscope",
            "protocol": self.protocol_name,
            "connection_type": "lan",
            "config": defaults,
        }

    def get_commands(self) -> List[Dict[str, Any]]:
        """Command descriptors for UI help / auto-completion."""
        return [
            {"name": "*IDN?", "syntax": "*IDN?",
             "description": "识别仪器，返回 厂商,型号,序列号,固件版本", "parameters": []},
            {"name": "*RST", "syntax": "*RST",
             "description": "复位到默认状态", "parameters": []},
            {"name": "*OPC?", "syntax": "*OPC?",
             "description": "操作完成查询，用于同步（返回 1）", "parameters": []},
            {"name": "SYSTem:ERRor?", "syntax": ":SYSTem:ERRor?",
             "description": "读取并清除错误队列，排错首选", "parameters": []},
            {"name": "RUN", "syntax": ":RUN",
             "description": "启动采集", "parameters": []},
            {"name": "STOP", "syntax": ":STOP",
             "description": "停止采集（读 RAW 波形前必须先停止）", "parameters": []},
            {"name": "SINGle", "syntax": ":SINGle",
             "description": "单次触发", "parameters": []},
            {"name": "AUToscale", "syntax": ":AUToscale",
             "description": "自动设置垂直/时基/触发", "parameters": []},
            {"name": "CHANnel<n>:SCALe", "syntax": ":CHANnel<n>:SCALe <scale>",
             "description": "垂直刻度（V/div）；1X 探头 1mV-10V，10X 探头 10mV-100V",
             "parameters": [{"name": "scale", "type": "number"}]},
            {"name": "CHANnel<n>:PROBe", "syntax": ":CHANnel<n>:PROBe <atten>",
             "description": "探头衰减比（1/10/100…）",
             "parameters": [{"name": "atten", "type": "number"}]},
            {"name": "TIMebase:SCALe", "syntax": ":TIMebase[:MAIN]:SCALe <scale>",
             "description": "主时基刻度（s/div）",
             "parameters": [{"name": "scale", "type": "number"}]},
            {"name": "TRIGger:EDGe:LEVel", "syntax": ":TRIGger:EDGe:LEVel <level>",
             "description": "边沿触发电平（V），如 0.16 = 160mV",
             "parameters": [{"name": "level", "type": "number"}]},
            {"name": "TRIGger:SWEep", "syntax": ":TRIGger:SWEep <mode>",
             "description": "触发方式 AUTO|NORMal|SINGle",
             "parameters": [{"name": "mode", "type": "string"}]},
            {"name": "MEASure:ITEM", "syntax": ":MEASure:ITEM <item>,<src>",
             "description": "启用测量项（VPP/VMAX/VMIN/FREQuency/PERiod/RISetime…）",
             "parameters": [{"name": "item", "type": "string"},
                            {"name": "src", "type": "string"}]},
            {"name": "MEASure:ITEM?", "syntax": ":MEASure:ITEM? <item>,<src>",
             "description": "查询测量值，返回科学计数法",
             "parameters": [{"name": "item", "type": "string"},
                            {"name": "src", "type": "string"}]},
            {"name": "WAVeform:PREamble?", "syntax": ":WAVeform:PREamble?",
             "description": "返回 10 个波形参数（含 yincrement/yorigin/yreference）",
             "parameters": []},
            {"name": "WAVeform:DATA?", "syntax": ":WAVeform:DATA?",
             "description": "读取波形（IEEE 明确长度块），建议用 waveform 动作代替",
             "parameters": []},
            {"name": "waveform（动作）",
             "syntax": '{"action":"waveform","channel":"CHANnel1","format":"ASCii"}',
             "description": "插件动作：自动完成 PREamble + DATA 解析，返回 points/vpp/vmax/vmin/vrms",
             "parameters": [{"name": "channel", "type": "string"},
                            {"name": "format", "type": "string"},
                            {"name": "include_data", "type": "boolean"}]},
            {"name": "screenshot（动作）",
             "syntax": '{"action":"screenshot","path":"/tmp/s.png"}',
             "description": "插件动作：:DISPlay:DATA? 抓取屏幕并保存为 PNG",
             "parameters": [{"name": "path", "type": "string"}]},
        ]
