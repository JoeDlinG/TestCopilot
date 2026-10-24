"""Feedback centre API (issue #26).

POST /api/feedback          - submit a crash / idea / issue
GET  /api/feedback          - list stored reports (management view)
GET  /api/feedback/settings - is automatic crash reporting on?
PUT  /api/feedback/settings - turn it off/on

Automatic crash capture is opt-out and **never** carries credentials, so the
only things the server trusts from the client are the text fields, which are
sanitised before they are stored or forwarded.
"""
from __future__ import annotations

import time
from collections import deque
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.services import feedback_service as svc

router = APIRouter(prefix="/api/feedback", tags=["feedback"])

# Crude in-memory rate limit: a crashed render loop can otherwise fire hundreds
# of reports per second. Manual feedback is capped too, to stop spamming GitHub.
_WINDOW = 60.0
_MAX_PER_WINDOW = 20
_hits: deque = deque()


def _rate_limited() -> bool:
    now = time.time()
    while _hits and now - _hits[0] > _WINDOW:
        _hits.popleft()
    if len(_hits) >= _MAX_PER_WINDOW:
        return True
    _hits.append(now)
    return False


class FeedbackIn(BaseModel):
    kind: str = "issue"
    title: str = ""
    body: str = ""
    stack: str = ""
    log_tail: str = ""
    route: str = ""
    consent: bool = True
    attach_logs: bool = False
    system: Optional[Dict[str, Any]] = None


@router.post("")
async def submit_feedback(payload: FeedbackIn = Body(...), db: AsyncSession = Depends(get_db)):
    kind = (payload.kind or "").strip().lower()
    if kind == "crash":
        if not await svc.auto_report_enabled(db):
            return {
                "code": 0, "message": "success",
                "data": {"suppressed": True, "reason": "auto_report_disabled"},
            }
        if not payload.consent:
            return {"code": 0, "message": "success",
                    "data": {"suppressed": True, "reason": "no_consent"}}

    if _rate_limited():
        raise HTTPException(
            status_code=429,
            detail={"code": 42901, "message": "提交过于频繁，请稍后再试"},
        )

    # Fall back to the first stack line for crashes, but guard the index — an
    # empty title AND an empty stack used to raise IndexError here (caught by
    # the catch-all handler as a 500 instead of a clean 400).
    stack_lines = (payload.stack or "").splitlines()
    title = (payload.title or "").strip() or (stack_lines[0][:160] if stack_lines else "")
    if not title.strip():
        raise HTTPException(status_code=400, detail={"code": 40041, "message": "标题不能为空"})

    if kind == "crash":
        report = await svc.create_report(
            db, kind="crash", title=f"[crash] {title[:150]}",
            body=payload.body, stack=payload.stack, log_tail=payload.log_tail,
            route=payload.route, consent=True, attach_logs=True,
            system=payload.system or {},
        )
    else:
        if not (payload.title or "").strip() or not (payload.body or "").strip():
            raise HTTPException(
                status_code=400, detail={"code": 40042, "message": "请填写标题与描述"}
            )
        report = await svc.create_report(
            db, kind=kind, title=title, body=payload.body, route=payload.route,
            consent=payload.consent, attach_logs=payload.attach_logs,
            system=payload.system or {},
        )

    status = await svc.forward_report(db, report)
    return {
        "code": 0, "message": "success",
        "data": {
            "id": report.id,
            "status": status,
            "occurrences": report.occurrences,
            "github_issue_number": report.github_issue_number,
            "token_configured": bool(settings.GITHUB_TOKEN),
        },
    }


@router.get("")
async def list_feedback(limit: int = 50, db: AsyncSession = Depends(get_db)):
    return {
        "code": 0, "message": "success",
        "data": {
            "items": await svc.list_reports(db, limit=min(limit, 200)),
            "token_configured": bool(settings.GITHUB_TOKEN),
        },
    }


@router.get("/settings")
async def get_feedback_settings(db: AsyncSession = Depends(get_db)):
    return {
        "code": 0, "message": "success",
        "data": {
            "auto_crash_report": await svc.auto_report_enabled(db),
            "token_configured": bool(settings.GITHUB_TOKEN),
            "repo": settings.GITHUB_REPO,
        },
    }


@router.put("/settings")
async def put_feedback_settings(payload: dict = Body(...), db: AsyncSession = Depends(get_db)):
    if "auto_crash_report" in payload:
        await svc.set_auto_report(db, bool(payload["auto_crash_report"]))
    return {
        "code": 0, "message": "success",
        "data": {"auto_crash_report": await svc.auto_report_enabled(db)},
    }
