"""Shared helper for reading parsed result values back out of step results.

Parsed values are stored with the step that produced them
(``test_step_results.parsed_results``) — there is no separate metrics/trend
table. Reading a trend therefore means walking executions in chronological
order and flattening their per-reply samples into one point per reply.

Used by:
  * ``GET /api/testcases/{id}/parsed-trend``  (standalone history view)
  * ``GET /api/dashboards/snapshot``          (custom dashboard widgets)
"""
from __future__ import annotations
import json
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import TestExecution, TestStepResult
from app.services.response_parser import response_parser


def samples_of(parsed: Any) -> List[List[Dict[str, Any]]]:
    """``parsed_results`` is either the per-reply series object or the legacy
    flat list (a single sample)."""
    if isinstance(parsed, dict):
        samples = parsed.get("samples")
        if isinstance(samples, list) and samples:
            return [s for s in samples if isinstance(s, list)]
        last = parsed.get("last")
        return [last] if isinstance(last, list) else []
    if isinstance(parsed, list):
        return [parsed]
    return []


async def collect_parsed_series(
    db: AsyncSession, test_case_id: str, limit: int = 50
) -> Dict[str, Any]:
    """Return chronological per-field series of parsed values for a test case.

    ``num`` is the numeric view used for plotting (``None`` for values that are
    not numeric, e.g. plain strings) and ``status`` is the judgement outcome of
    that single reply: ``ok`` / ``fail`` / ``unknown`` / ``error``.
    """
    exec_rows = await db.execute(
        select(
            TestExecution.id,
            TestExecution.created_at,
            TestExecution.started_at,
            TestExecution.status,
            TestExecution.result,
        )
        .where(TestExecution.testcase_id == test_case_id)
        .order_by(TestExecution.created_at.desc())
        .limit(limit)
    )
    executions = list(exec_rows.all())
    if not executions:
        return {"fields": [], "series": {}, "executions": [], "total_points": 0}

    # chronological order for plotting
    executions.reverse()
    exec_ids = [e[0] for e in executions]
    exec_meta = {
        e[0]: {
            "created_at": e[1].isoformat() if e[1] else None,
            "started_at": e[2].isoformat() if e[2] else None,
            "status": e[3],
            "result": e[4],
        }
        for e in executions
    }

    step_rows = await db.execute(
        select(TestStepResult)
        .where(
            TestStepResult.execution_id.in_(exec_ids),
            TestStepResult.parsed_results.isnot(None),
        )
        .order_by(TestStepResult.step_index.asc())
    )
    steps = list(step_rows.scalars().all())

    series: Dict[str, List[Dict[str, Any]]] = {}
    for s in steps:
        try:
            parsed = json.loads(s.parsed_results or "[]")
        except (TypeError, ValueError):
            continue
        samples = samples_of(parsed)
        if not samples:
            continue
        meta = exec_meta.get(s.execution_id, {})
        # one point per reply, so a step that repeated a command N times
        # contributes N points instead of a single collapsed one
        for seq, sample in enumerate(samples):
            for p in sample:
                if not isinstance(p, dict):
                    continue
                name = str(p.get("name") or "").strip()
                if not name:
                    continue
                value = p.get("value")
                num = response_parser.to_number(value)
                series.setdefault(name, []).append({
                    "execution_id": s.execution_id,
                    "step_index": s.step_index,
                    "step_label": s.label,
                    "seq": seq,
                    "total": len(samples),
                    "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                    "started_at": meta.get("started_at"),
                    "value": value,
                    "num": num,
                    "ok": bool(p.get("ok")),
                    "status": p.get("status") or ("ok" if p.get("ok") else "fail"),
                    "detail": p.get("detail"),
                })

    order = {e[0]: i for i, e in enumerate(executions)}
    for points in series.values():
        points.sort(
            key=lambda pt: (
                order.get(pt["execution_id"], 0), pt["step_index"], pt["seq"]
            )
        )

    return {
        "fields": list(series.keys()),
        "series": series,
        "executions": [{"id": e[0], **exec_meta[e[0]]} for e in executions],
        "total_points": sum(len(v) for v in series.values()),
    }


def summarise_judgement(series: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    """Aggregate judgement outcomes across every parsed field.

    Semantics: a parsed value outside its configured min/max is a **FAIL
    judgement of that test step** — a test result, *not* a system alarm and
    *not* a device alarm. ``unknown`` means an empty frame (no data / timeout)
    where judgement was skipped.
    """
    total = ok = fail = unknown = error = 0
    by_field: Dict[str, Dict[str, Any]] = {}
    failures: List[Dict[str, Any]] = []

    for field, points in series.items():
        counts = {"total": 0, "ok": 0, "fail": 0, "unknown": 0, "error": 0}
        last_value = None
        last_num = None
        last_status = None
        for pt in points:
            st = pt.get("status") or ("ok" if pt.get("ok") else "fail")
            counts["total"] += 1
            counts[st if st in counts else "error"] += 1
            total += 1
            if st == "ok":
                ok += 1
            elif st == "fail":
                fail += 1
                failures.append({
                    "field": field,
                    "value": pt.get("value"),
                    "num": pt.get("num"),
                    "detail": pt.get("detail"),
                    "execution_id": pt.get("execution_id"),
                    "step_index": pt.get("step_index"),
                    "step_label": pt.get("step_label"),
                    "completed_at": pt.get("completed_at"),
                })
            elif st == "unknown":
                unknown += 1
            else:
                error += 1
            last_value = pt.get("value")
            last_num = pt.get("num")
            last_status = st
        counts["last_value"] = last_value
        counts["last_num"] = last_num
        counts["last_status"] = last_status
        counts["pass_rate"] = (
            round(counts["ok"] / counts["total"] * 100, 1) if counts["total"] else None
        )
        by_field[field] = counts

    # most recent failures first — that is what an operator wants to see
    failures.sort(key=lambda f: (f.get("completed_at") or ""), reverse=True)

    return {
        "total": total,
        "ok": ok,
        "fail": fail,
        "unknown": unknown,
        "error": error,
        "pass_rate": round(ok / total * 100, 1) if total else None,
        "by_field": by_field,
        "failures": failures[:200],
        "failure_fields": sorted({f["field"] for f in failures}),
    }
