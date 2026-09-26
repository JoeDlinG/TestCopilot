#!/usr/bin/env python3
"""
Test script: 模拟 mini-Gateway-100 多行响应行为，验证 SerialInterface.send() 的修复。

使用虚拟串口 (pty) 模拟设备行为：
- master_fd → 模拟设备端（读写 master 端）
- slave_name → pyserial 打开 slave 端作为串口

PTY 数据流: pyserial(slave) <--kernel--> master(模拟器)

测试场景：
1. 单行响应 — 基础功能
2. TSTRT 空行+数据 — 原始 Bug：设备先发空行再发数据
3. 多字段响应 SYSID
4. 多行响应（5行） — 验证循环读取
5. TSTRT 多行变体 — 模拟测试数据持续输出
"""

import os
import sys
import time
import asyncio
import threading
import pty
import tty
import select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

# Simulate mini-Gateway-100 behavior
RESPONSE_MAP = {
    "@11_CONFIG=CAN1,BAUDRATE,500K;": "CAN1,BAUDRATE,500K",
    "@11_TSTRT;": "\r\nTEST_START",
    "@11_TSTRT;(multiline)": "\r\nTEST_START\r\nDATA,1,100,OK\r\nDATA,2,200,OK\r\nDATA,3,300,OK\r\nTEST_RUNNING\r\n",
    "@11_SYSID;": "2000,1.0,120000,23Y0000,MGW100_V1.4.8",
    "@11_MLTEST;": "LINE_1\r\nLINE_2\r\nLINE_3\r\nLINE_4\r\nLINE_5",
    "@11_ECHO;": "ECHO_OK",
}


def device_simulator(master_fd):
    """Simulate mini-Gateway-100 behavior on the master side of pty."""
    buffer = b""
    while True:
        try:
            r, _, _ = select.select([master_fd], [], [], 0.5)
            if not r:
                continue
            data = os.read(master_fd, 1024)
            if not data:
                break
            buffer += data
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                cmd = line.decode(errors="replace").strip()
                if not cmd:
                    continue
                response = RESPONSE_MAP.get(cmd, f"UNKNOWN:{cmd}")
                time.sleep(0.01)
                os.write(master_fd, (response + "\r\n").encode())
                print(f"  [DEVICE] Got: {cmd!r} -> Sent: {response!r}")
        except OSError:
            break


async def run_tests(interface, label):
    """Run all test cases using the given interface."""
    print(f"\n{'='*60}")
    print(f"{label}")
    print(f"{'='*60}")

    all_passed = True

    # Test 1: Single line
    print("\n--- Test 1: 单行响应 ---")
    resp = await interface.send("@11_CONFIG=CAN1,BAUDRATE,500K;")
    print(f"  Received: {resp!r}")
    if resp == "CAN1,BAUDRATE,500K":
        print("  ✓ PASS")
    else:
        print(f"  ✗ FAIL: expected 'CAN1,BAUDRATE,500K'")
        all_passed = False

    # Test 2: TSTRT with leading empty line (THE ORIGINAL BUG)
    print("\n--- Test 2: 空行+单行 (@11_TSTRT — 原始 BUG 场景) ---")
    resp = await interface.send("@11_TSTRT;")
    line_count = resp.count('\n') + 1 if resp else 0
    print(f"  Received: {resp!r} ({line_count} lines)")
    # After fix: should get "\nTEST_START" or "TEST_START" (trailing empty stripped)
    if "TEST_START" in resp and line_count >= 1:
        print("  ✓ PASS: 成功捕获 TEST_START（修复前会丢失）")
    else:
        print(f"  ✗ FAIL: 未捕获到 TEST_START")
        all_passed = False

    # Test 3: SYSID
    print("\n--- Test 3: 多字段单行 (@11_SYSID) ---")
    resp = await interface.send("@11_SYSID;")
    print(f"  Received: {resp!r}")
    if "MGW100_V1.4.8" in resp:
        print("  ✓ PASS")
    else:
        print(f"  ✗ FAIL")
        all_passed = False

    # Test 4: Multi-line response (THE KEY FIX)
    print("\n--- Test 4: 多行响应 5行 (@11_MLTEST) — 核心修复验证 ---")
    resp = await interface.send("@11_MLTEST;")
    line_count = resp.count('\n') + 1 if resp else 0
    print(f"  Received: {resp!r} ({line_count} lines)")
    if line_count == 5 and "LINE_1" in resp and "LINE_5" in resp:
        print("  ✓ PASS: 完整捕获 5 行（修复前只捕获 1 行）")
    else:
        print(f"  ✗ FAIL: 预期 5 行，实际 {line_count} 行")
        all_passed = False

    # Test 5: TSTRT multiline variant
    print("\n--- Test 5: TSTRT 多行变体 (测试数据流) ---")
    resp = await interface.send("@11_TSTRT;(multiline)")
    line_count = resp.count('\n') + 1 if resp else 0
    print(f"  Received: {resp!r} ({line_count} lines)")
    if "DATA,1,100,OK" in resp and "DATA,3,300,OK" in resp and "TEST_RUNNING" in resp:
        print(f"  ✓ PASS: 完整捕获测试数据 ({line_count} 行)")
    else:
        print(f"  ✗ FAIL: 测试数据不完整")
        all_passed = False

    return all_passed


async def main_async(slave_name, label):
    from app.communication import SerialInterface

    interface = SerialInterface(
        port=slave_name,
        config={
            "baudrate": 115200,
            "timeout": 1.0,
            "termination_char": "\n",
            "read_timeout": 0.3,
            "inter_line_grace": 0.05,
        },
    )
    await interface.connect()
    result = await run_tests(interface, label)
    await interface.disconnect()
    return result


def main():
    master_fd, slave_fd = pty.openpty()
    tty.setraw(master_fd)
    tty.setraw(slave_fd)
    slave_name = os.ttyname(slave_fd)
    print(f"虚拟串口: master_fd={master_fd}, slave={slave_name}")

    sim_thread = threading.Thread(target=device_simulator, args=(master_fd,), daemon=True)
    sim_thread.start()

    try:
        result = asyncio.run(main_async(slave_name, "修复后验证"))
        summary = "✓ 所有测试通过 — 修复成功！" if result else "✗ 存在失败"
        print(f"\n{'='*60}\n{summary}\n{'='*60}")
        return 0 if result else 1
    finally:
        os.close(master_fd)
        os.close(slave_fd)


if __name__ == "__main__":
    sys.exit(main())
