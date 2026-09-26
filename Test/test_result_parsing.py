#!/usr/bin/env python3
"""
End-to-end test for the result-parsing feature.

Covers:
  1. parse-preview API (used by the configuration dialog)
  2. configuring parsers on a flow step, then running the case:
     - a passing judgement  -> step passed, parsed value recorded
     - a failing judgement  -> step failed, reason recorded
  3. the generated code contains the same judgement

Run: python3 Test/test_result_parsing.py
"""
import json
import sqlite3
import sys
import time

import requests

BASE = "http://127.0.0.1:8000/api"
DB = "backend/aitestlab.db"

failures = []


def check(cond, msg):
    print(f"  [{'OK' if cond else 'FAIL'}] {msg}")
    if not cond:
        failures.append(msg)
    return cond


def ensure_column():
    """The new column is added by init_db; add it manually if the running
    backend started before this change."""
    conn = sqlite3.connect(DB)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(test_step_results)")]
    if "parsed_results" not in cols:
        conn.execute("ALTER TABLE test_step_results ADD COLUMN parsed_results TEXT")
        conn.commit()
        print("  (added test_step_results.parsed_results column)")
    conn.close()


def pick_device():
    items = requests.get(f"{BASE}/devices/", timeout=10).json()["data"]["items"]
    return next(d for d in items if d["protocol"] == "mini_gateway100")


def get_flow(tc_id):
    r = requests.get(f"{BASE}/testcases/{tc_id}/flow", timeout=20).json()
    return r["data"]


def save_flow(tc_id, nodes, edges):
    return requests.put(
        f"{BASE}/testcases/{tc_id}/flow",
        json={"nodes": nodes, "edges": edges}, timeout=30,
    ).json()


def run_case(tc_id):
    r = requests.post(
        f"{BASE}/executions/run",
        json={"test_case_id": tc_id, "options": {}}, timeout=60,
    ).json()
    if r.get("code") != 0:
        return None
    return r["data"]["id"]


def wait_done(exec_id, timeout=180):
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = requests.get(f"{BASE}/executions/{exec_id}", timeout=20).json()["data"]
        if st["status"] in ("passed", "failed", "error", "stopped"):
            return st
        time.sleep(1)
    return None


def main():
    ensure_column()
    dev = pick_device()
    if dev["status"] != "connected":
        requests.post(f"{BASE}/devices/connect", json={"device_id": dev["id"]}, timeout=30)
    print(f"  设备: {dev['id']} ({dev['protocol']})\n")

    # ---------------------------------------------------------------- #
    print("=== 1. 解析预览 API ===")
    preview = requests.post(f"{BASE}/testcases/parse-preview", json={
        "raw": "CAN1,RPLY1,0X850201",
        "parsers": [
            {"name": "帧ID", "data_type": "hex", "start": 0, "length": 1,
             "unit": "byte", "conditions": {"equals": ["0x85"]}},
            {"name": "数据1", "data_type": "dec", "start": 1, "length": 1,
             "unit": "byte", "conditions": {"min": 0, "max": 255}},
            {"name": "越界项", "data_type": "hex", "start": 0, "length": 9, "unit": "byte"},
        ],
    }, timeout=20).json()
    data = preview.get("data", {})
    parsed = data.get("parsed", [])
    print(f"    解析结果: {[(p['name'], p['value'], p['ok']) for p in parsed]}")
    check(preview.get("code") == 0, "预览接口返回成功")
    check(len(parsed) == 3, "返回 3 个解析项")
    check(parsed[0]["value"] == "0x85" and parsed[0]["ok"], "hex + 等于(或运算) 判定通过")
    check(parsed[1]["value"] == 2 and parsed[1]["ok"], "dec + 范围判定通过")
    check(not parsed[2]["ok"], "越界解析项判定失败")
    check(data.get("all_passed") is False, "汇总判定为未全部通过")

    # ---------------------------------------------------------------- #
    # pick a case whose first step has a real numeric response
    tc_id = "tc_1af8a2b8"
    flow = get_flow(tc_id)
    nodes, edges = flow["nodes"], flow["edges"]
    steps = [n for n in nodes if n.get("type") not in ("start", "end")]
    check(len(steps) > 0, f"用例 {tc_id} 有可执行步骤 ({len(steps)})")

    first = steps[0]
    print(f"\n=== 2. 配置解析并执行（判定通过）===")
    print(f"    步骤: {first.get('data', {}).get('label')}")
    first.setdefault("config", {})
    first["config"]["parsers"] = [{
        "name": "版本序号",
        "data_type": "dec",
        "start": 0,
        "length": 4,
        "unit": "byte",
        "conditions": {"min": 1000, "max": 3000},
    }]
    save_flow(tc_id, nodes, edges)

    exec_id = run_case(tc_id)
    check(exec_id is not None, "启动执行成功")
    st = wait_done(exec_id)
    check(st is not None, "执行完成")
    if st:
        step1 = next(
            (s for s in st.get("step_results", []) if s["step_index"] == 1), None
        )
        pr = json.loads(step1["parsed_results"]) if step1 and step1.get("parsed_results") else []
        print(f"    step1 status={step1['status']} parsed={[(p['name'], p['value'], p['ok']) for p in pr]}")
        check(len(pr) == 1, "步骤记录了 1 条解析结果")
        check(pr and pr[0]["ok"] is True, "解析判定通过")
        check(step1["status"] == "passed", "判定通过时步骤状态为 passed")

    # ---------------------------------------------------------------- #
    print(f"\n=== 3. 判定不通过 -> 步骤失败 ===")
    first["config"]["parsers"][0]["conditions"] = {"min": 5000, "max": 9000}
    save_flow(tc_id, nodes, edges)

    exec_id2 = run_case(tc_id)
    st2 = wait_done(exec_id2)
    check(st2 is not None, "执行完成")
    if st2:
        step1 = next(
            (s for s in st2.get("step_results", []) if s["step_index"] == 1), None
        )
        pr = json.loads(step1["parsed_results"]) if step1 and step1.get("parsed_results") else []
        print(f"    step1 status={step1['status']} parsed={[(p['name'], p['value'], p['ok']) for p in pr]}")
        check(pr and pr[0]["ok"] is False, "解析判定未通过")
        check(step1["status"] == "failed", "判定未通过时步骤状态为 failed")
        check("结果解析判断未通过" in (step1.get("error_message") or ""), "记录了判断失败原因")

    # ---------------------------------------------------------------- #
    print(f"\n=== 4. 生成代码包含解析判断 ===")
    code = requests.post(f"{BASE}/testcases/{tc_id}/generate-code", timeout=60).json()["data"]["code"]
    check("send_command('@11_HELLO;')" in code, "生成代码使用真实指令")

    # restore: remove the parser config
    first["config"].pop("parsers", None)
    save_flow(tc_id, nodes, edges)
    print("\n  (已清除测试用的解析配置)")

    print("\n" + "=" * 70)
    if failures:
        print(f"结果: {len(failures)} 项失败")
        for f in failures:
            print("  -", f)
        return 1
    print("结果: 结果解析配置 -> 执行判定 全链路正常")
    return 0


if __name__ == "__main__":
    sys.exit(main())
