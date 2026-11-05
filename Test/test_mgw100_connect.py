#!/usr/bin/env python3
"""Regression guard for the MG100 USB connection (no Ethernet involved).

Why this file exists
--------------------
The MG100 is connected over USB. On hosts where the kernel's ``cdc_acm``
driver is not bound (Jetson / embedded kernels, or after a hot replug) there is
NO ``/dev/ttyACM*`` node at all: `lsusb` sees `0483:5740`, pyserial sees zero
ports, and the app fails with a bare `[Errno 2]`. Two past bugs made that
unfixable:

  * issue #11's "hard-coded /dev/ default" fix was applied to only one plugin
    and never guarded, so every new MG100 device inherited `/dev/ttyACM0`;
  * the plugin had no way to reach the device without a kernel tty node.

Now the plugin has a `transport=usb` path (libusb bulk endpoints on the CDC
Data interface) and automatically falls back to it when the serial node is
missing but the USB device is present. A udev rule shipped in
`backend/install/` grants access and re-binds cdc_acm.

Tests use a simulated libusb device, so they need neither root nor hardware.

Run: ``python3 Test/test_mgw100_connect.py``
"""
import ast
import asyncio
import os
import sys
import types
from typing import List
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..", "backend")
sys.path.insert(0, BACKEND)

_failures: List[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("  PASS  " if ok else "  FAIL  ") + label + (f"  -> {detail}" if detail else ""))
    if not ok:
        _failures.append(label)


# --------------------------------------------------------------------------- #
# fake `usb` package — behaves like the MG100 CDC Data interface
# --------------------------------------------------------------------------- #
class _USBTimeoutError(Exception):
    pass


class _USBError(Exception):
    def __init__(self, msg, errno=None):
        super().__init__(msg)
        self.errno = errno


class FakeUSBDevice:
    """Responds to `@11_HELLO;` only AFTER the request is written."""

    def __init__(self, permission_denied=False):
        self.permission_denied = permission_denied
        self.inbox = []
        self.written = []
        outer = self

        class EP:
            def __init__(self, addr):
                self.bEndpointAddress = addr
                self.bmAttributes = 2  # bulk

            def write(inner, data, timeout=None):
                outer.written.append(bytes(data))
                if b"HELLO" in data.upper():
                    outer.inbox.append(b"@11_HELLO=2,11,12;")
                return len(data)

            def read(inner, size, timeout=None):
                if outer.inbox:
                    return outer.inbox.pop(0)
                raise _USBTimeoutError()

        self.ep_out, self.ep_in = EP(0x01), EP(0x81)

        class Interface:
            bInterfaceNumber = 1
            bInterfaceClass = 0x0A

            def endpoints(inner):
                return [outer.ep_out, outer.ep_in]

        class Config:
            def __iter__(inner):
                return iter([Interface()])

        self.config = Config()

    def get_active_configuration(self):
        if self.permission_denied:
            raise _USBError("[Errno 13] Access denied (insufficient permissions)", 13)
        return self.config

    def is_kernel_driver_active(self, n):
        return False


def fake_usb_modules(device):
    core = types.ModuleType("usb.core")
    util = types.ModuleType("usb.util")
    pkg = types.ModuleType("usb")
    pkg.core, pkg.util = core, util

    core.USBTimeoutError = _USBTimeoutError
    core.USBError = _USBError
    core.find = lambda **kwargs: device
    util.ENDPOINT_IN, util.ENDPOINT_OUT, util.ENDPOINT_TYPE_BULK = 0x80, 0x00, 2
    util.endpoint_direction = lambda addr: 0x80 if addr & 0x80 else 0x00
    util.endpoint_type = lambda attr: attr & 0x03
    util.claim_interface = lambda dev, n: None
    util.release_interface = lambda dev, n: None
    util.dispose_resources = lambda dev: None
    util.find_descriptor = lambda intf, custom_match: next(
        (e for e in intf.endpoints() if custom_match(e)), None
    )
    return {"usb": pkg, "usb.core": core, "usb.util": util}


def new_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop


