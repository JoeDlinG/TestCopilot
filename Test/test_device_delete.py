#!/usr/bin/env python3
"""Regression guard: a device must always be deletable.

Users reported DEV-001 / DEV-004 "cannot be deleted". The DELETE endpoint and
the button both worked for a *disconnected* row with no history, but two paths
hung or raised for real devices:

  * a row still marked ``connected`` made ``delete_device`` await a plugin's
    ``disconnect`` with no timeout — a stuck USB/CAN transport hung forever;
  * ``communication_logs.device_id`` is a NO ACTION foreign key and
    ``Device.logs`` is an ORM cascade, which an async session cannot lazy-load.

The service now tears the transport down under a timeout, deletes dependent
rows first and finishes with a bulk delete. These tests use a fake async
session so no database or hardware is required.

Run: ``python3 Test/test_device_delete.py``
"""
import asyncio
import os
import sys
from types import SimpleNamespace
from typing import List
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..", "backend")
sys.path.insert(0, BACKEND)

from app.services import device_service as ds  # noqa: E402
from app.services import project_service as ps  # noqa: E402
from app.models.models import DeviceStatus  # noqa: E402

_failures: List[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("  PASS  " if ok else "  FAIL  ") + label + (f"  -> {detail}" if detail else ""))
    if not ok:
        _failures.append(label)


class FakeResult:
    def __init__(self, rowcount: int = 1):
        self.rowcount = rowcount


class FakeSession:
    def __init__(self):
        self.statements: List[str] = []
        self.commits = 0

    async def execute(self, stmt):
        self.statements.append(str(stmt))
        return FakeResult(1)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass


class ImportSession:
    """Minimal async session for project-bundle device import."""

    def __init__(self, existing=None):
        self.existing = existing or []
        self.added = []
        scalars = mock.Mock()
        scalars.all = mock.Mock(return_value=self.existing)
        result = mock.Mock()
        result.scalars = mock.Mock(return_value=scalars)
        self._result = result

    async def execute(self, stmt):
        return self._result

    def add(self, obj):
        self.added.append(obj)


class HangingInterface:
    async def disconnect(self):
        await asyncio.sleep(30)


class ExplodingInterface:
    async def disconnect(self):
        raise RuntimeError("USB device vanished")


def new_service(device_status: str = "disconnected"):
    svc = ds.DeviceService()
    device = SimpleNamespace(id="dev_probe", status=device_status)
    svc.get_device = mock.AsyncMock(return_value=device)
    db = FakeSession()
    return svc, db


def statements_are_safe(db: FakeSession) -> bool:
    sql = " | ".join(db.statements)
    logs_idx = sql.find("communication_logs")
    dev_idx = sql.find("DELETE FROM devices")
    return (
        "DELETE FROM communication_logs" in sql
        and "DELETE FROM devices" in sql
        and 0 <= logs_idx < dev_idx  # dependent rows must go first
        and db.commits == 1
    )


async def run_cases() -> None:
    # 1. Plain disconnected device.
    with mock.patch.object(ds, "stop_device_monitor", lambda _id: None):
        svc, db = new_service()
        ok = await svc.delete_device(db, "dev_probe")
    check("ordinary device deleted", ok is True)
    check("logs cleared before device, committed once", statements_are_safe(db))

    # 2. Missing device is a clean no-op, never a commit.
    with mock.patch.object(ds, "stop_device_monitor", lambda _id: None):
        svc, db = new_service()
        svc.get_device = mock.AsyncMock(return_value=None)
        ok = await svc.delete_device(db, "dev_gone")
    check("missing device returns False", ok is False)
    check("missing device does not write", db.commits == 0 and not db.statements)

    # 3. Connected device whose transport hangs: timeout must not block delete.
    ds._active_connections["dev_probe"] = HangingInterface()
    ds._command_in_flight["dev_probe"] = True

    async def fake_wait_for(coro, timeout):
        # Real wait_for cancels the coroutine on timeout; mirror that so the
        # test does not leave an un-awaited coroutine behind.
        coro.close()
        raise asyncio.TimeoutError()

    with mock.patch.object(ds, "stop_device_monitor", lambda _id: None), \
         mock.patch.object(ds.asyncio, "wait_for", new=fake_wait_for):
        svc, db = new_service("connected")
        ok = await svc.delete_device(db, "dev_probe")
    check("connected device with hanging disconnect deleted", ok is True)
    check("hanging case still clears logs first", statements_are_safe(db))
    check("live connection state cleaned up",
          "dev_probe" not in ds._active_connections
          and "dev_probe" not in ds._command_in_flight)

    # 4. disconnect() raising must not abort the delete either.
    ds._active_connections["dev_probe"] = ExplodingInterface()
    with mock.patch.object(ds, "stop_device_monitor", lambda _id: None):
        svc, db = new_service("connected")
        ok = await svc.delete_device(db, "dev_probe")
    check("connected device with failing disconnect deleted", ok is True)
    check("no stale connection left behind", "dev_probe" not in ds._active_connections)

    # 5. A monitor that throws must not mask the delete.
    def bad_monitor(_id):
        raise RuntimeError("monitor already stopped")

    with mock.patch.object(ds, "stop_device_monitor", bad_monitor):
        svc, db = new_service()
        ok = await svc.delete_device(db, "dev_probe")
    check("monitor error does not block delete", ok is True)

    # 6. A project bundle saved while a device was connected must NOT create a
    #    ghost "connected" device on import — that was the DEV-004 case.
    bundle_row = {
        "id": "dev_ghost",
        "name": "PeakCAN USB",
        "type": "other",
        "protocol": "peakcan",
        "connection_type": "usb",
        "device_key": "DEV-004",
        "status": "connected",
        "connected_at": "2026-10-22T14:31:25+00:00",
        "last_seen": "2026-10-23T14:28:41+00:00",
        "config": {"interface": "auto"},
    }
    idb = ImportSession()
    stats = await ps._import_devices(idb, [bundle_row])
    check("bundle device imported", stats["created"] == 1 and len(idb.added) == 1,
          str(stats))
    ghost = idb.added[0]
    check("imported device is disconnected, not a ghost",
          ghost.status == DeviceStatus.DISCONNECTED.value, ghost.status)
    check("imported device has no stale connection timestamps",
          ghost.connected_at is None and ghost.last_seen is None,
          f"{ghost.connected_at} / {ghost.last_seen}")
    check("imported device keeps its identity and config",
          ghost.device_key == "DEV-004" and ghost.protocol == "peakcan")


def static_checks() -> None:
    api = open(os.path.join(BACKEND, "app", "api", "devices.py"), encoding="utf-8").read()
    check("DELETE route still delegates to service",
          '@router.delete("/{device_id}")' in api
          and "device_service.delete_device(db, device_id)" in api)

    front = open(os.path.join(HERE, "..", "frontend", "src", "pages", "Devices.tsx"),
                 encoding="utf-8").read()
    check("UI removes the row immediately", "setDevices(prev => prev.filter" in front)


def main() -> int:
    static_checks()
    asyncio.run(run_cases())
    if _failures:
        print(f"\nFAILED: {len(_failures)} check(s): {', '.join(_failures)}")
        return 1
    print(f"\nAll device-deletion checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
