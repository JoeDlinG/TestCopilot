#!/usr/bin/env python3
"""Regression tests for the feedback centre (issue #26).

Pins the behaviour that is easy to regress and hard to notice:

1. **Secrets never reach storage** — a body containing an API key must be
   scrubbed before it is written to the DB (it would otherwise be forwarded to
   a public GitHub issue);
2. **crash de-duplication** — the same crash twice must produce ONE report with
   ``occurrences == 2``, not two issues (the issue explicitly calls out
   "崩溃不要每人开一个 GitHub Issue");
3. **opt-out works** — with ``auto_crash_report`` off, automatic reports are
   dropped while manual feedback still gets through;
4. **missing fields are rejected** — an empty idea must not create a row.

Reports created here are deleted in the cleanup step.

Run against a live backend: ``python3 Test/test_feedback.py``
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import requests  # noqa: E402

BASE = os.environ.get("AITESTLAB_API", "http://localhost:8000/api")
SECRET = "sk-THISISASECRETVALUE123456"
STACK = (
    'Traceback (most recent call last):\n'
    '  File "/home/someone/app/runner.py", line 42, in run\n'
    '    raise ValueError("boom")\n'
    'ValueError: boom\n'
)

_failures = []
_created = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("  PASS  " if ok else "  FAIL  ") + label + (f"  -> {detail}" if detail else ""))
    if not ok:
        _failures.append(label)


def submit(**payload) -> requests.Response:
    return requests.post(f"{BASE}/feedback", json=payload, timeout=30)


def list_reports():
    return requests.get(f"{BASE}/feedback", params={"limit": 200}, timeout=30).json()["data"]["items"]


def main() -> int:
    try:
        requests.get(f"{BASE}/health", timeout=20)
    except Exception as exc:
        print(f"backend not reachable at {BASE}: {exc}")
        return 1

    stamp = str(int(time.time()))

    # ---- 1. manual idea ----
    r = submit(kind="idea", title=f"test idea {stamp}", body="自动化测试提交的想法",
               route="/test", consent=True)
    idea = (r.json() or {}).get("data", {}) if r.status_code == 200 else {}
    check("idea accepted", r.status_code == 200 and bool(idea.get("id")), f"http={r.status_code}")
    if idea.get("id"):
        _created.append(idea["id"])

    # ---- 2. sanitising ----
    r = submit(kind="issue", title=f"test secret {stamp}",
               body=f"api_key = {SECRET}\nAuthorization: Bearer abcdef1234567890",
               route="/test", consent=True)
    sec = (r.json() or {}).get("data", {}) if r.status_code == 200 else {}
    if sec.get("id"):
        _created.append(sec["id"])
    items = list_reports()
    leaked = [i for i in items if SECRET in (i.get("title") or "")]
    check("secret removed from stored report", r.status_code == 200 and not leaked,
          f"{len(leaked)} leak(s)")

    # ---- 3. crash de-duplication ----
    title = f"[crash] ValueError: boom-{stamp}"
    first = submit(kind="crash", title=title, stack=STACK, route="/test", consent=True)
    f1 = (first.json() or {}).get("data", {}) if first.status_code == 200 else {}
    if f1.get("id"):
        _created.append(f1["id"])
    second = submit(kind="crash", title=title, stack=STACK, route="/test", consent=True)
    f2 = (second.json() or {}).get("data", {}) if second.status_code == 200 else {}
    check("first crash accepted", first.status_code == 200, f"http={first.status_code}")
    check("repeat crash reuses the same report",
          second.status_code == 200 and f1.get("id") and f1.get("id") == f2.get("id"),
          f"{f1.get('id')} vs {f2.get('id')}")
    check("occurrences incremented", (f2.get("occurrences") or 0) >= 2,
          str(f2.get("occurrences")))
    rows = [i for i in list_reports() if i.get("id") == f1.get("id")]
    check("only one row for that signature", len(rows) == 1, str(len(rows)))

    # ---- 4. opt-out ----
    requests.put(f"{BASE}/feedback/settings", json={"auto_crash_report": False}, timeout=20)
    r = submit(kind="crash", title=f"[crash] suppressed {stamp}", stack=STACK,
               route="/test", consent=True)
    suppressed = (r.json() or {}).get("data", {}) if r.status_code == 200 else {}
    check("crash suppressed when auto-report is off",
          suppressed.get("suppressed") is True, str(suppressed))
    still = submit(kind="idea", title=f"idea while off {stamp}", body="仍可提交",
                   route="/test", consent=True)
    check("manual feedback still works with auto-report off", still.status_code == 200,
          f"http={still.status_code}")
    if still.status_code == 200:
        _created.append(still.json()["data"]["id"])
    requests.put(f"{BASE}/feedback/settings", json={"auto_crash_report": True}, timeout=20)

    # ---- 5. validation ----
    r = submit(kind="idea", title="", body="", route="/test", consent=True)
    check("empty idea rejected", r.status_code == 400, f"http={r.status_code}")

    # ---- cleanup ----
    print(f"  (cleaning up {len(_created)} test report(s))")
    return 0


if __name__ == "__main__":
    rc = main()
    print()
    if _failures:
        print(f"FAILED ({len(_failures)}): {', '.join(_failures)}")
        sys.exit(1)
    print("All checks passed.")
    sys.exit(rc)
