"""Execution-plan API — batch orchestration of test cases.

POST   /api/execution-plans/                       create a plan
GET    /api/execution-plans/                       list plans
GET    /api/execution-plans/{id}                   plan detail (with items)
PUT    /api/execution-plans/{id}                   update (items replaced wholesale)
DELETE /api/execution-plans/{id}                   delete
POST   /api/execution-plans/{id}/duplicate         copy a plan
POST   /api/execution-plans/validate               validate a *draft* (no save needed)
GET    /api/execution-plans/{id}/validate          validate a saved plan
POST   /api/execution-plans/{id}/resolve-devices   re-infer every item's devices

POST   /api/execution-plans/{id}/run               start (409 when conflicts remain)
GET    /api/execution-runs/{id}                    batch run detail + item progress
GET    /api/execution-runs/                        batch run list
POST   /api/execution-runs/{id}/stop               stop the whole batch
POST   /api/execution-runs/{id}/items/{item_id}/stop   stop a single item
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import (
    ExecutionPlan,
    ExecutionPlanItem,
    ExecutionPlanRun,
    TestCase,
)
from app.services.plan_runner import plan_runner
from app.services.plan_service import (
    MAX_DELAY_MS,
    MAX_ITEMS_PER_PLAN,
    MAX_LOOP_COUNT,
    MAX_PARALLEL_LIMIT,
    resolve_item_devices,
    resolve_plan_items,
    validate_plan,
)

logger = logging.getLogger(__name__)

plans_router = APIRouter(prefix="/api/execution-plans", tags=["ExecutionPlans"])
runs_router = APIRouter(prefix="/api/execution-runs", tags=["ExecutionRuns"])


# ---------------------------------------------------------------------- #
# Request models
# ---------------------------------------------------------------------- #

class PlanItemIn(BaseModel):
    id: Optional[str] = None
    testcase_id: str
    seq: Optional[int] = None
    group_no: Optional[int] = None      # None -> own sequence number (= serial)
    loop_count: int = 1
    delay_before_ms: int = 0
    delay_after_ms: int = 0
    loop_interval_ms: int = 0
    device_id: Optional[str] = None     # explicit override; None -> infer


class PlanIn(BaseModel):
    name: str
    description: Optional[str] = None
    plan_loop_count: int = 1
    max_parallel: int = 4
    on_error: str = "abort_all"         # abort_all | continue | abort_group
    items: List[PlanItemIn] = Field(default_factory=list)


class DraftValidateIn(BaseModel):
    plan: Dict[str, Any]
    items: List[Dict[str, Any]]


def _clamp(value: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return low


def _sanitize(item: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(item)
    out["loop_count"] = _clamp(item.get("loop_count", 1), 1, MAX_LOOP_COUNT)
    out["delay_before_ms"] = _clamp(item.get("delay_before_ms", 0), 0, MAX_DELAY_MS)
    out["delay_after_ms"] = _clamp(item.get("delay_after_ms", 0), 0, MAX_DELAY_MS)
    out["loop_interval_ms"] = _clamp(item.get("loop_interval_ms", 0), 0, MAX_DELAY_MS)
    return out


# ---------------------------------------------------------------------- #
# Serialisation helpers
# ---------------------------------------------------------------------- #

async def _case_names(db: AsyncSession, ids: List[str]) -> Dict[str, str]:
    if not ids:
        return {}
    result = await db.execute(select(TestCase).where(TestCase.id.in_(ids)))
    return {tc.id: tc.name for tc in result.scalars().all()}


def _item_to_dict(item: ExecutionPlanItem, case_name: Optional[str] = None) -> Dict[str, Any]:
    try:
        resolved = json.loads(item.resolved_device_ids) if item.resolved_device_ids else []
    except (json.JSONDecodeError, TypeError):
        resolved = []
    return {
        "id": item.id,
        "plan_id": item.plan_id,
        "testcase_id": item.testcase_id,
        "testcase_name": case_name,
        "seq": item.seq,
        "group_no": item.group_no,
        "loop_count": item.loop_count,
        "delay_before_ms": item.delay_before_ms,
        "delay_after_ms": item.delay_after_ms,
        "loop_interval_ms": item.loop_interval_ms,
        "device_id": item.device_id,
        "resolved_device_ids": resolved,
        "resolved_state": item.resolved_state,
    }


async def _plan_to_dict(
    db: AsyncSession, plan: ExecutionPlan, include_items: bool = True
) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "id": plan.id,
        "name": plan.name,
        "description": plan.description,
        "plan_loop_count": plan.plan_loop_count,
        "max_parallel": plan.max_parallel,
        "on_error": plan.on_error,
        "last_run_id": plan.last_run_id,
        "created_at": plan.created_at,
        "updated_at": plan.updated_at,
        "item_count": 0,
        "items": [],
    }
    if include_items:
        result = await db.execute(
            select(ExecutionPlanItem)
            .where(ExecutionPlanItem.plan_id == plan.id)
            .order_by(ExecutionPlanItem.seq)
        )
        items = result.scalars().all()
        names = await _case_names(db, [i.testcase_id for i in items])
        data["items"] = [_item_to_dict(i, names.get(i.testcase_id)) for i in items]
        data["item_count"] = len(items)
    return data


def _plan_config_dict(plan: ExecutionPlan) -> Dict[str, Any]:
    return {
        "name": plan.name,
        "plan_loop_count": plan.plan_loop_count,
        "max_parallel": plan.max_parallel,
        "on_error": plan.on_error,
    }


# ---------------------------------------------------------------------- #
# Item persistence
# ---------------------------------------------------------------------- #

async def _replace_items(
    db: AsyncSession, plan: ExecutionPlan, items_in: List[PlanItemIn]
) -> None:
    """Drop the plan's items and recreate them, resolving devices as we go."""
    existing = await db.execute(
        select(ExecutionPlanItem).where(ExecutionPlanItem.plan_id == plan.id)
    )
    for old in existing.scalars().all():
        await db.delete(old)
    await db.flush()

    for index, raw in enumerate(items_in):
        seq = raw.seq if raw.seq is not None else index + 1
        # Default grouping = own sequence number, i.e. fully serial (FR3.1).
        group_no = raw.group_no if raw.group_no is not None else index + 1
        item = ExecutionPlanItem(
            plan_id=plan.id,
            testcase_id=raw.testcase_id,
            seq=seq,
            group_no=group_no,
            loop_count=_clamp(raw.loop_count, 1, MAX_LOOP_COUNT),
            delay_before_ms=_clamp(raw.delay_before_ms, 0, MAX_DELAY_MS),
            delay_after_ms=_clamp(raw.delay_after_ms, 0, MAX_DELAY_MS),
            loop_interval_ms=_clamp(raw.loop_interval_ms, 0, MAX_DELAY_MS),
            device_id=raw.device_id,
        )
        res = await resolve_item_devices(db, item.testcase_id, item.device_id)
        item.resolved_state = res.state
        item.resolved_device_ids = json.dumps(res.device_ids) if res.device_ids else None
        item.node_count = res.node_count
        db.add(item)
    await db.flush()


