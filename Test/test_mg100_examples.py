#!/usr/bin/env python3
"""
Execute the two test scenarios from Test/TestExample against the real
Mini Gateway 100, using the command syntax defined in the (fixed) skill.

Test 1: 通过 mini Gateway 100 每隔 200ms 发送一条 CAN 消息 0x850201 (ID 0x13)，
        并显示回复的消息。
Test 2: 连接 mini-Gateway100，读取数字通道 1，如果读到是 0，则通过 CAN1 发送
        CAN 消息 0x850102 (ID 0x10)，并读取回复的消息；如果没有回复，提示 time out。

Run: python3 Test/test_mg100_examples.py
"""
import re
import sys
import time

import requests

BASE = "http://127.0.0.1:8000/api"

# A command that the device does not understand produces NO reply at all
# (the plugin then blocks for its read timeout). These responses are explicit
# device-side rejections.
ERROR_WORDS = ("NOT_SUPPORT", "WRONGPARA", "OUTOFRANGE", "UNAVAILABLE", "UNKNOWN")

failures = []


def find_device():
    r = requests.get(f"{BASE}/devices/", timeout=10).json()
    devices = r.get("data", r)
    if isinstance(devices, dict):
        devices = devices.get("items", [])
    candidates = [d for d in devices if d.get("protocol") == "mini_gateway100"]
    connected = [d for d in candidates if d.get("status") == "connected"]
    return (connected or candidates)[0]["id"] if candidates else None


def ensure_connected(device_id):
    """(Re)connect the device if the backend lost its in-memory connection."""
    r = requests.get(f"{BASE}/devices/{device_id}", timeout=10).json()
    d = r.get("data", r)
    if d.get("status") == "connected":
        return True
    print(f"设备当前未连接，正在连接 {device_id} ...")
    try:
        res = requests.post(
            f"{BASE}/devices/connect", json={"device_id": device_id}, timeout=20
        ).json()
    except Exception as e:
        print(f"连接异常: {e}")
        return False
    if res.get("code") != 0:
        print(f"连接失败: {res}")
        return False
    print("连接成功")
    return True


class Gateway:
    def __init__(self, device_id):
        self.device_id = device_id

    def send(self, cmd, note="", allow_unknown=False):
        try:
            r = requests.post(
                f"{BASE}/devices/{self.device_id}/command",
                json={"command": cmd}, timeout=20,
            )
            d = r.json()
        except Exception as e:
            print(f"  [FAIL] {cmd} -> exception {e}")
            failures.append(cmd)
            return None, None
        if d.get("code") != 0:
            print(f"  [FAIL] {cmd} -> {d}")
            failures.append(cmd)
            return None, None
        data = d.get("data", {})
        resp, dur = data.get("response"), data.get("duration_ms")

        words = tuple(w for w in ERROR_WORDS if not (allow_unknown and w == "UNKNOWN"))
        bad = []
        if (dur or 0) > 1500:
            bad.append("NO-REPLY(设备未识别)")
        if resp and any(w in str(resp) for w in words):
            bad.append(f"REJECTED({resp})")
        status = "[FAIL]" if bad else "[ OK ]"
        if bad:
            failures.append(f"{cmd} -> {'; '.join(bad)}")
        extra = f"  # {note}" if note else ""
        print(f"  {status} {cmd:<48} -> {resp!r} ({dur}ms){extra}")
        sys.stdout.flush()
        return resp, dur


