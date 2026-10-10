"""Batch scheduler for execution plans.

Runs a plan in the background:

* groups execute in ascending ``group_no`` order, **serially**;
* items inside one group run **in parallel** (bounded by ``max_parallel``);
* a single item's iterations run **serially**, separated by
  ``loop_interval_ms``;
* ``delay_before_ms`` / ``delay_after_ms`` bracket the whole item.

Every iteration produces its own ``TestExecution`` carrying
``plan_run_id`` / ``plan_item_id`` / ``iteration`` / ``group_no``, so the
existing single-run detail page keeps working unchanged (drill-down).
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.core.timeutils import utc_now
from app.models.models import (
    ExecutionPlanRun,
    ExecutionStatus,
    PlanRunStatus,
    TestCase,
    TestExecution,
    TestFlow,
)
from app.services.execution_service import execution_engine

logger = logging.getLogger(__name__)

# How often an interruptible wait re-checks its cancellation flag.
_TICK_MS = 100


class PlanRunner:
    """In-memory batch scheduler.

    The runner lives in the uvicorn process (same as the single-case runner);
    runs left ``running`` after a restart are reaped by ``reset_stale_runs``.
    """

    def __init__(self) -> None:
        self._tasks: Dict[str, asyncio.Task] = {}
        self._state: Dict[str, Dict[str, Any]] = {}
        self._cancel_run: Dict[str, bool] = {}
        self._cancel_item: Dict[str, set] = {}

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    async def start_run(
        self,
        db: AsyncSession,
        plan_id: Optional[str],
        plan: Dict[str, Any],
        items: List[Dict[str, Any]],
    ) -> ExecutionPlanRun:
        """Persist a run and launch it in the background."""
        snapshot = {"plan": plan, "items": items}
        run = ExecutionPlanRun(
            plan_id=plan_id,
            plan_name=plan.get("name"),
            plan_snapshot=json.dumps(snapshot, ensure_ascii=False),
            status=PlanRunStatus.RUNNING.value,
            total_items=len(items),
            started_at=utc_now(),
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)

        self._state[run.id] = {
            "status": PlanRunStatus.RUNNING.value,
            "items": {
                str(i.get("id")): {
                    "item_id": str(i.get("id")),
                    "testcase_id": i.get("testcase_id"),
                    "testcase_name": i.get("testcase_name"),
                    "group_no": i.get("group_no"),
                    "loop_count": int(i.get("loop_count") or 1),
                    "status": "pending",
                    "iteration": 0,
                    "execution_id": None,
                    "device_ids": i.get("resolved_device_ids") or [],
                }
                for i in items
            },
        }
        self._cancel_run[run.id] = False
        self._cancel_item[run.id] = set()

        task = asyncio.create_task(self._run(run.id, plan, items))
        self._tasks[run.id] = task
        logger.info("plan run %s started: %d items", run.id, len(items))
        return run

    def get_state(self, run_id: str) -> Optional[Dict[str, Any]]:
        return self._state.get(run_id)

    async def stop_run(self, db: AsyncSession, run_id: str) -> bool:
        """Stop the whole batch; already finished items keep their results."""
        self._cancel_run[run_id] = True
        task = self._tasks.get(run_id)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        run = await db.get(ExecutionPlanRun, run_id)
        if run and run.status == PlanRunStatus.RUNNING.value:
            run.status = PlanRunStatus.STOPPED.value
            run.completed_at = utc_now()
            run.duration_ms = int((run.completed_at - run.started_at).total_seconds() * 1000) if run.started_at else None
            await db.commit()
        state = self._state.get(run_id)
        if state:
            state["status"] = PlanRunStatus.STOPPED.value
            for st in state["items"].values():
                if st["status"] in ("pending", "running", "delaying"):
                    st["status"] = "stopped"
        logger.info("plan run %s stopped", run_id)
        return True

    async def stop_item(self, run_id: str, item_id: str) -> bool:
        """Stop a single item; the rest of its group keeps running."""
        self._cancel_item.setdefault(run_id, set()).add(str(item_id))
        state = self._state.get(run_id)
        if state and str(item_id) in state["items"]:
            st = state["items"][str(item_id)]
            if st["status"] in ("pending", "running", "delaying"):
                st["status"] = "stopped"
        logger.info("plan run %s item %s stop requested", run_id, item_id)
        return True

    # ------------------------------------------------------------------ #
    # Waiting helpers
    # ------------------------------------------------------------------ #

    async def _sleep(self, run_id: str, item_id: str, ms: int) -> None:
        """Sleep, but wake up early (and finish) when the run/item is stopped."""
        if ms <= 0:
            return
        remaining = ms
        while remaining > 0:
            if self._cancel_run.get(run_id) or str(item_id) in self._cancel_item.get(run_id, set()):
                return
            step = min(_TICK_MS, remaining)
            await asyncio.sleep(step / 1000.0)
            remaining -= step

    def _cancelled(self, run_id: str, item_id: str) -> bool:
        return self._cancel_run.get(run_id, False) or str(item_id) in self._cancel_item.get(run_id, set())

    # ------------------------------------------------------------------ #
    # Scheduler
    # ------------------------------------------------------------------ #

    async def _run(self, run_id: str, plan: Dict[str, Any], items: List[Dict[str, Any]]) -> None:
        state = self._state[run_id]
        on_error = str(plan.get("on_error") or "abort_all")
        max_parallel = max(1, min(16, int(plan.get("max_parallel") or 4)))
        plan_loop = max(1, int(plan.get("plan_loop_count") or 1))

        groups: Dict[int, List[Dict[str, Any]]] = {}
        for item in items:
            groups.setdefault(int(item.get("group_no") or 0), []).append(item)

        aborted = False
        try:
            for loop_round in range(plan_loop):
                if self._cancel_run.get(run_id):
                    break
                for gno in sorted(groups):
                    if self._cancel_run.get(run_id):
                        aborted = True
                        break
                    group_items = groups[gno]
                    sem = asyncio.Semaphore(max_parallel)
                    logger.info(
                        "run %s round %d group %d: %d item(s)",
                        run_id, loop_round + 1, gno, len(group_items),
                    )

                    async def _guarded(item: Dict[str, Any]) -> bool:
                        async with sem:
                            return await self._run_item(run_id, item, on_error)

                    results = await asyncio.gather(
                        *(_guarded(i) for i in group_items), return_exceptions=True
                    )

                    group_failed = any(
                        r is False for r in results if not isinstance(r, BaseException)
                    )
                    if group_failed:
                        if on_error in ("abort_all", "abort_group"):
                            aborted = True
                            break
                if aborted:
                    break
        except asyncio.CancelledError:
            aborted = True
        except Exception as e:  # pragma: no cover - defensive
            logger.exception("plan run %s crashed: %s", run_id, e)
            aborted = True
        finally:
            await self._finalize(run_id, aborted)

    async def _run_item(
        self, run_id: str, item: Dict[str, Any], on_error: str
    ) -> bool:
        """Run one plan item (all its iterations). Returns True when it passed."""
        item_id = str(item.get("id"))
        st = self._state[run_id]["items"].get(item_id)
        if st is None:
            return True

        loop_count = max(1, int(item.get("loop_count") or 1))
        interval = int(item.get("loop_interval_ms") or 0)
        st["status"] = "delaying"

        # ---- delay before the item starts ------------------------------
        if not await self._sleep_check(run_id, item_id, int(item.get("delay_before_ms") or 0)):
            st["status"] = "stopped"
            return False

        passed = True
        for k in range(1, loop_count + 1):
            if self._cancelled(run_id, item_id):
                st["status"] = "stopped"
                return False
            if k > 1 and interval:
                st["status"] = "delaying"
                if not await self._sleep_check(run_id, item_id, interval):
                    st["status"] = "stopped"
                    return False

            st["status"] = "running"
            st["iteration"] = k
            status = await self._execute_iteration(run_id, item, k)
            st["last_status"] = status
            if status != ExecutionStatus.PASSED.value:
                passed = False
                if on_error in ("abort_all", "abort_group"):
                    break

        # ---- delay after the item finished -----------------------------
        if not await self._sleep_check(run_id, item_id, int(item.get("delay_after_ms") or 0)):
            st["status"] = "stopped"
            return False

        st["status"] = "passed" if passed else "failed"
        return passed

    async def _sleep_check(self, run_id: str, item_id: str, ms: int) -> bool:
        """``_sleep`` + report whether we were *not* interrupted."""
        if ms <= 0:
            return not self._cancelled(run_id, item_id)
        await self._sleep(run_id, item_id, ms)
        return not self._cancelled(run_id, item_id)

    async def _execute_iteration(
        self, run_id: str, item: Dict[str, Any], iteration: int
    ) -> str:
        """Run a single iteration and return the resulting execution status."""
        testcase_id = item.get("testcase_id")
        db: AsyncSession = async_session()
        try:
            tc_result = await db.execute(select(TestCase).where(TestCase.id == testcase_id))
            test_case = tc_result.scalar_one_or_none()
            if not test_case:
                logger.error("run %s: test case %s missing", run_id, testcase_id)
                return ExecutionStatus.ERROR.value

            flow_result = await db.execute(
                select(TestFlow).where(TestFlow.testcase_id == testcase_id)
            )
            flow = flow_result.scalar_one_or_none()
            nodes, edges = [], []
            if flow:
                try:
                    nodes = json.loads(flow.nodes) if isinstance(flow.nodes, str) else (flow.nodes or [])
                except (json.JSONDecodeError, TypeError):
                    nodes = []
                try:
                    edges = json.loads(flow.edges) if isinstance(flow.edges, str) else (flow.edges or [])
                except (json.JSONDecodeError, TypeError):
                    edges = []

            execution = TestExecution(
                testcase_id=testcase_id,
                status=ExecutionStatus.RUNNING.value,
                total_steps=len([n for n in nodes if n.get("type") not in ("start", "end")]),
                started_at=utc_now(),
                # batch linkage
                plan_run_id=run_id,
                plan_item_id=str(item.get("id")),
                iteration=iteration,
                group_no=int(item.get("group_no") or 0),
            )
            db.add(execution)
            test_case.status = "running"
            await db.commit()
            await db.refresh(execution)

            st = self._state[run_id]["items"].get(str(item.get("id")))
            if st is not None:
                st["execution_id"] = execution.id

            exec_id = execution.id
            # Runs inline — and *closes* the session it is handed, so the
            # in-memory object can no longer be trusted. Re-read the
            # authoritative status from a fresh session instead.
            await execution_engine._run_execution(db, execution, nodes, edges, None)
            async with async_session() as fresh:
                row = await fresh.get(TestExecution, exec_id)
                status = row.status if row else ExecutionStatus.ERROR.value
            logger.info(
                "run %s iteration %d of %s -> %s",
                run_id, iteration, testcase_id, status,
            )
            return status
        except Exception as e:
            logger.exception(
                "run %s iteration %d of %s failed: %s", run_id, iteration, testcase_id, e
            )
            return ExecutionStatus.ERROR.value
        finally:
            try:
                await db.close()
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # Finalisation
    # ------------------------------------------------------------------ #

    async def _finalize(self, run_id: str, aborted: bool) -> None:
        state = self._state.get(run_id, {})
        items_state = state.get("items", {})

        passed = sum(1 for s in items_state.values() if s.get("status") == "passed")
        failed = sum(1 for s in items_state.values() if s.get("status") == "failed")
        stopped = sum(1 for s in items_state.values() if s.get("status") == "stopped")
        completed = passed + failed + stopped

        if aborted or stopped:
            status = PlanRunStatus.STOPPED.value
        elif failed:
            status = PlanRunStatus.FAILED.value
        else:
            status = PlanRunStatus.PASSED.value

        async with async_session() as db:
            run = await db.get(ExecutionPlanRun, run_id)
            if run:
                run.status = status
                run.completed_items = completed
                run.passed_items = passed
                run.failed_items = failed
                run.completed_at = utc_now()
                if run.started_at:
                    run.duration_ms = int(
                        (run.completed_at - run.started_at).total_seconds() * 1000
                    )
                await db.commit()
        state["status"] = status
        self._tasks.pop(run_id, None)
        logger.info(
            "plan run %s finished: %s (%d passed / %d failed / %d stopped)",
            run_id, status, passed, failed, stopped,
        )

    async def reset_stale_runs(self, db: AsyncSession) -> int:
        """Reap runs left 'running' by a previous process (mirrors executions)."""
        result = await db.execute(
            select(ExecutionPlanRun).where(
                ExecutionPlanRun.status == PlanRunStatus.RUNNING.value
            )
        )
        runs = result.scalars().all()
        for run in runs:
            run.status = PlanRunStatus.ERROR.value
            run.error_message = "进程重启，运行被中断"
            run.completed_at = utc_now()
        if runs:
            await db.commit()
        return len(runs)


plan_runner = PlanRunner()
