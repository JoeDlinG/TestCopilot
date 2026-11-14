#!/usr/bin/env python3
"""Regression guard for PCAN-USB ("DEV-002 cannot connect, even after replug").

The adapter was visible on USB (0c72:0012) while ``peak_usb`` was not loaded
and no ``can*`` interface existed. Replugging cannot fix that: loading a kernel
module and bringing a CAN link UP both need root. The plugin now prepares the
interface best-effort at connect time, and a udev rule + installer shipped in
``backend/install`` does it as root at plug-in time.

All system calls are mocked — no hardware, no root, no kernel changes.

Run: ``python3 Test/test_peakcan_prepare.py``
"""
import importlib.util
import os
import sys
from typing import List
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..", "backend")
sys.path.insert(0, BACKEND)

_spec = importlib.util.spec_from_file_location(
    "peakcan_plugin_under_test", os.path.join(BACKEND, "plugins", "peakcan_plugin.py")
)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)
P = mod.PeakCANPlugin

_failures: List[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("  PASS  " if ok else "  FAIL  ") + label + (f"  -> {detail}" if detail else ""))
    if not ok:
        _failures.append(label)


def proc(rc: int = 0, err: str = ""):
    return mock.Mock(returncode=rc, stderr=err, stdout="")


def base_patches(channels, up=False, run_result=None):
    """Common environment: Linux, given can* interfaces and IFF_UP flag."""
    return (
        mock.patch.object(P, "_is_windows", return_value=False),
        mock.patch.object(P, "_socketcan_channels", return_value=channels),
        mock.patch.object(P, "_iface_up", return_value=up),
        mock.patch.object(mod.subprocess, "run", return_value=run_result or proc()),
        mock.patch.object(mod.time, "sleep", return_value=None),
    )


def main() -> int:
    # 1. Existing but DOWN can0 must be configured and brought UP.
    a, b, c, d, e = base_patches(["can0"], up=False)
    with a, b, c, d as run, e:
        notes = P._ensure_socketcan_ready(500000)
    args = run.call_args[0][0] if run.call_args else []
    check("DOWN can0 brought up", any("can0" in str(x) for x in args)
          and "bitrate" in args and "500000" in args, str(args))
    check("setup result reported", any("up @" in n for n in notes), str(notes))

    # 1b. An already-UP can0 must be left untouched. This is the regression
    #     guard: re-applying `ip link set up type can bitrate` resets the
    #     controller and dropped the bus on every re-connect.
    a, b, c, d, e = base_patches(["can0"], up=True)
    with a, b, c, d as run, e:
        notes = P._ensure_socketcan_ready(500000)
    check("already-UP can0 is not reconfigured", run.call_count == 0,
          f"ip link set ran {run.call_count} time(s): {run.call_args_list}")

    # 2. Configured bitrate is honoured instead of a hard-coded default.
    a, b, c, d, e = base_patches(["can0"], up=False)
    with a, b, c, d as run, e:
        P._ensure_socketcan_ready(250000)
    args = run.call_args[0][0]
    check("configured bitrate used", "250000" in args, str(args))

    # 3. No can* interface -> load the kernel module, then re-scan.
    a, b, c, d, e = base_patches([], up=True)
    with a, b, c, d as run, e:
        b_mod = mock.patch.object(P, "_socketcan_channels",
                                  side_effect=[[], ["can0"]])
        with b_mod:
            notes = P._ensure_socketcan_ready(500000)
    check("peak_usb loaded when no can* exists",
          any("peak_usb" in str(call[0][0]) for call in run.call_args_list),
          str(run.call_args_list))
    check("new interface detected after modprobe",
          any("loaded" in n or "up @" in n or n == "" for n in notes), str(notes))

    # 4. Insufficient privileges must be reported, never raised.
    a, b, c, d, e = base_patches([], up=False,
                                 run_result=proc(1, "Operation not permitted"))
    with a, b, c, d, e:
        b_mod = mock.patch.object(P, "_socketcan_channels", return_value=["can0"])
        with b_mod:
            notes = P._ensure_socketcan_ready(500000)
    check("permission failure is non-fatal", isinstance(notes, list) and len(notes) > 0,
          str(notes))
    check("permission failure explained",
          any("not" in n or "permission" in n.lower() for n in notes), str(notes))

    # 5. Windows has no SocketCAN and must not touch ip/modprobe.
    with mock.patch.object(P, "_is_windows", return_value=True), \
         mock.patch.object(mod.subprocess, "run") as run:
        notes = P._ensure_socketcan_ready(500000)
    check("windows is a no-op", notes == [] and not run.called)

    # 6. Connection path actually invokes the preparation.
    src = open(os.path.join(BACKEND, "plugins", "peakcan_plugin.py"),
               encoding="utf-8").read()
    check("connect() prepares SocketCAN before choosing candidates",
          "self._prepare_notes = self._ensure_socketcan_ready(bitrate)" in src
          and src.index("_ensure_socketcan_ready(bitrate)") < src.index(
              "candidates = self._candidate_list(interface, channel, can)"))

    # 7. The one-time installer/rule are shipped and cover the root cause.
    install_dir = os.path.join(BACKEND, "install")
    rules = open(os.path.join(install_dir, "99-peakcan-socketcan.rules"),
                 encoding="utf-8").read()
    script = open(os.path.join(install_dir, "install_peakcan_rules.sh"),
                  encoding="utf-8").read()
    check("udev rule loads peak_usb for PEAK devices",
          'idVendor}=="0c72"' in rules and "modprobe peak_usb" in rules)
    check("udev rule brings can* UP with a bitrate",
          'KERNEL=="can*"' in rules and "ip link set %k up type can bitrate" in rules)
    check("installer installs rule and boot module",
          "/etc/udev/rules.d/99-peakcan-socketcan.rules" in script
          and "modules-load.d" in script and "modprobe peak_usb" in script)
    check("spec bundles the install directory",
          '"install"' in open(os.path.join(BACKEND, "aitestlab.spec"),
                              encoding="utf-8").read())

    # 8. Failure text must match the platform. This used to assert the Linux
    # installer unconditionally, so the suite always failed on Windows even
    # though the Windows PCAN-Basic hint is the correct behaviour (#28).
    with mock.patch.object(P, "_usb_hint", return_value=""):
        with mock.patch.object(P, "_is_windows", return_value=False):
            linux_hint = P._platform_hint()
        with mock.patch.object(P, "_is_windows", return_value=True):
            win_hint = P._platform_hint()
    check("Linux connect error points at the installer",
          "install_peakcan_rules.sh" in linux_hint, linux_hint[:100])
    check("Windows connect error points at PCAN-Basic, not udev",
          "PCAN-Basic" in win_hint and "install_peakcan_rules.sh" not in win_hint
          and "sudo" not in win_hint, win_hint[:100])

    if _failures:
        print(f"\nFAILED: {len(_failures)} check(s): {', '.join(_failures)}")
        return 1
    print("\nAll PCAN preparation checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
