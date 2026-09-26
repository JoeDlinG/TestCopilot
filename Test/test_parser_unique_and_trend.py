#!/usr/bin/env python3
"""
Tests for parser-name uniqueness and the historical parsed-value trend API.

  1. duplicate field names are rejected (same step AND across steps)
  2. empty name is rejected
  3. unique names are accepted; after a run the values are stored and
     readable through the trend endpoint (no separate trend table)

Run: python3 Test/test_parser_unique_and_trend.py
"""
import json
import sqlite3
import sys
import time

import requests

BASE = "http://127.0.0.1:8000/api"
DB = "backend/aitestlab.db"
TC = "tc_1af8a2b8"

failures = []


def check(cond, msg):
    print(f"  [{'OK' if cond else 'FAIL'}] {msg}")
    if not cond:
        failures.append(msg)
    return cond


def ensure_column():
    conn = sqlite3.connect(DB)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(test_step_results)")]
    if "parsed_results" not in cols:
        conn.execute("ALTER TABLE test_step_results ADD COLUMN parsed_results TEXT")
        conn.commit()
    conn.close()


def get_flow():
    return requests.get(f"{BASE}/testcases/{TC}/flow", timeout=20).json()["data"]


def save_flow(nodes, edges):
    return requests.put(
        f"{BASE}/testcases/{TC}/flow", json={"nodes": nodes, "edges": edges}, timeout=30
    )


