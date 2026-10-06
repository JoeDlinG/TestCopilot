"""Test case generation service — bridges AI generation with database persistence."""
from __future__ import annotations
import json
import logging
from typing import Optional, List, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.models import Device, TestCase, TestFlow
from app.services.ai_service import ai_service

logger = logging.getLogger(__name__)


class TestGenService:
    """Service for AI-powered test case generation and persistence."""

    async def generate_and_save(
        self,
        db: AsyncSession,
        requirements: str,
        model_id: Optional[str] = None,
        available_devices: Optional[List[Dict[str, Any]]] = None,
        input_type: str = "text",
        skill_protocols: Optional[List[str]] = None,
    ) -> dict:
        """Generate test cases from requirements and save to database."""
        # Generate via AI
        gen_result = await ai_service.generate_test_cases(
            db, model_id, requirements, available_devices,
            skill_protocols=skill_protocols,
        )

        parsed = gen_result.get("parsed", {})
        test_cases_data = parsed.get("test_cases", [])

        saved_cases = await self._save_cases(
            db, test_cases_data, requirements, model_id
        )

        return {
            "raw_response": gen_result.get("raw_response", ""),
            "saved_cases": saved_cases,
            "total_generated": len(saved_cases),
        }

    async def import_from_ai(
        self,
        db: AsyncSession,
        test_cases_data: List[Dict[str, Any]],
        requirements: str = "",
        model_id: Optional[str] = None,
        available_devices: Optional[List[Dict[str, Any]]] = None,
    ) -> dict:
        """Import pre-generated AI test cases and create flows for each."""
        saved_cases = await self._save_cases(
            db, test_cases_data, requirements, model_id, available_devices
        )
        return {
            "saved_cases": saved_cases,
            "total_imported": len(saved_cases),
        }

    async def _save_cases(
        self,
        db: AsyncSession,
        test_cases_data: List[Dict[str, Any]],
        requirements: str = "",
        model_id: Optional[str] = None,
        available_devices: Optional[List[Dict[str, Any]]] = None,
    ) -> list:
        """Save test cases and create flows for each."""
        # The AI may not have been told which devices exist (the import path
        # never carries a device list), so fall back to the devices we actually
        # have — otherwise every generated node ends up with an empty
        # "执行设备" and the executor has to guess.
        devices = [d for d in (available_devices or []) if d]
        if not devices:
            result = await db.execute(select(Device))
            devices = [
                {
                    "id": d.id, "name": d.name, "type": d.type,
                    "protocol": d.protocol, "status": d.status,
                }
                for d in result.scalars().all()
            ]

        saved_cases = []
        for tc_data in test_cases_data:
            # Create test case
            test_case = TestCase(
                name=tc_data.get("name", "Untitled Test Case"),
                description=tc_data.get("description", ""),
                requirement_raw=requirements,
                tags=json.dumps(tc_data.get("tags", []), ensure_ascii=False),
                ai_model_id=model_id,
            )
            db.add(test_case)
            await db.commit()
            await db.refresh(test_case)

            # Create flow from description
            flow_description = tc_data.get("flow_description", "")
            flow_nodes, flow_edges = self._description_to_flow(
                tc_data.get("steps", []),
                flow_description,
                available_devices=devices,
                case_devices=tc_data.get("devices_required") or [],
            )

            flow = TestFlow(
                testcase_id=test_case.id,
                nodes=json.dumps(flow_nodes, ensure_ascii=False),
                edges=json.dumps(flow_edges, ensure_ascii=False),
            )
            db.add(flow)
            await db.commit()
            await db.refresh(flow)

            # Link flow to test case
            test_case.flow_id = flow.id
            await db.commit()

            saved_cases.append({
                "id": test_case.id,
                "name": test_case.name,
                "description": test_case.description,
                "flow_id": flow.id,
                "tags": tc_data.get("tags", []),
            })

        return saved_cases

    # ------------------------------------------------------------------ #
    # Device matching
    # ------------------------------------------------------------------ #

    @staticmethod
    def _match_device(
        hints: List[str], devices: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Map free-form hints (device_type / devices_required) to a device.

        Priority: exact protocol match → name contains hint → protocol/type
        contains hint. Falls back to ``None`` when nothing matches (the runtime
        then resolves the device from the command itself).
        """
        cleaned = [str(h or "").strip().lower() for h in hints if str(h or "").strip()]
        if not cleaned or not devices:
            return None

        def protocol(d: Dict[str, Any]) -> str:
            return str(d.get("protocol") or "").lower()

        def name(d: Dict[str, Any]) -> str:
            return str(d.get("name") or "").lower()

        def dtype(d: Dict[str, Any]) -> str:
            return str(d.get("type") or "").lower()

        for hint in cleaned:
            for d in devices:
                if protocol(d) and protocol(d) == hint:
                    return d
        # "PeakCAN" / "Mini Gateway 100" style hints
        for hint in cleaned:
            for d in devices:
                if hint and (hint in name(d) or name(d) in hint):
                    return d
        for hint in cleaned:
            for d in devices:
                if hint and (hint in protocol(d) or hint in dtype(d)):
                    return d
        return None

    @classmethod
    def _device_hints(
        cls, step: Dict[str, Any], case_devices: List[str]
    ) -> List[str]:
        """All device hints a single step carries, most specific first."""
        hints: List[str] = []
        for key in ("device_id", "device_name", "device", "device_type"):
            value = step.get(key)
            if isinstance(value, str) and value.strip():
                hints.append(value.strip())
        device = step.get("device")
        if isinstance(device, dict):
            hints.extend(
                str(device.get(k)).strip()
                for k in ("id", "name", "protocol", "type")
                if device.get(k)
            )
        params = step.get("parameters") or {}
        if isinstance(params, dict) and params.get("device_id"):
            hints.append(str(params["device_id"]).strip())
        hints.extend(str(c).strip() for c in (case_devices or []) if str(c or "").strip())
        return hints

    def _description_to_flow(
        self,
        steps: List[Dict[str, Any]],
        flow_description: str,
        available_devices: Optional[List[Dict[str, Any]]] = None,
        case_devices: Optional[List[str]] = None,
    ) -> tuple[List[Dict], List[Dict]]:
        """Convert test steps into ReactFlow nodes and edges.

        Supports node types: start, action, condition, loop, end.
        Condition nodes get true/false labelled edges; loop nodes get a body edge
        and an exit edge that continues to the next sequential node.
        """
        nodes: List[Dict] = []
        edges: List[Dict] = []

        devices = [d for d in (available_devices or []) if d]
        case_devices = [str(c) for c in (case_devices or []) if str(c or "").strip()]

        def device_fields(step: Dict[str, Any]) -> Dict[str, Any]:
            """Resolve *this step's* device so the node carries a real 设备 id.

            Without this every generated node had ``device_id: null`` and the
            runtime had to guess the device — it then picked the first
            connected one, so a PeakCAN step could be sent to a Mini Gateway.
            """
            dev = self._match_device(self._device_hints(step, case_devices), devices)
            if dev is None and len(devices) == 1:
                dev = devices[0]
            if dev is None:
                return {}
            return {
                "device_id": dev.get("id"),
                "device_protocol": dev.get("protocol"),
            }

        y_step = 120
        x_center = 400

        # ---- Start node ----
        nodes.append({
            "id": "node_start",
            "type": "start",
            "data": {"label": "开始"},
            "position": {"x": x_center, "y": 0},
            "config": {},
        })
        prev_id = "node_start"

        for i, step in enumerate(steps):
            node_id = f"node_{i + 1}"
            flow_type = (step.get("flow_type") or "action").lower()
            label = step.get("action", f"步骤 {i + 1}")
            config = {
                "device_id": None,
                "command": step.get("action", ""),
                "expected": step.get("expected_result", ""),
                "parameters": step.get("parameters", {}),
                "timeout": 5000,
                "retry_count": 0,
            }
            config.update(device_fields(step))

            if flow_type == "delay":
                # 延时节点：等待 duration_ms 毫秒后继续
                nodes.append({
                    "id": node_id,
                    "type": "delay",
                    "data": {"label": label or "延时"},
                    "position": {"x": x_center, "y": y_step},
                    "config": {
                        "command": "",
                        "expected": "",
                        "duration": step.get("duration_ms") or step.get("duration") or 1000,
                        "timeout": 5000,
                        **device_fields(step),
                    },
                })
                edges.append({
                    "id": f"edge_{prev_id}_{node_id}",
                    "source": prev_id, "target": node_id,
                    "label": "",
                })
                prev_id = node_id
                y_step += 80
                continue

            if flow_type == "condition":
                # Condition (diamond) node
                expr = step.get("condition", "True")
                config["condition"] = expr
                config["true_label"] = step.get("true_branch", "是")
                config["false_label"] = step.get("false_branch", "否")
                nodes.append({
                    "id": node_id,
                    "type": "condition",
                    "data": {"label": label},
                    "position": {"x": x_center, "y": y_step},
                    "config": config,
                })
                edges.append({
                    "id": f"edge_{prev_id}_{node_id}",
                    "source": prev_id, "target": node_id,
                    "label": "",
                })
                # Two outgoing edges (true/false) — connect to next steps
                true_node_id = f"node_{i + 1}_true"
                false_node_id = f"node_{i + 1}_false"
                edge_id_suffix = 1

                # True branch — a placeholder action node (will be refined later)
                nodes.append({
                    "id": true_node_id,
                    "type": "action",
                    "data": {"label": step.get("true_branch", "True")},
                    "position": {"x": x_center - 180, "y": y_step + 80},
                    "config": {
                        "command": step.get("true_branch", ""),
                        "expected": "",
                        **device_fields(step),
                    },
                })
                edges.append({
                    "id": f"edge_{node_id}_true",
                    "source": node_id, "target": true_node_id,
                    "label": "true",
                    "style": {"stroke": "#52c41a"},
                })

                nodes.append({
                    "id": false_node_id,
                    "type": "action",
                    "data": {"label": step.get("false_branch", "False")},
                    "position": {"x": x_center + 180, "y": y_step + 80},
                    "config": {
                        "command": step.get("false_branch", ""),
                        "expected": "",
                        **device_fields(step),
                    },
                })
                edges.append({
                    "id": f"edge_{node_id}_false",
                    "source": node_id, "target": false_node_id,
                    "label": "false",
                    "style": {"stroke": "#ff4d4f"},
                })
                # After condition, merge back to main flow below both branches
                merge_id = f"node_{i + 1}_merge"
                nodes.append({
                    "id": merge_id,
                    "type": "action",
                    "data": {"label": "继续"},
                    "position": {"x": x_center, "y": y_step + 180},
                    "config": {"command": "", "expected": "", **device_fields(step)},
                })
                edges.append({
                    "id": f"edge_true_merge",
                    "source": true_node_id, "target": merge_id,
                    "label": "",
                })
                edges.append({
                    "id": f"edge_false_merge",
                    "source": false_node_id, "target": merge_id,
                    "label": "",
                })
                prev_id = merge_id
                y_step += 200

            elif flow_type == "loop":
                # Loop node
                loop_type = step.get("loop_type", "for")
                var = step.get("loop_variable", "i")
                expr = step.get("loop_expression", "3")
                config["loop_type"] = loop_type
                config["variable"] = var
                config["condition"] = expr
                body_label = step.get("loop_body", label)
                nodes.append({
                    "id": node_id,
                    "type": "loop",
                    "data": {"label": label},
                    "position": {"x": x_center, "y": y_step},
                    "config": config,
                })
                edges.append({
                    "id": f"edge_{prev_id}_{node_id}",
                    "source": prev_id, "target": node_id,
                    "label": "",
                })
                # Body node
                body_node_id = f"{node_id}_body"
                nodes.append({
                    "id": body_node_id,
                    "type": "action",
                    "data": {"label": body_label},
                    "position": {"x": x_center, "y": y_step + 80},
                    # 循环体用同一步骤的命令，方便运行时引擎真的按次数迭代
                    "config": {
                        "command": (
                            step.get("loop_body") or step.get("action") or body_label
                        ),
                        "expected": step.get("expected_result", ""),
                        "parameters": step.get("parameters", {}),
                        **device_fields(step),
                    },
                })
                edges.append({
                    "id": f"edge_{node_id}_body",
                    "source": node_id, "target": body_node_id,
                    "label": "body",
                })
                # After-loop exit node
                exit_id = f"{node_id}_exit"
                nodes.append({
                    "id": exit_id,
                    "type": "action",
                    "data": {"label": "循环结束"},
                    "position": {"x": x_center, "y": y_step + 180},
                    "config": {"command": "", "expected": "", **device_fields(step)},
                })
                edges.append({
                    "id": f"edge_body_exit",
                    "source": body_node_id, "target": exit_id,
                    "label": "exit",
                })
                prev_id = exit_id
                y_step += 200

            else:
                # Normal action node
                nodes.append({
                    "id": node_id,
                    "type": "action",
                    "data": {"label": label},
                    "position": {"x": x_center, "y": y_step},
                    "config": config,
                })
                edges.append({
                    "id": f"edge_{prev_id}_{node_id}",
                    "source": prev_id, "target": node_id,
                    "label": "",
                })
                prev_id = node_id
                y_step += 80

        # ---- End node ----
        end_idx = len(steps) + 1
        end_id = f"node_{end_idx}"
        nodes.append({
            "id": end_id,
            "type": "end",
            "data": {"label": "结束"},
            "position": {"x": x_center, "y": y_step},
            "config": {},
        })
        edges.append({
            "id": f"edge_{prev_id}_{end_id}",
            "source": prev_id, "target": end_id,
            "label": "",
        })

        return nodes, edges


testgen_service = TestGenService()
