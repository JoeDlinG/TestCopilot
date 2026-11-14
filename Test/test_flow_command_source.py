#!/usr/bin/env python3
"""Regression guards for "edit an instruction, regenerate code -> old command
is still there".

Root cause: a flow node can carry several *copies* of its command — the
user-editable ``config.command`` text, the AI generator's hidden
``config.parameters.command(s)`` / ``config.commands``, and free-text
``data.label`` / ``config.expected``. ``_extract_commands`` used to merge all
of them, and the editor only updated the visible one, so regenerating emitted
both the new command and a stale hidden copy (MG100: ``0X20`` lingering after
the user had changed the RX id to ``0X10``). Deleting the whole node removed
every copy, which is why deleting a step appeared to work.

Fix: command sources are a *priority list*, not a union — first source that
yields commands wins. The frontend also drops hidden copies when the visible
command is edited, and shows the effective command in the edit form.

Run: ``python3 Test/test_flow_command_source.py``
"""
import json
import os
import sqlite3
import sys
from typing import List

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND)

from app.services.codegen_service import codegen_service, node_commands  # noqa: E402
from app.services.execution_service import (  # noqa: E402
    ExecutionEngine, normalize_flow_commands,
)

_failures: List[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("  PASS  " if ok else "  FAIL  ") + label + (f"  -> {detail}" if detail else ""))
    if not ok:
        _failures.append(label)


def text(path: str) -> str:
    return open(os.path.join(ROOT, path), encoding="utf-8").read()


def action_node(nid: str, **cfg):
    return {
        "id": nid,
        "type": "action",
        "data": {"label": cfg.pop("label", "step")},
        "config": cfg,
    }


def simple_flow(*nodes):
    nodes = [action_node("start", label="begin"), *nodes, action_node("end", label="end")]
    nodes[0]["type"] = "start"
    nodes[-1]["type"] = "end"
    edges = [
        {"id": f"e{i}", "source": nodes[i]["id"], "target": nodes[i + 1]["id"], "label": ""}
        for i in range(len(nodes) - 1)
    ]
    return list(nodes), edges


def code_for(*nodes) -> str:
    ns, es = simple_flow(*nodes)
    return codegen_service.generate_python(ns, es, "issue_command_source")


# --------------------------------------------------------------------------- #
# 1. The reported bug: visible command edited, hidden copy stale
# --------------------------------------------------------------------------- #
def polluted_node_checks() -> None:
    node = action_node(
        "n1",
        label="配置 CAN1 接收消息 ID：标准帧 0X10",
        command="@11_CONFIG=CAN1,RX,RPLY1,STD,0X10; // 修改后的指令",
        expected="收到 #11_CONFIG=CAN1,RX,RPLY1,STD,0X10; 配置成功",
        parameters={"command": "@11_CONFIG=CAN1,RX,RPLY1,STD,0X20;"},
        device_id="dev1",
    )
    cmds = node_commands(node)
    check("visible command wins, stale hidden copy dropped",
          cmds == ["@11_CONFIG=CAN1,RX,RPLY1,STD,0X10;"], str(cmds))

    code = code_for(node)
    check("generated code has NO 0X20", "0X20" not in code.upper())
    check("generated code has 0X10", "0X10" in code.upper())
    check("generated code sends exactly one CONFIG command",
          code.count("send_command(") == 1, str(code.count("send_command(")))

    # The same node with the visible field left as a Chinese summary must keep
    # working — 37+ real AI-generated nodes rely on the hidden structured field.
    node_ai = action_node(
        "n1",
        label="配置 CAN1 接收消息别名",
        command="配置 CAN1 接收消息别名（中文摘要）",
        expected="配置成功",
        parameters={"command": "@11_CONFIG=CAN1,RX,RPLY1,STD,0X20;"},
        device_id="dev1",
    )
    cmds_ai = node_commands(node_ai)
    check("AI-generated node still resolves hidden command",
          cmds_ai == ["@11_CONFIG=CAN1,RX,RPLY1,STD,0X20;"], str(cmds_ai))


# --------------------------------------------------------------------------- #
# 2. label / expected must never be a command source
# --------------------------------------------------------------------------- #
def free_text_checks() -> None:
    node = action_node(
        "n1",
        label="注释里提到 @11_TSTOP; 但不是指令",
        command="发送 HELLO 握手，确认通信正常",
        expected="期望返回 @11_HELLO; 的应答",
        device_id="dev1",
    )
    cmds = node_commands(node)
    check("command-like text in label/expected is not executed",
          cmds == [], str(cmds))

    # A legacy hand-written flow that has its command ONLY in the label is
    # still supported by the last-resort fallback.
    legacy = action_node("n1", label="@11_HELLO;", command="", expected="", device_id="dev1")
    check("legacy label-only flow still resolves",
          node_commands(legacy) == ["@11_HELLO;"], str(node_commands(legacy)))


# --------------------------------------------------------------------------- #
# 3. Deleting a step still works (user's control experiment)
# --------------------------------------------------------------------------- #
def delete_node_checks() -> None:
    a = action_node("a", label="A", command="@11_HELLO;", device_id="dev1")
    b = action_node("b", label="B", command="@11_SYSID;", device_id="dev1")
    two = code_for(a, b)
    one = code_for(a)
    check("two nodes -> both commands", "@11_HELLO;" in two and "@11_SYSID;" in two)
    check("deleted node -> command gone", "@11_SYSID;" not in one and "@11_HELLO;" in one)


