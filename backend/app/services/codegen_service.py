"""Flowchart-to-code generator.

Walks a ReactFlow test-flow graph (nodes + edges) and emits a standalone,
executable Python script that mirrors the flow structure — sequential steps,
condition branches (if/else), loops (for/while), and parallel gateways.
"""
from __future__ import annotations
import json
from collections import defaultdict
from typing import Dict, List, Any, Optional, Set


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
            "",
            "logging.basicConfig(level=logging.INFO)",
            "log = logging.getLogger(__name__)",
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

        def walk(node_id: str, indent: int, branch_stack: Set[str]) -> None:
            """Recursive DFS code generation."""
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

            if ntype in ("start", "input"):
                visited_global.add(node_id)
                body_lines.append(f"{prefix}# ===== {label or 'Start'} =====")

            elif ntype in ("end", "output"):
                visited_global.add(node_id)
                end_label = label or "Flow completed"
                body_lines.append(f"{prefix}log.info('{end_label}')")

            elif ntype in ("action", "test_step", "default"):
                visited_global.add(node_id)
                cmd = config.get("command", label)
                device = config.get("device_id") or "device"
                expected = config.get("expected") or config.get("expected_result") or ""
                timeout_ms = config.get("timeout", 5000) / 1000
                step_no = config.get("step_number", "")
                step_label = f"[Step {step_no}]" if step_no else "[Step]"
                body_lines.append(f"{prefix}log.info('{step_label} {cmd}')")
                if device and device != "None":
                    body_lines.append(f"{prefix}response = {device}.send_command({cmd!r})")
                else:
                    body_lines.append(f"{prefix}# response = send_command({cmd!r})  # TODO: wire real device")
                if expected:
                    body_lines.append(f"{prefix}assert response == {expected!r}, f'Expected {expected!r}, got {{response}}'")
                body_lines.append(f"{prefix}time.sleep({timeout_ms})")
                body_lines.append(f"{prefix}results['steps'].append({{'step': {cmd!r}, 'status': 'passed'}})")
                body_lines.append(f"{prefix}results['passed'] += 1")
                body_lines.append("")

            elif ntype == "condition":
                visited_global.add(node_id)
                expr = config.get("condition", "True")
                nbrs = adj.get(node_id, [])
                true_nbrs = [nb for nb in nbrs if _edge_label(node_id, nb["target"]) in ("true", "yes", "y", "")]
                false_nbrs = [nb for nb in nbrs if _edge_label(node_id, nb["target"]) in ("false", "no", "n")]

                # If no labelled edges, treat first edge as true, second as false
                if not true_nbrs and not false_nbrs:
                    if len(nbrs) >= 1:
                        true_nbrs = [nbrs[0]]
                    if len(nbrs) >= 2:
                        false_nbrs = [nbrs[1]]

                body_lines.append(f"{prefix}if {expr}:")
                if true_nbrs:
                    walk(true_nbrs[0]["target"], indent + 1, branch_stack | {node_id})
                else:
                    body_lines.append(f"{prefix}    pass  # true (no target)")

                if false_nbrs:
                    body_lines.append(f"{prefix}else:")
                    walk(false_nbrs[0]["target"], indent + 1, branch_stack | {node_id})
                else:
                    body_lines.append(f"{prefix}else:")
                    body_lines.append(f"{prefix}    pass")

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

            # After processing current node, walk remaining unvisited neighbours
            remaining = []
            for nb in adj.get(node_id, []):
                # Skip condition branches (already walked inside the condition branch)
                if ntype == "condition":
                    if _edge_label(node_id, nb["target"]) in ("true", "false", "yes", "no", "y", "n"):
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
            walk(start_id, indent=2, branch_stack=set())

        if not visited_global:
            body_lines.append("        log.warning('Empty flow — no steps to execute.')")

        body_lines.append("")
        body_lines.append("        log.info(f'Results: {results[\"passed\"]} passed, {results[\"failed\"]} failed')")
        body_lines.append("        return results")
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