def main():
    ensure_column()
    devices = requests.get(f"{BASE}/devices/", timeout=10).json()["data"]["items"]
    dev = next(d for d in devices if d["protocol"] == "mini_gateway100")
    if dev["status"] != "connected":
        requests.post(f"{BASE}/devices/connect", json={"device_id": dev["id"]}, timeout=30)

    flow = get_flow()
    nodes, edges = flow["nodes"], flow["edges"]
    actions = [n for n in nodes if n.get("type") not in ("start", "end")]
    check(len(actions) >= 2, f"用例有 {len(actions)} 个可执行步骤")

    a, b = actions[0], actions[3] if len(actions) > 3 else actions[1]

    def with_parsers(node, parsers):
        node = dict(node)
        cfg = dict(node.get("config") or {})
        cfg["parsers"] = parsers
        node["config"] = cfg
        return node

    def rebuild(parsers_a, parsers_b):
        return [
            with_parsers(n, parsers_a) if n["id"] == a["id"]
            else with_parsers(n, parsers_b) if n["id"] == b["id"]
            else n
            for n in nodes
        ]

    spec = lambda name, **kw: {
        "name": name, "data_type": kw.get("data_type", "dec"),
        "start": kw.get("start", 0), "length": kw.get("length", 4),
        "unit": "byte", "conditions": kw.get("conditions", {}),
    }

    # ---------------------------------------------------------------- #
    print("=== 1. 名称唯一性校验 ===")
    r = save_flow(
        rebuild([spec("电压"), spec("电压")], []), edges
    )
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    check(r.status_code == 400, f"同一步骤内重名被拒绝 (HTTP {r.status_code})")
    check("重复" in json.dumps(body, ensure_ascii=False), "错误信息提示名称重复")

    r = save_flow(rebuild([spec("电压")], [spec("电压")]), edges)
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    check(r.status_code == 400, f"跨步骤重名被拒绝 (HTTP {r.status_code})")
    check("重复" in json.dumps(body, ensure_ascii=False), "错误信息提示名称重复")

    r = save_flow(rebuild([spec("   ")], []), edges)
    check(r.status_code == 400, f"空名称被拒绝 (HTTP {r.status_code})")

    # ---------------------------------------------------------------- #
    print("\n=== 2. 唯一名称可保存 ===")
    r = save_flow(
        rebuild(
            [spec("版本序号", conditions={"min": 1000, "max": 3000})],
            [spec("循环标识", data_type="string", start=0, length=4)],
        ),
        edges,
    )
    check(r.status_code == 200, f"唯一名称保存成功 (HTTP {r.status_code})")

    # ---------------------------------------------------------------- #
    print("\n=== 3. 执行后解析值落库并可读趋势 ===")
    run = requests.post(
        f"{BASE}/executions/run", json={"test_case_id": TC, "options": {}}, timeout=60
    ).json()
    check(run.get("code") == 0, "启动执行成功")
    exec_id = run["data"]["id"]

    deadline = time.time() + 180
    while time.time() < deadline:
        st = requests.get(f"{BASE}/executions/{exec_id}", timeout=20).json()["data"]
        if st["status"] in ("passed", "failed", "error", "stopped"):
            break
        time.sleep(1)

    stored = []
    for s in st.get("step_results", []):
        if s.get("parsed_results"):
            stored.extend(json.loads(s["parsed_results"]))
    names = [p["name"] for p in stored]
    print(f"    落库解析项: {names}")
    check("版本序号" in names, "解析值已落库（版本序号）")
    check("循环标识" in names, "解析值已落库（循环标识）")
    check(any(p["name"] == "版本序号" and p["ok"] for p in stored), "范围内判定 PASS")

    # judgement failure is a result, not an alarm: force one and confirm FAIL
    save_flow(
        rebuild(
            [spec("版本序号", conditions={"min": 9000, "max": 9999})],
            [spec("循环标识", data_type="string", start=0, length=4)],
        ),
        edges,
    )
    run2 = requests.post(
        f"{BASE}/executions/run", json={"test_case_id": TC, "options": {}}, timeout=60
    ).json()
    exec_id2 = run2["data"]["id"]
    deadline = time.time() + 180
    while time.time() < deadline:
        st2 = requests.get(f"{BASE}/executions/{exec_id2}", timeout=20).json()["data"]
        if st2["status"] in ("passed", "failed", "error", "stopped"):
            break
        time.sleep(1)
    failed = [
        p for s in st2.get("step_results", [])
        if s.get("parsed_results")
        for p in json.loads(s["parsed_results"])
        if p["name"] == "版本序号" and not p["ok"]
    ]
    check(bool(failed), "超出上下限 -> 判定 FAIL（作为测试结果记录）")
    step_failed = any(
        s["status"] == "failed" for s in st2.get("step_results", [])
    )
    check(step_failed, "判定 FAIL 时该步骤状态为 failed")

    # ---------------------------------------------------------------- #
    print("\n=== 4. 历史趋势接口（不新建表）===")
    trend = requests.get(f"{BASE}/testcases/{TC}/parsed-trend?limit=20", timeout=30).json()
    data = trend.get("data", {})
    print(f"    fields={data.get('fields')} 点数={data.get('total_points')}")
    check(trend.get("code") == 0, "趋势接口返回成功")
    check("版本序号" in (data.get("fields") or []), "趋势包含字段 版本序号")
    series = (data.get("series") or {}).get("版本序号") or []
    check(len(series) >= 2, f"趋势有多个采样点 ({len(series)})")
    check(all("num" in p for p in series), "每个点带数值 num")
    check(
        any(p.get("ok") is False for p in series) or any(p.get("ok") for p in series),
        "趋势点带判定结果 ok",
    )
    # chronological order: executions listed oldest -> newest
    execs = data.get("executions") or []
    check(len(execs) >= 2, f"趋势覆盖多次执行 ({len(execs)})")

    # restore
    for n in nodes:
        if isinstance(n.get("config"), dict):
            n["config"].pop("parsers", None)
    save_flow(nodes, edges)
    print("\n  (已清除测试用的解析配置)")

    print("\n" + "=" * 70)
    if failures:
        print(f"结果: {len(failures)} 项失败")
        for f in failures:
            print("  -", f)
        return 1
    print("结果: 名称唯一性校验 + 趋势（复用落库数据）全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
