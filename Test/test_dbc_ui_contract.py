#!/usr/bin/env python3
"""Regression guards for the DBC import -> parser config -> UI chain.

Symptom this suite locks down: the import toast says "导入成功", the row IS
committed to SQLite, yet the DBC page and the "pick a DBC signal" dialog both
stay empty. Root cause: every other router answers with
``{code: 0, message: "success", data: ...}`` but ``/api/dbc/*`` answers with
the bare payload; the pages called ``extractItems()``, which only understands
the envelope, and therefore always rendered ``[]``.

Also guards the standalone-window launcher so the packaged exe never opens
the UI as a tab in the user's everyday browser window.

Run: ``python Test/test_dbc_ui_contract.py``
"""
import asyncio
import importlib.util
import json
import os
import sys
import tempfile
from typing import Any, List
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
BACKEND = os.path.join(ROOT, "backend")
FRONTEND = os.path.join(ROOT, "frontend", "src")
sys.path.insert(0, BACKEND)

_failures: List[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("  PASS  " if ok else "  FAIL  ") + label + (f"  -> {detail}" if detail else ""))
    if not ok:
        _failures.append(label)


def text(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# --------------------------------------------------------------------------
# Faithful Python replicas of the two frontend unwrapping helpers. Keeping
# them here means a backend shape change is caught even without a browser.
# --------------------------------------------------------------------------
def unwrap_payload(body: Any, fallback: Any = None) -> Any:
    if body is None:
        return fallback
    is_envelope = (
        isinstance(body, dict) and "code" in body and "data" in body
    )
    if not is_envelope:
        return body
    if body["code"] != 0:
        raise ValueError(str(body.get("message") or f"code={body['code']}"))
    return body["data"] if body["data"] is not None else fallback


def extract_items(response_body: Any) -> list:
    """Old, broken helper (kept to prove the regression scenario)."""
    data = response_body if (
        isinstance(response_body, dict) and response_body.get("code") == 0
    ) else []
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return data["items"]
    if isinstance(data, list):
        return data
    return []


def extract_items_compat(response_body: Any) -> list:
    payload = unwrap_payload(response_body)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        return payload["items"]
    return []


def api_chain_checks() -> None:
    """Real DB + real API round trip, then unwrap exactly like the UI does."""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from fastapi.testclient import TestClient
    from app.core.database import Base, get_db
    from app.main import app

    # app.main inspects static/ at import time; a fresh clone may not have it.
    os.makedirs(os.path.join(BACKEND, "static"), exist_ok=True)

    fixture = os.path.join(HERE, "dbc", "mg100_demo.dbc")
    if not os.path.isfile(fixture):
        fixture = os.path.join(HERE, "fixtures", "mg100_demo.dbc")
    with open(fixture, "rb") as fh:
        content = fh.read()

    with tempfile.TemporaryDirectory() as td:
        engine = create_async_engine(f"sqlite+aiosqlite:///{td}/ui.db")
        Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async def prepare():
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

        asyncio.run(prepare())

        async def override_get_db():
            async with Session() as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db
        try:
            client = TestClient(app, raise_server_exceptions=False)

            up = client.post(
                "/api/dbc/upload",
                files={"file": ("mg100_demo.dbc", content, "text/plain")},
            )
            check("POST /api/dbc/upload -> 200", up.status_code == 200, str(up.status_code))
            imported = unwrap_payload(up.json())
            check("import payload unwraps to a real record",
                  isinstance(imported, dict) and bool(imported.get("id")), str(imported))
            file_id = (imported or {}).get("id")

            listed = client.get("/api/dbc/files")
            check("GET /api/dbc/files -> 200", listed.status_code == 200)
            raw = listed.json()
            check("files endpoint returns a BARE array (no code envelope)",
                  isinstance(raw, list) and (not raw or "code" not in raw[0]),
                  type(raw).__name__)
            check("old extractItems() reproduces the empty-UI bug",
                  extract_items(raw) == [], str(extract_items(raw)))
            rows = extract_items_compat(raw)
            check("extractItemsCompat() recovers the imported rows",
                  len(rows) == 1 and rows[0].get("id") == file_id, str(rows))
            check("row carries message/signal counts for the table",
                  bool(rows) and rows[0].get("message_count", 0) > 0
                  and rows[0].get("signal_count", 0) > 0, str(rows[:1]))

            # Both response shapes must keep working.
            wrapped = {"code": 0, "message": "success", "data": raw}
            check("compat helper also accepts the standard envelope",
                  extract_items_compat(wrapped) == rows)
            check("compat helper accepts {items:[...]} pagination shape",
                  extract_items_compat({"code": 0, "data": {"items": raw}}) == rows)
            try:
                unwrap_payload({"code": 1, "message": "boom", "data": None})
                rejected = False
            except ValueError:
                rejected = True
            check("non-zero envelope code surfaces as an error, not empty data", rejected)

            detail = client.get(f"/api/dbc/files/{file_id}")
            check("GET /api/dbc/files/{id} -> 200", detail.status_code == 200)
            doc = unwrap_payload(detail.json())
            messages = (doc or {}).get("messages") or []
            check("detail unwraps to messages", len(messages) == 3, str(len(messages)))
            signals = [s for m in messages for s in (m.get("signals") or [])]
            check("detail exposes signals for the picker", len(signals) >= 1,
                  str(len(signals)))

            spec_res = client.post(f"/api/dbc/signals/{signals[0]['id']}/parser-spec")
            check("POST parser-spec -> 200", spec_res.status_code == 200,
                  str(spec_res.status_code))
            spec = unwrap_payload(spec_res.json())
            check("generated ParserSpec has a name and signal geometry",
                  isinstance(spec, dict) and bool(spec.get("name"))
                  and "start" in spec and "length" in spec
                  and "byte_order" in spec, str(spec)[:220])

            dup = client.post(
                "/api/dbc/upload",
                files={"file": ("mg100_demo.dbc", content, "text/plain")},
            )
            dup_doc = unwrap_payload(dup.json())
            check("duplicate import is flagged, not a silent second row",
                  bool(dup_doc and dup_doc.get("duplicate"))
                  and len(extract_items_compat(client.get("/api/dbc/files").json())) == 1,
                  str(dup_doc))
        finally:
            app.dependency_overrides.pop(get_db, None)
            asyncio.run(engine.dispose())


def frontend_contract_checks() -> None:
    helper = text(os.path.join(FRONTEND, "services", "apiHelper.ts"))
    page = text(os.path.join(FRONTEND, "pages", "Dbc.tsx"))
    picker = text(os.path.join(FRONTEND, "components", "DbcSignalPicker.tsx"))
    messages = text(os.path.join(FRONTEND, "i18n", "messages.ts"))

    check("apiHelper exports unwrapPayload", "export function unwrapPayload" in helper)
    check("apiHelper exports extractItemsCompat",
          "export function extractItemsCompat" in helper)
    check("compat helper handles bare arrays",
          "if (Array.isArray(payload)) return payload as T[]" in helper)
    check("compat helper rejects non-zero envelope codes",
          "if (body.code !== 0)" in helper)

    for name, src in (("Dbc.tsx", page), ("DbcSignalPicker.tsx", picker)):
        check(f"{name}: list uses extractItemsCompat", "extractItemsCompat" in src)
        check(f"{name}: no broken extractItems() left", "extractItems(" not in src)
        check(f"{name}: detail/spec use unwrapPayload", "unwrapPayload" in src)

    check("Dbc.tsx validates import response id before showing success",
          "if (!payload || !payload.id)" in page)
    check("Dbc.tsx verifies the new row reached the refreshed list",
          "fresh.some(f => f.id === payload.id)" in page)
    check("Dbc.tsx distinguishes duplicate imports",
          "payload.duplicate ? t('dbc.importDuplicate')" in page)
    check("Dbc.tsx broadcasts the DBC change event",
          "window.dispatchEvent(new CustomEvent('aitestlab:dbc-changed'" in page)
    check("DbcSignalPicker listens for the DBC change event",
          "window.addEventListener('aitestlab:dbc-changed', refresh)" in picker)
    check("DbcSignalPicker still refreshes on open", "if (open)" in picker
          and "void loadFiles()" in picker)
    check("DbcSignalPicker refuses a blank ParserSpec",
          "if (!spec || !spec.name)" in picker)

    for key in ("dbc.importDuplicate", "dbc.importEmptyResult", "dbc.importNotListed"):
        check(f"i18n has {key} in zh + en", messages.count(f"'{key}'") == 2,
              str(messages.count(f"'{key}'")))


def launcher_checks() -> None:
    """The exe must open a standalone app window, not reuse a browser tab."""
    run_path = os.path.join(BACKEND, "run.py")
    src = text(run_path)
    check("run.py defines _open_app_window", "def _open_app_window(" in src)
    check("run.py uses --app= for a chromeless window", '--app={url}' in src)
    check("run.py isolates a dedicated browser profile",
          '--user-data-dir={profile}' in src and 'BrowserProfile' in src)
    check("run.py suppresses first-run / default-browser prompts",
          "--no-first-run" in src and "--no-default-browser-check" in src)
    check("run.py keeps an opt-out switch", "AITESTLAB_APP_WINDOW" in src)
    check("fallback asks for a NEW window, not a tab",
          "webbrowser.open(url, new=1, autoraise=True)" in src)
    check("headless smoke tests still suppress the browser",
          'AITESTLAB_NO_BROWSER' in src and '_open_browser_later' in src)
    check("health polling before opening is preserved",
          "_probe_app(port)" in src and "ProxyHandler({})" in src)

    spec = importlib.util.spec_from_file_location("aitestlab_run_under_test", run_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    with tempfile.TemporaryDirectory() as td:
        fake_exe = os.path.join(td, "chrome.exe")
        with open(fake_exe, "wb") as fh:
            fh.write(b"MZ")
        calls = []
        with patch.object(mod, "_data_dir", return_value=td), \
             patch.object(mod, "_browser_candidates", return_value=[fake_exe]), \
             patch("subprocess.Popen", side_effect=lambda args, **kw: calls.append((args, kw))):
            ok = mod._open_app_window("http://127.0.0.1:8123/")
        check("_open_app_window launches a browser", ok and len(calls) == 1, str(len(calls)))
        if calls:
            args = calls[0][0]
            check("app URL is passed via --app=",
                  "--app=http://127.0.0.1:8123/" in args, str(args[:3]))
            check("profile is a private per-app directory",
                  any(a.startswith("--user-data-dir=")
                      and a.endswith("BrowserProfile") for a in args), str(args[:3]))
            check("no tab-reuse flags leak into the app window",
                  not any(a in args for a in ("--new-tab", "--new-window")), str(args))

        # Prefer the dedicated window; never fall through to webbrowser.open.
        with patch.object(mod, "_open_app_window", return_value=True) as app_win, \
             patch("webbrowser.open", side_effect=AssertionError("fallback used")):
            os.environ.pop("AITESTLAB_APP_WINDOW", None)
            mod._open_browser_now(8123)
            check("_open_browser_now prefers the dedicated window",
                  app_win.call_count == 1, str(app_win.call_count))
            os.environ["AITESTLAB_APP_WINDOW"] = "0"
            try:
                with patch("webbrowser.open", return_value=True) as legacy:
                    mod._open_browser_now(8123)
                    check("opt-out still opens a new window",
                          legacy.called and legacy.call_args.kwargs.get("new") == 1,
                          str(legacy.call_args))
            finally:
                os.environ.pop("AITESTLAB_APP_WINDOW", None)

    candidates = mod._browser_candidates()
    print(f"  INFO  detected Chromium browsers on this host: {len(candidates)}")
    for path in candidates[:3]:
        print(f"        {path}")


def main() -> int:
    api_chain_checks()
    frontend_contract_checks()
    launcher_checks()
    if _failures:
        print(f"\nFAILED: {len(_failures)} check(s): {', '.join(_failures)}")
        return 1
    print("\nAll DBC UI contract + standalone window guards passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