# --------------------------------------------------------------------------- #
# 1. static guard — issue #11 recommendation #4, never implemented before
# --------------------------------------------------------------------------- #
def test_static_defaults() -> None:
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
                    if value.value.startswith("/dev/") or value.value.startswith("/tmp/"):
                        offenders.append(f"{name}:{value.lineno}: {value.value!r}")
    check("no hard-coded /dev/ or /tmp/ as a plugin config default",
          not offenders, "; ".join(offenders))

    from plugins.mini_gateway100_plugin import MiniGateway100Plugin

    schema = MiniGateway100Plugin().get_config_schema()
    port = schema.get("properties", {}).get("port", {})
    check("MG100 serial port has no persisted default",
          "default" not in port and bool(port.get("placeholder")), f"keys={sorted(port)}")
    check("usb transport is offered in the schema",
          "usb" in schema["properties"]["transport"].get("enum", []))


# --------------------------------------------------------------------------- #
# 2. serial-path errors when there is no USB device to fall back to
# --------------------------------------------------------------------------- #
def test_serial_errors(loop) -> None:
    import plugins.mini_gateway100_plugin as mg

    # Force "no USB device present" so the serial branch is exercised directly.
    with mock.patch.object(mg.MiniGateway100Plugin, "_usb_device_present", return_value=False):
        plugin = mg.MiniGateway100Plugin()
        try:
            loop.run_until_complete(
                plugin.connect({"transport": "serial", "port": "/definitely/not/a/serial/port"})
            )
            ok, msg = False, "connect unexpectedly succeeded"
        except ConnectionError as e:
            msg = str(e)
            ok = all(t in msg for t in ("/definitely/not/a/serial/port", "串口", "以太网"))
        except Exception as e:
            ok, msg = False, f"{type(e).__name__}: {e}"
        check("missing serial node gives an actionable error", ok, msg[:180])

        plugin2 = mg.MiniGateway100Plugin()
        try:
            loop.run_until_complete(plugin2.connect({"transport": "serial", "port": ""}))
            ok2, msg2 = False, "connect unexpectedly succeeded"
        except (ValueError, ConnectionError) as e:
            msg2 = str(e)
            ok2 = "串口" in msg2 and "以太网" in msg2
        except Exception as e:
            ok2, msg2 = False, f"{type(e).__name__}: {e}"
        check("blank serial port is rejected with guidance", ok2, msg2[:140])

        # Windows COM names are not filesystem paths: the POSIX existence check
        # must be skipped, otherwise every Windows serial connect would fail.
        fake_serial = types.ModuleType("serial")

        class SerialException(Exception):
            pass

        def Serial(**kwargs):
            raise SerialException(f"could not open port {kwargs.get('port')}")

        fake_serial.SerialException = SerialException
        fake_serial.Serial = Serial
        fake_serial.EIGHTBITS, fake_serial.PARITY_NONE, fake_serial.STOPBITS_ONE = 8, "N", 1
        plugin3 = mg.MiniGateway100Plugin()
        with mock.patch.object(mg.os, "name", "nt"), \
                mock.patch.dict(sys.modules, {"serial": fake_serial}):
            try:
                loop.run_until_complete(plugin3.connect({"transport": "serial", "port": "COM3"}))
                win_ok, win_msg = False, "connect unexpectedly succeeded"
            except ConnectionError as e:
                win_msg = str(e)
                win_ok = "设备文件不存在" not in win_msg and "以太网" in win_msg
            except Exception as e:
                win_ok, win_msg = False, f"{type(e).__name__}: {e}"
        check("Windows COM ports skip the POSIX file check", win_ok, win_msg[:140])