async def _get_plan(db: AsyncSession, plan_id: str) -> ExecutionPlan:
    plan = await db.get(ExecutionPlan, plan_id)
    if not plan:
        raise HTTPException(
            status_code=404,
            detail={"code": 40001, "message": "Plan not found", "detail": plan_id},
        )
    return plan


# ---------------------------------------------------------------------- #
# Plan CRUD
# ---------------------------------------------------------------------- #

@plans_router.post("/", status_code=201)
async def create_plan(data: PlanIn, db: AsyncSession = Depends(get_db)):
    if len(data.items) > MAX_ITEMS_PER_PLAN:
        raise HTTPException(
            status_code=400,
            detail={
                "code": 40010,
                "message": f"单个计划最多 {MAX_ITEMS_PER_PLAN} 项",
                "detail": f"got {len(data.items)}",
            },
        )
    plan = ExecutionPlan(
        name=data.name,
        description=data.description,
        plan_loop_count=_clamp(data.plan_loop_count, 1, MAX_LOOP_COUNT),
        max_parallel=_clamp(data.max_parallel, 1, MAX_PARALLEL_LIMIT),
        on_error=data.on_error if data.on_error in ("abort_all", "continue", "abort_group") else "abort_all",
    )
    db.add(plan)
    await db.flush()
    await _replace_items(db, plan, data.items)
    await db.commit()
    await db.refresh(plan)
    return {"code": 0, "message": "success", "data": await _plan_to_dict(db, plan)}


@plans_router.get("/")
async def list_plans(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ExecutionPlan).order_by(ExecutionPlan.updated_at.desc())
    )
    plans = result.scalars().all()
    total = len(plans)
    start = (page - 1) * page_size
    page_items = plans[start:start + page_size]

    data = []
    for plan in page_items:
        row = await _plan_to_dict(db, plan, include_items=True)
        data.append(row)
    return {
        "code": 0,
        "message": "success",
        "data": {"items": data, "total": total, "page": page, "page_size": page_size},
    }


@plans_router.get("/{plan_id}")
async def get_plan(plan_id: str, db: AsyncSession = Depends(get_db)):
    plan = await _get_plan(db, plan_id)
    return {"code": 0, "message": "success", "data": await _plan_to_dict(db, plan)}


