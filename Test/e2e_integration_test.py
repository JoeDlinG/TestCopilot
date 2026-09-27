#!/usr/bin/env python3
"""端到端集成测试：设备 -> AI 生成用例 -> 执行 -> 报告。

覆盖完整业务链路：
  1. 选取已连接的设备（作为 AI 生成的可用设备上下文）；
  2. 调用 AI 生成测试用例并落库；
  3. 执行生成出的用例；
  4. 基于执行结果生成测试报告并下载校验。

运行前请确保后端 (uvicorn, :8000) 与前端已启动。
退出码 0 表示全链路通过，非 0 表示失败。
"""
import json
import sys
import time
import urllib.request
import urllib.error

BASE = "http://localhost:8000/api"

passed, failed = [], []


def check(name, ok, detail=""):
    (passed if ok else failed).append(name)
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}" + (f" -- {detail}" if detail else ""))


def call(method, path, body=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path, data=data,
        headers={"Content-Type": "application/json"}, method=method,
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def main():
    print("=== E2E Integration Test: device -> AI gen -> execute -> report ===\n")

    # ---------- 1. 设备 ----------
    devs = call("GET", "/devices/").get("data", {}).get("items", [])
    connected = [d for d in devs if d.get("status") == "connected"]
    check("device: backend reachable & device list fetched", bool(devs), f"{len(devs)} devices")
    check("device: at least one connected device", bool(connected),
          f"connected={[d['name'] for d in connected]}")
    available_devices = [
        {"id": d["id"], "name": d["name"], "type": d["type"],
         "protocol": d["protocol"], "connection_type": d.get("connection_type")}
        for d in connected
    ]

    # ---------- 2. AI 生成用例 ----------
    requirements = (
        "对 Mini Gateway 100 网关联接设备进行 CAN 总线周期性报文发送，"
        "并验证是否能收到预期的回复报文；包含初始化、周期发送、接收校验、结果判定等步骤。"
    )
    try:
        gen = call("POST", "/testcases/generate", {
            "requirements": requirements,
            "available_devices": available_devices,
            "model_id": None,  # 使用默认模型
        }, timeout=180)
        saved = (gen.get("data") or {}).get("saved_cases", [])
        check("ai-gen: request succeeded (code==0)", gen.get("code") == 0,
              f"http code={gen.get('code')}")
        check("ai-gen: at least one test case saved", bool(saved),
              f"saved={len(saved)}")
    except Exception as e:
        check("ai-gen: request succeeded", False, f"exception={e}")
        saved = []

    if not saved:
        print("\nSUMMARY: generation produced no cases; aborting remaining steps.")
        print_summary()
        return 1

    tc_id = saved[0]["id"]
    check("ai-gen: test case has flow linked",
          bool(saved[0].get("flow_id")), f"flow_id={saved[0].get('flow_id')}")

    # ---------- 3. 执行 ----------
    try:
        run = call("POST", "/executions/run", {"test_case_id": tc_id}, timeout=120)
        exec_id = (run.get("data") or {}).get("id") or (run.get("data") or {}).get("execution_id")
        check("execute: run started (code==0)", run.get("code") == 0, f"exec_id={exec_id}")
    except Exception as e:
        check("execute: run started", False, f"exception={e}")
        exec_id = None

    if exec_id:
        # poll until terminal
        terminal = {"completed", "passed", "failed", "stopped", "error", "aborted"}
        final = None
        for _ in range(120):
            try:
                st = call("GET", f"/executions/{exec_id}", timeout=20)
                final = (st.get("data") or {})
                if final.get("status") in terminal:
                    break
            except Exception:
                pass
            time.sleep(2)
        check("execute: reached terminal state",
              final is not None and final.get("status") in terminal,
              f"status={final.get('status') if final else None}")
        check("execute: produced step results",
              (final or {}).get("total_steps", 0) > 0,
              f"total={final.get('total_steps')} passed={final.get('passed_steps')} "
              f"failed={final.get('failed_steps')}")
    else:
        final = None

    # ---------- 4. 报告 ----------
    if exec_id:
        try:
            rep = call("POST", "/reports/generate", {
                "title": "E2E 集成测试报告 - MG100 CAN 周期发送",
                "execution_id": exec_id,
                "format": "html",
            }, timeout=60)
            rep_data = rep.get("data") or {}
            rid = rep_data.get("id")
            check("report: generated (code==0)", rep.get("code") == 0, f"report_id={rid}")
            check("report: status == generated",
                  rep_data.get("status") == "generated",
                  f"status={rep_data.get('status')}")
            # verify downloadable
            if rid:
                try:
                    req = urllib.request.Request(BASE + f"/reports/{rid}/download")
                    with urllib.request.urlopen(req, timeout=30) as r:
                        size = len(r.read())
                    check("report: downloadable file exists", size > 0, f"bytes={size}")
                except Exception as e:
                    check("report: downloadable file exists", False, f"exception={e}")
        except Exception as e:
            check("report: generated", False, f"exception={e}")

    print_summary()
    return 0 if not failed else 1


def print_summary():
    print("\n=== SUMMARY ===")
    print(f"PASS ({len(passed)}): {', '.join(passed)}")
    if failed:
        print(f"FAIL ({len(failed)}): {', '.join(failed)}")
    else:
        print("ALL STEPS PASSED ✓")


if __name__ == "__main__":
    sys.exit(main())
