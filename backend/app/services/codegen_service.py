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


def assertion_stmt(expected: str) -> str:
    """Build an assertion line for an expected-result string.

    Supports numeric comparisons (">10", "<=3.3"), containment
    ("contains OK" / "包含 OK") and plain equality.
    """
    e = str(expected).strip()
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
                    f"assert {needle!r} in str(response), "
                    f"f\"判断失败: {{response}} 不包含 {needle}\""
                )
    return (
        f"assert str(response).strip() == {e!r}, "
        f"f\"判断失败: 期望 {e}, 实际 {{response}}\""
    )


# Emitted into generated scripts so they can parse and judge responses exactly
# like the platform's ResponseParser does at runtime.
PARSE_HELPER = r'''

def _to_bytes(raw):
    """Convert a device response into raw bytes (hex or text)."""
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw)
    s = str(raw or "").strip()
    if not s:
        return b""
    groups = re.findall(r"(?i)\b0x([0-9a-f]+)\b", s)
    if groups:
        joined = "".join(groups)
        if len(joined) % 2 == 0:
            return bytes.fromhex(joined)
    compact = re.sub(r"[,\s_]+", "", s).lower().replace("0x", "")
    if compact and re.fullmatch(r"[0-9a-f]+", compact) and len(compact) % 2 == 0:
        return bytes.fromhex(compact)
    return s.encode("utf-8", errors="replace")


def parse_field(raw, data_type="string", start=0, length=1, unit="byte"):
    """Slice a response and convert it, mirroring the platform parser."""
    data = _to_bytes(raw)
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
            "",
            "",
            "def run() -> dict:",
            '    """Execute the test flow and return a summary dict."""',
            "    results = {'passed': 0, 'failed': 0, 'skipped': 0, 'steps': []}",
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

                cmds = commands or ([raw_cmd] if raw_cmd else [])
                if not cmds:
                    body_lines.append(f"{prefix}# 该步骤没有可下发的设备指令")
                    body_lines.append(f"{prefix}results['skipped'] += 1")
                    body_lines.append("")
                else:
                    wired = bool(device) and device != "None"
                    for cmd, count in collapse_runs(cmds):
                        call = f"response = {device}.send_command({cmd!r})" if wired \
                            else f"# response = send_command({cmd!r})  # TODO: wire real device"
                        if count > 1:
                            # e.g. "循环读取 100 次" -> emit a loop, not 100 lines
                            body_lines.append(f"{prefix}for _repeat in range({count}):")
                            body_lines.append(f"{prefix}    {call}")
                        else:
                            body_lines.append(f"{prefix}{call}")
                    if expected:
                        body_lines.append(f"{prefix}{assertion_stmt(expected)}")

                    # result parsing + judgement, mirroring the runtime engine
                    for pidx, spec in enumerate(config.get("parsers") or []):
                        name = spec.get("name") or f"字段{pidx + 1}"
                        dtype = spec.get("data_type") or "string"
                        start = spec.get("start", 0)
                        length = spec.get("length", 1)
                        unit = spec.get("unit") or "byte"
                        cond = spec.get("conditions") or {}
                        var = f"parsed_{pidx}"
                        body_lines.append(f"{prefix}# 结果解析: {name}")
                        body_lines.append(
                            f"{prefix}{var} = parse_field(response, data_type={dtype!r}, "
                            f"start={start}, length={length}, unit={unit!r})"
                        )
                        body_lines.append(f"{prefix}log.info(f'解析 {name} = {{{var}}}')")
                        body_lines.append(
                            f"{prefix}results['steps'].append({{'step': {name!r}, "
                            f"'parsed': {var}}})"
                        )
                        lo = cond.get("min")
                        hi = cond.get("max")
                        if lo is not None:
                            body_lines.append(
                                f"{prefix}assert {var} >= {lo!r}, "
                                f"f\"解析 {name}: {{{var}}} 低于最小值 {lo}\""
                            )
                        if hi is not None:
                            body_lines.append(
                                f"{prefix}assert {var} <= {hi!r}, "
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
                            body_lines.append(
                                f"{prefix}assert {clause}, "
                                f"f\"解析 {name}: {{{var}}} 不在期望值 {list(equals)} 内\""
                            )

                    body_lines.append(f"{prefix}time.sleep({timeout_ms})")
                    body_lines.append(f"{prefix}results['steps'].append({{'step': {label or raw_cmd!r}, 'status': 'passed'}})")
                    body_lines.append(f"{prefix}results['passed'] += 1")
                    body_lines.append("")

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

                # Walk branches WITHOUT following remaining neighbours so the
                # convergence point stays outside the if/else block.
                body_lines.append(f"{prefix}if {expr}:")
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

                if loop_type == "for":
                    body_lines.append(f"{prefix}for {var} in range(int({expr})):")
                else:
                    body_lines.append(f"{prefix}while {expr}:")

                if body_nbrs:
                    walk(body_nbrs[0]["target"], indent + 1, branch_stack | {node_id})
                else:
                    body_lines.append(f"{prefix}    pass  # loop body")

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
