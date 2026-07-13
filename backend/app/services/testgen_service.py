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
    ) -> dict:
        """Generate test cases from requirements and save to database."""
        # Generate via AI
        gen_result = await ai_service.generate_test_cases(
            db, model_id, requirements, available_devices
        )

        parsed = gen_result.get("parsed", {})
        test_cases_data = parsed.get("test_cases", [])

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

        return {
            "raw_response": gen_result.get("raw_response", ""),
            "saved_cases": saved_cases,
            "total_generated": len(saved_cases),
        }

    def _description_to_flow(
        self, steps: List[Dict[str, Any]], flow_description: str
    ) -> tuple[List[Dict], List[Dict]]:
        """Convert test steps into ReactFlow nodes and edges."""
        nodes = []
        edges = []

        # Start node
        nodes.append({
            "id": "node_start",
            "type": "start",
            "label": "开始",
            "position": {"x": 300, "y": 0},
            "config": {},
        })

        # Step nodes
        for i, step in enumerate(steps):
            node_id = f"node_{i + 1}"
            nodes.append({
                "id": node_id,
                "type": "test_step",
                "label": step.get("action", f"Step {i + 1}"),
                "position": {"x": 300, "y": 100 + i * 120},
                "config": {
                    "device_id": None,
                    "command": step.get("action", ""),
                    "expected": step.get("expected_result", ""),
                    "parameters": step.get("parameters", {}),
                    "timeout": 5000,
                    "retry_count": 0,
                },
            })

            # Edges
            source = "node_start" if i == 0 else f"node_{i}"
            edges.append({
                "id": f"edge_{i + 1}",
                "source": source,
                "target": node_id,
                "label": "",
            })

        # End node
        end_idx = len(steps) + 1
        nodes.append({
            "id": f"node_{end_idx}",
            "type": "end",
            "label": "结束",
            "position": {"x": 300, "y": 100 + len(steps) * 120},
            "config": {},
        })

        if steps:
            edges.append({
                "id": f"edge_{end_idx}",
                "source": f"node_{len(steps)}",
                "target": f"node_{end_idx}",
                "label": "",
            })
        else:
            edges.append({
                "id": "edge_end",
                "source": "node_start",
                "target": f"node_{end_idx}",
                "label": "",
            })

        return nodes, edges


testgen_service = TestGenService()