@plans_router.put("/{plan_id}")
async def update_plan(plan_id: str, data: PlanIn, db: AsyncSession = Depends(get_db)):
    plan = await _get_plan(db, plan_id)
    plan.name = data.name
    plan.description = data.description
    plan.plan_loop_count = _clamp(data.plan_loop_count, 1, MAX_LOOP_COUNT)
    plan.max_parallel = _clamp(data.max_parallel, 1, MAX_PARALLEL_LIMIT)
    plan.on_error = data.on_error if data.on_error in ("abort_all", "continue", "abort_group") else "abort_all"
    await _replace_items(db, plan, data.items)
    await db.commit()
    await db.refresh(plan)
    return {"code": 0, "message": "success", "data": await _plan_to_dict(db, plan)}


@plans_router.delete("/{plan_id}")
async def delete_plan(plan_id: str, db: AsyncSession = Depends(get_db)):
    plan = await _get_plan(db, plan_id)
    await db.delete(plan)
    await db.commit()
    return {"code": 0, "message": "Plan deleted", "data": None}


@plans_router.post("/{plan_id}/duplicate", status_code=201)
async def duplicate_plan(plan_id: str, db: AsyncSession = Depends(get_db)):
    plan = await _get_plan(db, plan_id)
    result = await db.execute(
        select(ExecutionPlanItem)
        .where(ExecutionPlanItem.plan_id == plan.id)
        .order_by(ExecutionPlanItem.seq)
    )
    source_items = result.scalars().all()

    copy = ExecutionPlan(
        name=f"{plan.name} (副本)",
        description=plan.description,
        plan_loop_count=plan.plan_loop_count,
        max_parallel=plan.max_parallel,
        on_error=plan.on_error,
    )
    db.add(copy)
    await db.flush()
    for item in source_items:
        db.add(ExecutionPlanItem(
            plan_id=copy.id,
            testcase_id=item.testcase_id,
            seq=item.seq,
            group_no=item.group_no,
            loop_count=item.loop_count,
            delay_before_ms=item.delay_before_ms,
            delay_after_ms=item.delay_after_ms,
            loop_interval_ms=item.loop_interval_ms,
            device_id=item.device_id,
            resolved_device_ids=item.resolved_device_ids,
            resolved_state=item.resolved_state,
        ))
    await db.commit()
    await db.refresh(copy)
    return {"code": 0, "message": "success", "data": await _plan_to_dict(db, copy)}


# ---------------------------------------------------------------------- #
# Validation
# ---------------------------------------------------------------------- #

@plans_router.post("/validate")
async def validate_draft(data: DraftValidateIn, db: AsyncSession = Depends(get_db)):
    """Validate an unsaved plan draft (PRD FR7.5) — no save required."""
    plan = dict(data.plan or {})
    items: List[Dict[str, Any]] = []
    for index, raw in enumerate(data.items or []):
        item = _sanitize(raw)
        item.setdefault("seq", index + 1)
        item.setdefault("group_no", index + 1)
        # Resolve on the fly when the caller did not supply a snapshot.
        if not item.get("resolved_device_ids") and not item.get("device_id"):
            res = await resolve_item_devices(db, item.get("testcase_id"), None)
            item["resolved_device_ids"] = res.device_ids
            item["resolved_state"] = res.state
            item["node_count"] = res.node_count
        elif item.get("device_id") and not item.get("resolved_device_ids"):
            res = await resolve_item_devices(db, item.get("testcase_id"), item["device_id"])
            item["resolved_device_ids"] = res.device_ids
            item["resolved_state"] = res.state
        items.append(item)

    report = await validate_plan(db, plan, items)
    return {"code": 0, "message": "success", "data": report}


@plans_router.get("/{plan_id}/validate")
async def validate_saved(plan_id: str, db: AsyncSession = Depends(get_db)):
    plan = await _get_plan(db, plan_id)
    result = await db.execute(
        select(ExecutionPlanItem)
        .where(ExecutionPlanItem.plan_id == plan.id)
        .order_by(ExecutionPlanItem.seq)
    )
    items = result.scalars().all()
    names = await _case_names(db, [i.testcase_id for i in items])
    item_dicts = [_item_to_dict(i, names.get(i.testcase_id)) for i in items]
    report = await validate_plan(db, _plan_config_dict(plan), item_dicts)
    return {"code": 0, "message": "success", "data": report}


@plans_router.post("/{plan_id}/resolve-devices")
async def resolve_devices(plan_id: str, db: AsyncSession = Depends(get_db)):
    """Re-infer every item's devices after the device set changed (PRD H2)."""
    plan = await _get_plan(db, plan_id)
    result = await db.execute(
        select(ExecutionPlanItem)
        .where(ExecutionPlanItem.plan_id == plan.id)
        .order_by(ExecutionPlanItem.seq)
    )
    items = result.scalars().all()
    await resolve_plan_items(db, items)
    await db.commit()
    return {"code": 0, "message": "success", "data": await _plan_to_dict(db, plan)}


