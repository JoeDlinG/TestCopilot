#!/usr/bin/env python3
"""
End-to-end check: a test case execution must really talk to the device.

Before the fix, flow nodes of type "action" were never executed: the engine
fell through to a catch-all branch that marked every step PASSED with
"Step completed" (no command was sent, nothing was logged, and no CAN frame
ever left the box).

This script:
  1. connects the Mini Gateway 100
  2. runs a generated test case through the real execution engine
  3. verifies every step carries a real device response
  4. verifies rows were written to communication_logs

Run: python3 Test/test_execution_real.py
"""
import json
import sqlite3
import sys
import time

import requests

BASE = "http://127.0.0.1:8000/api"
DB = "/home/joelj/Documents/TestCopilot/backend/aitestlab.db"

failures = []


def check(cond, msg):
    print(f"  [{'OK' if cond else 'FAIL'}] {msg}")
    if not cond:
        failures.append(msg)
    return cond


def log_count():
    c = sqlite3.connect(DB)
    n = c.execute("select count(*) from communication_logs").fetchone()[0]
    c.close()
    return n


def connect(device_id):
    r = requests.post(f"{BASE}/devices/connect",
                      json={"device_id": device_id}, timeout=30).json()
    return r.get("code") == 0, r


def pick_test_case(want=None):
    """Pick a test case whose flow has 'action' nodes."""
    c = sqlite3.connect(DB)
    rows = c.execute(
        "select tc.id, tc.name, f.nodes from test_cases tc "
        "join test_flows f on f.testcase_id = tc.id "
        "order by tc.rowid desc limit 20"
    ).fetchall()
    c.close()
    fallback = None
    for tc_id, name, nodes in rows:
        try:
            parsed = json.loads(nodes)
        except Exception:
            continue
        if not any(n.get("type") == "action" for n in parsed):
            continue
        if want is None:
            return tc_id, name, parsed
        if want.lower() in tc_id.lower() or want.lower() in (name or "").lower():
            return tc_id, name, parsed
        if fallback is None:
            fallback = (tc_id, name, parsed)
    return fallback if fallback else (None, None, None)


