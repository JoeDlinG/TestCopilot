"""Flowchart-to-code generator.

Walks a ReactFlow test-flow graph (nodes + edges) and emits a standalone,
executable Python script that mirrors the flow structure — sequential steps,
condition branches (if/else), loops (for/while), and parallel gateways.
"""
from __future__ import annotations
import json
import re
from collections import defaultdict
from typing import Dict, List, Any, Optional, Set, Tuple

from app.services import flow_context


def node_commands(node: Dict) -> List[str]:
    """Return the real device commands carried by a node.

    Reuses the execution engine's extractor so that generated code and the
    actual run issue exactly the same commands. Natural-language steps like
    "握手与版本：@11_HELLO; @11_SYSID;" yield ['@11_HELLO;', '@11_SYSID;']
    instead of the raw sentence (which is not a valid device command).
    """
    config = node.get("config") or {}
    declared = config.get("commands")
    if isinstance(declared, list) and declared:
        return [str(c).strip() for c in declared if str(c).strip()]
    try:
        from app.services.execution_service import ExecutionEngine
        return ExecutionEngine._extract_commands(node)
    except Exception:
        return []


def collapse_runs(commands: List[str]) -> List[Tuple[str, int]]:
    """Collapse repeated identical commands into (command, count) runs."""
    runs: List[Tuple[str, int]] = []
    for c in commands:
        if runs and runs[-1][0] == c:
            runs[-1] = (c, runs[-1][1] + 1)
        else:
            runs.append((c, 1))
    return runs


def assertion_stmt(expected: str, render: bool = False) -> str:
    """Build an assertion line for an expected-result string.

    Supports numeric comparisons (">10", "<=3.3"), containment
    ("contains OK" / "包含 OK") and plain equality.

    When *render* is True the literal is wrapped in ``_r(..., ctx)`` so the
    expectation may itself reference ``{前序节点输出}``.
    """
    e = str(expected).strip()

    def lit(value: str) -> str:
        return f"_r({value!r}, ctx)" if render else repr(value)

    m = re.match(r"^(>=|<=|==|!=|>|<)\s*(-?\d+(?:\.\d+)?)$", e)
    if m:
        op, val = m.group(1), m.group(2)
        return (
            f"assert float(response) {op} {val}, "
            f"f\"判断失败: {{response}} {op} {val}\""
        )
    low = e.lower()
    for kw in ("contains", "包含"):
        if low.startswith(kw):
            needle = e[len(kw):].strip().strip("'\"")
            if needle:
                return (
                    f"assert {lit(needle)} in str(response), "
                    f"f\"判断失败: {{response}} 不包含 {needle}\""
                )
    return (
        f"assert str(response).strip() == {lit(e)}, "
        f"f\"判断失败: 期望 {e}, 实际 {{response}}\""
    )


