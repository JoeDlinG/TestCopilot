"""Self-test for the Modbus TCP plugin.

Runs the driver against a **minimal, independently written** Modbus TCP server
(raw asyncio sockets — deliberately *not* pymodbus) so a bug shared with the
library would still be caught.

Usage::

    python backend/plugins/selftest/modbus_tcp_selftest.py

Exit code 0 = all checks passed, 1 = at least one failure.
"""

from __future__ import annotations

import asyncio
import os
import struct
import sys
import types
from typing import Dict, List, Tuple

# --------------------------------------------------------------------------- #
# Make the plugin importable without the full FastAPI app on the path.
# --------------------------------------------------------------------------- #

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.abspath(os.path.join(_HERE, "..", ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

try:  # normal case: running inside the backend
    from app.services.plugin_service import BaseProtocolPlugin  # noqa: F401
except Exception:  # standalone: inject a minimal stub base class
    stub_pkg = types.ModuleType("app")
    stub_svc = types.ModuleType("app.services")
    stub_ps = types.ModuleType("app.services.plugin_service")

    class BaseProtocolPlugin:  # type: ignore[no-redef]
        plugin_name = "Base Protocol"
        protocol_name = "custom"
        version = "0.1.0"

    stub_ps.BaseProtocolPlugin = BaseProtocolPlugin
    stub_svc.plugin_service = stub_ps
    stub_pkg.services = stub_svc
    sys.modules.setdefault("app", stub_pkg)
    sys.modules.setdefault("app.services", stub_svc)
    sys.modules.setdefault("app.services.plugin_service", stub_ps)

import importlib.util  # noqa: E402

_PLUGIN_PATH = os.path.join(_BACKEND, "plugins", "modbus_tcp_plugin.py")
_spec = importlib.util.spec_from_file_location("modbus_tcp_plugin", _PLUGIN_PATH)
assert _spec and _spec.loader
modbus_tcp_plugin = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(modbus_tcp_plugin)

ModbusTcpProtocolPlugin = modbus_tcp_plugin.ModbusTcpProtocolPlugin

# pymodbus installs its own frame tracer on import. Its ``Log.error`` appends a
# full frame dump whenever DEBUG is *disabled*, so the only way to keep the
# report readable is: enable DEBUG (no dump) + drop the handlers (no output).
import logging  # noqa: E402


def _silence_pymodbus() -> None:
    lg = logging.getLogger("pymodbus.logging")
    lg.setLevel(logging.DEBUG)
    for handler in list(lg.handlers):
        lg.removeHandler(handler)
    lg.addHandler(logging.NullHandler())
    lg.propagate = False


_silence_pymodbus()


# --------------------------------------------------------------------------- #
# Minimal Modbus TCP server (independent implementation)
# --------------------------------------------------------------------------- #

class ModbusMemory:
    def __init__(self) -> None:
        self.coils = [0] * 200
        self.discrete = [0] * 200
        self.holding = [0] * 200
        self.input = [0] * 200

    def region(self, fc: int) -> List[int]:
        return {1: self.coils, 2: self.discrete, 3: self.holding, 4: self.input}[fc]


class MiniModbusServer:
    """Handles FC01/02/03/04/05/06/15/16 with a tiny in-memory register map."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self.host = host
        self.port = port
        self.mem = ModbusMemory()
        self._server = None
        self.no_reply = False  # simulate a dead link when True

    async def start(self) -> int:
        self._server = await asyncio.start_server(self._handle, self.host, self.port)
        self.port = self._server.sockets[0].getsockname()[1]
        return self.port

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while True:
                header = await reader.readexactly(7)
                if self.no_reply:
                    continue  # swallow the request -> client times out
                tid, _pid, length, uid = struct.unpack(">HHHB", header)
                pdu = await reader.readexactly(length - 1)
                resp_pdu = self._process(pdu)
                out = struct.pack(">HHHB", tid, 0, len(resp_pdu) + 1, uid) + resp_pdu
                writer.write(out)
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass
        finally:
            try:
                writer.close()
            except Exception:
                pass

    def _exception(self, fc: int, code: int) -> bytes:
        return bytes([fc | 0x80, code])

    def _process(self, pdu: bytes) -> bytes:
        fc = pdu[0]
        try:
            if fc in (1, 2):
                addr, count = struct.unpack(">HH", pdu[1:5])
                area = self.mem.region(fc)
                if addr + count > len(area):
                    return self._exception(fc, 2)
                bits = area[addr:addr + count]
                packed = bytearray((count + 7) // 8)
                for i, b in enumerate(bits):
                    if b:
                        packed[i // 8] |= 1 << (i % 8)
                return bytes([fc, len(packed)]) + bytes(packed)

            if fc in (3, 4):
                addr, count = struct.unpack(">HH", pdu[1:5])
                area = self.mem.region(fc)
                if addr + count > len(area):
                    return self._exception(fc, 2)
                data = b"".join(struct.pack(">H", v) for v in area[addr:addr + count])
                return bytes([fc, len(data)]) + data

            if fc == 5:
                addr, value = struct.unpack(">HH", pdu[1:5])
                if addr >= len(self.mem.coils):
                    return self._exception(fc, 2)
                self.mem.coils[addr] = 1 if value == 0xFF00 else 0
                return pdu[:5]

            if fc == 6:
                addr, value = struct.unpack(">HH", pdu[1:5])
                if addr >= len(self.mem.holding):
                    return self._exception(fc, 2)
                self.mem.holding[addr] = value
                return pdu[:5]

            if fc == 15:
                addr, qty, byte_count = struct.unpack(">HHB", pdu[1:6])
                if addr + qty > len(self.mem.coils):
                    return self._exception(fc, 2)
                for i in range(qty):
                    byte = pdu[6 + i // 8]
                    self.mem.coils[addr + i] = (byte >> (i % 8)) & 1
                return pdu[:5]

            if fc == 16:
                addr, qty = struct.unpack(">HH", pdu[1:5])
                if addr + qty > len(self.mem.holding):
                    return self._exception(fc, 2)
                for i in range(qty):
                    self.mem.holding[addr + i] = struct.unpack(
                        ">H", pdu[6 + i * 2: 8 + i * 2]
                    )[0]
                return pdu[:5]

            return self._exception(fc, 1)
        except Exception:
            return self._exception(fc, 4)


# --------------------------------------------------------------------------- #
# Checks
# --------------------------------------------------------------------------- #

class Checker:
    def __init__(self) -> None:
        self.results: List[Tuple[str, bool, str]] = []

    def record(self, name: str, ok: bool, detail: str = "") -> None:
        self.results.append((name, ok, detail))
        flag = "PASS" if ok else "FAIL"
        print(f"  [{flag}] {name}" + (f" — {detail}" if detail else ""))

    def expect(self, name: str, actual, expected) -> None:
        self.record(name, actual == expected, f"得到 {actual!r}，期望 {expected!r}")

    @property
    def failed(self) -> int:
        return sum(1 for _, ok, _ in self.results if not ok)


async def run_checks() -> int:
    server = MiniModbusServer()
    port = await server.start()
    print(f"最小 Modbus TCP 从站已启动：127.0.0.1:{port}\n")

    checker = Checker()
    plugin = ModbusTcpProtocolPlugin()

    try:
        # ---- V1 connect -------------------------------------------------- #
        ok = await plugin.connect({"host": "127.0.0.1", "port": port, "slave_id": 1, "timeout": 2.0})
        checker.record("V1 连接设备", ok is True and plugin.get_status()["connected"])

        # ---- V2 read holding registers ----------------------------------- #
        server.mem.holding[10] = 17000
        server.mem.holding[11] = 0
        checker.expect(
            "V2 FC03 读保持寄存器（裸地址）",
            await plugin.send("FC03:10:2"),
            "17000,0",
        )
        checker.expect(
            "V2b FC03 读保持寄存器（40011 引用地址 → 10）",
            await plugin.send("FC03:40011:2"),
            "17000,0",
        )
        checker.expect(
            "V2c FC03 单寄存器读（标量）",
            await plugin.send("FC03:10:1"),
            "17000",
        )

        # ---- V3 write single register + read back ------------------------ #
        ack = await plugin.send("FC06:20:1234")
        checker.record("V3 FC06 写单个寄存器", ack == "OK", f"返回 {ack!r}")
        checker.expect("V3b 写后读回一致", await plugin.send("FC03:20:1"), "1234")

        # ---- V4 float32 word order --------------------------------------- #
        # 1.5f = 0x3FC00000 -> registers big/big = [0x3FC0, 0x0000]
        server.mem.holding[30] = 0x3FC0
        server.mem.holding[31] = 0x0000
        big = await plugin.send({"fc": 3, "addr": 30, "count": 2, "dtype": "float32"})
        checker.expect("V4 float32 字序 big", big, "1.5")

        # Same bytes, but registers swapped -> device using little word order
        server.mem.holding[32] = 0x0000
        server.mem.holding[33] = 0x3FC0
        little = await plugin.send(
            {"fc": 3, "addr": 32, "count": 2, "dtype": "float32", "word_order": "little"}
        )
        checker.expect("V4b float32 字序 little", little, "1.5")
        wrong = await plugin.send({"fc": 3, "addr": 32, "count": 2, "dtype": "float32"})
        checker.record("V4c 字序开关确实改变结果", wrong != "1.5", f"错误字序得到 {wrong!r}")

        # ---- V5 coils ----------------------------------------------------- #
        server.mem.coils[0] = 0
        checker.expect("V5 FC01 读线圈（00001 → 0）", await plugin.send("FC01:00001:4"), "0,0,0,0")
        ack = await plugin.send("FC05:00003:1")
        checker.record("V5b FC05 写线圈", ack == "OK", f"返回 {ack!r}")
        checker.expect("V5c 线圈写后读回", await plugin.send("FC01:00001:4"), "0,0,1,0")

        # ---- V6 error + timeout ------------------------------------------ #
        err = await plugin.send("FC03:99999:1")
        checker.record(
            "V6 非法地址返回 ERROR 且不断开",
            err.startswith("ERROR:") and "ILLEGAL_DATA_ADDRESS" in err,
            f"返回 {err!r}",
        )
        checker.record(
            "V6b 设备异常后连接仍然健康",
            plugin.get_status()["connected"] is True,
        )

        # typed response format
        typed = await plugin.send(
            {"fc": 3, "addr": 10, "count": 2, "dtype": "uint16", "response_format": "typed"}
        )
        checker.record(
            "V6c response_format 切换（P0-1 预留）",
            isinstance(typed, dict) and typed.get("kind") in ("regs", "scalar"),
            f"kind={typed.get('kind') if isinstance(typed, dict) else type(typed)}",
        )

        await plugin.disconnect()

        # ---- timeout / dead link ------------------------------------------ #
        server.no_reply = True
        plugin2 = ModbusTcpProtocolPlugin()
        await plugin2.connect({"host": "127.0.0.1", "port": port, "timeout": 0.5})
        try:
            await plugin2.send("FC03:10:1")
            checker.record("V7 无响应时抛 ConnectionError", False, "未抛异常")
        except ConnectionError as exc:
            checker.record("V7 无响应时抛 ConnectionError", True, str(exc)[:60])
        except Exception as exc:
            checker.record("V7 无响应时抛 ConnectionError", False, f"抛了 {type(exc).__name__}: {exc}")
        await plugin2.disconnect()
        server.no_reply = False

        # ---- malformed command -------------------------------------------- #
        plugin3 = ModbusTcpProtocolPlugin()
        await plugin3.connect({"host": "127.0.0.1", "port": port})
        for bad in ("FC99:1:1", "FC03", "", "hello:1:1"):
            try:
                await plugin3.send(bad)
                checker.record(f"V8 非法命令被拒绝: {bad!r}", False, "未抛异常")
            except ValueError:
                checker.record(f"V8 非法命令被拒绝: {bad!r}", True)
            except Exception as exc:
                checker.record(
                    f"V8 非法命令被拒绝: {bad!r}", False, f"抛了 {type(exc).__name__}"
                )
        await plugin3.disconnect()

    finally:
        await server.stop()

    passed = len(checker.results) - checker.failed
    print(f"\n合计 {len(checker.results)} 项：通过 {passed}，失败 {checker.failed}")
    return 1 if checker.failed else 0


def main() -> int:
    if modbus_tcp_plugin.AsyncModbusTcpClient is None:
        print("跳过：未安装 pymodbus（pip install pymodbus==3.16.1）")
        return 2
    return asyncio.run(run_checks())


if __name__ == "__main__":
    sys.exit(main())
