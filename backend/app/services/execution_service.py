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
from app.services.program_logger import start_execution_log, finish_execution_log
from app.api.websocket import broadcast_execution_update
from app.core.timeutils import utc_now

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
    # Structured JSON device commands (PeakCAN and friends), e.g.
    #   {"action": "send", "arbitration_id": 32, "data": [...]}
    # Braces never nest in a command payload, so a simple non-greedy body is
    # enough — the JSON is then validated with json.loads below.
    _JSON_CMD_RE = re.compile(r"\{[^{}]*\}")
    # python-can string form: "123#11223344AABBCCDD"
    _CAN_STR_RE = re.compile(r"\b([0-9A-Fa-f]{1,8})#([0-9A-Fa-f]{0,128})\b")
    # python-can pseudo-code the AI/user may write, e.g.
    #   bus.send_periodic(can.Message(arbitration_id=0x20, ...), 0.2)
    _PYCAN_FN_RE = re.compile(
        r"(?:(?:bus|self\._bus)\s*\.\s*)?"
        r"(?:send_periodic|send_cyclic|cyclic_send|send|recv|receive|can\.Message)\s*\(",
        re.IGNORECASE,
    )
    # keys that identify a dict as a *device command*, not a random object
    _JSON_CMD_KEYS = frozenset({
        "action", "arbitration_id", "can_id", "is_extended_id", "is_fd",
    })
    # "循环读取回复(例如 100 次)" -> repeat the command that many times
    _REPEAT_RE = re.compile(r"(?:循环|重复)[^0-9]{0,15}?(\d+)\s*次")
    MAX_REPEAT = 50

    @classmethod
    def _json_commands(cls, text: str) -> List[str]:
        """Pull JSON device commands (``{"action": ...}``) out of free text.

        PeakCAN commands are structured payloads, so they cannot be embedded in
        a sentence the way ``@11_MSGREQ=...;`` can — without this the command
        list stayed empty and the step was skipped ("不含可下发的设备指令").
        """
        found: List[str] = []
        for m in cls._JSON_CMD_RE.finditer(text or ""):
            raw = m.group(0)
            try:
                obj = json.loads(raw)
            except (ValueError, TypeError):
                continue
            if isinstance(obj, dict) and cls._JSON_CMD_KEYS & set(obj):
                found.append(raw)
        return found

    @classmethod
    def _python_can_commands(cls, text: str) -> List[str]:
        """Pull python-can pseudo-code calls (``bus.send_periodic(...)`` etc.)
        out of free text, honouring nested ``can.Message(...)`` parentheses.

        A call whose ``(`` sits *inside* an already-matched outer call (e.g. the
        ``can.Message(...)`` inside ``bus.send_periodic(can.Message(...), 0.2)``)
        is not reported again — otherwise the executor would send the same frame
        twice.
        """
        spans: List[tuple] = []  # (start, end, expr)
        for m in cls._PYCAN_FN_RE.finditer(text or ""):
            open_idx = m.end() - 1
            depth = 0
            for i in range(open_idx, len(text)):
                ch = text[i]
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        spans.append((m.start(), i + 1, text[m.start() : i + 1]))
                        break
        return [
            expr
            for start, end, expr in spans
            if not any(s < start < e for s, e, _ in spans)
        ]

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
            str(config.get("expected") or ""),
        ])
        found.extend(cls._CMD_RE.findall(text))
        found.extend(cls._json_commands(text))
        found.extend(
            f"{m.group(1)}#{m.group(2)}" for m in cls._CAN_STR_RE.finditer(text)
        )
        found.extend(cls._python_can_commands(text))
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
        text = (command or "").strip()
        if re.match(r"^@\d+_", text):
            return "mini_gateway100"
        if text.startswith("{"):
            try:
                obj = json.loads(text)
            except (ValueError, TypeError):
                return None
            if isinstance(obj, dict):
                if {"arbitration_id", "can_id", "is_extended_id", "is_fd"} & set(obj):
                    return "peakcan"
                action = str(obj.get("action") or "").strip().lower()
                if action in (
                    "send", "send_can", "send_canfd", "send_message",
                    "send_periodic", "stop_periodic",
                ):
                    return "peakcan"
            return None
        # python-can string form: 123#11223344
        if re.match(r"^[0-9A-Fa-f]{1,8}#[0-9A-Fa-f]*$", text):
            return "peakcan"
        # python-can pseudo-code: bus.send_periodic(...) / bus.send(...) / bus.recv(...)
        if ExecutionEngine._PYCAN_FN_RE.match(text):
            return "peakcan"
        if text.startswith("@"):
            return "mini_gateway100"
        return None

    def _desired_protocols(
        self, config: Dict[str, Any], commands: List[str]
    ) -> set:
        """Protocols the commands / node configuration expect a device for."""
        desired = {p for p in (self._infer_protocol(c) for c in commands) if p}
        cfg_protocol = str((config or {}).get("device_protocol") or "").strip()
        if cfg_protocol:
            desired.add(cfg_protocol)
        params = (config or {}).get("parameters") or {}
        if isinstance(params, dict):
            proto = str(params.get("protocol") or params.get("device_protocol") or "")
            if proto.strip():
                desired.add(proto.strip())
        return desired

    async def _resolve_device(
        self,
        config: Dict[str, Any],
        options: Optional[Dict[str, Any]],
        commands: List[str],
    ) -> Optional[str]:
        """Pick the connected device that should execute these commands.

        The device is resolved from, in order: an explicit ``device_id``, the
        protocol the commands imply, and only then "any connected device".
        When a protocol *is* identified but no matching device is connected the
        answer is ``None`` — sending a PeakCAN payload to an unrelated device is
        exactly how a test could "pass" without the CAN frame ever leaving the
        adapter.
        """
        for source in (config or {}, options or {}):
            did = source.get("device_id")
            if did:
                return did

        desired = self._desired_protocols(config, commands)

        async with async_session() as session:
            result = await session.execute(
                select(Device).where(Device.status == "connected")
            )
            devices = result.scalars().all()

        if not devices:
            return None
        for proto in desired:
            for dev in devices:
                if (dev.protocol or "").lower() == proto.lower():
                    return dev.id
        if desired:
            return None
        return devices[0].id

    async def _missing_device_hint(
        self, config: Dict[str, Any], commands: List[str]
    ) -> str:
        """Human readable reason for an unresolvable device."""
        desired = self._desired_protocols(config, commands)
        if not desired:
            return "没有已连接的设备可下发指令"
        names = ", ".join(sorted(desired))
        return f"未找到已连接的 {names} 设备，命令未下发"

    # ------------------------------------------------------------------ #
    # Flow graph helpers (edges are followed instead of a flat node list)
    # ------------------------------------------------------------------ #

    # Hard ceilings so a malformed flow can never hang a run forever.
    MAX_NODE_EXECUTIONS = 2000
    MAX_LOOP_ITERATIONS = 1000

    # Edge labels that identify the body / the exit of a loop.
    _BODY_LABELS = {"body", "loop", "循环体", "true", "yes", "y", "是", "1"}
    _EXIT_LABELS = {
        "exit", "after", "loop_exit", "结束", "循环结束",
        "false", "no", "n", "否", "0",
    }
    # Edge labels of a condition node.
    _TRUE_LABELS = {"true", "yes", "y", "是", "通过", "pass", "ok", "1"}
    _FALSE_LABELS = {"false", "no", "n", "否", "不通过", "fail", "ng", "0"}

    @classmethod
    def _loop_bounds(
        cls,
        node_map: Dict[str, Any],
        adj: Dict[str, List[tuple]],
        incoming: Dict[str, int],
        node_id: str,
    ) -> tuple:
        """Return ``(body_start, body_end)`` of a loop node — or (None, None).

        ``body_end`` is the node the loop *resumes from* after iterating, so the
        walking code never re-enters the body through the exit edge.
        """
        succ = adj.get(node_id) or []
        if not succ:
            return None, None

        explicit = [t for t, lbl in succ if lbl in cls._BODY_LABELS]
        if explicit:
            body_start = explicit[0]
        elif len(succ) == 1:
            candidate = succ[0][0]
            cand_succ = adj.get(candidate) or []
            # Canonical shape drawn by the generator: 循环 → 循环体 → 合并点，
            # where the merge point has several incoming edges. Anything else is
            # treated as a plain successor (no body) — we never loop the rest of
            # the flow by accident.
            if len(cand_succ) == 1 and incoming.get(cand_succ[0][0], 0) >= 2:
                body_start = candidate
            else:
                return None, None
        else:
            exit_targets = [t for t, lbl in succ if lbl in cls._EXIT_LABELS]
            body = [t for t, _ in succ if t not in exit_targets]
            if not body:
                return None, None
            body_start = body[0]

        body_succ = adj.get(body_start) or []
        for tgt, lbl in body_succ:
            if lbl in cls._EXIT_LABELS:
                return body_start, tgt
        if len(body_succ) == 1:
            return body_start, body_succ[0][0]
        return body_start, None

    @classmethod
    def _loop_iterations(
        cls, node: Dict[str, Any], ctx: Dict[str, Any]
    ) -> int:
        """Iteration count of a loop node.

        Returns ``-1`` for a ``while`` loop whose condition can only be judged
        at run time; the walker then evaluates it before every round.
        """
        config = node.get("config") or {}
        for key in ("repeat", "count", "times", "iterations"):
            value = config.get(key)
            if value not in (None, ""):
                try:
                    count = int(flow_context.coerce_value(value, "int"))
                    return max(1, min(count, cls.MAX_LOOP_ITERATIONS))
                except (TypeError, ValueError):
                    continue

        loop_type = str(config.get("loop_type") or "for").strip().lower()
        expr = str(
            config.get("loop_expression") or config.get("condition") or ""
        ).strip()
        if loop_type == "while":
            return -1

        value = flow_context.safe_eval(expr, ctx) if expr else None
        if isinstance(value, bool):
            count = 1 if value else 0
        elif isinstance(value, int):
            count = value
        else:
            try:
                count = len(value)
            except TypeError:
                count = 1
        return max(1, min(int(count), cls.MAX_LOOP_ITERATIONS))

    async def _iterate_loop(
        self,
        walk,
        body_start: Optional[str],
        body_end: Optional[str],
        iterations: int,
        ctx: Dict[str, Any],
        node: Dict[str, Any],
    ) -> int:
        """Run the loop body, returning how many rounds were executed."""
        if not body_start:
            return 0
        config = node.get("config") or {}
        var = str(config.get("variable") or "i")
        condition = str(
            config.get("loop_expression") or config.get("condition") or ""
        ).strip()
        stop_at = {body_end} if body_end else set()

        rounds = 0
        for round_index in range(self.MAX_LOOP_ITERATIONS):
            if iterations < 0:
                # while: the condition decides, using the loop variable
                if not flow_context.eval_condition(condition, ctx):
                    break
            elif round_index >= iterations:
                break
            ctx[var] = round_index + 1
            await walk(body_start, stop_at)
            rounds += 1
        return rounds

    @classmethod
    def _branch_target(
        cls, succ: List[tuple], outcome: Optional[bool]
    ) -> Optional[str]:
        """Pick the outgoing edge of a condition node for *outcome*."""
        if not succ:
            return None
        if outcome is None:
            # unjudgeable condition: follow the first edge, as documented
            return succ[0][0]
        wanted = cls._TRUE_LABELS if outcome else cls._FALSE_LABELS
        for tgt, lbl in succ:
            if lbl in wanted:
                return tgt
        unlabelled = [t for t, lbl in succ if not lbl]
        if unlabelled:
            # both edges unlabelled: creation order is true-then-false
            return unlabelled[0] if outcome else (
                unlabelled[1] if len(unlabelled) > 1 else unlabelled[0]
            )
        return succ[0][0] if outcome else (
            succ[1][0] if len(succ) > 1 else succ[0][0]
        )

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

        # Parse edges — the runtime walks the graph, so branches / loops need them
        edges = []
        if flow and flow.edges:
            try:
                edges = json.loads(flow.edges) if isinstance(flow.edges, str) else flow.edges
            except json.JSONDecodeError:
                pass

        # Create execution record
        options_json = json.dumps(options, ensure_ascii=False) if options else None
        execution = TestExecution(
            testcase_id=testcase_id,
            status=ExecutionStatus.RUNNING.value,
            options=options_json,
            total_steps=len([n for n in nodes if n.get("type") not in ("start", "end")]),
            started_at=utc_now(),
        )
        db.add(execution)
        await db.commit()
        await db.refresh(execution)

        # Update test case status
        test_case.status = "running"
        await db.commit()

        # Run execution in background.
        #
        # IMPORTANT: the background task must NOT share the request-scoped
        # session.  The route keeps using it after ``create_task`` (and FastAPI
        # closes it once the response is sent), which raises
        # ``IllegalStateChangeError`` ("... is already in progress") inside the
        # task — the execution then died silently, stuck at "running" with no
        # step results.  Give the task a session of its own.
        task_db = async_session()
        task = asyncio.create_task(
            self._run_execution(task_db, execution, nodes, edges, options)
        )
        self._running_executions[execution.id] = task

        return execution

    async def reset_stale_executions(self, db: AsyncSession) -> int:
        """Mark executions left 'running' by a previous process as errored.

        The runner lives in memory only, so anything still marked ``running``
        after a restart can never finish — and a stuck 'running' row keeps the
        UI's start button disabled forever.
        """
        try:
            result = await db.execute(
                select(TestExecution).where(
                    TestExecution.status == ExecutionStatus.RUNNING.value
                )
            )
            stale = result.scalars().all()
            for ex in stale:
                ex.status = ExecutionStatus.ERROR.value
                ex.result = ExecutionResult.ABORTED.value
                ex.completed_at = ex.completed_at or utc_now()
                if ex.started_at:
                    ex.duration_ms = int(
                        (ex.completed_at - ex.started_at).total_seconds() * 1000
                    )
                ex.error_message = "服务重启，执行中断"
            if stale:
                # a case parked in 'running' blocks a fresh run too
                tc_ids = [ex.testcase_id for ex in stale]
                tc_result = await db.execute(
                    select(TestCase).where(
                        TestCase.id.in_(tc_ids), TestCase.status == "running"
                    )
                )
                for tc in tc_result.scalars().all():
                    tc.status = "draft"
                await db.commit()
                logger.info(f"Reset {len(stale)} stale running execution(s)")
            return len(stale)
        except Exception as e:
            logger.warning(f"Failed to reset stale executions: {e}")
            return 0

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
        execution.completed_at = utc_now()
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
        edges: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
    ):
        """Run the flow in the background, owning the session it is given.

        ``db`` is a dedicated session created by :meth:`start_execution`
        (never the request-scoped one), so it is safe to use it for as long
        as the execution lasts — and this wrapper is responsible for closing
        it, since nobody else will.
        """
        try:
            await self._execute_flow(db, execution, nodes, edges, options)
        finally:
            try:
                await db.close()
            except Exception as e:  # pragma: no cover - closing is best effort
                logger.warning(f"Failed to close execution session: {e}")

    async def _execute_flow(
        self,
        db: AsyncSession,
        execution: TestExecution,
        nodes: List[Dict[str, Any]],
        edges: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
    ):
        """Internal: Run the test flow execution.

        The flow is walked along its edges (not as a flat list), so condition
        nodes really take one branch and loop nodes really repeat their body —
        the same semantics the code generator implements.
        """
        execution_id = execution.id
        stop_on_error = (options or {}).get("stop_on_error", True)
        timeout_per_step = (options or {}).get("timeout_per_step", 30000)

        # One log folder per run: logs/executions/<execution_id>/
        run_log = start_execution_log(execution_id)

        try:
            # Get execution steps (non-start/end nodes)
            step_nodes = [
                n for n in nodes
                if n.get("type") not in ("start", "end")
            ]

            # ---- graph: node lookup + adjacency (P2) ----
            node_map: Dict[str, Dict[str, Any]] = {
                n.get("id"): n for n in nodes if n.get("id")
            }
            adj: Dict[str, List[tuple]] = {}
            incoming: Dict[str, int] = {}
            for edge in edges or []:
                src, tgt = edge.get("source"), edge.get("target")
                if not src or not tgt:
                    continue
                label = str(edge.get("label") or "").strip().lower()
                adj.setdefault(src, []).append((tgt, label))
                incoming[tgt] = incoming.get(tgt, 0) + 1

            # step_index stays the *plan position* of the node, so the UI's step
            # list keeps matching the drawn flow even with branches/loops.
            step_index_of: Dict[str, int] = {
                n.get("id"): i + 1 for i, n in enumerate(step_nodes)
            }

            def index_of(node_id: str) -> int:
                return step_index_of.get(node_id, len(step_index_of) + 1)

            state: Dict[str, Any] = {
                "rows": {},                 # node_id -> TestStepResult
                "visits": {},               # node_id -> visit count
                "loop_iterations": {},      # node_id -> iteration count
                "loop_command_mode": {},    # node_id -> True when the loop node
                                            # itself carries the commands
                "condition_outcome": None,
                "executions": 0,
                "stopped": False,
            }

            # 流程上下文：初始化节点声明的变量 + 各节点产生的输出返回值（#4）
            ctx: Dict[str, Any] = flow_context.seed_context(nodes)

            async def execute_node(node: Dict[str, Any], step_index: int) -> str:
                """Execute one node, persist + broadcast its result, return status."""
                node_id = node.get("id", f"node_{step_index}")
                node_type = node.get("type", "test_step")
                label = (
                    node.get("label")
                    or (node.get("data") or {}).get("label")
                    or f"Step {step_index}"
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

                # Create (or reuse) the step result. A loop body is visited once
                # per iteration: reusing the row keeps the step list aligned
                # with the flow plan instead of exploding into N duplicate rows.
                visit = state["visits"].get(node_id, 0) + 1
                state["visits"][node_id] = visit
                step_result = state["rows"].get(node_id)
                if step_result is None:
                    step_result = TestStepResult(
                        execution_id=execution_id,
                        step_index=step_index,
                        node_id=node_id,
                        node_type=node_type,
                        label=label,
                        status=StepStatus.RUNNING.value,
                        command=" | ".join(commands) or config.get("command", ""),
                        expected=expected_text,
                        started_at=utc_now(),
                    )
                    state["rows"][node_id] = step_result
                    async with db as session:
                        session.add(step_result)
                        await session.commit()
                else:
                    # repeat visit: reset the row for this round
                    step_result.status = StepStatus.RUNNING.value
                    step_result.command = " | ".join(commands) or config.get("command", "")
                    step_result.expected = expected_text
                    step_result.error_message = None

                await broadcast_execution_update(execution_id, {
                    "type": "step_started",
                    "execution_id": execution_id,
                    "step_index": step_index,
                    "node_id": node_id,
                    "label": label,
                    "visit": visit,
                })

                # Execute step
                try:
                    if (
                        node_type in self.COMMAND_NODE_TYPES
                        or (node_type == "loop" and state["loop_command_mode"].get(node_id))
                    ):
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
                            reason = await self._missing_device_hint(config, commands)
                            step_result.status = StepStatus.FAILED.value
                            step_result.actual = f"[未执行] {reason}"
                            step_result.error_message = reason
                            logger.warning(
                                f"Step {step_index} of {execution_id} not executed: {reason}"
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
                                        f"Step {step_index} of {execution_id} "
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
                        # 分支判定结果交给 walker 决定走哪条边
                        state["condition_outcome"] = outcome
                    elif node_type == "loop":
                        # 循环节点本身不下发指令（循环体节点才是真正执行的动作）
                        iterations = state["loop_iterations"].get(node_id)
                        if iterations is None:
                            step_result.status = StepStatus.SKIPPED.value
                            step_result.actual = "[跳过] 循环控制节点，不下发设备指令"
                        elif iterations < 0:
                            step_result.status = StepStatus.PASSED.value
                            step_result.actual = "循环控制：按条件迭代（while）"
                        else:
                            step_result.status = StepStatus.PASSED.value
                            step_result.actual = f"循环共执行 {iterations} 轮"
                    else:
                        step_result.status = StepStatus.PASSED.value
                        step_result.actual = "Step completed"
                        ctx.update(flow_context.collect_outputs(node, ctx, {}))

                except Exception as e:
                    step_result.status = StepStatus.FAILED.value
                    step_result.error_message = str(e)
                    logger.error(f"Step {step_index} failed: {e}")

                    await broadcast_execution_update(execution_id, {
                        "type": "step_failed",
                        "execution_id": execution_id,
                        "step_index": step_index,
                        "error": str(e),
                    })

                    if stop_on_error:
                        state["stopped"] = True

                finally:
                    if visit > 1:
                        # 记下这是第几轮，便于在界面上看出循环轨迹
                        step_result.actual = (
                            f"[第 {visit} 轮] {step_result.actual or ''}"
                        ).strip()
                    step_result.completed_at = utc_now()
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
                    "step_index": step_index,
                    "status": step_result.status,
                    "actual": step_result.actual,
                    "parsed_results": _safe_json(step_result.parsed_results),
                    # 当前流程上下文（输入参数 / 输出返回值），便于在界面上追踪串联
                    "context": dict(ctx),
                })
                if run_log:
                    run_log.program(
                        f"step {step_index} [{step_result.status}] {label} | "
                        f"cmd={step_result.command!r} -> actual={step_result.actual!r}"
                        + (f" | error={step_result.error_message!r}"
                           if step_result.error_message else "")
                    )
                return step_result.status

            # ---- graph walk (P2): follow edges, honour branches & loops ----
            start_id = None
            for n in nodes:
                if (n.get("type") or "") in ("start", "input"):
                    start_id = n.get("id")
                    break
            if start_id is None:
                for n in nodes:
                    if not incoming.get(n.get("id")):
                        start_id = n.get("id")
                        break
            if start_id is None and nodes:
                start_id = nodes[0].get("id")

            async def walk(from_id: Optional[str], stop_at: set) -> Optional[str]:
                """Execute nodes from *from_id* until a node in *stop_at* (or the end).

                Returns the id it stopped at so the caller (loop handling) can
                continue the flow from there.
                """
                current = from_id
                while current and current not in stop_at:
                    state["executions"] += 1
                    if state["executions"] > self.MAX_NODE_EXECUTIONS:
                        raise RuntimeError(
                            "流程执行步数超过上限，请检查是否存在无法退出的循环"
                        )
                    node = node_map.get(current)
                    if node is None:
                        return None
                    node_type = (node.get("type") or "action")
                    succ = adj.get(current, [])

                    if node_type in ("start", "end", "input"):
                        current = succ[0][0] if succ else None
                        continue

                    if node_type == "loop":
                        body_start, body_end = self._loop_bounds(
                            node_map, adj, incoming, current
                        )
                        state["loop_command_mode"][current] = body_start is None
                        iterations = self._loop_iterations(node, ctx)
                        state["loop_iterations"][current] = iterations
                        status = await execute_node(node, index_of(current))
                        if state["stopped"]:
                            return None
                        if body_start is not None and status != StepStatus.SKIPPED.value:
                            rounds = await self._iterate_loop(
                                walk, body_start, body_end, iterations, ctx, node
                            )
                            # 让界面上看到真实的循环轮数（while 只有跑完才知道）
                            loop_row = state["rows"].get(current)
                            if loop_row is not None and rounds >= 0:
                                loop_row.actual = f"循环共执行 {rounds} 轮"
                                async with db as session:
                                    session.add(loop_row)
                                    await session.commit()
                        current = body_end if body_start and body_end else (
                            succ[0][0] if succ else None
                        )
                        continue

                    status = await execute_node(node, index_of(current))
                    if state["stopped"]:
                        return None

                    if node_type == "condition":
                        current = self._branch_target(
                            succ, state.pop("condition_outcome", None)
                        )
                    else:
                        current = succ[0][0] if succ else None
                return current

            if start_id:
                await walk(start_id, set())

            # Finalize execution
            async with db as session:
                result = await session.execute(
                    select(TestExecution).where(TestExecution.id == execution_id)
                )
                exec_record = result.scalar_one_or_none()
                if exec_record:
                    exec_record.completed_at = utc_now()
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
            finish_execution_log(execution_id)

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
