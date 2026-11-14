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
import tempfile
import time
import types
from pathlib import Path
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

    # The old guard was an empty assertion: the real projects dir only had a
    # .gitkeep, so "parses 0 -> 0" was trivially true. Build a genuine bundle
    # in a temp dir so the cache is actually exercised (issue #32 review #1).
    with tempfile.TemporaryDirectory() as td:
        project_dir = Path(td)
        bundle = {
            "schema": ps.SCHEMA,
            "project_name": "CacheGuard",
            "app_version": "test",
            # Deliberately NO "counts": exercise the fallback as well.
            "data": {"devices": [{"id": "d1"}], "test_cases": [],
                     "models": [{"id": "m1"}, {"id": "m2"}]},
        }
        bundle_path = project_dir / "Project_CacheGuard.json"
        bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
        changed = json.dumps({**bundle, "project_name": "CacheGuardUpdated"})

        real_loads = ps.json.loads
        calls = []

        def counting(*args, **kwargs):
            calls.append(1)
            return real_loads(*args, **kwargs)

        with mock.patch.object(ps, "PROJECTS_DIR", project_dir), \
                mock.patch.object(ps.json, "loads", counting):
            ps._PROJECT_META_CACHE.clear()
            first = ps.list_projects()
            n1 = len(calls)
            second = ps.list_projects()
            n2 = len(calls)
            check("cache guard parses a real bundle", n1 == 1, f"parses {n1}")
            check("second list_projects() does not re-parse bundles",
                  n2 == n1, f"parses {n1} -> {n2}")
            check("list_projects() returned a non-empty entry",
                  len(first) == 1 and first == second, str(len(first)))
            check("counts recomputed when the header is missing",
                  first[0]["counts"] == {"devices": 1, "test_cases": 0,
                                         "models": 2}, str(first[0]["counts"]))

            bundle_path.write_text(changed, encoding="utf-8")
            later = time.time() + 5
            os.utime(str(bundle_path), (later, later))
            third = ps.list_projects()
            check("changed bundle is re-parsed", len(calls) > n2,
                  f"parses {n2} -> {len(calls)}")
            check("updated header metadata is visible",
                  third[0]["project_name"] == "CacheGuardUpdated",
                  str(third[0]["project_name"]))

            bundle_path.unlink()
            ps.list_projects()
            check("deleted bundle is evicted from the cache",
                  str(bundle_path) not in ps._PROJECT_META_CACHE,
                  str(list(ps._PROJECT_META_CACHE)))
        ps._PROJECT_META_CACHE.clear()

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

    # Upgrade compatibility: a v2.3.4/2.3.5 row saved with transport=usb on
    # Windows must connect via the CDC COM port without a manual re-edit.
    with mock.patch.object(mod.os, "name", "nt"):
        legacy = P()
        with mock.patch.object(legacy, "_connect_serial",
                               new=mock.AsyncMock(return_value=None)):
            legacy_ok = asyncio.run(legacy.connect(
                {"transport": "usb", "serial_port": "COM7"}))
        check("legacy Windows transport=usb downgrades to serial",
              legacy_ok is True and legacy._transport == "serial"
              and legacy._config.get("port") == "COM7"
              and legacy._config.get("transport") == "serial",
              f"{legacy._transport} / {legacy._config}")

    # Behavioural assertion (not a string scan): pyusb's NoBackendError must be
    # translated into an actionable ConnectionError with the libusb hint.
    usb_pkg = types.ModuleType("usb")
    usb_core = types.ModuleType("usb.core")
    usb_util = types.ModuleType("usb.util")

    class _NoBackendError(ValueError):
        pass

    class _USBError(IOError):
        pass

    def _find(**kwargs):
        raise _NoBackendError("No backend available")

    usb_core.NoBackendError = _NoBackendError
    usb_core.USBError = _USBError
    usb_core.find = _find
    usb_pkg.core, usb_pkg.util = usb_core, usb_util
    with mock.patch.dict(sys.modules, {"usb": usb_pkg, "usb.core": usb_core,
                                       "usb.util": usb_util}), \
            mock.patch.object(mod.os, "name", "posix"):
        try:
            asyncio.run(P()._connect_usb({}))
            nb_raised, nb_msg = False, "connect unexpectedly succeeded"
        except ConnectionError as e:
            nb_raised, nb_msg = True, str(e)
        except Exception as e:  # noqa: BLE001 - report the real failure type
            nb_raised, nb_msg = False, f"{type(e).__name__}: {e}"
    check("NoBackendError becomes an actionable ConnectionError",
          nb_raised and "libusb" in nb_msg, nb_msg[:160])

    plugin_src = text("backend/plugins/mini_gateway100_plugin.py")
    check("NoBackendError branch exists", "NoBackendError" in plugin_src
          and "_usb_backend_hint" in plugin_src)
    check("Windows legacy usb downgrade is implemented",
          'os.name == "nt" and transport == "usb"' in plugin_src)
    check("Windows build drops the unused libusb hidden import",
          'if sys.platform != "win32":' in text("backend/aitestlab.spec")
          and 'hiddenimports += ["usb.backend.libusb1"]' in text("backend/aitestlab.spec"))
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
