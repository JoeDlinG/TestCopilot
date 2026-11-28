#!/usr/bin/env python3
"""Real-browser E2E for the DBC import -> parser config -> UI chain.

Unlike the pure-Python contract suite, this one renders the actual React UI in
Chromium and performs the import through the hidden file input, then walks the
whole "pick a DBC signal -> generate parser spec -> save -> reopen" flow.

Optional by design: it needs Playwright + a running backend, and is NOT part of
``run_all.sh`` (which must stay hardware/browser independent).

Usage:
  AITESTLAB_E2E_BASE=http://127.0.0.1:8011 \
    <envs/default>/python.exe Test/e2e_dbc_ui.py
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
BASE = os.environ.get("AITESTLAB_E2E_BASE", "http://127.0.0.1:8011").rstrip("/")
SHOTS = os.path.join(ROOT, ".build_tmp")
FIXTURE_DBC = os.path.join(ROOT, "Test", "dbc", "mg100_demo.dbc")


def make_unique_dbc():
    """Content-hash de-duplication means a byte-identical re-run adds no row.

    Append a unique DBC comment so every E2E run really exercises the
    import -> persist -> refresh -> render path.
    """
    import time
    os.makedirs(SHOTS, exist_ok=True)
    stamp = time.strftime("%H%M%S")
    path = os.path.join(SHOTS, f"e2e_dbc_{stamp}.dbc")
    with open(FIXTURE_DBC, encoding="utf-8") as fh:
        text = fh.read()
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"{text}\n// AITestLab DBC UI E2E {stamp}\n")
    return path

_op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_fails = []


def check(label, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + label + (f"  -> {detail}" if detail else ""))
    if not ok:
        _fails.append(label)


def api(method, path, body=None):
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with _op.open(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(raw)
        except ValueError:
            return exc.code, raw[:300]


def service_ready():
    try:
        with _op.open(BASE + "/api/health", timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def seed_baseline_dbc():
    """Guarantee at least one imported file so list rendering can be checked."""
    with _op.open(BASE + "/api/dbc/files", timeout=8) as resp:
        rows = json.loads(resp.read().decode("utf-8"))
    if rows:
        return
    path = os.path.join(ROOT, "Test", "dbc", "mg100_demo.dbc")
    with open(path, "rb") as fh:
        content = fh.read()
    boundary = "----aitestlabe2ebaseline"
    body = (
        (f"--{boundary}\r\n").encode()
        + b'Content-Disposition: form-data; name="file"; filename="mg100_demo.dbc"\r\n'
        + b"Content-Type: text/plain\r\n\r\n" + content + b"\r\n"
        + (f"--{boundary}--\r\n").encode()
    )
    req = urllib.request.Request(
        BASE + "/api/dbc/upload", data=body, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with _op.open(req, timeout=20) as resp:
        json.loads(resp.read().decode("utf-8"))


def seed_case():
    """Create one test case with a single step so the parser dialog can open."""
    st, res = api("POST", "/api/testcases/", {"name": "DBC-E2E-临时用例", "tags": ["e2e"]})
    if st != 200:
        return None
    tc_id = (res.get("data") or {}).get("id") or res.get("id")
    if not tc_id:
        return None
    nodes = [{
        "id": "step_e2e_1", "type": "default",
        "position": {"x": 100, "y": 100},
        "data": {"label": "步骤1"},
        "config": {"command": "READ"},
    }]
    api("POST", f"/api/testcases/{tc_id}/flow", {"nodes": nodes, "edges": []})
    return tc_id


def main() -> int:
    if not service_ready():
        print(f"  [SKIP] backend not responding at {BASE}")
        return 0
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  [SKIP] Playwright is not installed in this interpreter")
        return 0

    os.makedirs(SHOTS, exist_ok=True)
    seed_baseline_dbc()
    dbc_file = make_unique_dbc()
    errors = []
    tc_id = None
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-proxy-server"])
        context = browser.new_context(
            viewport={"width": 1440, "height": 960}, locale="zh-CN",
        )
        page = context.new_page()
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        try:
            # ---------- 1. DBC list renders imported data ----------
            page.goto(BASE + "/dbc", wait_until="networkidle", timeout=30000)
            page.wait_for_selector(".ant-table, .ant-empty", timeout=15000)
            check("DBC page mounted",
                  bool(re.search(r"DBC (数据库|Database)", page.locator("body").inner_text())))
            rows_before = page.locator(".ant-table-tbody tr:not(.ant-table-placeholder)").count()
            check("DBC list is not blank before the new import", rows_before >= 1,
                  f"rows={rows_before}")
            page.screenshot(path=os.path.join(SHOTS, "e2e_dbc_01_list_before.png"))

            # ---------- 2. import via the real hidden file input ----------
            page.locator("input[type=file]").set_input_files(dbc_file)
            page.wait_for_timeout(1200)
            toast = page.locator(".ant-message-notice-content").all_inner_texts()
            check("import success toast shown",
                  any(re.search(r"导入成功|已导入|Imported", x) for x in toast), str(toast))
            page.wait_for_function(
                "() => document.querySelectorAll('.ant-table-tbody tr:not(.ant-table-placeholder)').length > %d"
                % rows_before, timeout=15000,
            )
            body_text = page.locator(".ant-table-tbody").inner_text()
            check("newly imported DBC appears in the table",
                  os.path.splitext(os.path.basename(dbc_file))[0] in body_text,
                  body_text[:200].replace("\n", " | "))
            check("table shows message/signal counts",
                  any(ch.isdigit() for ch in body_text), body_text[:200].replace("\n", " | "))
            page.screenshot(path=os.path.join(SHOTS, "e2e_dbc_02_list_after.png"))

            # ---------- 3. detail view with messages + signals ----------
            page.get_by_role("button", name=re.compile("查看|View")).first.click()
            page.wait_for_selector(".ant-table-row-expand-icon", timeout=15000)
            detail = page.locator(".ant-table-tbody").first.inner_text()
            check("detail view lists CAN messages", "0x" in detail,
                  detail[:180].replace("\n", " | "))
            page.locator(".ant-table-row-expand-icon").first.click()
            page.wait_for_timeout(600)
            expanded = page.locator(".ant-table-expanded-row").first.inner_text()
            check("expanded message shows signals", "EngineSpeed" in expanded
                  or "Speed" in expanded or len(expanded.strip()) > 20,
                  expanded[:180].replace("\n", " | "))
            page.screenshot(path=os.path.join(SHOTS, "e2e_dbc_03_detail.png"))

            # ---------- 4. parser config dialog ----------
            tc_id = seed_case()
            check("seed test case created", bool(tc_id), str(tc_id))
            page.goto(BASE + "/testcases", wait_until="networkidle", timeout=30000)
            page.wait_for_selector(".ant-table-row-expand-icon", timeout=15000)
            page.locator(".ant-table-row-expand-icon").first.click()
            page.wait_for_timeout(700)
            page.get_by_role("button", name=re.compile("解析配置|Parser config")).first.click()
            page.wait_for_timeout(700)
            check("parser config dialog opened",
                  page.locator(".ant-modal").filter(has_text="结果解析配置").count() >= 1)
            page.get_by_role("button", name=re.compile("从 DBC 信号生成|Generate from DBC signal")).click()
            page.wait_for_timeout(900)
            picker = page.locator(".ant-modal").filter(has_text=re.compile("选择 DBC 信号|Pick a DBC signal")).last
            picker_text = picker.inner_text()
            check("DBC picker no longer shows the empty state",
                  not re.search(r"暂无 DBC 文件|No DBC files", picker_text),
                  picker_text[:160].replace("\n", " | "))
            check("DBC picker lists imported files",
                  "mg100_demo" in picker_text or "body_chassis" in picker_text,
                  picker_text[:160].replace("\n", " | "))
            page.screenshot(path=os.path.join(SHOTS, "e2e_dbc_04_picker.png"))

            # ---------- 5. generate a parser spec and save it ----------
            picker.get_by_role("button", name=re.compile("查看|View")).first.click()
            page.wait_for_selector(".ant-modal .ant-table-row-expand-icon", timeout=15000)
            page.locator(".ant-modal .ant-table-row-expand-icon").first.click()
            page.wait_for_timeout(700)
            picker.get_by_role("button", name=re.compile("生成解析项|Generate spec")).first.click()
            page.wait_for_timeout(900)
            cfg = page.locator(".ant-modal").filter(has_text="结果解析配置").last
            cfg_text = cfg.inner_text()
            check("generated parser row is visible in parser config",
                  bool(re.search(r"添加解析项|Add parser", cfg_text))
                  and page.locator(".ant-modal input").count() > 0,
                  cfg_text[:160].replace("\n", " | "))
            page.screenshot(path=os.path.join(SHOTS, "e2e_dbc_05_parser_filled.png"))
            cfg.get_by_role("button", name=re.compile("保存解析配置|Save parser")).click()
            page.wait_for_timeout(1200)
            saved = page.locator(".ant-message-notice-content").all_inner_texts()
            check("parser config saved",
                  any(re.search(r"已保存|saved", x, re.I) for x in saved), str(saved))

            # ---------- 6. reopen: the row was persisted ----------
            page.get_by_role("button", name=re.compile("解析配置|Parser config")).first.click()
            page.wait_for_timeout(800)
            reopened = page.locator(".ant-modal").filter(has_text="结果解析配置").last
            values = reopened.locator("input").evaluate_all(
                "els => els.map(e => e.value).filter(Boolean)")
            check("reopened dialog keeps DBC-generated parser name",
                  any(v and v != "字段1" for v in values), str(values[:8]))
            page.screenshot(path=os.path.join(SHOTS, "e2e_dbc_06_parser_reopened.png"))
        finally:
            if tc_id:
                api("DELETE", f"/api/testcases/{tc_id}")
            browser.close()

    check("no uncaught browser page errors", not errors, str(errors[:3]))
    if _fails:
        print(f"\nFAILED: {len(_fails)} check(s): {', '.join(_fails)}")
        return 1
    print("\nDBC import -> parser config -> UI browser E2E passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