def main():
    print("=== 1. 设备连接 ===")
    devices = requests.get(f"{BASE}/devices/", timeout=10).json()["data"]["items"]
    gw = next((d for d in devices if d["protocol"] == "mini_gateway100"), None)
    if not check(gw is not None, "找到 mini_gateway100 设备"):
        return 1
    ok, res = connect(gw["id"])
    if not check(ok, f"连接设备 {gw['id']}"):
        print("   ", res)
        return 1

    print("\n=== 2. 选择测试用例 ===")
    want = sys.argv[1] if len(sys.argv) > 1 else None
    tc_id, tc_name, nodes = pick_test_case(want)
    if not check(tc_id is not None, "找到含 action 节点的用例"):
        return 1
    steps = [n for n in nodes if n.get("type") not in ("start", "end")]
    print(f"  用例: {tc_name} ({tc_id}), 步骤数 {len(steps)}")

    print("\n=== 3. 执行 ===")
    before_logs = log_count()
    r = requests.post(f"{BASE}/executions/run",
                      json={"test_case_id": tc_id, "options": {}}, timeout=60).json()
    if not check(r.get("code") == 0, "启动执行"):
        print("   ", r)
        return 1
    exec_id = r["data"]["id"]
    total = r["data"].get("total_steps")
    print(f"  execution: {exec_id}, total_steps: {total}")
    check(total and total > 0, f"total_steps > 0 (实际 {total})")

    # wait for completion
    for _ in range(60):
        st = requests.get(f"{BASE}/executions/{exec_id}", timeout=20).json()["data"]
        if st.get("status") in ("passed", "failed", "completed", "error", "stopped"):
            break
        time.sleep(0.5)
    print(f"  最终状态: {st.get('status')}, "
          f"passed={st.get('passed_steps')}, failed={st.get('failed_steps')}")

    print("\n=== 4. 校验步骤真实执行 ===")
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    rows = c.execute(
        "select * from test_step_results where execution_id=? order by step_index",
        (exec_id,),
    ).fetchall()
    c.close()
    check(len(rows) > 0, f"产生了 {len(rows)} 条步骤记录")
    simulated = 0
    notrun = 0
    real = 0
    for r in rows:
        d = dict(r)
        actual = (d.get("actual") or "").strip()
        cmd = (d.get("command") or "")[:60]
        dur = d.get("duration_ms")
        print(f"    step{d['step_index']:>2} [{d['status']:>6}] {dur:>5}ms "
              f"{cmd} -> {actual[:90]}")
        if "Step completed" in actual or "[Simulated]" in actual:
            simulated += 1
        elif actual.startswith("[未执行]"):
            notrun += 1
        elif actual:
            real += 1
    check(simulated == 0, f"没有步骤停留在模拟/占位状态 (发现 {simulated})")
    check(notrun == 0, f"没有步骤因缺少设备而未执行 (发现 {notrun})")
    check(real > 0, f"存在真实设备响应 (共 {real} 步)")

    print("\n=== 4b. 校验周期发送真的在设备侧运行 ===")
    # If the case started a PROCESS, the device keeps a loop counter. A
    # non-zero / growing counter proves frames were actually emitted.
    try:
        r1 = requests.post(f"{BASE}/devices/{gw['id']}/command",
                           json={"command": "@11_PROCESS=1,DEFINE;"}, timeout=20).json()
        time.sleep(1.0)
        r2 = requests.post(f"{BASE}/devices/{gw['id']}/command",
                           json={"command": "@11_PROCESS=1,DEFINE;"}, timeout=20).json()
    except Exception as e:
        print(f"  [WARN] 查询进程状态失败: {e}")
        r1 = r2 = None
    if r1 and r2 and r1.get("code") == 0 and r2.get("code") == 0:
        a, b = r1["data"]["response"], r2["data"]["response"]
        print(f"    DEFINE: {a!r} -> {b!r}")
        import re as _re
        m1, m2 = _re.search(r"LOOP=(\d+)", str(a)), _re.search(r"LOOP=(\d+)", str(b))
        if m1 and m2:
            l1, l2 = int(m1.group(1)), int(m2.group(1))
            print(f"    LOOP {l1} -> {l2} (1s 内 +{l2 - l1})")
            if l2 > l1:
                print("  [OK] 设备侧进程仍在循环执行 -> CAN 报文持续发送到总线")
            elif l2 > 0:
                print("  [OK] 设备侧累计循环计数 > 0 -> 周期内确实发送过 CAN 报文")
            else:
                print("  [ -- ] 该用例未留下运行中的进程（可能已 STOP 或未使用 PROCESS）")
        else:
            print("  [ -- ] 未解析到 LOOP 计数")
    # clean up: make sure no process keeps transmitting
    try:
        requests.post(f"{BASE}/devices/{gw['id']}/command",
                      json={"command": "@11_PROCESS=1,STOP;"}, timeout=20)
        requests.post(f"{BASE}/devices/{gw['id']}/command",
                      json={"command": "@11_TSTOP;"}, timeout=20)
    except Exception:
        pass

    print("\n=== 5. 校验通信日志 ===")
    after_logs = log_count()
    delta = after_logs - before_logs
    check(delta > 0, f"通信日志新增 {delta} 条 (执行前 {before_logs} -> 执行后 {after_logs})")

    c = sqlite3.connect(DB)
    recent = c.execute(
        "select timestamp, direction, substr(raw_data,1,70) from communication_logs "
        "order by timestamp desc limit 8"
    ).fetchall()
    c.close()
    print("  最近日志:")
    for ts, direction, data in recent:
        print(f"    {ts}  {direction:<8} {data}")

    print("\n" + "=" * 70)
    if failures:
        print(f"结果: {len(failures)} 项失败")
        for f in failures:
            print("  -", f)
        return 1
    print("结果: 执行引擎真实下发指令，通信日志有记录 —— 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