# --------------------------------------------------------------------------- #
# 4. Structured JSON commands (PeakCAN) & config.commands
# --------------------------------------------------------------------------- #
def structured_checks() -> None:
    node = action_node(
        "n1",
        label="启动周期发送",
        command="启动周期发送（中文摘要）",
        expected="启动成功",
        parameters={"command": '{"action": "send_periodic", "arbitration_id": 16}'},
        device_id="dev1",
    )
    check("JSON hidden command resolved",
          node_commands(node) == ['{"action": "send_periodic", "arbitration_id": 16}'],
          str(node_commands(node)))

    # Editing the visible field to a new JSON command must drop the old copy.
    node["config"]["command"] = '{"action": "receive"}'
    check("edited JSON command drops stale hidden JSON",
          node_commands(node) == ['{"action": "receive"}'], str(node_commands(node)))

    listed = action_node(
        "n2", label="L", command="描述", commands=["@11_HELLO;", "@11_SYSID;"], device_id="dev1",
    )
    check("config.commands list still works",
          node_commands(listed) == ["@11_HELLO;", "@11_SYSID;"], str(node_commands(listed)))


# --------------------------------------------------------------------------- #
# 5. Real DB: the reported test case must no longer emit 0X20
# --------------------------------------------------------------------------- #
def real_db_checks() -> None:
    db_path = os.path.join(BACKEND, "aitestlab.db")
    if not os.path.exists(db_path):
        print("  SKIP  real DB checks (aitestlab.db not present)")
        return
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT nodes, edges FROM test_flows WHERE testcase_id=?", ("tc_bc2a04ba",))
    row = cur.fetchone()
    conn.close()
    if not row:
        print("  SKIP  real DB checks (reported case not present)")
        return
    ns = json.loads(row[0])
    es = json.loads(row[1])
    code = codegen_service.generate_python(ns, es, "CAN 每 200ms 周期发送 0x850201 并显示回复")
    sends = [l for l in code.splitlines() if "send_command(" in l]
    check("real case: no 0X20 in any send_command",
          all("0X20" not in s.upper() for s in sends))
    check("real case: new 0X10 command present",
          any("0X10" in s.upper() for s in sends))
    check("real case: exactly one CONFIG RX send",
          sum("RPLY1,STD" in s for s in sends) == 1,
          str(sum("RPLY1,STD" in s for s in sends)))


# --------------------------------------------------------------------------- #
# 6. Source guards: frontend must not re-create stale hidden copies
# --------------------------------------------------------------------------- #
def normalization_checks() -> None:
    edited = action_node(
        "n1",
        label="L",
        command="@11_CONFIG=CAN1,RX,RPLY1,STD,0X10;",
        parameters={"command": "@11_CONFIG=CAN1,RX,RPLY1,STD,0X20;", "other": "keep"},
        commands=["@11_TSTOP;"],
        device_id="dev1",
    )
    norm = normalize_flow_commands([edited])[0]
    cfg = norm["config"]
    check("save-normalisation drops stale parameters.command",
          "command" not in cfg["parameters"])
    check("save-normalisation keeps unrelated parameters",
          cfg["parameters"].get("other") == "keep")
    check("save-normalisation drops stale config.commands",
          "commands" not in cfg)
    check("save-normalisation keeps the visible command",
          cfg["command"] == "@11_CONFIG=CAN1,RX,RPLY1,STD,0X10;")

    ai_node = action_node(
        "n2",
        label="中文摘要",
        command="配置 CAN1 接收消息别名（中文摘要）",
        parameters={"command": "@11_CONFIG=CAN1,RX,RPLY1,STD,0X20;"},
        device_id="dev1",
    )
    norm_ai = normalize_flow_commands([ai_node])[0]
    check("AI-generated node keeps its hidden command on save",
          norm_ai["config"]["parameters"]["command"]
          == "@11_CONFIG=CAN1,RX,RPLY1,STD,0X20;")

    exported = json.dumps(normalize_flow_commands([edited]), ensure_ascii=False)
    check("exported project JSON has no 0X20", "0X20" not in exported.upper())


def source_guards() -> None:
    editor = text("frontend/src/pages/TestFlowEditor.tsx")
    engine = text("backend/app/services/execution_service.py")
    codegen = text("backend/app/services/codegen_service.py")
    api = text("backend/app/api/testcases.py")

    check("editor exposes effective command", "effectiveCommand(" in editor)
    check("editor drops stale hidden params on command change",
          "delete prevParams.command" in editor and "delete nextConfig.commands" in editor)
    check("editor allows clearing label", "label: vals.label ?? ''" in editor)
    check("extractor uses a priority ladder, not a union",
          "_scan_commands" in engine and "first source that yields commands wins" in engine)
    check("codegen delegates to the engine (no config.commands shortcut)",
          "ExecutionEngine._extract_commands(node)" in codegen
          and "declared = config.get" not in codegen)
    check("flow save normalises both create and update paths",
          api.count("normalize_flow_commands(data.nodes)") == 2)


def main() -> int:
    polluted_node_checks()
    free_text_checks()
    delete_node_checks()
    structured_checks()
    normalization_checks()
    real_db_checks()
    source_guards()
    if _failures:
        print(f"\nFAILED: {len(_failures)} check(s): {', '.join(_failures)}")
        return 1
    print("\nAll flow-command-source regression guards passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
