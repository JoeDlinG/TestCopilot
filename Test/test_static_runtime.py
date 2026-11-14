#!/usr/bin/env python3
"""Issue #29 / #28 guard: runtime behaviour of the static/SPA routes.

The existing boot guards only scan source strings, which is why `HEAD /`
returned 405 for months while all 15 suites stayed green. This suite builds a
throw-away ``static/`` tree, imports the real FastAPI app with it, and asserts
*behaviour* through TestClient — no live server required.

Also pins issue #28's release-gate runtime assertion list: HEAD liveness,
explicit JS MIME, JSON 404 for unknown API paths and assets.

Run: ``python3 Test/test_static_runtime.py``
"""
import os
import sys
import tempfile
from typing import List

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND)

_failures: List[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("  PASS  " if ok else "  FAIL  ") + label + (f"  -> {detail}"))
    if not ok:
        _failures.append(label)


def text(path: str) -> str:
    with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
        return fh.read()


def main() -> int:
    with tempfile.TemporaryDirectory() as static_dir:
        os.makedirs(os.path.join(static_dir, "assets"))
        with open(os.path.join(static_dir, "index.html"), "w") as fh:
            fh.write("<!doctype html><html><body><div id='root'></div></body></html>")
        with open(os.path.join(static_dir, "assets", "index-test.js"), "w") as fh:
            fh.write("console.log('runtime guard');")

        # Settings is a module-level singleton built at import time, so the
        # override must be in place before app.main is imported (its routes are
        # registered conditionally on the static tree existing).
        previous = os.environ.get("STATIC_DIR")
        os.environ["STATIC_DIR"] = static_dir
        try:
            from fastapi.testclient import TestClient
            from app.main import app
        finally:
            if previous is None:
                os.environ.pop("STATIC_DIR", None)
            else:
                os.environ["STATIC_DIR"] = previous

        client = TestClient(app)

        head = client.head("/")
        check("HEAD / returns 200 (ops liveness probe)", head.status_code == 200,
              str(head.status_code))

        head_spa = client.head("/testcases")
        check("HEAD /<spa-route> returns 200", head_spa.status_code == 200,
              str(head_spa.status_code))

        index = client.get("/")
        check("GET / serves the SPA shell", index.status_code == 200
              and "<div id='root'>" in index.text, str(index.status_code))
        check("index.html is no-store",
              "no-store" in index.headers.get("cache-control", ""),
              index.headers.get("cache-control", ""))
        check("index.html has exactly one charset",
              index.headers.get("content-type", "").count("charset=") <= 1,
              index.headers.get("content-type", ""))

        js = client.get("/assets/index-test.js")
        check("JS asset is served with an explicit javascript MIME",
              js.status_code == 200
              and js.headers.get("content-type", "").startswith("application/javascript"),
              js.headers.get("content-type", ""))
        head_js = client.head("/assets/index-test.js")
        check("HEAD on an asset returns 200 with the same MIME",
              head_js.status_code == 200
              and head_js.headers.get("content-type", "").startswith("application/javascript"),
              str(head_js.status_code))

        missing = client.get("/assets/does-not-exist-abc.js")
        check("missing asset is a JSON 404, never HTML",
              missing.status_code == 404 and "text/html" not in missing.headers.get("content-type", ""),
              str(missing.status_code))

        unknown = client.get("/api/no-such-route")
        check("unknown /api path is a JSON 404",
              unknown.status_code == 404
              and unknown.headers.get("content-type", "").startswith("application/json"),
              str(unknown.status_code))

        health = client.get("/api/health")
        check("/api/health exposes degraded + boot_warnings",
              health.status_code == 200
              and "degraded" in health.json() and "boot_warnings" in health.json(),
              str(health.status_code))

        # The catch-all now accepts HEAD; make sure that never turns an API
        # path into an HTML document for method probes.
        head_api = client.head("/api/health")
        check("HEAD on an API path is never served as HTML",
              "text/html" not in head_api.headers.get("content-type", ""),
              f"{head_api.status_code} {head_api.headers.get('content-type')}")

        diag = client.get("/api/system/diag").json()
        check("diag entry_media_type is javascript",
              diag.get("entry_media_type", "").startswith("application/javascript"),
              str(diag.get("entry_media_type")))
        check("diag index_media_type is html",
              diag.get("index_media_type", "").startswith("text/html"),
              str(diag.get("index_media_type")))

    main_py = text("backend/app/main.py")
    check("root route declares GET and HEAD",
          '@app.api_route("/", methods=["GET", "HEAD"])' in main_py)
    check("SPA fallback declares GET and HEAD",
          '@app.api_route("/{full_path:path}", methods=["GET", "HEAD"])' in main_py)
    check("assets are served by an explicit route, not StaticFiles",
          '@app.api_route("/assets/{asset_path:path}"' in main_py
          and "app.mount(\"/assets\"" not in main_py)
    check("boot guard never dereferences a null body",
          "document.body || document.documentElement" in text("frontend/index.html")
          and "DOMContentLoaded" in text("frontend/index.html"))

    if _failures:
        print(f"\nFAILED: {len(_failures)} check(s): {', '.join(_failures)}")
        return 1
    print("\nAll static-route runtime guards passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
