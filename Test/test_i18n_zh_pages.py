#!/usr/bin/env python3
"""Regression guard for the Chinese UI of ModelConfig / DebugTerminal / Projects.

Those three pages used to leak English into a zh-CN session: raw backend field
names as table headings, ``active`` / ``UNKNOWN`` / ``Base URL`` literals and a
first-run Tour mask that dimmed and blocked the whole workspace. The catalogue
is compiled with the project's own esbuild so this checks the *real* merged
messages, not a regex approximation.

Run: ``python3 Test/test_i18n_zh_pages.py``
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from typing import List

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
FRONT = os.path.join(ROOT, "frontend")
PAGES = os.path.join(FRONT, "src", "pages")

_failures: List[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("  PASS  " if ok else "  FAIL  ") + label + (f"  -> {detail}" if detail else ""))
    if not ok:
        _failures.append(label)


def load_catalogue():
    esbuild = os.path.join(FRONT, "node_modules", ".bin", "esbuild")
    if not os.path.isfile(esbuild):
        return None
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "messages.cjs")
        subprocess.run(
            [esbuild, os.path.join(FRONT, "src", "i18n", "messages.ts"),
             "--bundle", "--platform=node", "--format=cjs",
             f"--outfile={out}", "--log-level=error"],
            check=True, capture_output=True,
        )
        js = ("const m=require(" + json.dumps(out) + ").messages;"
              "process.stdout.write(JSON.stringify(m))")
        res = subprocess.run(["node", "-e", js], check=True,
                             capture_output=True, text=True)
        return json.loads(res.stdout)


def page(name: str) -> str:
    return open(os.path.join(PAGES, name), encoding="utf-8").read()


def main() -> int:
    cat = load_catalogue()
    if cat is None:
        print("  SKIP  esbuild not installed — cannot verify the merged catalogue")
        return 0

    zh, en = cat["zh-CN"], cat["en-US"]
    check("zh/en catalogues are complete", len(zh) == len(en) and len(zh) > 1200,
          f"{len(zh)}/{len(en)}")

    targets = ["ModelConfig.tsx", "DebugTerminal.tsx", "ProjectManager.tsx"]
    for name in targets:
        src = page(name)
        keys = sorted(set(re.findall(r"\bt\(\s*'([^']+)'", src)))
        missing = [k for k in keys if k not in zh or k not in en]
        check(f"{name}: every t() key resolves", not missing, str(missing[:8]))
        leaked = [k for k in keys if k in zh and not re.search(r"[\u4e00-\u9fff]", zh[k])
                  and not re.fullmatch(r"[\W\w]*\{[A-Za-z]+\}[\W\w]*", zh[k])
                  and not re.fullmatch(r"[：、（）·\s]+", zh[k])]
        check(f"{name}: zh values are translated", not leaked, str(leaked[:8]))

    new_keys = ["status.active", "status.inactive", "status.error", "label.baseUrl",
                "label.apiKey", "label.unknown", "term.errorColon", "field.deviceKey",
                "field.connectionType"]
    check("new value/field labels exist in both locales",
          all(k in zh and k in en for k in new_keys),
          str([k for k in new_keys if k not in zh or k not in en]))

    mc = page("ModelConfig.tsx")
    check("ModelConfig uses translated status/base-url labels",
          "title: 'Base URL'" not in mc and 'label="API Key"' not in mc
          and 'label="Base URL"' not in mc and ">s</Tag>" not in mc
          and "t('status.active')" in mc)

    dt = page("DebugTerminal.tsx")
    check("DebugTerminal has no UNKNOWN / raw 'Error:' / shouted protocol",
          "'UNKNOWN'" not in dt and "Error: ${msg.error}" not in dt
          and "protocol?.toUpperCase()" not in dt
          and "t('term.errorColon')" in dt)
    check("DebugTerminal keeps three columns from collapsing",
          "minWidth: 860" in dt)

    pm = page("ProjectManager.tsx")
    check("Projects preview translates raw field names",
          "FIELD_LABEL_KEY" in pm and "title: FIELD_LABEL_KEY[k]" in pm
          and "title: k," not in pm)
    check("Projects wizard strings are no longer mangled",
          "createdParen')}}" not in pm and ".json){t('punct.colon')}" not in pm)

    tour = open(os.path.join(FRONT, "src", "components", "help", "OnboardingTour.tsx"),
                encoding="utf-8").read()
    check("first-run tour no longer masks/blocks the UI", "mask={false}" in tour)

    # The shipped bundle must contain the fix, not a stale October build.
    dist = os.path.join(FRONT, "dist", "assets")
    if os.path.isdir(dist):
        blob = ""
        for f in os.listdir(dist):
            if f.endswith(".js"):
                blob += open(os.path.join(dist, f), encoding="utf-8", errors="ignore").read()
        check("built bundle contains the new zh labels",
              "已激活" in blob and "设备ID号" in blob)
        check("built bundle contains translated column headings",
              "FIELD_LABEL_KEY" not in blob and "API 地址（Base URL）" in blob)
    else:
        print("  SKIP  frontend/dist not built yet")

    if _failures:
        print(f"\nFAILED: {len(_failures)} check(s): {', '.join(_failures)}")
        return 1
    print("\nAll Chinese-UI checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
