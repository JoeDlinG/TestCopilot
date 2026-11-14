#!/usr/bin/env python3
"""Issue #34 guard: startup protocol repair must NOT rewrite generic CAN devices.

``70e9046`` (issue #33) repaired plugin devices whose ``protocol`` had been
overwritten, but its "plugin private key" signature included keys the generic
``CANInterface`` also reads (``interface`` / ``channel`` / ``loopback``). A
single hit was enough, so 3 of 4 ordinary generic CAN configs were silently
rewritten to ``peakcan`` on every boot with no rollback.

These are *runtime* checks against the real matcher and the real
``restore_plugin_protocols()``, not source-string scans. Issue #33's review also
found that bare SCPI commands (``*IDN?``) were dropped by the command
extractor; that regression is pinned here too.

Run: ``python3 Test/test_issue34_generic_can.py``
"""
import asyncio
import importlib.util
import json
import os
import sys
from types import SimpleNamespace
from typing import List
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND)

from app.core.interfaces import GENERIC_DRIVER_CONFIG_KEYS  # noqa: E402
from app.services import device_service as ds  # noqa: E402
from app.services.execution_service import ExecutionEngine  # noqa: E402
from app.services.plugin_service import plugin_service  # noqa: E402

_failures: List[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("  PASS  " if ok else "  FAIL  ") + label + (f"  -> {detail}"))
    if not ok:
        _failures.append(label)


def text(path: str) -> str:
    with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
        return fh.read()