# Emitted into generated scripts so they can parse and judge responses exactly
# like the platform's ResponseParser does at runtime.
PARSE_HELPER = r'''

def _pick_groups(groups, hex_field):
    """Choose which 0x.. field(s) form the payload."""
    if not groups:
        return []
    hf = str(hex_field if hex_field is not None else "all").strip().lower()
    if hf in ("", "all", "*", "全部"):
        return groups
    if hf in ("first", "第一个"):
        return groups[:1]
    if hf in ("last", "最后", "最后一个"):
        return groups[-1:]
    try:
        idx = int(hf)
    except (TypeError, ValueError):
        return groups
    if idx < 0:
        idx = len(groups) + idx
    return groups[idx:idx + 1] if 0 <= idx < len(groups) else groups[-1:]


def _to_bytes(raw, hex_field="all"):
    """Convert a device response into raw bytes (hex or text)."""
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw)
    s = str(raw or "").strip()
    if not s:
        return b""
    groups = re.findall(r"(?i)\b0x([0-9a-f]+)\b", s)
    if groups:
        joined = "".join(_pick_groups(groups, hex_field))
        if joined and len(joined) % 2 == 0:
            return bytes.fromhex(joined)
    compact = re.sub(r"[,\s_]+", "", s).lower().replace("0x", "")
    if compact and re.fullmatch(r"[0-9a-f]+", compact) and len(compact) % 2 == 0:
        return bytes.fromhex(compact)
    return s.encode("utf-8", errors="replace")


def is_empty_frame(raw):
    """True when the reply carries no payload (e.g. 'CAN1,RPLY1,0X' = timeout)."""
    if raw is None:
        return True
    if isinstance(raw, (bytes, bytearray)):
        return len(raw) == 0
    s = str(raw).strip()
    if not s:
        return True
    for m in re.finditer(r"(?i)0x([0-9a-f]*)(?![0-9a-f])", s):
        if not m.group(1):
            return True
    return False


def parse_field(raw, data_type="string", start=0, length=1, unit="byte", hex_field="all"):
    """Slice a response and convert it, mirroring the platform parser."""
    if is_empty_frame(raw):
        # empty frame / timeout: nothing to judge
        return "unknown"
    data = _to_bytes(raw, hex_field)
    if unit == "bit":
        bits = "".join(f"{b:08b}" for b in data)
        if start + length > len(bits):
            raise ValueError(f"bit range {start}:{start + length} exceeds {len(bits)} bits")
        value = int(bits[start:start + length], 2)
    else:
        if start + length > len(data):
            raise ValueError(f"byte range {start}:{start + length} exceeds {len(data)} bytes")
        value = data[start:start + length]

    if data_type == "hex":
        return f"0x{value:X}" if isinstance(value, int) else "0x" + value.hex().upper()
    if data_type == "bin":
        if isinstance(value, int):
            return format(value, f"0{max(1, value.bit_length())}b")
        return "".join(f"{b:08b}" for b in value)
    if data_type == "bool":
        return bool(value) if isinstance(value, int) else any(value)
    if data_type == "dec":
        if isinstance(value, int):
            return value
        txt = value.decode("utf-8", errors="replace").strip()
        try:
            return float(txt) if re.search(r"[.eE]", txt) else int(txt)
        except ValueError:
            return int.from_bytes(value, "big")
    if isinstance(value, int):
        return str(value)
    return value.decode("utf-8", errors="replace").rstrip("\x00").strip()
'''


def _init_literal(value: Any, vtype: str) -> str:
    """Render an init-node variable value as a Python literal of the given type.

    Types: int / float / string / bool / hex. Empty or missing values become
    ``None`` so a variable can be declared without an initial value.
    """
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return "None"
    text = str(value).strip()
    try:
        if vtype == "int":
            try:
                return str(int(text, 0))
            except ValueError:
                return str(int(float(text)))
        if vtype == "float":
            return str(float(text))
        if vtype == "bool":
            return "True" if text.lower() in ("true", "1", "yes", "y", "on") else "False"
        if vtype == "hex":
            return hex(int(text, 16))
    except (ValueError, TypeError):
        return repr(text)
    return repr(text)


