"""Custom dashboard API routes.

A dashboard stores *only* a description — a grid layout plus widget
definitions. Measured values are never persisted here; they are resolved on
every request from the step results that already carry ``parsed_results``.

GET    /api/dashboards/               - List dashboards (seeds built-in templates)
POST   /api/dashboards/               - Create dashboard
GET    /api/dashboards/snapshot       - One-shot runtime payload for all widgets
GET    /api/dashboards/{id}           - Get dashboard
PUT    /api/dashboards/{id}           - Update dashboard
DELETE /api/dashboards/{id}           - Delete dashboard
POST   /api/dashboards/{id}/duplicate - Copy a dashboard
POST   /api/dashboards/{id}/set-default - Mark as the default dashboard
POST   /api/dashboards/import         - Import a dashboard from JSON
"""
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import Dashboard, Device, TestExecution, TestCase
from app.schemas.schemas import DashboardCreate, DashboardUpdate
from app.services.trend_service import collect_parsed_series, summarise_judgement

router = APIRouter(prefix="/api/dashboards", tags=["Dashboards"])

DEFAULT_DATA_SOURCE = {"test_case_id": None, "limit": 50, "refresh_sec": 10}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _load_json(raw: Any, fallback: Any) -> Any:
    if raw is None:
        return fallback
    if isinstance(raw, (list, dict)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return fallback


def _dashboard_to_dict(d: Dashboard) -> dict:
    return {
        "id": d.id,
        "name": d.name,
        "description": d.description,
        "layout": _load_json(d.layout, []),
        "widgets": _load_json(d.widgets, []),
        "data_source": {**DEFAULT_DATA_SOURCE, **(_load_json(d.data_source, {}) or {})},
        "is_default": bool(d.is_default),
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "updated_at": d.updated_at.isoformat() if d.updated_at else None,
    }


def _new_widget(wid: str, wtype: str, title: str, **cfg: Any) -> dict:
    return {"id": wid, "type": wtype, "title": title, "config": cfg}


def _layout_item(i: str, x: int, y: int, w: int, h: int) -> dict:
    return {"i": i, "x": x, "y": y, "w": w, "h": h, "minW": 2, "minH": 2}


def _template_debug() -> dict:
    """调试视图：设备状态 + 执行统计 + 通信日志。"""
    widgets = [
        _new_widget("w_dev", "device_status", "设备状态"),
        _new_widget("w_stat", "execution_stats", "执行统计"),
        _new_widget("w_log", "comm_log", "通信日志", limit=12),
    ]
    layout = [
        _layout_item("w_dev", 0, 0, 5, 6),
        _layout_item("w_stat", 5, 0, 7, 6),
        _layout_item("w_log", 0, 6, 12, 8),
    ]
    return {
        "name": "调试视图",
        "description": "内置模板：盯设备在线状态、执行统计与最新收发报文",
        "layout": layout,
        "widgets": widgets,
        "data_source": dict(DEFAULT_DATA_SOURCE),
        "is_default": False,
    }


def _template_endurance() -> dict:
    """长稳视图：解析数值卡片 + 趋势曲线 + 判定结果汇总 + 执行统计。"""
    widgets = [
        _new_widget("w_val", "parsed_value", "解析数值", field=""),
        _new_widget("w_trend", "trend_chart", "解析值趋势", fields=[], height=300),
        _new_widget("w_judge", "judge_summary", "判定结果汇总"),
        _new_widget("w_stat", "execution_stats", "执行统计"),
    ]
    layout = [
        _layout_item("w_val", 0, 0, 4, 5),
        _layout_item("w_trend", 4, 0, 8, 5),
        _layout_item("w_judge", 0, 5, 8, 7),
        _layout_item("w_stat", 8, 5, 4, 7),
    ]
    return {
        "name": "长稳视图",
        "description": "内置模板：长时间稳定性测试 —— 盯解析值、看漂移、汇总 FAIL 判定",
        "layout": layout,
        "widgets": widgets,
        "data_source": dict(DEFAULT_DATA_SOURCE),
        "is_default": False,
    }


async def _seed_templates(db: AsyncSession) -> None:
    """Create the two built-in templates the first time the table is empty."""
    for tpl in (_template_endurance(), _template_debug()):
        db.add(Dashboard(
            name=tpl["name"],
            description=tpl["description"],
            layout=json.dumps(tpl["layout"], ensure_ascii=False),
            widgets=json.dumps(tpl["widgets"], ensure_ascii=False),
            data_source=json.dumps(tpl["data_source"], ensure_ascii=False),
            is_default=False,
        ))
    await db.commit()


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@router.get("/")
async def list_dashboards(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Dashboard).order_by(Dashboard.created_at.asc()))
    items = list(result.scalars().all())
    if not items:
        await _seed_templates(db)
        result = await db.execute(select(Dashboard).order_by(Dashboard.created_at.asc()))
        items = list(result.scalars().all())
    return {
        "code": 0, "message": "success",
        "data": [_dashboard_to_dict(d) for d in items],
    }