# --------------------------------------------------------------------------- #
# 3. USB-native transport — the actual fix for "USB plugged in but no tty"
# --------------------------------------------------------------------------- #
def test_usb_transport(loop) -> None:
    import plugins.mini_gateway100_plugin as mg

    dev = FakeUSBDevice()
    modules = fake_usb_modules(dev)
    with mock.patch.dict(sys.modules, modules):
        plugin = mg.MiniGateway100Plugin()
        ok = loop.run_until_complete(plugin.connect({
            "transport": "usb", "usb_vid": "0483", "usb_pid": "5740",
        }))
        check("USB 原生传输 connect", ok is True)
        check("USB VID/PID 按十六进制解析",
              plugin._usb_ids({"usb_vid": "0483", "usb_pid": "5740"}) == (0x0483, 0x5740))
        result = loop.run_until_complete(plugin.send("@11_HELLO;"))
        check("USB 原生传输指令往返", "2,11,12" in str(result), str(result))
        check("USB 写出了完整帧",
              bool(dev.written) and dev.written[0].startswith(b"@11_HELLO;"),
              str(dev.written[:1]))
        loop.run_until_complete(plugin.disconnect())

    # The real-world case: config still says serial + /dev/ttyACM0, no such
    # node, but the MG100 is on USB -> must auto-switch and work.
    dev2 = FakeUSBDevice()
    modules2 = fake_usb_modules(dev2)
    with mock.patch.dict(sys.modules, modules2):
        plugin2 = mg.MiniGateway100Plugin()
        ok2 = loop.run_until_complete(plugin2.connect({
            "transport": "serial", "port": "/dev/ttyACM0",
        }))
        check("串口节点缺失时自动切到 USB", ok2 is True and plugin2._transport == "usb",
              str(plugin2._transport))
        result2 = loop.run_until_complete(plugin2.send("@11_HELLO;"))
        check("自动回退后指令仍可收发", "2,11,12" in str(result2), str(result2))
        loop.run_until_complete(plugin2.disconnect())

    # Permission denied -> point at the shipped udev installer.
    dev3 = FakeUSBDevice(permission_denied=True)
    modules3 = fake_usb_modules(dev3)
    with mock.patch.dict(sys.modules, modules3):
        plugin3 = mg.MiniGateway100Plugin()
        try:
            loop.run_until_complete(plugin3.connect({"transport": "usb"}))
            hint_ok, hint = False, "connect unexpectedly succeeded"
        except ConnectionError as e:
            hint = str(e)
            hint_ok = "install_usb_rules.sh" in hint and "权限" in hint
        except Exception as e:
            hint_ok, hint = False, f"{type(e).__name__}: {e}"
    check("USB 权限不足时指向 udev 安装脚本", hint_ok, hint[:160])


def test_udev_rule() -> None:
    rule = os.path.join(BACKEND, "install", "99-mg100-usb.rules")
    text = open(rule, encoding="utf-8").read() if os.path.isfile(rule) else ""
    check("udev 规则授予 USB 访问权限",
          'ATTR{idVendor}=="0483"' in text and 'MODE="0664"' in text)
    check("udev 规则触发 cdc_acm 绑定", "cdc_acm/new_id" in text)
    installer = os.path.join(BACKEND, "install", "install_usb_rules.sh")
    check("安装脚本存在且可执行提示正确",
          os.path.isfile(installer) and "udevadm control --reload-rules" in
          open(installer, encoding="utf-8").read())


# --------------------------------------------------------------------------- #
# 4. interface <-> transport mapping (config dialog must stay in sync)
# --------------------------------------------------------------------------- #
def test_interface_mapping() -> None:
    from app.core.interfaces import apply_plugin_transport

    ser = apply_plugin_transport(
        "mini_gateway100", "usb", {}, {},
        {"transport": "serial", "port": "/dev/ttyACM0", "baudrate": 115200},
    )
    check("USB 接口映射到 transport=usb", ser.get("transport") == "usb", str(ser))
    check("USB 接口清掉旧串口路径", "port" not in ser, str(ser))

    serial = apply_plugin_transport(
        "mini_gateway100", "serial", {"serial_port": "/dev/ttyUSB0"},
        {"serial_port": "/dev/ttyUSB0"}, {"transport": "usb"},
    )
    check("串口接口映射回 transport=serial 且带正确端口",
          serial.get("transport") == "serial" and serial.get("port") == "/dev/ttyUSB0",
          str(serial))


def main() -> int:
    print("=== MG100 USB connection regression guard ===")
    loop = new_loop()
    try:
        test_static_defaults()
        test_serial_errors(loop)
        test_usb_transport(loop)
        test_udev_rule()
        test_interface_mapping()
    finally:
        loop.close()
        asyncio.set_event_loop(None)
    print()
    if _failures:
        print(f"FAILED ({len(_failures)}): {', '.join(_failures)}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