class CodeGenService:
    """Service that converts a test flowchart into executable Python code."""

    def generate_python(
        self,
        nodes: List[Dict],
        edges: List[Dict],
        test_case_name: str = "auto_generated_test",
    ) -> str:
        """Return a complete Python script string for the given flow."""
        node_map: Dict[str, dict] = {n["id"]: n for n in nodes} if isinstance(nodes[0], dict) else {}

        # Build adjacency sorted by position for deterministic output
        adj: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for e in edges:
            adj[e["source"]].append({
                "target": e["target"],
                "label": (e.get("label") or "").strip().lower(),
            })

        # Find start node
        start_id: Optional[str] = None
        for n in nodes:
            t = n.get("type", "")
            if t in ("start", "input"):
                start_id = n["id"]
                break
        if not start_id:
            for n in nodes:
                if not any(e["target"] == n["id"] for e in edges):
                    start_id = n["id"]
                    break
        if not start_id and nodes:
            start_id = nodes[0]["id"]

        header = [
            '"""Auto-generated test script.',
            f"   Test case: {test_case_name}",
            f"   Node count: {len(nodes)}, Edge count: {len(edges)}",
            '"""',
            "",
            "import time",
            "import logging",
            "import re",
            "",
            "logging.basicConfig(level=logging.INFO)",
            "log = logging.getLogger(__name__)",
            "",
            PARSE_HELPER,
            flow_context.RUNTIME_HELPER,
            "",
            "",
            "def run() -> dict:",
            '    """Execute the test flow and return a summary dict."""',
            "    results = {'passed': 0, 'failed': 0, 'skipped': 0, 'steps': []}",
            "    # 流程上下文：初始化节点的变量 + 各节点的输出返回值（供 {占位符} 引用）",
            "    ctx = {}",
            "",
        ]

        body_lines: List[str] = []
        visited_global: Set[str] = set()
        _edge_label_cache: Dict[str, str] = {}

        # Pre-compute dominant label for condition edges
        for nid, nbrs in adj.items():
            if nid in node_map and node_map[nid].get("type") == "condition":
                for nb in nbrs:
                    _edge_label_cache[f"{nid}->{nb['target']}"] = nb["label"]

        def _edge_label(src: str, tgt: str) -> str:
            return _edge_label_cache.get(f"{src}->{tgt}", "")

        def _emit_inputs(prefix: str, node: Dict) -> None:
            """Emit the resolution of a node's declared input parameters (#4)."""
            specs = flow_context.node_inputs(node)
            if not specs:
                return
            body_lines.append(f"{prefix}# ---- 输入参数 ----")
            for spec in specs:
                body_lines.append(
                    f"{prefix}ctx[{spec['name']!r}] = _p({spec['name']!r}, ctx, "
                    f"{spec['default']!r}, {spec['type']!r})"
                )

        def _emit_outputs(prefix: str, node: Dict, scope: Dict[str, str]) -> None:
            """Emit the evaluation of a node's declared output return values."""
            specs = flow_context.node_outputs(node)
            if not specs:
                return
            scope_lit = "{" + ", ".join(f"{k!r}: {v}" for k, v in scope.items()) + "}"
            fallback = "response" if "response" in scope else "result"
            for spec in specs:
                expr = str(spec.get("value") or fallback).strip() or fallback
                value = f"_out({expr!r}, {scope_lit})"
                if spec["type"] in ("int", "float", "bool", "hex"):
                    value = f"_cast({value}, {spec['type']!r})"
                body_lines.append(f"{prefix}ctx[{spec['name']!r}] = {value}")
                body_lines.append(
                    f"{prefix}log.info('↳ 输出 ' + {spec['name']!r} + "
                    f"' = ' + str(ctx[{spec['name']!r}]))"
                )

        def walk(node_id: str, indent: int, branch_stack: Set[str], no_remaining: bool = False) -> None:
            """Recursive DFS code generation.

            When *no_remaining* is True (used inside condition branches), the node
            emits its own code but does NOT walk successor/"remaining" neighbours.
            This keeps convergence points outside the if/else block.
            """
            if node_id in branch_stack:
                return  # cycle guard
            node = node_map.get(node_id)
            if node is None:
                return

            ntype = node.get("type", "default")
            data = node.get("data", {}) or {}
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except Exception:
                    data = {"label": data}
            config = node.get("config", {}) or {}
            label = data.get("label", "") or ""
            prefix = "    " * indent
            branch_targets: Set[str] = set()

            if ntype in ("start", "input"):
                visited_global.add(node_id)
                body_lines.append(f"{prefix}# ===== {label or 'Start'} =====")

            elif ntype in ("end", "output"):
                visited_global.add(node_id)
                end_label = label or "Flow completed"
                body_lines.append(f"{prefix}log.info('{end_label}')")

            elif ntype in ("action", "test_step", "default"):
                visited_global.add(node_id)
                raw_cmd = config.get("command", "") or ""
                commands = node_commands(node)
                device = config.get("device_id") or "device"
                expected = config.get("expected") or config.get("expected_result") or ""
                timeout_ms = config.get("timeout", 5000) / 1000
                step_no = config.get("step_number", "")
                step_label = f"[Step {step_no}]" if step_no else "[Step]"
                body_lines.append(f"{prefix}log.info({(step_label + ' ' + (label or raw_cmd))!r})")

                # 输入参数：优先取前序节点同名输出，其次取默认值
                _emit_inputs(prefix, node)

                cmds = commands or ([raw_cmd] if raw_cmd else [])
                if not cmds:
                    body_lines.append(f"{prefix}# 该步骤没有可下发的设备指令")
                    body_lines.append(f"{prefix}results['skipped'] += 1")
                    body_lines.append("")
                else:
                    if not commands:
                        # The extractor found no real command, so the raw node
                        # text is being sent verbatim. That is correct for
                        # protocols like SCPI/serial (the command simply has no
                        # ``@11_..;`` shape), but wrong when the field holds a
                        # Chinese description — surface it so it is obvious.
                        body_lines.append(
                            f"{prefix}# ⚠️ 未能解析出结构化设备指令，此处直接下发节点原文；"
                            f"若原文是中文描述而非真实指令，请在节点「执行命令」里填写真实指令"
                            f"（如 @11_TSTOP; 或 JSON 命令）"
                        )
                    wired = bool(device) and device != "None"
                    for cmd, count in collapse_runs(cmds):
                        # {占位符} 在运行时由上下文渲染，支持引用前序节点的输出
                        call = f"response = {device}.send_command(_r({cmd!r}, ctx))" if wired \
                            else f"# response = send_command(_r({cmd!r}, ctx))  # TODO: wire real device"
                        if count > 1:
                            # e.g. "循环读取 100 次" -> emit a loop, not 100 lines
                            body_lines.append(f"{prefix}for _repeat in range({count}):")
                            body_lines.append(f"{prefix}    {call}")
                        else:
                            body_lines.append(f"{prefix}{call}")
                    if expected:
                        body_lines.append(f"{prefix}{assertion_stmt(expected, render=True)}")

                    # result parsing + judgement, mirroring the runtime engine
                    parsed_vars: Dict[str, str] = {}
                    for pidx, spec in enumerate(config.get("parsers") or []):
                        name = spec.get("name") or f"字段{pidx + 1}"
                        dtype = spec.get("data_type") or "string"
                        start = spec.get("start", 0)
                        length = spec.get("length", 1)
                        unit = spec.get("unit") or "byte"
                        cond = spec.get("conditions") or {}
                        var = f"parsed_{pidx}"
                        parsed_vars[var] = var
                        body_lines.append(f"{prefix}# 结果解析: {name}")
                        hex_field = spec.get("hex_field") or "all"
                        body_lines.append(
                            f"{prefix}{var} = parse_field(response, data_type={dtype!r}, "
                            f"start={start}, length={length}, unit={unit!r}, "
                            f"hex_field={hex_field!r})"
                        )
                        body_lines.append(f"{prefix}log.info(f'解析 {name} = {{{var}}}')")
                        body_lines.append(
                            f"{prefix}results['steps'].append({{'step': {name!r}, "
                            f"'parsed': {var}}})"
                        )
                        lo = cond.get("min")
                        hi = cond.get("max")
                        checks: List[str] = []
                        if lo is not None:
                            checks.append(
                                f"assert {var} >= {lo!r}, "
                                f"f\"解析 {name}: {{{var}}} 低于最小值 {lo}\""
                            )
                        if hi is not None:
                            checks.append(
                                f"assert {var} <= {hi!r}, "
                                f"f\"解析 {name}: {{{var}}} 超出最大值 {hi}\""
                            )
                        equals = cond.get("equals") or []
                        if isinstance(equals, str):
                            equals = [v.strip() for v in equals.split(",") if v.strip()]
                        if equals:
                            str_opts = ", ".join(repr(str(e).strip().lower()) for e in equals)
                            # numeric options so "0x85" also matches 133, like
                            # the runtime parser does
                            num_opts: List[float] = []
                            for e in equals:
                                try:
                                    num_opts.append(float(str(e).strip()))
                                except ValueError:
                                    pass
                            clause = f"str({var}).strip().lower() in [{str_opts}]"
                            if num_opts:
                                clause += f" or {var} in {num_opts!r}"
                            checks.append(
                                f"assert {clause}, "
                                f"f\"解析 {name}: {{{var}}} 不在期望值 {list(equals)} 内\""
                            )
                        if checks:
                            # an empty frame has no value - skip judgement
                            body_lines.append(
                                f"{prefix}if {var} != \"unknown\":"
                            )
                            body_lines.extend(f"{prefix}    {c}" for c in checks)

                    # 输出返回值：写入上下文，供后续节点 {占位符} 引用
                    _emit_outputs(prefix, node, {"response": "response", **parsed_vars})

                    body_lines.append(f"{prefix}time.sleep({timeout_ms})")
                    body_lines.append(f"{prefix}results['steps'].append({{'step': {label or raw_cmd!r}, 'status': 'passed'}})")
                    body_lines.append(f"{prefix}results['passed'] += 1")
                    body_lines.append("")

            elif ntype == "init":
                # 初始化 / 重置节点：集中声明变量，供后续节点引用
                visited_global.add(node_id)
                body_lines.append(f"{prefix}# ===== 初始化 / 变量声明（同时写入流程上下文） =====")
                for spec in flow_context.init_node_variables(node):
                    vname = spec["name"]
                    vtype = spec["type"]
                    body_lines.append(
                        f"{prefix}{vname} = {_init_literal(spec.get('value'), vtype)}"
                    )
                    # 同时写入上下文，后续节点可用 {变量名} 或条件表达式直接引用
                    body_lines.append(f"{prefix}ctx[{vname!r}] = {vname}")
                    if spec.get("desc"):
                        body_lines.append(f"{prefix}# {spec.get('desc')}")
                _emit_inputs(prefix, node)
                _emit_outputs(prefix, node, {})

            elif ntype == "delay":
                # 延时节点：等待若干毫秒（支持 {占位符} 引用前序节点输出）
                visited_global.add(node_id)
                raw_ms = config.get("duration", config.get("duration_ms", 0))
                body_lines.append(f"{prefix}# ===== 延时 {raw_ms} ms =====")
                _emit_inputs(prefix, node)
                body_lines.append(
                    f"{prefix}_delay_ms = _cast(_r({str(raw_ms)!r}, ctx), 'float') or 0.0"
                )
                body_lines.append(f"{prefix}log.info('延时 ' + str(_delay_ms) + ' ms')")
                body_lines.append(f"{prefix}time.sleep(max(0.0, _delay_ms) / 1000.0)")
                body_lines.append(
                    f"{prefix}results['steps'].append({{'step': {label!r}, 'status': 'passed'}})"
                )
                body_lines.append(f"{prefix}results['passed'] += 1")
                body_lines.append("")
                _emit_outputs(prefix, node, {"delay_ms": "_delay_ms"})

            elif ntype == "condition":
                visited_global.add(node_id)
                expr = config.get("condition", "True")
                nbrs = adj.get(node_id, [])
                labelled_true = [nb for nb in nbrs if _edge_label(node_id, nb["target"]) in ("true", "yes", "y")]
                labelled_false = [nb for nb in nbrs if _edge_label(node_id, nb["target"]) in ("false", "no", "n")]
                unlabelled = [
                    nb for nb in nbrs
                    if nb not in labelled_true and nb not in labelled_false
                ]

                # Unlabelled edges are the common case when a branch is added
                # on the canvas: fall back to edge order (first = true,
                # second = false) instead of treating *every* unlabelled edge
                # as the true branch.
                true_nbrs = list(labelled_true)
                false_nbrs = list(labelled_false)
                if not true_nbrs and unlabelled:
                    true_nbrs = [unlabelled.pop(0)]
                if not false_nbrs and unlabelled:
                    false_nbrs = [unlabelled.pop(0)]
                # any remaining unlabelled edges are convergence/other links
                branch_targets = {
                    nb["target"] for nb in (true_nbrs + false_nbrs)
                }

                true_tgt = true_nbrs[0]["target"] if true_nbrs else None
                false_tgt = false_nbrs[0]["target"] if false_nbrs else None

                # 输入参数 + 条件表达式（可引用 {前序节点输出}）
                _emit_inputs(prefix, node)
                _emit_outputs(prefix, node, {"result": f"_cond({expr!r}, ctx)"})

                # Walk branches WITHOUT following remaining neighbours so the
                # convergence point stays outside the if/else block.
                # 条件表达式以流程上下文为变量求值，支持写 "voltage > 10"
                body_lines.append(f"{prefix}if _cond({expr!r}, ctx):")
                if true_tgt:
                    walk(true_tgt, indent + 1, branch_stack | {node_id}, no_remaining=True)
                else:
                    body_lines.append(f"{prefix}    pass  # true (no target)")

                if false_tgt:
                    body_lines.append(f"{prefix}else:")
                    walk(false_tgt, indent + 1, branch_stack | {node_id}, no_remaining=True)
                else:
                    body_lines.append(f"{prefix}else:")
                    body_lines.append(f"{prefix}    pass")

                # Find convergence: first node reachable from BOTH branch targets
                if true_tgt and false_tgt:
                    true_succ_ids = {nb["target"] for nb in adj.get(true_tgt, [])}
                    false_succ_ids = {nb["target"] for nb in adj.get(false_tgt, [])}
                    convergence = [cid for cid in true_succ_ids & false_succ_ids
                                   if cid not in visited_global]
                    for cid in convergence:
                        walk(cid, indent, branch_stack | {node_id})

            elif ntype == "loop":
                visited_global.add(node_id)
                loop_type = config.get("loop_type", "for")
                expr = config.get("condition", "3")
                var = config.get("variable", "i")
                # while 增强：进入条件 / 跳出条件 / 最大迭代次数
                entry = (config.get("entry_condition") or "").strip()
                entry_fail = config.get("entry_fail_action", "skip")
                break_cond = (config.get("break_condition") or "").strip()
                max_iter = config.get("max_iterations", None)
                # 循环节点自身的执行命令 / 预期结果（与操作节点一致）
                raw_cmd = config.get("command", "") or ""
                expected = config.get("expected") or config.get("expected_result") or ""
                device = config.get("device_id") or "device"
                cmds = node_commands(node) or ([raw_cmd] if raw_cmd else [])
                nbrs = adj.get(node_id, [])

                # Separate body edges from exit edges
                body_nbrs: List[dict] = []
                exit_nbrs: List[dict] = []
                for nb in nbrs:
                    if nb["label"] in ("body", ""):
                        body_nbrs.append(nb)
                    elif nb["label"] in ("exit", "next", "after"):
                        exit_nbrs.append(nb)
                    elif not body_nbrs:
                        body_nbrs.append(nb)
                    else:
                        exit_nbrs.append(nb)

                # 输入参数：优先取前序节点同名输出，其次取默认值
                _emit_inputs(prefix, node)

                # 进入条件：整段循环包在 if 中，不满足时跳过或判失败
                loop_indent = indent
                if entry:
                    body_lines.append(
                        f"{prefix}# 进入条件：不满足时"
                        f"{'判定为失败' if entry_fail == 'fail' else '跳过整个循环'}"
                    )
                    body_lines.append(f"{prefix}if _cond({entry!r}, ctx):")
                    loop_indent = indent + 1
                loop_prefix = "    " * loop_indent
                body_prefix = "    " * (loop_indent + 1)

                if max_iter:
                    body_lines.append(f"{loop_prefix}_loop_iter = 0")

                if loop_type == "for":
                    body_lines.append(f"{loop_prefix}for {var} in range(int(_r({expr!r}, ctx))):")
                else:
                    body_lines.append(f"{loop_prefix}while _cond({expr!r}, ctx):")

                # 最大迭代保护：条件恒真时防止卡死执行引擎
                if max_iter:
                    body_lines.append(f"{body_prefix}_loop_iter += 1")
                    body_lines.append(f"{body_prefix}if _loop_iter > int({max_iter}):")
                    body_lines.append(
                        f"{body_prefix}    log.warning('循环已达最大迭代次数 "
                        f"{max_iter}，强制跳出')"
                    )
                    body_lines.append(f"{body_prefix}    break")

                # 循环节点自身携带的命令：生成 send_command + 断言 + 结果解析
                loop_parsed: Dict[str, str] = {}
                if cmds:
                    wired = bool(device) and device != "None"
                    for cmd, count in collapse_runs(cmds):
                        call = f"response = {device}.send_command(_r({cmd!r}, ctx))" if wired \
                            else f"# response = send_command(_r({cmd!r}, ctx))  # TODO: wire real device"
                        body_lines.append(f"{body_prefix}{call}")
                    if expected:
                        body_lines.append(f"{body_prefix}{assertion_stmt(expected, render=True)}")
                    for pidx, spec in enumerate(config.get("parsers") or []):
                        name = spec.get("name") or f"字段{pidx + 1}"
                        dtype = spec.get("data_type") or "string"
                        start = spec.get("start", 0)
                        length = spec.get("length", 1)
                        unit = spec.get("unit") or "byte"
                        cond = spec.get("conditions") or {}
                        pvar = f"parsed_{pidx}"
                        loop_parsed[pvar] = pvar
                        hex_field = spec.get("hex_field") or "all"
                        body_lines.append(f"{body_prefix}# 结果解析: {name}")
                        body_lines.append(
                            f"{body_prefix}{pvar} = parse_field(response, data_type={dtype!r}, "
                            f"start={start}, length={length}, unit={unit!r}, "
                            f"hex_field={hex_field!r})"
                        )
                        body_lines.append(
                            f"{body_prefix}results['steps'].append({{'step': {name!r}, "
                            f"'parsed': {pvar}}})"
                        )
                        lo = cond.get("min")
                        hi = cond.get("max")
                        pchecks: List[str] = []
                        if lo is not None:
                            pchecks.append(
                                f"assert {pvar} >= {lo!r}, "
                                f"f\"解析 {name}: {{{pvar}}} 低于最小值 {lo}\""
                            )
                        if hi is not None:
                            pchecks.append(
                                f"assert {pvar} <= {hi!r}, "
                                f"f\"解析 {name}: {{{pvar}}} 超出最大值 {hi}\""
                            )
                        if pchecks:
                            # 空帧没有数值，跳过判定
                            body_lines.append(f"{body_prefix}if {pvar} != \"unknown\":")
                            body_lines.extend(f"{body_prefix}    {c}" for c in pchecks)

                # 输出返回值：写入上下文，供后续节点 {占位符} 引用
                if cmds:
                    _emit_outputs(body_prefix, node, {"response": "response", **loop_parsed})

                if body_nbrs:
                    walk(body_nbrs[0]["target"], loop_indent + 1, branch_stack | {node_id})
                elif not cmds:
                    body_lines.append(f"{body_prefix}pass  # loop body")

                # 跳出条件：每轮结束后判断，满足则提前退出
                if break_cond:
                    body_lines.append(f"{body_prefix}# 跳出条件")
                    body_lines.append(f"{body_prefix}if _cond({break_cond!r}, ctx):")
                    body_lines.append(f"{body_prefix}    log.info('满足跳出条件，提前结束循环')")
                    body_lines.append(f"{body_prefix}    break")

                # 进入条件不满足时的 else 分支
                if entry:
                    body_lines.append(f"{prefix}else:")
                    if entry_fail == "fail":
                        body_lines.append(
                            f"{prefix}    raise AssertionError('循环进入条件不满足: {entry}')"
                        )
                    else:
                        body_lines.append(
                            f"{prefix}    log.info('跳过循环：进入条件不满足 ({entry})')"
                        )

                # Walk exit target after the loop
                if exit_nbrs:
                    walk(exit_nbrs[0]["target"], indent, branch_stack | {node_id})

            # ---- Walk remaining unvisited successors (unless suppressed) ----
            if no_remaining:
                return

            remaining = []
            for nb in adj.get(node_id, []):
                # Skip condition branches (already emitted inside if/else).
                # Matching on the resolved targets also covers unlabelled
                # edges, which previously leaked out of the branch and were
                # emitted a second time as sequential code.
                if ntype == "condition" and nb["target"] in branch_targets:
                    continue
                # Skip loop body edges (already walked inside the loop block)
                if ntype == "loop":
                    if nb["label"] in ("body", "") and body_nbrs and nb["target"] == body_nbrs[0]["target"]:
                        continue
                remaining.append(nb)

            for nb in remaining:
                if nb["target"] not in visited_global:
                    walk(nb["target"], indent, branch_stack | {node_id})

        if start_id:
            walk(start_id, indent=1, branch_stack=set())

        # Nodes that are not reachable from the start (e.g. a condition that
        # was dropped on the canvas but never wired up) used to be silently
        # dropped, so adding a judgement appeared to "change nothing" in the
        # generated code. Emit them in a clearly marked section instead.
        orphans = [
            n for n in nodes
            if n.get("id") not in visited_global
            and n.get("type") not in ("start", "input")
        ]
        if orphans:
            body_lines.append("")
            body_lines.append("    # ===== 以下节点未连接到主流程（已生成但不会被执行） =====")
            body_lines.append("    # 提示: 在流程图中用连线将其接入主流程，即可参与执行")
            for o in orphans:
                walk(o["id"], indent=1, branch_stack=set())

        if not visited_global:
            body_lines.append("    log.warning('Empty flow — no steps to execute.')")

        body_lines.append("")
        body_lines.append("    log.info(f'Results: {results[\"passed\"]} passed, {results[\"failed\"]} failed')")
        body_lines.append("    return results")
        body_lines.append("")
        body_lines.append("")
        body_lines.append("if __name__ == '__main__':")
        body_lines.append("    run()")

        return "\n".join(header + body_lines)

    def generate_json_summary(self, nodes, edges, name="") -> dict:
        """Return a structured JSON description of the flow."""
        node_map = {n["id"]: n for n in nodes}
        steps = []
        for edge in edges:
            src = node_map.get(edge["source"], {})
            tgt = node_map.get(edge["target"], {})
            steps.append({
                "from": src.get("data", {}).get("label", edge["source"]),
                "to": tgt.get("data", {}).get("label", edge["target"]),
                "condition": edge.get("label", ""),
            })
        return {
            "test_case": name,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "node_types": list(set(n.get("type", "default") for n in nodes)),
            "execution_path": steps,
        }


codegen_service = CodeGenService()
