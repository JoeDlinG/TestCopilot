#!/usr/bin/env python3
"""Guards for Issues #30 and #32.

#30: Windows must not enter the Linux-only libusb path, and choosing the USB
     interface must preserve the user's COM3 instead of forcing raw USB.
#32: one protocol registry, an explicit @babel/parser dependency, a cached
     project listing and no Linux udev scripts in the Windows package.

Run: ``python3 Test/test_regression_guards.py``
"""
import asyncio
import importlib.util
import json
import os
import sys
from unittest import mock
from typing import List

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND)

from app.core.interfaces import (  # noqa: E402
    STANDARD_PROTOCOLS, apply_plugin_transport,
)
import app.core.interfaces as itf  # noqa: E402
from app.services import device_service as ds  # noqa: E402
from app.services import project_service as ps  # noqa: E402

_failures: List[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("  PASS  " if ok else "  FAIL  ") + label + (f"  -> {detail}" if detail else ""))
    if not ok:
        _failures.append(label)


def text(path: str) -> str:
    return open(os.path.join(ROOT, path), encoding="utf-8").read()


def load_mg100():
    spec = importlib.util.spec_from_file_location(
        "mg100_under_test",
        os.path.join(BACKEND, "plugins", "mini_gateway100_plugin.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def protocol_registry_checks() -> None:
    """#32.1 — the two copies must really be the same object."""
    check("service aliases the single registry",
          ds._STANDARD_PROTOCOLS is STANDARD_PROTOCOLS)
    check("pcie/pxi are standard protocols",
          {"pcie", "pxi"} <= set(STANDARD_PROTOCOLS))
    api = text("backend/app/api/devices.py")
    check("API has no second hand-maintained set",
          "_STANDARD_PROTOCOLS = {" not in api)
    check("API imports the shared constant",
          "STANDARD_PROTOCOLS" in api
          and "plugin_protocol in STANDARD_PROTOCOLS" in api)


def build_and_project_checks() -> None:
    """#32.2 / #32.3 — declared build dependency and cheap project listing."""
    pkg = json.loads(text("frontend/package.json"))
    lock = json.loads(text("frontend/package-lock.json"))
    check("@babel/parser declared in devDependencies",
          "@babel/parser" in pkg.get("devDependencies", {}))
    check("@babel/parser declared in lockfile root",
          "@babel/parser" in lock["packages"][""].get("devDependencies", {}))
    check("i18n-guard really imports it",
          "@babel/parser" in text("frontend/scripts/i18n-guard.mjs"))

    check("project listing has a metadata cache",
          "_PROJECT_META_CACHE" in text("backend/app/services/project_service.py"))
    real_loads = ps.json.loads
    calls = []

    def counting(*args, **kwargs):
        calls.append(1)
        return real_loads(*args, **kwargs)

    with mock.patch.object(ps.json, "loads", counting):
        first = ps.list_projects()
        n1 = len(calls)
        second = ps.list_projects()
        n2 = len(calls)
    check("second list_projects() does not re-parse bundles", n2 == n1,
          f"parses {n1} -> {n2}")
    check("list_projects() returned entries", isinstance(first, list)
          and first == second)

    check("1MB demo bundle no longer sits in the project list",
          not os.path.isfile(os.path.join(BACKEND, "projects", "Project_TestDemo.json")))
    check("demo bundle kept as a test fixture",
          os.path.isfile(os.path.join(ROOT, "Test", "fixtures", "Project_TestDemo.json")))
    check("exported workspaces are gitignored",
          "backend/projects/Project_*.json" in text(".gitignore"))


def windows_checks() -> None:
    """#30 + #32.4 — Windows paths and packaging."""
    # Interface binding: COM3 must survive on Windows.
    stored = {"transport": "usb", "port": "/dev/ttyACM0", "baudrate": 115200}
    with mock.patch.object(itf.os, "name", "nt"):
        win = apply_plugin_transport(
            "mini_gateway100", "usb", {"serial_port": "COM3"},
            {"serial_port": "COM3"}, dict(stored),
        )
    check("Windows USB uses serial transport", win["transport"] == "serial", str(win))
    check("Windows USB keeps COM3 in config.port", win.get("port") == "COM3", str(win))
    check("Windows USB keeps baudrate", win.get("baudrate") == 115200, str(win))

    with mock.patch.object(itf.os, "name", "posix"):
        posix = apply_plugin_transport(
            "mini_gateway100", "usb", {"serial_port": "/dev/ttyACM0"},
            {}, dict(stored),
        )
    check("POSIX USB keeps raw bulk transport",
          posix["transport"] == "usb" and "port" not in posix, str(posix))

    mod = load_mg100()
    P = mod.MiniGateway100Plugin
    inst = P()

    with mock.patch.object(mod.os, "name", "nt"):
        try:
            asyncio.run(inst._connect_usb({}))
            raised = False
            msg = ""
        except ConnectionError as e:
            raised = True
            msg = str(e)
        check("Windows _connect_usb fails fast with an actionable message",
              raised and "COM3" in msg and "sudo bash" not in msg, msg[:120])
        check("Windows permission hint has no udev/sudo",
              "sudo bash" not in P._usb_permission_hint(0x0483, 0x5740))
        check("Windows USB probe disabled",
              P._usb_device_present({}) is False)

    plugin_src = text("backend/plugins/mini_gateway100_plugin.py")
    check("NoBackendError is handled", "NoBackendError" in plugin_src
          and "_usb_backend_hint" in plugin_src)
    check("kernel-driver API guarded by platform",
          'if os.name != "nt"' in plugin_src
          and "is_kernel_driver_active" in plugin_src)

    spec = text("backend/aitestlab.spec")
    check("Windows build excludes Linux install scripts",
          'sys.platform != "win32"' in spec
          and 'datas.append((os.path.join(backend_dir, "install"), "install"))' in spec)
    check("platform-specific installer hint", "install_script" in
          text("backend/plugins/peakcan_plugin.py")
          and "None if self._is_windows()" in text("backend/plugins/peakcan_plugin.py"))


def pcan_reset_guard() -> None:
    """Regression: connect must never reconfigure an already-UP CAN interface.

    A CAN link's operstate is always ``unknown`` (no carrier), so the old
    ``operstate == "up"`` check re-ran ``ip link set … up type can bitrate …``
    on every connect, resetting the controller and dropping the bus. It must
    use the IFF_UP flag instead.
    """
    src = text("backend/plugins/peakcan_plugin.py")
    check("IFF_UP helper exists", 'def _iface_up(' in src
          and "/flags" in src and "0x1" in src)
    check("_ensure_socketcan_ready uses IFF_UP, not operstate==",
          "cls._iface_up(ch)" in src
          and '_operstate(ch) == "up"' not in src)


def main() -> int:
    protocol_registry_checks()
    build_and_project_checks()
    windows_checks()
    pcan_reset_guard()
    if _failures:
        print(f"\nFAILED: {len(_failures)} check(s): {', '.join(_failures)}")
        return 1
    print("\nAll #30/#32 regression guards passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
