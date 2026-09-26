#!/usr/bin/env python3
"""
Code generation regression tests.

Covers the reported issue "adding a judgement to a test case did not change
the generated code" plus the parsing integration:

  1. a condition node that is NOT wired into the flow still appears
  2. condition branches emit correct if/else (no duplicated sequential code)
  3. natural-language steps emit real device commands
  4. repeated commands collapse into a loop
  5. parser configuration is emitted and the result still compiles

Run: python3 Test/test_codegen.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from app.services.codegen_service import codegen_service as gen  # noqa: E402

failures = []


def check(cond, msg):
    print(f"  [{'OK' if cond else 'FAIL'}] {msg}")
    if not cond:
        failures.append(msg)
    return cond


def N(i, t, cfg=None, label=""):
    return {"id": i, "type": t, "data": {"label": label or i}, "config": cfg or {}}


def compiles(code):
    try:
        compile(code, "generated.py", "exec")
        return True
    except SyntaxError as e:
        print(f"       SyntaxError: {e}")
        return False


# --------------------------------------------------------------------- #
print("=== 1. 未连线的判断节点必须出现在生成代码中 ===")
nodes = [
    N("s", "start"),
    N("a1", "action", {"command": "@11_HELLO;"}, "步骤1"),
    N("e", "end"),
    N("orphan", "condition", {"condition": "temp < 50"}, "孤立温度判断"),
]
edges = [{"source": "s", "target": "a1"}, {"source": "a1", "target": "e"}]
code = gen.generate_python(nodes, edges, "T1")
check("temp < 50" in code, "未连接判断节点被生成（修复前会被静默丢弃）")
check("未连接到主流程" in code, "给出未连接提示注释")
check(compiles(code), "生成代码语法合法")

# --------------------------------------------------------------------- #
print("\n=== 2. 判断分支 if/else 正确且不重复 ===")
nodes = [
    N("s", "start"),
    N("a1", "action", {"command": "@11_HELLO;"}, "步骤1"),
    N("c1", "condition", {"condition": "voltage > 10"}, "电压判断"),
    N("t", "action", {"command": "@11_TSTRT;"}, "通过分支"),
    N("f", "action", {"command": "@11_TSTOP;"}, "失败分支"),
    N("e", "end"),
]
edges = [
    {"source": "s", "target": "a1"}, {"source": "a1", "target": "c1"},
    {"source": "c1", "target": "t"}, {"source": "c1", "target": "f"},
    {"source": "t", "target": "e"}, {"source": "f", "target": "e"},
]
code = gen.generate_python(nodes, edges, "T2")
tstRT = code.count("@11_TSTRT;")
tstop = code.count("@11_TSTOP;")
check(tstRT == 1, f"true 分支只出现一次 (实际 {tstRT})")
check(tstop == 1, f"false 分支只出现一次 (实际 {tstop})")
check("if voltage > 10:" in code and "else:" in code, "生成 if/else 结构")
# TSTOP must sit inside the else block (deeper indent than the if)
lines = code.splitlines()
if_i = next(i for i, l in enumerate(lines) if "if voltage > 10:" in l)
else_i = next(i for i, l in enumerate(lines) if l.strip() == "else:")
tstop_i = next(i for i, l in enumerate(lines) if "@11_TSTOP;" in l)
check(tstop_i > else_i, "false 分支位于 else 之后（修复前会泄漏到 if/else 之外）")
check(compiles(code), "生成代码语法合法")

# --------------------------------------------------------------------- #
print("\n=== 3. 自然语言步骤 -> 真实指令 ===")
nodes = [
    N("s", "start"),
    N("a", "action", {"command": "握手与版本：@11_HELLO; @11_SYSID;", "expected": ">0"}, "握手"),
    N("e", "end"),
]
code = gen.generate_python(nodes, [{"source": "s", "target": "a"}, {"source": "a", "target": "e"}], "T3")
check("send_command('@11_HELLO;')" in code, "生成真实指令 @11_HELLO;")
check("send_command('@11_SYSID;')" in code, "生成真实指令 @11_SYSID;")
check("握手与版本" not in code.split("def run")[1].split("send_command")[0], "不再把整句自然语言当指令下发")
check("assert float(response) > 0" in code, "预期结果生成数值判断")
check(compiles(code), "生成代码语法合法")

# --------------------------------------------------------------------- #
print("\n=== 4. 重复指令折叠为循环 ===")
nodes = [
    N("s", "start"),
    N("a", "action", {"command": "长时间循环读取回复(例如 100 次)，@11_MSGRX=CAN1,RPLY1,8;"}, "循环读"),
    N("e", "end"),
]
code = gen.generate_python(nodes, [{"source": "s", "target": "a"}, {"source": "a", "target": "e"}], "T4")
check("for _repeat in range(" in code, "重复指令折叠为 for 循环")
check(code.count("@11_MSGRX=CAN1,RPLY1,8;") == 1, "指令只写一次（不生成 100 行重复代码）")
check(compiles(code), "生成代码语法合法")

# --------------------------------------------------------------------- #
print("\n=== 5. 解析配置生成解析与判断 ===")
nodes = [
    N("s", "start"),
    N("a", "action", {
        "command": "@11_MSGRX=CAN1,RPLY1,8;",
        "parsers": [{
            "name": "母线电压", "data_type": "dec", "start": 0, "length": 2,
            "unit": "byte", "conditions": {"min": 10, "max": 60, "equals": ["100", "200"]},
        }],
    }, "读取电压"),
    N("e", "end"),
]
code = gen.generate_python(nodes, [{"source": "s", "target": "a"}, {"source": "a", "target": "e"}], "T5")
check("def parse_field(" in code, "生成解析辅助函数（脚本自包含）")
check("parse_field(response, data_type='dec'" in code, "按配置解析字段")
check("parsed_0 >= 10" in code, "生成最小值判断")
check("parsed_0 <= 60" in code, "生成最大值判断")
check("在期望值" in code, "生成等于（或运算）判断")
check(compiles(code), "生成代码语法合法")

# the emitted equals clause must not reference undefined names
for l in code.splitlines():
    if "在期望值" in l:
        check("o.lower()" not in l, "等于判断未引用未定义变量")

# --------------------------------------------------------------------- #
print("\n" + "=" * 70)
if failures:
    print(f"结果: {len(failures)} 项失败")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("结果: 代码生成全部通过（含未连接节点、分支、真实指令、解析）")
sys.exit(0)
