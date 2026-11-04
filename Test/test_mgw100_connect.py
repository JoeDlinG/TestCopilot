#!/usr/bin/env python3
"""Regression guard for the MG100 connection error (and issue #11's bug class).

Why this file exists
--------------------
Closed issue #11 fixed "a plugin hard-codes a POSIX device path as its config
default, so connecting fails with a raw OS error and no guidance" — but **only
in the RIGOL plugin**. Its recommendation #4 ("add a static check over
`backend/plugins/` so new plugins cannot repeat it") was never implemented,
and v0.11.0 later added Ethernet transport to MG100 without checking that the
interface dialog could actually select it. The result: every newly created MG100
device inherited `transport: serial` + `port: /dev/ttyACM0`, and when no
USB-CDC device was attached the connect failed with a bare `[Errno 2]`.

This test pins all three links so it cannot come back:

1. no plugin may expose a hard-coded `/dev/...` or `/tmp/...` as a config
   schema **default** (static AST scan, all plugins, not just MG100);
2. MG100's serial-connect failure must produce an ACTIONABLE error (names the
   port, lists available ports, offers the Ethernet alternative);
3. MG100 over Ethernet must actually connect and round-trip a command against
   a mock TCP server, and `apply_plugin_transport()` must keep the plugin's
   transport/protocol in sync with the chosen interface.

Run without hardware: ``python3 Test/test_mgw100_connect.py``
"""
import ast
import asyncio
import os
import socket
import sys
import threading
from typing import List

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..", "backend")
sys.path.insert(0, BACKEND)

_failures: List[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("  PASS  " if ok else "  FAIL  ") + label + (f"  -> {detail}" if detail else ""))
    if not ok:
        _failures.append(label)


# --------------------------------------------------------------------------- #
# 1. static guard — issue #11 recommendation #4, never implemented before
# --------------------------------------------------------------------------- #
def scan_plugin_defaults() -> List[str]:
    """Find `"/dev/..."` / `"/tmp/..."` used as a config schema default."""
    offenders = []
    plugin_dir = os.path.join(BACKEND, "plugins")
    for name in sorted(os.listdir(plugin_dir)):
        if not name.endswith(".py"):
            continue
        path = os.path.join(plugin_dir, name)
        tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values):
                if not (isinstance(key, ast.Constant) and key.value == "default"):
                    continue
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    literal = value.value
                    if literal.startswith("/dev/") or literal.startswith("/tmp/"):
                        offenders.append(f"{name}:{value.lineno}: default={literal!r}")
    return offenders


def test_static_defaults() -> None:
    offenders = scan_plugin_defaults()
    check("no hard-coded /dev/ or /tmp/ as a plugin config default",
          not offenders, "; ".join(offenders))

    from plugins.mini_gateway100_plugin import MiniGateway100Plugin

    schema = MiniGateway100Plugin().get_config_schema()
    port = schema.get("properties", {}).get("port", {})
    check("MG100 serial port has no persisted default",
          "default" not in port and bool(port.get("placeholder")),
          f"keys={sorted(port)}")


# --------------------------------------------------------------------------- #
# 2. actionable serial error
# --------------------------------------------------------------------------- #
def test_serial_error() -> None:
    from plugins.mini_gateway100_plugin import MiniGateway100Plugin

    plugin = MiniGateway100Plugin()
    missing = "/definitely/not/a/serial/port"
    try:
        asyncio.get_event_loop().run_until_complete(
            plugin.connect({"transport": "serial", "port": missing})
        )
        ok, msg = False, "connect unexpectedly succeeded"
    except ConnectionError as e:
        msg = str(e)
        ok = all(token in msg for token in (missing, "以太网", "串口"))
    except Exception as e:
        ok, msg = False, f"{type(e).__name__}: {e}"
    check("missing serial port gives an actionable error", ok, msg[:220])

    plugin2 = MiniGateway100Plugin()
    try:
        asyncio.get_event_loop().run_until_complete(
            plugin2.connect({"transport": "serial", "port": ""})
        )
        ok2, msg2 = False, "connect unexpectedly succeeded"
    except (ValueError, ConnectionError) as e:
        msg2 = str(e)
        ok2 = "串口" in msg2 and "以太网" in msg2
    except Exception as e:
        ok2, msg2 = False, f"{type(e).__name__}: {e}"
    check("blank serial port is rejected with guidance", ok2, msg2[:160])

    # On Windows "COM3" is not a filesystem path. os.path.exists("COM3") is
    # always False, so the early check must be skipped there — otherwise every
    # Windows serial connection would be rejected as "device file missing".
    from unittest import mock
    import plugins.mini_gateway100_plugin as mg

    plugin3 = mg.MiniGateway100Plugin()
    loop = asyncio.new_event_loop()
    try:
        with mock.patch.object(mg.os, "name", "nt"):
            try:
                loop.run_until_complete(
                    plugin3.connect({"transport": "serial", "port": "COM3"})
                )
                win_ok, win_msg = False, "connect unexpectedly succeeded"
            except ConnectionError as e:
                win_msg = str(e)
                win_ok = "设备文件不存在" not in win_msg and "以太网" in win_msg
            except Exception as e:
                win_ok, win_msg = False, f"{type(e).__name__}: {e}"
    finally:
        loop.close()
    check("Windows COM ports are not rejected by the POSIX file check",
          win_ok, win_msg[:160])


