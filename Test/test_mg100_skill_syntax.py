#!/usr/bin/env python3
"""
Audit every command string in the Mini Gateway 100 skill against the grammar
of "Mini Gateway 100 - User Manual v1.5" + verified device behaviour, then
smoke-test the read-only commands on the real device.

Run: python3 Test/test_mg100_skill_syntax.py
"""
import re
import sys

import requests

SKILL = "/home/joelj/Documents/TestCopilot/backend/plugins/skills/mini_gateway100_skill.md"
BASE = "http://127.0.0.1:8000/api"

KNOWN_CMDS = {
    "HELLO", "SYSID", "PSUV", "PSUC", "PSDV", "PSDC", "ETH", "RTC", "STORAGE",
    "SETDIG", "CLRDIG", "GETDIG", "CALBRT", "GETVOLT", "SETVOLT", "OPEN",
    "CLOSE", "CONFIG", "TSTRT", "TSTOP", "MSGTX", "MSGRX", "PROCESS", "SYNCHRO",
}
BAUDRATES = {"10K", "20K", "33.3K", "40K", "83.3K", "100K", "125K", "250K",
             "500K", "1000K", "1M"}

errors = []


def check(cmd: str):
    """Validate one command string; record violations."""
    if not re.match(r"^@\d+_[A-Z]+(=.*)?;$", cmd):
        errors.append(f"{cmd}: 基本格式错误 (应为 @<ID>_<COMMAND>[=<PARAMS>];)")
        return
    body = cmd[1:-1]
    _, rest = body.split("_", 1)
    name = re.match(r"[A-Z]+", rest).group(0)
    if name not in KNOWN_CMDS:
        errors.append(f"{cmd}: 未知命令 {name}")
    params = rest[len(name):]
    if params.startswith("="):
        params = params[1:]

    # hex values must use an uppercase 0X prefix
    for hx in re.findall(r"0[xX][0-9A-Fa-f]+", cmd):
        if not hx.startswith("0X"):
            errors.append(f"{cmd}: 十六进制前缀必须大写 0X (发现 {hx})")

    if name == "CONFIG":
        parts = params.split(",")
        if len(parts) >= 3 and parts[1].upper() == "BAUDRATE":
            if parts[2] not in BAUDRATES:
                errors.append(f"{cmd}: 波特率 {parts[2]} 不在支持列表 "
                              f"{sorted(BAUDRATES)}")
        elif len(parts) >= 5:
            # CAN<ch>,<direction>,<alias>,<ID type>,<ID>
            if parts[1].upper() not in ("TX", "RX"):
                errors.append(f"{cmd}: direction 必须为 TX/RX")
            if parts[3].upper() not in ("STD", "EXT"):
                errors.append(f"{cmd}: ID type 必须为 STD/EXT")
            if not re.match(r"^0X[0-9A-F]+$", parts[4]):
                errors.append(f"{cmd}: CAN ID 必须为 0X+大写十六进制")

    if name == "MSGTX" and params:
        parts = params.split(",")
        if len(parts) >= 3 and not re.match(r"^0X[0-9A-F]+$", parts[2]):
            errors.append(f"{cmd}: MSGTX 数据必须以 0X 开头")

    if name == "PROCESS":
        parts = params.split(",")
        if len(parts) >= 3 and parts[1].upper() == "DEFINE" and parts[2].isdigit():
            gran = int(parts[2])
            if gran % 10 != 0:
                errors.append(f"{cmd}: granularity 必须是 10 的倍数")


def main():
    print("=== 1. 静态语法审查 (skill 中所有指令) ===")
    with open(SKILL, encoding="utf-8") as f:
        content = f.read()
    # Collect commands together with the line they appear on, so that syntax
    # templates ("@11_MSGTX=CAN<ch>...") and deliberately-wrong examples
    # (documented as 错误/不支持) can be excluded from validation.
    entries = []
    skipped = []
    for line in content.splitlines():
        for c in re.findall(r"@\d+_[A-Z]+(?:=[^;\n`]*)?;", line):
            if "<" in c or ">" in c:
                skipped.append(c)
            elif "错误" in line or "不支持" in line or "✗" in line:
                skipped.append(c)
            else:
                entries.append(c)
    cmds = sorted(set(entries))
    print(f"共提取 {len(cmds)} 条可执行指令（跳过 {len(skipped)} 条模板/反例）")
    for c in cmds:
        check(c)
    if errors:
        print(f"\n发现 {len(errors)} 处问题:")
        for e in errors:
            print("  -", e)
    else:
        print("全部通过：无语法/取值错误")
    for c in cmds:
        print(f"    {c}")

    print("\n=== 2. 只读指令实机验证 ===")
    r = requests.get(f"{BASE}/devices/", timeout=10).json()
    devices = r.get("data", r)
    if isinstance(devices, dict):
        devices = devices.get("items", [])
    cands = [d for d in devices if d.get("protocol") == "mini_gateway100"]
    if not cands:
        print("未找到 mini_gateway100 设备，跳过实机验证")
        return 1 if errors else 0
    dev = cands[0]
    if dev.get("status") != "connected":
        requests.post(f"{BASE}/devices/connect",
                      json={"device_id": dev["id"]}, timeout=20)
    did = dev["id"]

    # NOTE: @11_SYNCHRO=... is documented in the manual but the V1.4.8
    # firmware never replies, so it is excluded here (and from the skill).
    read_only = [
        "@11_HELLO;", "@11_SYSID;", "@11_GETDIG=1;", "@11_GETDIG=5;",
        "@11_GETVOLT=1;", "@11_GETVOLT=2;", "@11_PSDV;", "@11_PSDC;",
        "@11_ETH;", "@11_RTC=GET;", "@11_STORAGE=DLSTOP;",
    ]
    bad = 0
    for c in read_only:
        try:
            resp = requests.post(f"{BASE}/devices/{did}/command",
                                 json={"command": c}, timeout=20).json()
        except Exception as e:
            print(f"  [FAIL] {c:<24} -> exception {e}")
            bad += 1
            continue
        if resp.get("code") != 0:
            print(f"  [FAIL] {c:<24} -> {resp}")
            bad += 1
            continue
        d = resp.get("data", {})
        dur = d.get("duration_ms") or 0
        mark = "OK" if dur < 1500 else "FAIL(无应答)"
        if dur >= 1500:
            bad += 1
        print(f"  [{mark}] {c:<24} -> {d.get('response')!r} ({dur}ms)")

    ok = not errors and bad == 0
    print("\n" + "=" * 60)
    print("结论:", "全部通过" if ok else f"存在问题 (静态 {len(errors)} / 实机 {bad})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
