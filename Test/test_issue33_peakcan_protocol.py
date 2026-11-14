#!/usr/bin/env python3
"""Regression guard for issue #33 (P0): "edit device interface" overwrote a
plugin device's protocol (``peakcan`` -> ``can``), silently bypassing the
PeakCAN plugin so running a test case disconnected the device.

The fix has three layers, all asserted here without hardware:

* P0-2 — the protocol decision uses the *plugin whitelist* and recognises a
  polluted device by its private config keys, so it is never rewritten again.
* P0-1 — a startup repair restores already-polluted rows.
* P0-3 — the CAN channel column and ``config.channel`` stay in sync (transport
  binding), so the mandatory field is not shown empty and never drifts.

Plus the two amplifiers (P1): re-connect tears down the old bus, and a
command-semantic error no longer disconnects the device.

Run: ``python3 Test/test_issue33_peakcan_protocol.py``
"""
import asyncio
import importlib.util
import os
import sys
from typing import List
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND)

from app.core.interfaces import (  # noqa: E402
    apply_plugin_transport, column_from_config,
)
from app.services import device_service as ds  # noqa: E402
from app.services.plugin_service import plugin_service  # noqa: E402

_failures: List[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("  PASS  " if ok else "  FAIL  ") + label + (f"  -> {detail}" if detail else ""))
    if not ok:
        _failures.append(label)


def text(path: str) -> str:
    return open(os.path.join(ROOT, path), encoding="utf-8").read()


def load_peakcan():
    spec = importlib.util.spec_from_file_location(
        "peakcan_under_test", os.path.join(BACKEND, "plugins", "peakcan_plugin.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.PeakCANPlugin


# --------------------------------------------------------------------------- #
# P0-3 — channel sync via the transport binding
# --------------------------------------------------------------------------- #
def binding_checks() -> None:
    src = text("backend/app/core/interfaces.py")
    check("peakcan has a can binding", '"peakcan"' in src
          and '"from_column": {"channel": "can_channel"}' in src)

    stored = {"interface": "auto", "channel": "PCAN_USBBUS1", "bitrate": 500000,
              "loopback": False, "skip_error_frames": True}
    out = apply_plugin_transport(
        "peakcan", "can", {"can_channel": "PCAN_USBBUS1"},
        {"can_channel": "PCAN_USBBUS1"}, dict(stored),
    )
    check("PUT syncs can_channel -> config.channel",
          out.get("channel") == "PCAN_USBBUS1", str(out))
    check("binding does not invent a transport key",
          "transport" not in out, str(out))

    back = column_from_config("peakcan", "can")
    check("GET backfills can_channel from config.channel",
          back.get("can_channel") == "channel", str(back))


# --------------------------------------------------------------------------- #
# P0-2 / P0-1 — private-key pollution recognition
# --------------------------------------------------------------------------- #
def pollution_checks() -> None:
    PeakCANPlugin = load_peakcan()
    private = plugin_service.plugin_private_keys(PeakCANPlugin)
    check("PeakCAN signature keys detected",
          {"channel", "interface"} <= private, str(sorted(private)))

    # A polluted row: protocol was overwritten to 'can', but the config still
    # carries the PeakCAN private keys.
    polluted_config = {"interface": "auto", "channel": "PCAN_USBBUS1",
                       "bitrate": 500000, "loopback": False,
                       "skip_error_frames": True}

    async def run_match():
        with mock.patch.object(
            plugin_service, "list_enabled_plugins_detail",
            new=mock.AsyncMock(return_value=[("peakcan", PeakCANPlugin)]),
        ):
            return await plugin_service.match_device_to_plugin(None, polluted_config)

    match = asyncio.run(run_match())
    check("polluted device recognised as peakcan", match == "peakcan", str(match))

    async def run_clean():
        with mock.patch.object(
            plugin_service, "list_enabled_plugins_detail",
            new=mock.AsyncMock(return_value=[("peakcan", PeakCANPlugin)]),
        ):
            # A genuine CAN device: no plugin private keys.
            return await plugin_service.match_device_to_plugin(
                None, {"bitrate": 500000, "fd": False, "timeout": 2.0}
            )

    check("genuine CAN device NOT misidentified", asyncio.run(run_clean()) is None)


# --------------------------------------------------------------------------- #
# P1-4 — command-semantic errors must not disconnect
# --------------------------------------------------------------------------- #
def transport_error_checks() -> None:
    check("command-semantic ValueError is not a transport error",
          ds._is_transport_error(ValueError("byte must be in range(0, 256)")) is False)
    check("bad CAN string is not a transport error",
          ds._is_transport_error(ValueError("Invalid CAN string format")) is False)
    check("ConnectionError is a transport error",
          ds._is_transport_error(ConnectionError("PeakCAN is not connected")) is True)
    check("wrapped CanError (bus-off) is a transport error",
          ds._is_transport_error(RuntimeError("PeakCAN send error: bus-off")) is True)


# --------------------------------------------------------------------------- #
# Source guards — the fixes must be wired into the right call sites
# --------------------------------------------------------------------------- #
def source_guards() -> None:
    api = text("backend/app/api/devices.py")
    svc = text("backend/app/services/device_service.py")
    main = text("backend/app/main.py")
    itf = text("backend/app/core/interfaces.py")

    check("API uses the plugin whitelist, not 'not in STANDARD_PROTOCOLS'",
          "get_enabled_protocol_names" in api
          and "plugin_protocol not in STANDARD_PROTOCOLS" not in api)
    check("API restores a polluted device on interface edit",
          "match_device_to_plugin" in api)
    check("startup runs the pollution repair",
          "restore_plugin_protocols" in main and "restore_plugin_protocols" in svc)
    check("re-connect tears down the old bus",
          "_active_connections.pop(device.id, None)" in svc)
    check("send_command classifies transport vs command errors",
          "_is_transport_error" in svc and "post-send bookkeeping failed" in svc)
    check("GET backfill helper exists", "column_from_config" in itf)


def main() -> int:
    binding_checks()
    pollution_checks()
    transport_error_checks()
    source_guards()
    if _failures:
        print(f"\nFAILED: {len(_failures)} check(s): {', '.join(_failures)}")
        return 1
    print("\nAll issue #33 regression guards passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