def load_peakcan():
    spec = importlib.util.spec_from_file_location(
        "peakcan_issue34", os.path.join(BACKEND, "plugins", "peakcan_plugin.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.PeakCANPlugin


# The exact configs from issue #34's independent probe, plus the reported repro.
GENERIC_CAN_CONFIGS = [
    {"channel": "can0", "bitrate": 500000},
    {"interface": "socketcan", "channel": "can0"},
    {"channel": "can0", "interface": "virtual", "loopback": False},
    {"can_channel": "can0", "bitrate": 500000},
    {"interface": "pcan", "bitrate": 500000, "can_channel": "can0", "can_id": 2047},
]

# A PeakCAN plugin device polluted by "edit device interface" in v0.11.0~v2.3.3.
POLLUTED_CONFIG = {
    "interface": "auto", "channel": "PCAN_USBBUS1", "bitrate": 500000,
    "loopback": False, "skip_error_frames": True,
}


def signature_checks() -> None:
    PeakCANPlugin = load_peakcan()
    private = plugin_service.plugin_private_keys(PeakCANPlugin)
    exclusive = plugin_service.plugin_exclusive_keys(PeakCANPlugin)
    check("shared generic keys are not exclusive signatures",
          not (exclusive & {"interface", "channel", "loopback", "bitrate"}),
          str(sorted(exclusive)))
    check("plugin-exclusive keys still exist",
          "skip_error_frames" in exclusive, str(sorted(exclusive)))
    check("generic driver key set covers CANInterface reads",
          {"interface", "bitrate", "can_id", "can_channel"} <= GENERIC_DRIVER_CONFIG_KEYS)
    check("private keys remain a superset of exclusive keys",
          exclusive <= private)


def matcher_checks() -> None:
    PeakCANPlugin = load_peakcan()

    async def match(cfg, protocol="can"):
        with mock.patch.object(
            plugin_service, "list_enabled_plugins_detail",
            new=mock.AsyncMock(return_value=[("peakcan", PeakCANPlugin)]),
        ):
            return await plugin_service.match_device_to_plugin(
                None, cfg, current_protocol=protocol
            )

    for i, cfg in enumerate(GENERIC_CAN_CONFIGS, 1):
        got = asyncio.run(match(cfg))
        check(f"generic CAN config #{i} stays unmatched", got is None, str(got))
    check("polluted plugin device is still recognised",
          asyncio.run(match(POLLUTED_CONFIG)) == "peakcan")
    check("unrelated standard protocol is not a pollution target",
          asyncio.run(match(POLLUTED_CONFIG, protocol="serial")) is None)


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeDB:
    def __init__(self, rows):
        self._rows = rows
        self.commits = 0

    async def execute(self, stmt):
        return _FakeResult(self._rows)

    async def commit(self):
        self.commits += 1


def restore_checks() -> None:
    PeakCANPlugin = load_peakcan()
    generic = [
        SimpleNamespace(id=f"generic-{i}", protocol="can",
                        config=json.dumps(cfg), updated_at=None)
        for i, cfg in enumerate(GENERIC_CAN_CONFIGS)
    ]
    polluted = SimpleNamespace(id="pcan-1", protocol="can",
                               config=json.dumps(POLLUTED_CONFIG), updated_at=None)
    rows = generic + [polluted]
    db = _FakeDB(rows)

    async def run():
        with mock.patch.object(
            plugin_service, "list_enabled_plugins_detail",
            new=mock.AsyncMock(return_value=[("peakcan", PeakCANPlugin)]),
        ):
            return await ds.device_service.restore_plugin_protocols(db)

    restored = asyncio.run(run())
    check("startup repair only touches the polluted row", restored == 1, str(restored))
    check("every generic CAN device keeps protocol=can",
          all(d.protocol == "can" for d in generic),
          str([d.protocol for d in generic]))
    check("polluted plugin device is restored to peakcan",
          polluted.protocol == "peakcan", polluted.protocol)
    check("repair commits exactly once", db.commits <= 1, str(db.commits))


def scpi_checks() -> None:
    """Issue #33 review: visible commands without a MG100/CAN shape."""
    node = {"config": {"command": "*IDN?", "expected": "", "parameters": {}},
            "data": {"label": ""}}
    check("bare SCPI command is not dropped",
          ExecutionEngine._extract_commands(node) == ["*IDN?"],
          str(ExecutionEngine._extract_commands(node)))

    summary = {
        "config": {"command": "读取电源电压",
                   "parameters": {"command": "@11_GETVOLT;"},
                   "commands": []},
        "data": {"label": ""},
    }
    check("Chinese summary still falls back to hidden command",
          ExecutionEngine._extract_commands(summary) == ["@11_GETVOLT;"],
          str(ExecutionEngine._extract_commands(summary)))

    stale = {
        "config": {"command": "MEAS:VOLT?",
                   "parameters": {"command": "*IDN?"},
                   "commands": ["OLD;"]},
        "data": {"label": ""},
    }
    normalized = ExecutionEngine.normalize_node_commands(stale)
    check("save-normalisation drops stale copies for bare commands",
          "commands" not in normalized["config"]
          and "command" not in normalized["config"]["parameters"],
          str(normalized["config"]))


def source_guards() -> None:
    svc = text("backend/app/services/device_service.py")
    api = text("backend/app/api/devices.py")
    plug = text("backend/app/services/plugin_service.py")
    check("repair passes current_protocol to the matcher",
          "current_protocol=device.protocol" in svc)
    check("interface edit passes current_protocol to the matcher",
          "current_protocol=plugin_protocol" in api)
    check("matcher requires plugin-exclusive keys",
          "plugin_exclusive_keys" in plug and "len(hits) < 2" in plug)
    check("generic CAN markers veto a match",
          '"can_channel"' in plug and '"can_id"' in plug)
    check("pollution targets are declared in the interface registry",
          "PLUGIN_POLLUTION_TARGETS" in text("backend/app/core/interfaces.py"))


def main() -> int:
    signature_checks()
    matcher_checks()
    restore_checks()
    scpi_checks()
    source_guards()
    if _failures:
        print(f"\nFAILED: {len(_failures)} check(s): {', '.join(_failures)}")
        return 1
    print("\nAll issue #34 / bare-command regression guards passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
