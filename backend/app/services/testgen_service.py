"""Test case generation service — bridges AI generation with database persistence."""
from __future__ import annotations
import json
import logging
from typing import Optional, List, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.models import TestCase, TestFlow
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
    ) -> dict:
        """Import pre-generated AI test cases and create flows for each."""
        saved_cases = await self._save_cases(
            db, test_cases_data, requirements, model_id
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
    ) -> list:
        """Save test cases and create flows for each."""
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
                tc_data.get("steps", []), flow_description
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

    def _description_to_flow(
        self, steps: List[Dict[str, Any]], flow_description: str
    ) -> tuple[List[Dict], List[Dict]]:
        """Convert test steps into ReactFlow nodes and edges.

        Supports node types: start, action, condition, loop, end.
        Condition nodes get true/false labelled edges; loop nodes get a body edge
        and an exit edge that continues to the next sequential node.
        """
        nodes: List[Dict] = []
        edges: List[Dict] = []

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
                    "config": {"command": step.get("true_branch", ""), "expected": ""},
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
                    "config": {"command": step.get("false_branch", ""), "expected": ""},
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
                    "config": {"command": "", "expected": ""},
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
                    "config": {"command": body_label, "expected": ""},
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
                    "config": {"command": "", "expected": ""},
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