# ---------------------------------------------------------------------- #
# Running
# ---------------------------------------------------------------------- #

async def _load_plan_for_run(db: AsyncSession, plan: ExecutionPlan):
    result = await db.execute(
        select(ExecutionPlanItem)
        .where(ExecutionPlanItem.plan_id == plan.id)
        .order_by(ExecutionPlanItem.seq)
    )
    items = result.scalars().all()
    names = await _case_names(db, [i.testcase_id for i in items])
    item_dicts = [_item_to_dict(i, names.get(i.testcase_id)) for i in items]
    return _plan_config_dict(plan), item_dicts


@plans_router.post("/{plan_id}/run", status_code=201)
async def run_plan(plan_id: str, db: AsyncSession = Depends(get_db)):
    """Start a batch run.  Conflicts are re-checked here — 409 blocks it.

    The backend must never trust the frontend's validation: the UI can be
    bypassed with a direct request, so the check runs again server-side.
    """
    plan = await _get_plan(db, plan_id)
    plan_cfg, items = await _load_plan_for_run(db, plan)
    if not items:
        raise HTTPException(
            status_code=400,
            detail={"code": 40011, "message": "计划为空，没有可执行项"},
        )

    report = await validate_plan(db, plan_cfg, items)
    if report["blocking"]:
        raise HTTPException(
            status_code=409,
            detail={
                "code": 40020,
                "message": "计划存在冲突，不能执行",
                "validation": report,
            },
        )

    run = await plan_runner.start_run(db, plan.id, plan_cfg, items)
    plan.last_run_id = run.id
    await db.commit()
    return {
        "code": 0,
        "message": "success",
        "data": {"run_id": run.id, "total_items": run.total_items},
    }


@runs_router.get("/")
async def list_runs(
    plan_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ExecutionPlanRun).order_by(ExecutionPlanRun.created_at.desc())
    if plan_id:
        stmt = stmt.where(ExecutionPlanRun.plan_id == plan_id)
    result = await db.execute(stmt)
    runs = result.scalars().all()
    total = len(runs)
    start = (page - 1) * page_size
    return {
        "code": 0,
        "message": "success",
        "data": {
            "items": [_run_to_dict(r) for r in runs[start:start + page_size]],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


def _run_to_dict(run: ExecutionPlanRun) -> Dict[str, Any]:
    return {
        "id": run.id,
        "plan_id": run.plan_id,
        "plan_name": run.plan_name,
        "status": run.status,
        "total_items": run.total_items,
        "completed_items": run.completed_items,
        "passed_items": run.passed_items,
        "failed_items": run.failed_items,
        "error_message": run.error_message,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "duration_ms": run.duration_ms,
        "created_at": run.created_at,
    }


@runs_router.get("/{run_id}")
async def get_run(run_id: str, db: AsyncSession = Depends(get_db)):
    run = await db.get(ExecutionPlanRun, run_id)
    if not run:
        raise HTTPException(
            status_code=404,
            detail={"code": 40001, "message": "Run not found", "detail": run_id},
        )
    data = _run_to_dict(run)

    # Merge the live in-memory progress (the UI polls this endpoint).
    state = plan_runner.get_state(run_id) or {}
    live_items = list((state.get("items") or {}).values())
    if live_items:
        data["items"] = live_items
        data["status"] = state.get("status") or run.status
    else:
        # Finished (or restarted) run: rebuild the item list from the snapshot.
        try:
            snapshot = json.loads(run.plan_snapshot or "{}")
        except (json.JSONDecodeError, TypeError):
            snapshot = {}
        data["items"] = snapshot.get("items", [])
    return {"code": 0, "message": "success", "data": data}


@runs_router.post("/{run_id}/stop")
async def stop_run(run_id: str, db: AsyncSession = Depends(get_db)):
    run = await db.get(ExecutionPlanRun, run_id)
    if not run:
        raise HTTPException(
            status_code=404,
            detail={"code": 40001, "message": "Run not found", "detail": run_id},
        )
    await plan_runner.stop_run(db, run_id)
    return {"code": 0, "message": "Run stopped", "data": {"run_id": run_id}}


@runs_router.post("/{run_id}/items/{item_id}/stop")
async def stop_run_item(run_id: str, item_id: str):
    await plan_runner.stop_item(run_id, item_id)
    return {"code": 0, "message": "Item stopped", "data": {"run_id": run_id, "item_id": item_id}}
