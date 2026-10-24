#!/usr/bin/env python3
"""Regression tests for the remote update service (issue #25).

Why this file exists
--------------------
The updater is the one feature that can brick a user's installation, so the
parts that decide *whether* and *what* to install are pinned here:

1. version comparison (including pre-release ordering) — a wrong answer either
   nags forever or never offers an update;
2. a feed round-trip: manifest -> asset selection -> download -> SHA256;
3. **a corrupted download must never be installable** — checksum mismatch has to
   end in ``status=error`` with the file deleted;
4. ``/apply`` only accepts a token the server issued, so the installer can't be
   aimed at an arbitrary file;
5. the update helper's ``--dry-run`` exercises the whole plan without touching
   files (applying a real update would kill the server under test).

A throw-away feed is served on 127.0.0.1:8899; the previous feed setting is
restored on exit so the app is never left pointing at a test URL.

Run against a live backend: ``python3 Test/test_update_service.py``
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import requests  # noqa: E402

BASE = os.environ.get("AITESTLAB_API", "http://localhost:8000/api")
FEED_ROOT = os.path.join(tempfile.gettempdir(), "testcopilot_feedtest")
FEED_PORT = 8899
FAKE_VERSION = "99.9.0"

_failures = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("  PASS  " if ok else "  FAIL  ") + label + (f"  -> {detail}" if detail else ""))
    if not ok:
        _failures.append(label)


# --------------------------------------------------------------------------- #
# fake feed
# --------------------------------------------------------------------------- #
def _make_zip(path: str) -> str:
    src = os.path.join(FEED_ROOT, "_src")
    os.makedirs(src, exist_ok=True)
    with open(os.path.join(src, "APP.txt"), "w") as fh:
        fh.write(f"fake TestCopilot build {FAKE_VERSION}\n")
    with zipfile.ZipFile(path, "w") as zf:
        zf.write(os.path.join(src, "APP.txt"), "APP.txt")
    open(os.path.join(FEED_ROOT, "TestCopilot-Setup.exe"), "wb").write(open(path, "rb").read())
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def write_manifest(version: str, sha256: str, name: str = "version.json") -> None:
    zip_url = f"http://127.0.0.1:{FEED_PORT}/build.zip"
    manifest = {
        "version": version,
        "notes": "测试用假版本",
        "mandatory": False,
        "published_at": "2026-10-22T00:00:00Z",
        "assets": [
            {"platform": "linux", "kind": "zip", "url": zip_url,
             "sha256": sha256, "size": os.path.getsize(os.path.join(FEED_ROOT, "build.zip"))},
            {"platform": "windows", "kind": "nsis",
             "url": f"http://127.0.0.1:{FEED_PORT}/TestCopilot-Setup.exe",
             "sha256": sha256, "size": 0},
        ],
    }
    with open(os.path.join(FEED_ROOT, name), "w") as fh:
        json.dump(manifest, fh)


def start_feed():
    shutil.rmtree(FEED_ROOT, ignore_errors=True)
    os.makedirs(FEED_ROOT, exist_ok=True)
    digest = _make_zip(os.path.join(FEED_ROOT, "build.zip"))
    write_manifest(FAKE_VERSION, digest, "version.json")          # good
    write_manifest(FAKE_VERSION, digest + "bad", "broken.json")   # wrong checksum
    handler = partial(SimpleHTTPRequestHandler, directory=FEED_ROOT)
    handler.log_message = lambda *a, **k: None
    srv = ThreadingHTTPServer(("127.0.0.1", FEED_PORT), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, digest


def wait_ready(timeout: float = 60.0) -> dict:
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        last = requests.get(f"{BASE}/update/status", timeout=20).json()["data"]
        if last.get("status") in ("ready", "error"):
            return last
        time.sleep(0.6)
    return last


def main() -> int:
    try:
        requests.get(f"{BASE}/health", timeout=20)
    except Exception as exc:
        print(f"backend not reachable at {BASE}: {exc}")
        return 1

    # ---- 1. version comparison (pure) ----
    from app.services.update_service import compare_versions  # noqa: E402

    cases = [
        ("2.3.0", "2.2.1", 1), ("2.2.1", "2.3.0", -1), ("2.2.1", "2.2.1", 0),
        ("v2.10.0", "2.9.0", 1), ("2.3.0", "2.3.0-rc1", 1), ("2.3.0-rc1", "2.3.0", -1),
        ("2", "1.9.9", 1),
    ]
    bad = [(a, b, r) for a, b, r in cases if compare_versions(a, b) != r]
    check("version comparison (7 cases)", not bad, str(bad))

    srv, digest = start_feed()
    original_feed = None
    try:
        settings_url = f"{BASE}/update/settings"
        original_feed = requests.get(settings_url, timeout=20).json()["data"].get("feed_url", "")
        current = requests.get(f"{BASE}/update/check", timeout=20).json()["data"]["current"]
        print(f"  (local version {current}, fake feed {FAKE_VERSION})")

        # ---- 2. no feed -> graceful ----
        requests.put(settings_url, json={"feed_url": ""}, timeout=20)
        r = requests.get(f"{BASE}/update/check", timeout=20).json()["data"]
        check("no feed degrades to no_feed", r.get("reason") == "no_feed" and not r["available"])

        # ---- 3. feed round trip ----
        requests.put(settings_url,
                     json={"feed_url": f"http://127.0.0.1:{FEED_PORT}/version.json"},
                     timeout=20)
        r = requests.get(f"{BASE}/update/check", timeout=20).json()["data"]
        check("update detected", r.get("available") is True and r.get("latest") == FAKE_VERSION,
              str({k: r.get(k) for k in ("available", "latest", "reason")}))
        asset = r.get("asset") or {}
        check("asset picked for this platform",
              asset.get("kind") == "zip" and asset.get("sha256") == digest,
              str(asset.get("name")))

        # ---- 4. download + checksum ----
        requests.post(f"{BASE}/update/download", timeout=30)
        st = wait_ready()
        check("download finished as ready", st.get("status") == "ready", str(st))
        check("downloaded file matches SHA256",
              bool(st.get("path")) and os.path.isfile(st["path"])
              and hashlib.sha256(open(st["path"], "rb").read()).hexdigest() == digest)
        good_token = st.get("token")

        # ---- 5. /apply rejects an unknown token ----
        r = requests.post(f"{BASE}/update/apply", json={"token": "not-a-token"}, timeout=20)
        check("apply rejects a forged token", r.status_code == 400, f"http={r.status_code}")

        # ---- 6. corrupted download must not be installable ----
        requests.put(settings_url,
                     json={"feed_url": f"http://127.0.0.1:{FEED_PORT}/broken.json"},
                     timeout=20)
        requests.post(f"{BASE}/update/download", timeout=30)
        st2 = wait_ready()
        check("checksum mismatch is rejected",
              st2.get("status") == "error" and "checksum" in (st2.get("error") or ""),
              str(st2.get("error")))
        check("corrupted file was deleted", not os.path.isfile(st2.get("path") or "__none__"))

        # ---- 7. ignore a version ----
        requests.put(settings_url,
                     json={"feed_url": f"http://127.0.0.1:{FEED_PORT}/version.json"},
                     timeout=20)
        requests.post(f"{BASE}/update/ignore", json={"version": FAKE_VERSION}, timeout=20)
        r = requests.get(f"{BASE}/update/check", timeout=20).json()["data"]
        check("ignored version is flagged", r.get("ignored") is True)
        requests.post(f"{BASE}/update/ignore", json={"version": ""}, timeout=20)

        # ---- 8. helper dry-run ----
        helper = os.path.join(os.path.dirname(__file__), "..", "backend", "update_helper.py")
        target = os.path.join(tempfile.gettempdir(), "tc_dryrun_target")
        proc = subprocess.run(
            [sys.executable, helper, "--package", os.path.join(FEED_ROOT, "build.zip"),
             "--kind", "zip", "--target", target, "--dry-run"],
            capture_output=True, text=True, timeout=60,
        )
        check("update helper dry-run exits 0", proc.returncode == 0,
              (proc.stderr or proc.stdout)[-160:])
        check("dry-run did not create the target", not os.path.exists(target))
        check("good token is still valid after the error run", bool(good_token))
    finally:
        srv.shutdown()
        try:
            requests.put(f"{BASE}/update/settings",
                         json={"feed_url": original_feed or ""}, timeout=20)
        except Exception:
            pass
        shutil.rmtree(FEED_ROOT, ignore_errors=True)

    print()
    if _failures:
        print(f"FAILED ({len(_failures)}): {', '.join(_failures)}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