# --------------------------------------------------------------------------- #
# 3. Ethernet path really works (mock TCP server) + interface mapping
# --------------------------------------------------------------------------- #
def start_mock_gateway():
    """A tiny TCP server speaking the MG100 `@11_...;` framing."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    stop = threading.Event()

    def serve():
        srv.settimeout(0.4)
        while not stop.is_set():
            try:
                conn, _ = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with conn:
                conn.settimeout(0.5)
                try:
                    data = conn.recv(4096)
                except socket.timeout:
                    continue
                # Replies are framed as @<ID>_<CMD>=<RESULT>; — the plugin's
                # _parse_response() returns the part after '='.
                if b"HELLO" in data.upper():
                    conn.sendall(b"@11_HELLO=2,11,12;")
                elif b"SYSID" in data.upper():
                    conn.sendall(b"@11_SYSID=MGW100_V1.4.8;")
                else:
                    conn.sendall(b"0;")
        srv.close()

    threading.Thread(target=serve, daemon=True).start()
    return port, stop, srv


def test_ethernet_roundtrip() -> None:
    from plugins.mini_gateway100_plugin import MiniGateway100Plugin

    port, stop, srv = start_mock_gateway()
    plugin = MiniGateway100Plugin()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        connected = loop.run_until_complete(plugin.connect({
            "transport": "ethernet", "host": "127.0.0.1",
            "tcp_port": port, "connect_timeout": 3.0,
        }))
        check("MG100 connects over Ethernet", connected is True)
        if connected:
            result = loop.run_until_complete(plugin.send("@11_HELLO;"))
            text = str(result)
            check("MG100 Ethernet command round-trips", "2,11,12" in text, text[:120])
        loop.run_until_complete(plugin.disconnect())
    finally:
        stop.set()
        try:
            srv.close()
        except OSError:
            pass
        loop.close()
        asyncio.set_event_loop(None)


def test_interface_mapping() -> None:
    from app.core.interfaces import apply_plugin_transport

    eth = apply_plugin_transport(
        "mini_gateway100", "ethernet",
        {"ip_address": "192.168.0.120", "port": 6025},
        {"ip_address": "192.168.0.120", "port": 6025},
        {"transport": "serial", "port": "/dev/ttyACM0", "baudrate": 115200},
    )
    check("interface=ethernet sets transport=ethernet", eth.get("transport") == "ethernet", str(eth))
    check("interface=ethernet carries host/tcp_port",
          eth.get("host") == "192.168.0.120" and eth.get("tcp_port") == 6025, str(eth))
    check("interface=ethernet drops stale serial config",
          "port" not in eth and "baudrate" not in eth, str(eth))

    ser = apply_plugin_transport(
        "mini_gateway100", "serial",
        {"serial_port": "/dev/ttyUSB0"},
        {"serial_port": "/dev/ttyUSB0"},
        {"transport": "ethernet", "host": "192.168.0.120", "tcp_port": 6025},
    )
    check("interface=serial sets transport=serial and the right port",
          ser.get("transport") == "serial" and ser.get("port") == "/dev/ttyUSB0", str(ser))
    check("interface=serial drops stale Ethernet config",
          "host" not in ser and "tcp_port" not in ser, str(ser))


def main() -> int:
    print("=== MG100 connection regression guard ===")
    test_static_defaults()
    test_serial_error()
    test_interface_mapping()
    test_ethernet_roundtrip()
    print()
    if _failures:
        print(f"FAILED ({len(_failures)}): {', '.join(_failures)}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