@router.get("/snapshot")
async def dashboard_snapshot(
    test_case_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """One request that feeds every widget.

    Keeps a dashboard with N widgets at a single poll instead of N requests.
    """
    # ---- devices ----
    dev_rows = await db.execute(select(Device).order_by(Device.name.asc()))
    devices = list(dev_rows.scalars().all())
    device_items = [{
        "id": d.id,
        "name": d.name,
        "type": d.type,
        "protocol": d.protocol,
        "connection_type": d.connection_type,
        "status": d.status,
        "address": d.visa_address or d.serial_port or d.can_channel or (
            f"{d.ip_address}:{d.port}" if d.ip_address else None
        ),
        "connected_at": d.connected_at.isoformat() if d.connected_at else None,
        "last_seen": d.last_seen.isoformat() if d.last_seen else None,
    } for d in devices]

    # ---- executions ----
    ex_rows = await db.execute(
        select(
            TestExecution.id, TestExecution.testcase_id, TestExecution.status,
            TestExecution.result, TestExecution.total_steps,
            TestExecution.passed_steps, TestExecution.failed_steps,
            TestExecution.duration_ms, TestExecution.created_at,
            TestExecution.completed_at, TestExecution.error_message,
        ).order_by(desc(TestExecution.created_at)).limit(200)
    )
    execs = list(ex_rows.all())
    total_exec = len(execs)
    by_status: Dict[str, int] = {}
    for e in execs:
        by_status[e[2]] = by_status.get(e[2], 0) + 1
    passed = by_status.get("passed", 0)
    failed = by_status.get("failed", 0)
    error = by_status.get("error", 0)
    running = by_status.get("running", 0) + by_status.get("pending", 0)
    finished = passed + failed + error
    exec_items = [{
        "id": e[0], "test_case_id": e[1], "status": e[2], "result": e[3],
        "total_steps": e[4], "passed_steps": e[5], "failed_steps": e[6],
        "duration_ms": e[7],
        "created_at": e[8].isoformat() if e[8] else None,
        "completed_at": e[9].isoformat() if e[9] else None,
        "error_message": e[10],
    } for e in execs[:20]]

    # ---- parsed values + judgement ----
    parsed: Dict[str, Any] = {
        "fields": [], "series": {}, "executions": [], "total_points": 0,
    }
    judgement = summarise_judgement({})
    test_case_name = None
    if test_case_id:
        tc = await db.get(TestCase, test_case_id)
        test_case_name = tc.name if tc else None
        parsed = await collect_parsed_series(db, test_case_id, limit=limit)
        judgement = summarise_judgement(parsed["series"])

        # expose every field as a ready-to-card latest value
        latest: Dict[str, Any] = {}
        for field, points in parsed["series"].items():
            if not points:
                continue
            last = points[-1]
            nums = [p["num"] for p in points if p["num"] is not None]
            latest[field] = {
                "field": field,
                "value": last.get("value"),
                "num": last.get("num"),
                "status": last.get("status"),
                "detail": last.get("detail"),
                "points": len(points),
                "min": min(nums) if nums else None,
                "max": max(nums) if nums else None,
                "avg": round(sum(nums) / len(nums), 6) if nums else None,
                "fail_count": sum(
                    1 for p in points
                    if (p.get("status") or "") == "fail"
                ),
                "updated_at": last.get("completed_at") or last.get("started_at"),
            }
        parsed["latest"] = latest

    return {
        "code": 0, "message": "success",
        "data": {
            "generated_at": datetime.utcnow().isoformat(),
            "test_case_id": test_case_id,
            "test_case_name": test_case_name,
            "devices": {
                "total": len(devices),
                "connected": sum(1 for d in devices if d.status == "connected"),
                "list": device_items,
            },
            "executions": {
                "total": total_exec,
                "passed": passed,
                "failed": failed,
                "error": error,
                "running": running,
                "pass_rate": round(passed / finished * 100, 1) if finished else None,
                "by_status": by_status,
                "recent": exec_items,
            },
            "parsed": parsed,
            "judgement": judgement,
        },
    }


@router.post("/")
async def create_dashboard(data: DashboardCreate, db: AsyncSession = Depends(get_db)):
    payload = data.model_dump()
    d = Dashboard(
        name=payload["name"],
        description=payload.get("description"),
        layout=json.dumps(payload.get("layout") or [], ensure_ascii=False),
        widgets=json.dumps(payload.get("widgets") or [], ensure_ascii=False),
        data_source=json.dumps(
            {**DEFAULT_DATA_SOURCE, **(payload.get("data_source") or {})},
            ensure_ascii=False,
        ),
        is_default=bool(payload.get("is_default")),
    )
    db.add(d)
    await db.commit()
    await db.refresh(d)
    if d.is_default:
        await _clear_other_defaults(db, d.id)
    return {"code": 0, "message": "success", "data": _dashboard_to_dict(d)}


async def _clear_other_defaults(db: AsyncSession, keep_id: str) -> None:
    result = await db.execute(select(Dashboard))
    for d in result.scalars().all():
        if d.id != keep_id and d.is_default:
            d.is_default = False
    await db.commit()


async def _get_or_404(db: AsyncSession, dashboard_id: str) -> Dashboard:
    d = await db.get(Dashboard, dashboard_id)
    if not d:
        raise HTTPException(status_code=404, detail={
            "code": 40004, "message": "Dashboard not found",
        })
    return d


@router.get("/{dashboard_id}")
async def get_dashboard(dashboard_id: str, db: AsyncSession = Depends(get_db)):
    d = await _get_or_404(db, dashboard_id)
    return {"code": 0, "message": "success", "data": _dashboard_to_dict(d)}


@router.put("/{dashboard_id}")
async def update_dashboard(
    dashboard_id: str, data: DashboardUpdate, db: AsyncSession = Depends(get_db)
):
    d = await _get_or_404(db, dashboard_id)
    payload = data.model_dump(exclude_unset=True)
    if "name" in payload and payload["name"]:
        d.name = payload["name"]
    if "description" in payload:
        d.description = payload["description"]
    if "layout" in payload:
        d.layout = json.dumps(payload["layout"] or [], ensure_ascii=False)
    if "widgets" in payload:
        d.widgets = json.dumps(payload["widgets"] or [], ensure_ascii=False)
    if "data_source" in payload:
        d.data_source = json.dumps(
            {**DEFAULT_DATA_SOURCE, **(payload["data_source"] or {})},
            ensure_ascii=False,
        )
    if "is_default" in payload:
        d.is_default = bool(payload["is_default"])
    d.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(d)
    if d.is_default:
        await _clear_other_defaults(db, d.id)
    return {"code": 0, "message": "success", "data": _dashboard_to_dict(d)}


@router.delete("/{dashboard_id}")
async def delete_dashboard(dashboard_id: str, db: AsyncSession = Depends(get_db)):
    d = await _get_or_404(db, dashboard_id)
    was_default = d.is_default
    await db.delete(d)
    await db.commit()
    if was_default:
        # keep exactly one default around so the UI always has a landing view
        result = await db.execute(select(Dashboard).order_by(Dashboard.created_at.asc()))
        first = result.scalars().first()
        if first:
            first.is_default = True
            await db.commit()
    return {"code": 0, "message": "success", "data": None}


@router.post("/{dashboard_id}/duplicate")
async def duplicate_dashboard(dashboard_id: str, db: AsyncSession = Depends(get_db)):
    src = await _get_or_404(db, dashboard_id)
    copy = Dashboard(
        name=f"{src.name} 副本",
        description=src.description,
        layout=src.layout,
        widgets=src.widgets,
        data_source=src.data_source,
        is_default=False,
    )
    db.add(copy)
    await db.commit()
    await db.refresh(copy)
    return {"code": 0, "message": "success", "data": _dashboard_to_dict(copy)}


@router.post("/{dashboard_id}/set-default")
async def set_default_dashboard(dashboard_id: str, db: AsyncSession = Depends(get_db)):
    d = await _get_or_404(db, dashboard_id)
    await _clear_other_defaults(db, d.id)
    d.is_default = True
    await db.commit()
    await db.refresh(d)
    return {"code": 0, "message": "success", "data": _dashboard_to_dict(d)}


@router.post("/import")
async def import_dashboard(data: DashboardCreate, db: AsyncSession = Depends(get_db)):
    """Import a dashboard previously exported as JSON."""
    payload = data.model_dump()
    if not payload.get("layout") and not payload.get("widgets"):
        raise HTTPException(status_code=400, detail={
            "code": 40001, "message": "导入内容缺少 layout / widgets",
        })
    d = Dashboard(
        name=payload.get("name") or "导入的仪表盘",
        description=payload.get("description"),
        layout=json.dumps(payload.get("layout") or [], ensure_ascii=False),
        widgets=json.dumps(payload.get("widgets") or [], ensure_ascii=False),
        data_source=json.dumps(
            {**DEFAULT_DATA_SOURCE, **(payload.get("data_source") or {})},
            ensure_ascii=False,
        ),
        is_default=False,
    )
    db.add(d)
    await db.commit()
    await db.refresh(d)
    return {"code": 0, "message": "success", "data": _dashboard_to_dict(d)}
