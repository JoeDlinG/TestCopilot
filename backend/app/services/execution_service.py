"""Test execution engine service.

Parses test flow diagrams, executes steps sequentially/conditionally,
and records results at both execution and step level.
"""
from __future__ import annotations
import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import async_session
from app.models.models import (
    TestCase, TestFlow, TestExecution, TestStepResult, Device,
    ExecutionStatus, ExecutionResult, StepStatus,
)
from app.services.device_service import device_service
from app.services.response_parser import response_parser
from app.services import flow_context
from app.api.websocket import broadcast_execution_update

logger = logging.getLogger(__name__)


def _safe_json(raw: Optional[str]) -> Optional[Any]:
    """Decode a JSON column, tolerating NULL/empty/invalid content."""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


class ExecutionEngine:
    """Engine for executing test flows."""

    # Node types that must be run as real device commands. AI-generated flows
    # use "action"; manually built ones use "test_step"/"command".
    COMMAND_NODE_TYPES = ("action", "test_step", "command")

    def __init__(self):
        self._running_executions: Dict[str, asyncio.Task] = {}

    # ------------------------------------------------------------------ #
    # Command / device resolution helpers
    # ------------------------------------------------------------------ #

    # Commands look like "@11_MSGRX=CAN1,RPLY1,8;" - the parameter part may
    # contain commas (all device parameters are comma separated), so only ";"
    # whitespace/quotes and CJK punctuation may terminate a command.
    _CMD_RE = re.compile(r"@\d+_[A-Z]+(?:=[^;\s\"'，。]+)?;")
    _CMD_RE_LOOSE = re.compile(r"@\d+_[A-Z]+(?:=[^;\s\"'，。]+)?")
    # "循环读取回复(例如 100 次)" -> repeat the command that many times
    _REPEAT_RE = re.compile(r"(?:循环|重复)[^0-9]{0,15}?(\d+)\s*次")
    MAX_REPEAT = 50

    @classmethod
    def _extract_commands(cls, node: Dict[str, Any]) -> List[str]:
        """Extract the real device command(s) carried by a flow node.

        The generator writes structured commands into ``config.parameters``
        (``command`` or ``commands``), while ``config.command`` is usually a
        natural-language sentence that merely embeds them - so it is parsed as
        a fallback.
        """
        config = node.get("config") or {}
        params = config.get("parameters") or {}
        found: List[str] = []

        raw_list = params.get("commands")
        if isinstance(raw_list, list):
            found.extend(str(c).strip() for c in raw_list if c)
        single = params.get("command")
        if single:
            found.append(str(single).strip())

        text = " ".join([
            str(config.get("command") or ""),
            str((node.get("data") or {}).get("label") or ""),
        ])
        found.extend(cls._CMD_RE.findall(text))
        if not found:
            # tolerate commands written without the trailing ";"
            found.extend(cls._CMD_RE_LOOSE.findall(text))

        ordered: List[str] = []
        seen = set()
        for cmd in found:
            if cmd and cmd not in seen:
                seen.add(cmd)
                ordered.append(cmd)

        # A single command described as "循环读取 N 次" is executed N times.
        m = cls._REPEAT_RE.search(text)
        if m and len(ordered) == 1:
            ordered = ordered * min(int(m.group(1)), cls.MAX_REPEAT)

        return ordered

    @staticmethod
    def _infer_protocol(command: str) -> Optional[str]:
        """Guess the device protocol from a command string."""
        if re.match(r"^@\d+_", command):
            return "mini_gateway100"
        return None

    async def _resolve_device(
        self,
        config: Dict[str, Any],
        options: Optional[Dict[str, Any]],
        commands: List[str],
    ) -> Optional[str]:
        """Pick the connected device that should execute these commands."""
        for source in (config or {}, options or {}):
            did = source.get("device_id")
            if did:
                return did

        protocols = {
            p for p in (self._infer_protocol(c) for c in commands) if p
        }

        async with async_session() as session:
            result = await session.execute(
                select(Device).where(Device.status == "connected")
            )
            devices = result.scalars().all()

        if not devices:
            return None
        if protocols:
            for dev in devices:
                if dev.protocol in protocols:
                    return dev.id
        return devices[0].id

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
            total_steps=len([n for n in nodes if n.get("type") not in ("start", "end")]),
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

            # 流程上下文：初始化节点声明的变量 + 各节点产生的输出返回值（#4）
            ctx: Dict[str, Any] = flow_context.seed_context(nodes)

            for idx, node in enumerate(step_nodes):
                node_id = node.get("id", f"node_{idx}")
                node_type = node.get("type", "test_step")
                label = (
                    node.get("label")
                    or (node.get("data") or {}).get("label")
                    or f"Step {idx + 1}"
                )
                config = node.get("config", {}) or {}
                commands = self._extract_commands(node)

                # 输入参数：优先取前序节点同名输出，其次取默认值
                ctx.update(flow_context.resolve_inputs(node, ctx))
                # 命令/预期结果中的 {占位符} 用上下文渲染，实现节点间数据串联
                commands = [flow_context.render_template(c, ctx) for c in commands]
                expected_text = flow_context.render_template(
                    config.get("expected") or config.get("expected_result") or "", ctx
                )

                # Create step result
                step_result = TestStepResult(
                    execution_id=execution_id,
                    step_index=idx + 1,
                    node_id=node_id,
                    node_type=node_type,
                    label=label,
                    status=StepStatus.RUNNING.value,
                    command=" | ".join(commands) or config.get("command", ""),
                    expected=expected_text,
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
                    if node_type in self.COMMAND_NODE_TYPES:
                        device_id = await self._resolve_device(config, options, commands)

                        if not commands:
                            # Steps like "汇总显示结果" carry no device command.
                            # They are presentation-only: skip them instead of
                            # marking the whole case failed.
                            step_result.status = StepStatus.SKIPPED.value
                            step_result.actual = "[跳过] 该步骤不含可下发的设备指令"
                        elif not device_id:
                            # Never report success for a step that did not
                            # actually run - that is how tests "passed" while
                            # nothing was ever sent to the device.
                            reason = "没有已连接的设备可下发指令"
                            step_result.status = StepStatus.FAILED.value
                            step_result.actual = f"[未执行] {reason}"
                            step_result.error_message = reason
                            logger.warning(
                                f"Step {idx + 1} of {execution_id} not executed: {reason}"
                            )
                        else:
                            results = []
                            responses: List[str] = []
                            for cmd in commands:
                                response = await device_service.send_command(
                                    db, device_id, cmd,
                                    execution_id=execution_id,
                                    step_result_id=step_result.id,
                                )
                                resp_text = response.get("response", "") or ""
                                responses.append(resp_text)
                                results.append(f"{cmd} -> {resp_text}")
                            # Keep the stored result readable when a command
                            # was repeated many times (e.g. "循环读取 100 次").
                            if len(results) > 8:
                                results = (
                                    results[:5]
                                    + [f"...(共 {len(results)} 条)"]
                                    + results[-3:]
                                )
                            step_result.actual = " | ".join(results)
                            step_result.status = StepStatus.PASSED.value

                            # ---- result parsing + judgement ----
                            # A step may repeat the same command N times
                            # ("循环读取 100 次"). Every reply is a sample, so
                            # the curve gets N points instead of only the last
                            # one. Empty frames are reported as "unknown" and
                            # are excluded from the judgement.
                            # 节点局部作用域：response + 各解析字段，
                            # 供输出返回值表达式取值（response / parsed_0 …）
                            node_scope: Dict[str, Any] = {
                                "response": responses[-1] if responses else "",
                            }
                            parsers = config.get("parsers")
                            if parsers:
                                samples: List[List[Dict[str, Any]]] = [
                                    response_parser.parse_all(r, parsers)
                                    for r in responses
                                ]
                                # 最后一条应答的每个解析字段都暴露给输出表达式
                                for _pidx, _p in enumerate(samples[-1] if samples else []):
                                    node_scope[f"parsed_{_pidx}"] = _p.get("value")
                                    if _p.get("name"):
                                        node_scope[str(_p["name"])] = _p.get("value")
                                passed, summary = response_parser.summarize_series(
                                    samples
                                )
                                step_result.parsed_results = json.dumps({
                                    "count": len(samples),
                                    "samples": samples,
                                    "last": samples[-1] if samples else [],
                                }, ensure_ascii=False)
                                step_result.actual = (
                                    f"{step_result.actual} || 解析: {summary}"
                                )
                                if not passed:
                                    step_result.status = StepStatus.FAILED.value
                                    step_result.error_message = (
                                        f"结果解析判断未通过: {summary}"
                                    )
                                    logger.warning(
                                        f"Step {idx + 1} of {execution_id} "
                                        f"failed judgement: {summary}"
                                    )
                            # 输出返回值写入上下文，供后续节点引用
                            ctx.update(
                                flow_context.collect_outputs(node, ctx, node_scope)
                            )
                    elif node_type == "delay":
                        # 延时节点：等待若干毫秒（{占位符} 用流程上下文渲染）
                        raw_ms = config.get("duration", config.get("duration_ms", 0))
                        ms_text = flow_context.render_template(str(raw_ms or 0), ctx)
                        delay_ms = flow_context.coerce_value(ms_text, "float")
                        try:
                            delay_ms = max(0.0, float(delay_ms))
                        except (TypeError, ValueError):
                            raise ValueError(f"延时时长无效: {raw_ms!r}（请填写毫秒数）")
                        await asyncio.sleep(delay_ms / 1000.0)
                        step_result.status = StepStatus.PASSED.value
                        step_result.actual = f"延时 {delay_ms:g} ms"
                        ctx.update(flow_context.collect_outputs(node, ctx, {"delay_ms": delay_ms}))
                    elif node_type == "condition":
                        cond_expr = flow_context.render_template(
                            config.get("condition") or "True", ctx
                        )
                        outcome = flow_context.eval_condition(cond_expr, ctx)
                        ctx.update(
                            flow_context.collect_outputs(
                                node, ctx, {"result": outcome}
                            )
                        )
                        step_result.status = StepStatus.PASSED.value
                        step_result.actual = (
                            f"Condition evaluated: {cond_expr} -> {outcome}"
                        )
                    elif node_type == "loop":
                        step_result.status = StepStatus.PASSED.value
                        step_result.actual = "Loop completed"
                    else:
                        step_result.status = StepStatus.PASSED.value
                        step_result.actual = "Step completed"
                        ctx.update(flow_context.collect_outputs(node, ctx, {}))

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
                    "actual": step_result.actual,
                    "parsed_results": _safe_json(step_result.parsed_results),
                    # 当前流程上下文（输入参数 / 输出返回值），便于在界面上追踪串联
                    "context": dict(ctx),
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
