#!/usr/bin/env python3
"""Issue #29 guard: the 11-01 white-screen / first-launch defences must exist.

Those fixes lived in a local worktree and never reached the main branch. This
suite pins the four markers (explicit MIME, boot guard, ErrorBoundary, health
probe + port negotiation) so a future merge cannot silently drop them again.

Run: ``python3 Test/test_boot_guards.py``
"""
import json
import os
import sys
import urllib.error
import urllib.request
from typing import List

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
_failures: List[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("  PASS  " if ok else "  FAIL  ") + label + (f"  -> {detail}" if detail else ""))
    if not ok:
        _failures.append(label)


def text(path: str) -> str:
    return open(os.path.join(ROOT, path), encoding="utf-8").read()


def main() -> int:
    main_py = text("backend/app/main.py")
    for marker in ("_MEDIA_TYPES", "_media_type", "_register_media_types",
                   "[boot] frontend bundle", "/api/system/diag",
                   '"application/javascript"', "no-store"):
        check(f"main.py has {marker}", marker in main_py)
    check("FileResponse passes explicit media_type",
          "media_type=_media_type(" in main_py)
    check("asset 4xx + / requests are logged",
          'path.startswith("/assets/")' in main_py and '[boot] GET /' in main_py)
    check("SPA fallback cannot swallow API routes",
          'full_path.startswith("api/")' in main_py
          and 'path.rstrip("/") in _API_ROUTE_PATHS' in main_py)

    run_py = text("backend/run.py")
    check("health probe bypasses system proxy", "ProxyHandler({})" in run_py)
    check("browser waits for /api/health", "_probe_app" in run_py
          and "/api/health" in run_py)
    check("no fixed 2.5s sleep guess",
          "time.sleep(2.5)" not in run_py
          and "delay: float = 2.5" not in run_py
          and "time.sleep(delay)" not in run_py)
    check("port negotiation reuses a running instance",
          "_negotiate_port" in run_py and "_port_in_use" in run_py
          and "sys.exit(0)" in run_py)

    index = text("frontend/index.html")
    check("inline boot guard present", "data-boot-guard" in index)
    check("boot guard has 8s and 25s timeouts",
          "8000" in index and "25000" in index)
    check("boot guard explains MIME failures",
          "application/javascript" in index)
    check("boot guard points at /api/system/diag", "/api/system/diag" in index)

    entry = text("frontend/src/main.tsx")
    check("ErrorBoundary mounted", "ErrorBoundary" in entry)
    check("ErrorBoundary component exists",
          os.path.isfile(os.path.join(ROOT, "frontend/src/components/ErrorBoundary.tsx")))

    tour = text("frontend/src/components/help/OnboardingTour.tsx")
    check("tour storage key carries a version suffix",
          "testcopilot.onboarding.v2" in tour)
    check("tour self-checks viewport placement",
          "ant-tour-inner" in tour and "1800" in tour)

    # Runtime evidence bundle (only if the backend happens to be running).
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/api/system/diag",
                                    timeout=5) as r:
            diag = json.loads(r.read().decode("utf-8"))
        check("diag reports JS MIME explicitly",
              diag["entry_media_type"].startswith("application/javascript"),
              diag["entry_media_type"])
        check("diag reports index as no-store",
              diag["boot_guards"]["index_no_store"] is True)
        with urllib.request.urlopen("http://127.0.0.1:8000/", timeout=5) as r:
            content_type = r.headers.get("Content-Type", "")
            r.read(256)
        check("index Content-Type has exactly one charset",
              content_type.count("charset=") <= 1, content_type)
        with urllib.request.urlopen("http://127.0.0.1:8000/api/projects/",
                                    timeout=5) as r:
            body = json.loads(r.read().decode("utf-8"))
        check("API collection with trailing slash is JSON", isinstance(body, dict),
              type(body).__name__)
        try:
            urllib.request.urlopen("http://127.0.0.1:8000/api/no-such-route/",
                                   timeout=5)
            check("unknown API path is a 404", False, "returned 200")
        except urllib.error.HTTPError as err:
            check("unknown API path is a JSON 404",
                  err.code == 404
                  and "application/json" in err.headers.get("Content-Type", ""),
                  f"{err.code} {err.headers.get('Content-Type')}")
    except Exception as e:
        print(f"  SKIP  backend not running ({type(e).__name__})")

    if _failures:
        print(f"\nFAILED: {len(_failures)} check(s): {', '.join(_failures)}")
        return 1
    print("\nAll boot-guard checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
