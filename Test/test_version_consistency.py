#!/usr/bin/env python3
"""Issue #31 guard: one version everywhere.

``APP_VERSION`` drives /api/health (and therefore remote-update comparisons),
the NSIS output name and DisplayVersion, HISTORY's top chapter and the KANBAN
stamp. They silently drifted after a large fix commit. Fail when any two of
them disagree.

Run: ``python3 Test/test_version_consistency.py``
"""
import json
import os
import re
import sys
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
    cfg = re.search(r'APP_VERSION:\s*str\s*=\s*"([^"]+)"',
                    text("backend/app/core/config.py")).group(1)
    nsi = re.search(r'!define\s+APP_VERSION\s+"([^"]+)"',
                    text("backend/aitestlab.nsi")).group(1)
    hist = re.search(r"^## .*?（v(\d+\.\d+\.\d+)）", text("HISTORY.md"), re.M).group(1)
    kanban = re.search(r"v(\d+\.\d+\.\d+)", text("KANBAN.md")).group(1)

    print("  versions:", dict(config=cfg, nsi=nsi, history=hist, kanban=kanban))
    check("config == NSIS", cfg == nsi, f"{cfg} / {nsi}")
    check("config == HISTORY top chapter", cfg == hist, f"{cfg} / {hist}")
    check("config == KANBAN stamp", cfg == kanban, f"{cfg} / {kanban}")
    check("version is semver", bool(re.fullmatch(r"\d+\.\d+\.\d+", cfg)), cfg)
    check("NSIS OutFile uses APP_VERSION",
          "Setup-v${APP_VERSION}.exe" in text("backend/aitestlab.nsi"))

    # Runtime authority for #25 remote update: /api/health must report the same
    # version. ``_negotiate_port()`` may move the dev server to 8001+, and a
    # system proxy makes plain urlopen miss localhost entirely — both used to
    # turn this assertion into a permanent silent SKIP (issue #31 review #1).
    port = os.environ.get("AITESTLAB_PORT", "8000").strip() or "8000"
    url = f"http://127.0.0.1:{port}/api/health"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=5) as r:
            live = json.loads(r.read().decode("utf-8")).get("version")
        check("live /api/health version matches", live == cfg, f"{live} / {cfg}")
    except Exception as e:
        print(f"  SKIP  backend not running on {url} ({type(e).__name__}: {e})")

    if _failures:
        print(f"\nFAILED: {len(_failures)} check(s): {', '.join(_failures)}")
        return 1
    print("\nAll version-consistency checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
