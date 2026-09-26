#!/usr/bin/env python3
"""
Verify the WebSocket feeds that back the two new monitoring windows:

  1. /ws/devices/{id}      -> command_sent / command_response / device_data
  2. /ws/executions/{id}   -> step_started / step_completed / execution_completed

Run: python3 Test/test_ws_monitor.py
"""
import asyncio
import json
import sys

import requests
import websockets

BASE = "http://127.0.0.1:8000/api"
WS = "ws://127.0.0.1:8000"

failures = []


def check(cond, msg):
    print(f"  [{'OK' if cond else 'FAIL'}] {msg}")
    if not cond:
        failures.append(msg)
    return cond


def pick_device():
    items = requests.get(f"{BASE}/devices/", timeout=10).json()["data"]["items"]
    return next(d for d in items if d["protocol"] == "mini_gateway100")


async def test_device_ws(dev_id):
    print("=== 1. 设备通信 WebSocket (/ws/devices) ===")
    async with websockets.connect(f"{WS}/ws/devices/{dev_id}") as ws:
        # give the server a moment to send the "connected" frame
        got = []
        try:
            first = await asyncio.wait_for(ws.recv(), timeout=5)
            got.append(json.loads(first))
        except asyncio.TimeoutError:
            pass

        # issue a command through the REST API - it must show up on the socket
        requests.post(f"{BASE}/devices/{dev_id}/command",
                      json={"command": "@11_HELLO;"}, timeout=20)

        deadline = asyncio.get_event_loop().time() + 8
        while asyncio.get_event_loop().time() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=2)
            except asyncio.TimeoutError:
                break
            msg = json.loads(raw)
            got.append(msg)
            if msg.get("type") == "command_response":
                break

        types = [m.get("type") for m in got]
        print(f"    收到消息类型: {types}")
        check("command_sent" in types, "收到 command_sent（下发帧）")
        check("command_response" in types, "收到 command_response（响应帧）")

        sent = next((m for m in got if m.get("type") == "command_sent"), {})
        resp = next((m for m in got if m.get("type") == "command_response"), {})
        print(f"    TX: {sent.get('command')!r}")
        print(f"    RX: {resp.get('response')!r}")
        check(sent.get("command") == "@11_HELLO;", "下发内容与命令一致")
        check(resp.get("response") not in (None, ""), "响应内容非空")


async def test_execution_ws(dev_id, tc_id):
    print("\n=== 2. 执行步骤 WebSocket (/ws/executions) ===")
    if dev_id and requests.get(f"{BASE}/devices/", timeout=10).json():
        pass
    r = requests.post(f"{BASE}/executions/run",
                      json={"test_case_id": tc_id, "options": {}}, timeout=60).json()
    if r.get("code") != 0:
        check(False, f"启动执行失败: {r}")
        return
    exec_id = r["data"]["id"]
    print(f"    execution: {exec_id}")

    async with websockets.connect(f"{WS}/ws/executions/{exec_id}") as ws:
        events = []
        deadline = asyncio.get_event_loop().time() + 60
        while asyncio.get_event_loop().time() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=3)
            except asyncio.TimeoutError:
                st = requests.get(f"{BASE}/executions/{exec_id}", timeout=20).json()["data"]
                if st["status"] in ("passed", "failed", "error", "stopped"):
                    break
                continue
            msg = json.loads(raw)
            events.append(msg)
            if msg.get("type") == "execution_completed":
                break

        types = [e.get("type") for e in events]
        steps = [e for e in events if e.get("type") in ("step_started", "step_completed")]
        print(f"    事件类型: {types}")
        print(f"    步骤事件数: {len(steps)}")
        for e in steps[:6]:
            print(f"      {e.get('type')}: step={e.get('step_index')} "
                  f"label={str(e.get('label'))[:34]!r} status={e.get('status')}")

        check(len(steps) > 0, f"收到步骤级实时事件 ({len(steps)} 条)")
        check("step_started" in types, "收到 step_started（步骤开始）")
        check("execution_completed" in types, "收到 execution_completed（执行结束）")

        started = [e for e in events if e.get("type") == "step_started"]
        check(all(e.get("step_index") is not None for e in started),
              "step_started 携带 step_index（用于定位流程图步骤）")


async def main():
    dev = pick_device()
    print(f"  设备: {dev['id']} ({dev['protocol']}) status={dev['status']}\n")
    if dev["status"] != "connected":
        requests.post(f"{BASE}/devices/connect", json={"device_id": dev["id"]}, timeout=30)

    await test_device_ws(dev["id"])
    await test_execution_ws(dev["id"], "tc_0c55f55c")

    print("\n" + "=" * 70)
    if failures:
        print(f"结果: {len(failures)} 项失败")
        for f in failures:
            print("  -", f)
        return 1
    print("结果: 两个监控窗口的实时数据源均正常")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
