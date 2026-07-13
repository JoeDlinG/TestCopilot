"""Test execution engine service.

Parses test flow diagrams, executes steps sequentially/conditionally,
and records results at both execution and step level.
"""
from __future__ import annotations
import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.models import (
    TestCase, TestFlow, TestExecution, TestStepResult,
    ExecutionStatus, ExecutionResult, StepStatus,
)
from app.services.device_service import device_service
from app.api.websocket import broadcast_execution_update

logger = logging.getLogger(__name__)


class ExecutionEngine:
    """Engine for executing test flows."""

    def __init__(self):
        self._running_executions: Dict[str, asyncio.Task] = {}

    async def start_execution(
        self,
        db: AsyncSession,
        testcase_id: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> TestExecution:
        """Start a test execution for a test case."""
        # Verify test case exists
        tc_result = await db.execute(select(TestCase).where(TestCase.id == testcase_id))
        test_case = tc_result.scalar_one_or_none()
        if not test_case:
            raise ValueError(f"Test case {testcase_id} not found")

        # Load flow data
        flow_result = await db.execute(
            select(TestFlow).where(TestFlow.testcase_id == testcase_id)
        )
        flow = flow_result.scalar_one_or_none()

        # Parse nodes
        nodes = []
        if flow and flow.nodes:
            try:
                nodes = json.loads(flow.nodes) if isinstance(flow.nodes, str) else flow.nodes
            except json.JSONDecodeError:
                pass

        # Create execution record
        options_json = json.dumps(options, ensure_ascii=False) if options else None
        execution = TestExecution(
            testcase_id=testcase_id,
            status=ExecutionStatus.RUNNING.value,
            options=options_json,
            total_steps=len([n for n in nodes if n.get("type") in ("test_step", "command")]),
            started_at=datetime.utcnow(),
        )
        db.add(execution)
        await db.commit()
        await db.refresh(execution)

        # Update test case status
        test_case.status = "running"
        await db.commit()

        # Run execution in background
        task = asyncio.create_task(
            self._run_execution(db, execution, nodes, options)
        )
        self._running_executions[execution.id] = task

        return execution

    async def stop_execution(self, db: AsyncSession, execution_id: str) -> dict:
        """Stop a running execution."""
        if execution_id in self._running_executions:
            self._running_executions[execution_id].cancel()
            del self._running_executions[execution_id]

        result = await db.execute(
            select(TestExecution).where(TestExecution.id == execution_id)
        )
        execution = result.scalar_one_or_none()
        if not execution:
            raise ValueError(f"Execution {execution_id} not found")

        execution.status = ExecutionStatus.STOPPED.value
        execution.result = ExecutionResult.ABORTED.value
        execution.completed_at = datetime.utcnow()
        if execution.started_at:
            execution.duration_ms = int(
                (execution.completed_at - execution.started_at).total_seconds() * 1000
            )
        await db.commit()

        await broadcast_execution_update(execution_id, {
            "type": "execution_stopped",
            "execution_id": execution_id,
            "status": execution.status,
        })

        return {"message": "Execution stopped", "execution_id": execution_id}

    async def _run_execution(
        self,
        db: AsyncSession,
        execution: TestExecution,
        nodes: List[Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None,
    ):
        """Internal: Run the test flow execution."""
        execution_id = execution.id
        stop_on_error = (options or {}).get("stop_on_error", True)
        timeout_per_step = (options or {}).get("timeout_per_step", 30000)

        try:
            # Get execution steps (non-start/end nodes)
            step_nodes = [
                n for n in nodes
                if n.get("type") not in ("start", "end")
            ]

            for idx, node in enumerate(step_nodes):
                node_id = node.get("id", f"node_{idx}")
                node_type = node.get("type", "test_step")
                label = node.get("label", f"Step {idx + 1}")
                config = node.get("config", {})

                # Create step result
                step_result = TestStepResult(
                    execution_id=execution_id,
                    step_index=idx + 1,
                    node_id=node_id,
                    node_type=node_type,
                    label=label,
                    status=StepStatus.RUNNING.value,
                    command=config.get("command", ""),
                    expected=config.get("expected", ""),
                    started_at=datetime.utcnow(),
                )

                async with db as session:
                    session.add(step_result)
                    await session.commit()

                await broadcast_execution_update(execution_id, {
                    "type": "step_started",
                    "execution_id": execution_id,
                    "step_index": idx + 1,
                    "node_id": node_id,
                    "label": label,
                })

                # Execute step
                try:
                    if node_type == "test_step" or node_type == "command":
                        device_id = config.get("device_id")
                        command = config.get("command", "")
                        if device_id and command:
                            response = await device_service.send_command(
                                db, device_id, command,
                                execution_id=execution_id,
                                step_result_id=step_result.id,
                            )
                            step_result.actual = response.get("response", "")
                        else:
                            # Simulated step
                            await asyncio.sleep(0.5)
                            step_result.actual = f"[Simulated] {command}"

                        step_result.status = StepStatus.PASSED.value
                    elif node_type == "condition":
                        step_result.status = StepStatus.PASSED.value
                        step_result.actual = "Condition evaluated"
                    elif node_type == "loop":
                        step_result.status = StepStatus.PASSED.value
                        step_result.actual = "Loop completed"
                    else:
                        step_result.status = StepStatus.PASSED.value
                        step_result.actual = "Step completed"

                except Exception as e:
                    step_result.status = StepStatus.FAILED.value
                    step_result.error_message = str(e)
                    logger.error(f"Step {idx + 1} failed: {e}")

                    await broadcast_execution_update(execution_id, {
                        "type": "step_failed",
                        "execution_id": execution_id,
                        "step_index": idx + 1,
                        "error": str(e),
                    })

                    if stop_on_error:
                        break

                finally:
                    step_result.completed_at = datetime.utcnow()
                    if step_result.started_at:
                        step_result.duration_ms = int(
                            (step_result.completed_at - step_result.started_at).total_seconds() * 1000
                        )

                    async with db as session:
                        session.add(step_result)
                        await session.commit()

                await broadcast_execution_update(execution_id, {
                    "type": "step_completed",
                    "execution_id": execution_id,
                    "step_index": idx + 1,
                    "status": step_result.status,
                })

            # Finalize execution
            async with db as session:
                result = await session.execute(
                    select(TestExecution).where(TestExecution.id == execution_id)
                )
                exec_record = result.scalar_one_or_none()
                if exec_record:
                    exec_record.completed_at = datetime.utcnow()
                    if exec_record.started_at:
                        exec_record.duration_ms = int(
                            (exec_record.completed_at - exec_record.started_at).total_seconds() * 1000
                        )

                    # Count results
                    step_results = await session.execute(
                        select(TestStepResult).where(TestStepResult.execution_id == execution_id)
                    )
                    steps = step_results.scalars().all()

                    passed = sum(1 for s in steps if s.status == StepStatus.PASSED.value)
                    failed = sum(1 for s in steps if s.status == StepStatus.FAILED.value)
                    exec_record.passed_steps = passed
                    exec_record.failed_steps = failed

                    if failed == 0:
                        exec_record.status = ExecutionStatus.PASSED.value
                        exec_record.result = ExecutionResult.PASSED.value
                    else:
                        exec_record.status = ExecutionStatus.FAILED.value
                        exec_record.result = ExecutionResult.FAILED.value

                    await session.commit()

                # Update test case status
                tc_result = await session.execute(
                    select(TestCase).where(TestCase.id == exec_record.testcase_id)
                )
                test_case = tc_result.scalar_one_or_none()
                if test_case:
                    test_case.status = "passed" if failed == 0 else "failed"
                    await session.commit()

            await broadcast_execution_update(execution_id, {
                "type": "execution_completed",
                "execution_id": execution_id,
                "status": exec_record.status if exec_record else "completed",
                "result": exec_record.result if exec_record else "unknown",
            })

        except asyncio.CancelledError:
            logger.info(f"Execution {execution_id} was cancelled")
            raise
        except Exception as e:
            logger.error(f"Execution {execution_id} failed: {e}")
            await broadcast_execution_update(execution_id, {
                "type": "execution_error",
                "execution_id": execution_id,
                "error": str(e),
            })
        finally:
            self._running_executions.pop(execution_id, None)

    async def get_execution(self, db: AsyncSession, execution_id: str) -> Optional[TestExecution]:
        result = await db.execute(
            select(TestExecution).where(TestExecution.id == execution_id)
        )
        return result.scalar_one_or_none()

    async def list_executions(
        self,
        db: AsyncSession,
        testcase_id: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[List[TestExecution], int]:
        query = select(TestExecution)
        count_query = select(TestExecution)

        if testcase_id:
            query = query.where(TestExecution.testcase_id == testcase_id)
            count_query = count_query.where(TestExecution.testcase_id == testcase_id)
        if status:
            query = query.where(TestExecution.status == status)
            count_query = count_query.where(TestExecution.status == status)

        count_result = await db.execute(count_query)
        total = len(count_result.scalars().all())

        query = query.order_by(TestExecution.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await db.execute(query)
        executions = result.scalars().all()

        return executions, total

    async def get_step_results(
        self, db: AsyncSession, execution_id: str
    ) -> List[TestStepResult]:
        result = await db.execute(
            select(TestStepResult)
            .where(TestStepResult.execution_id == execution_id)
            .order_by(TestStepResult.step_index)
        )
        return result.scalars().all()


execution_engine = ExecutionEngine()
