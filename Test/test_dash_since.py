#!/usr/bin/env python3
"""Regression test for the dashboard ``since`` parameter.

Why this file exists
--------------------
The custom dashboard rendered **no data at all** while every widget claimed
"请先在顶部「数据源」选择一个测试用例". The real cause was one line in
``app/api/dashboards.py``::

    since_dt = datetime.fromisoformat(since)

``Date.toISOString()`` — which the frontend uses to set 起始时间 — produces a
trailing ``Z`` (``2026-10-17T16:00:00.000Z``). ``datetime.fromisoformat()``
rejects that suffix on Python < 3.11 (this project runs 3.8), so the request
failed with 400 / "Expected ISO-8601". The frontend's ``catch`` swallowed the
error and kept the previous (null) snapshot, so the page looked empty and gave
no hint as to why.

These tests pin the contract:

1. ``Z``-suffixed timestamps are accepted (the actual bug);
2. naive and explicit-offset timestamps still work;
3. garbage is still rejected with 400, not silently ignored;
4. ``since`` really filters — a future bound yields zero executions;
5. the stored 起始时间 of every existing dashboard round-trips without error.

Run against a live backend: ``python3 Test/test_dash_since.py``
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import requests  # noqa: E402

BASE = os.environ.get("AITESTLAB_API", "http://localhost:8000/api")
SNAP = f"{BASE}/dashboards/snapshot"

_failures = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("  PASS  " if ok else "  FAIL  ") + label + (f"  -> {detail}" if detail else ""))
    if not ok:
        _failures.append(label)


def snapshot(**params) -> requests.Response:
    return requests.get(SNAP, params=params, timeout=40)


def main() -> int:
    r = requests.get(f"{BASE}/health", timeout=20)
    if r.status_code != 200:
        print(f"backend not reachable at {BASE}: http {r.status_code}")
        return 1

    # A test case that actually has parsed results, so the widgets have data.
    tcs = requests.get(f"{BASE}/testcases/", params={"page": 1, "page_size": 20}, timeout=25)
    tc_id = None
    for tc in (tcs.json().get("data") or {}).get("items", []):
        if tc.get("id"):
            tc_id = tc["id"]
            break

    # 1) the bug: Z-suffixed ISO-8601 must be accepted
    r = snapshot(test_case_id=tc_id, limit=50, since="2026-10-17T16:00:00.000Z")
    check("since with trailing Z is accepted", r.status_code == 200,
          f"http={r.status_code} {r.text[:120]}")

    # 2) the other common shapes still work
    for label, value in [
        ("naive (no offset)", "2026-10-17T16:00:00"),
        ("explicit +00:00", "2026-10-17T16:00:00+00:00"),
        ("non-UTC offset", "2026-10-17T18:00:00+02:00"),
        ("date only", "2026-10-17"),
    ]:
        r = snapshot(test_case_id=tc_id, limit=50, since=value)
        check(f"since {label} accepted", r.status_code == 200, f"http={r.status_code}")

    # 3) garbage is still rejected rather than silently ignored
    r = snapshot(test_case_id=tc_id, limit=50, since="not-a-date")
    check("invalid since rejected with 400", r.status_code == 400, f"http={r.status_code}")

    # 4) since really filters: a bound in the future yields zero executions
    future = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    r = snapshot(test_case_id=tc_id, limit=50, since=future)
    total = ((r.json().get("data") or {}).get("executions") or {}).get("total")
    check("future since yields 0 executions", r.status_code == 200 and total == 0,
          f"total={total}")

    # 5) every stored dashboard must round-trip through its own data_source
    ds = requests.get(f"{BASE}/dashboards/", timeout=25).json().get("data") or []
    check("at least one dashboard exists", len(ds) > 0, f"count={len(ds)}")
    for d in ds:
        src = d.get("data_source") or {}
        r = snapshot(test_case_id=src.get("test_case_id"),
                     limit=src.get("limit") or 50,
                     since=src.get("since"))
        check(f"dashboard '{d.get('name')}' snapshot loads", r.status_code == 200,
              f"http={r.status_code} since={src.get('since')!r}")

    print()
    if _failures:
        print(f"FAILED ({len(_failures)}): {', '.join(_failures)}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