# --------------------------------------------------------------------------
# Test 1
# --------------------------------------------------------------------------
def test1(gw):
    print("\n" + "=" * 78)
    print("测试 1: 每 200ms 发送 CAN 消息 0x850201 (ID 0x13) 并显示回复")
    print("=" * 78)

    print("\n-- 握手 --")
    gw.send("@11_HELLO;")
    gw.send("@11_SYSID;")

    print("\n-- 清理残留进程 --")
    for pid in range(1, 5):
        gw.send(f"@11_PROCESS={pid},STOP;", allow_unknown=True)
        gw.send(f"@11_PROCESS={pid},DELETE;", allow_unknown=True)

    print("\n-- CAN1 配置 (TSTOP -> CONFIG -> TSTRT) --")
    gw.send("@11_TSTOP;", "复位配置")
    gw.send("@11_CONFIG=CAN1,BAUDRATE,500K;", "波特率必须大写 K")
    gw.send("@11_CONFIG=CAN1,TX,MSG13,STD,0X13;", "TX 别名 + 大写 0X")
    gw.send("@11_CONFIG=CAN1,RX,RPLY13,STD,0X20;", "RX 别名用于读取回复")
    gw.send("@11_TSTRT;", "使配置生效")

    print("\n-- 定义 200ms 周期进程 (granularity 100 x totalsteps 2) --")
    gw.send("@11_PROCESS=1,STOP;", allow_unknown=True)
    gw.send("@11_PROCESS=1,DELETE;", allow_unknown=True)
    gw.send("@11_PROCESS=1,DEFINE,100,2;", "周期 = 100 x 2 = 200ms")
    gw.send("@11_PROCESS=1,1,MSGTX,CAN1,MSG13,0X850201;", "step 必须在 1..totalsteps-1")
    gw.send("@11_PROCESS=1,END;")
    gw.send("@11_PROCESS=1,START;")

    print("\n-- 采样循环计数验证周期 --")
    samples = []
    for i in range(4):
        res, _ = gw.send("@11_PROCESS=1,DEFINE;")
        m = re.search(r"LOOP=(\d+)", str(res))
        samples.append((time.time(), int(m.group(1)) if m else None))
        if i < 3:
            time.sleep(1.0)
    if samples[0][1] is not None and samples[-1][1] is not None:
        dt = samples[-1][0] - samples[0][0]
        loops = samples[-1][1] - samples[0][1]
        if loops > 0:
            period = dt * 1000 / loops
            ok = 150 <= period <= 260
            print(f"  [{'OK' if ok else 'FAIL'}] {dt:.2f}s 内执行 {loops} 次 => 周期约 {period:.0f}ms (目标 200ms)")
            if not ok:
                failures.append(f"周期异常: {period:.0f}ms")
        else:
            print("  [WARN] 循环计数未增长")
    else:
        print(f"  [WARN] 未能解析 LOOP: {[s[1] for s in samples]}")

    print("\n-- 读取回复报文 --")
    for i in range(3):
        res, _ = gw.send("@11_MSGRX=CAN1,RPLY13,8;")
        if res and re.search(r"0X[0-9A-Fa-f]{2,}", str(res)):
            print(f"         收到回复数据: {res}")
        else:
            print(f"         第 {i+1} 次未收到回复 (空数据) -> time out")
        time.sleep(0.3)

    print("\n-- 停止 --")
    gw.send("@11_PROCESS=1,STOP;")
    gw.send("@11_TSTOP;")


# --------------------------------------------------------------------------
# Test 2
# --------------------------------------------------------------------------
def test2(gw):
    print("\n" + "=" * 78)
    print("测试 2: 读数字通道 1，若为 0 则用 CAN1 发送 0x850102 (ID 0x10) 并读回复")
    print("=" * 78)

    print("\n-- 握手 --")
    gw.send("@11_HELLO;")

    print("\n-- 读取数字通道 1 --")
    res, _ = gw.send("@11_GETDIG=1;")
    state = None
    m = re.match(r"\s*(\d+)\s*,\s*([01])\s*$", str(res or ""))
    if m:
        state = int(m.group(2))
        print(f"         数字通道 1 状态 = {state}")
    else:
        print(f"  [WARN] 无法解析数字通道状态: {res!r}")
        failures.append(f"GETDIG 解析失败: {res!r}")

    if state == 0:
        print("\n-- 状态为 0 -> 通过 CAN1 发送报文 --")
        gw.send("@11_TSTOP;")
        gw.send("@11_CONFIG=CAN1,BAUDRATE,500K;")
        gw.send("@11_CONFIG=CAN1,TX,MSG10,STD,0X10;")
        gw.send("@11_CONFIG=CAN1,RX,RPLY10,STD,0X11;")
        gw.send("@11_TSTRT;")
        gw.send("@11_MSGTX=CAN1,MSG10,0X850102;")

        print("\n-- 读取回复（最多重试 3 次，无回复则提示 time out）--")
        got_reply = False
        for i in range(3):
            res, _ = gw.send("@11_MSGRX=CAN1,RPLY10,8;")
            if res and re.search(r"0X[0-9A-Fa-f]{2,}", str(res)):
                print(f"         收到回复: {res}")
                got_reply = True
                break
            print(f"         第 {i+1} 次未收到回复 -> time out")
            time.sleep(0.5)
        if not got_reply:
            print("  [ OK ] 已按预期输出 time out 提示")
        gw.send("@11_TSTOP;")
    else:
        print(f"\n-- 状态为 {state}（非 0），跳过发送分支 --")


def main():
    device_id = find_device()
    if not device_id:
        print("未找到 mini_gateway100 设备")
        return 1
    print(f"使用设备: {device_id}")
    if not ensure_connected(device_id):
        return 1
    gw = Gateway(device_id)

    test1(gw)
    test2(gw)

    print("\n" + "=" * 78)
    if failures:
        print(f"结果: {len(failures)} 项失败")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("结果: 两个测试全部跑通（所有指令均被设备正确识别）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
