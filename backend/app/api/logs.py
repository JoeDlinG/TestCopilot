"""Communication logs and data export API routes.

GET    /api/logs/              - Query communication logs (with filters + pagination)
GET    /api/logs/{id}          - Get log detail
GET    /api/logs/export/csv    - Export logs as CSV
"""
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.timeutils import parse_iso_utc
from app.services.log_service import log_service

router = APIRouter(prefix="/api/logs", tags=["Logs"])


def _log_to_dict(log) -> dict:
    """Convert CommunicationLog to dict."""
    metadata = None
    if log.extra_meta:
        try:
            metadata = json.loads(log.extra_meta) if isinstance(log.extra_meta, str) else log.extra_meta
        except (json.JSONDecodeError, TypeError):
            metadata = log.extra_meta

    return {
        "id": log.id,
        "timestamp": log.timestamp.isoformat() if log.timestamp else None,
        "device_id": log.device_id,
        "execution_id": log.execution_id,
        "step_result_id": log.step_result_id,
        "direction": log.direction,
        "protocol": log.protocol,
        "raw_data": log.raw_data,
        "raw_data_hex": log.raw_data_hex,
        "raw_data_size": log.raw_data_size,
        "status": log.status,
        "error_message": log.error_message,
        "duration_ms": log.duration_ms,
        "metadata": metadata,
    }


@router.get("/")
async def list_logs(
    device_id: Optional[str] = Query(None),
    execution_id: Optional[str] = Query(None),
    protocol: Optional[str] = Query(None),
    direction: Optional[str] = Query(None),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    st = parse_iso_utc(start_time) if start_time else None
    et = parse_iso_utc(end_time) if end_time else None

    logs, total = await log_service.query_logs(
        db, device_id=device_id, execution_id=execution_id,
        protocol=protocol, direction=direction,
        start_time=st, end_time=et,
        page=page, page_size=page_size,
    )

    return {
        "code": 0, "message": "success",
        "data": {
            "items": [_log_to_dict(l) for l in logs],
            "total": total, "page": page, "page_size": page_size,
        },
    }


@router.get("/{log_id}")
async def get_log(log_id: str, db: AsyncSession = Depends(get_db)):
    log = await log_service.get_log(db, log_id)
    if not log:
        raise HTTPException(status_code=404, detail={
            "code": 40010, "message": "Log not found",
            "detail": f"No log with id={log_id}",
        })
    return {"code": 0, "message": "success", "data": _log_to_dict(log)}


@router.get("/export/csv")
async def export_logs_csv(
    device_id: Optional[str] = Query(None),
    execution_id: Optional[str] = Query(None),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    st = parse_iso_utc(start_time) if start_time else None
    et = parse_iso_utc(end_time) if end_time else None

    buffer, filename = await log_service.export_csv(
        db, device_id=device_id, execution_id=execution_id,
        start_time=st, end_time=et,
    )

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# --------------------------------------------------------------------- #
# Program / execution log files (logs/program, logs/executions/<id>)
# --------------------------------------------------------------------- #
@router.get("/program/files")
async def list_program_log_files():
    """List the global program execution log files (10 MB rotation)."""
    from app.services.program_logger import list_program_logs

    return {"code": 0, "message": "success", "data": list_program_logs()}


@router.get("/executions/{execution_id}/files")
async def list_execution_log_files(execution_id: str):
    """List the per-run log files (program + communication) for one execution."""
    from app.services.program_logger import list_execution_logs

    return {
        "code": 0,
        "message": "success",
        "data": {"execution_id": execution_id, "files": list_execution_logs(execution_id)},
    }


@router.get("/executions/{execution_id}/file/{name}")
async def read_execution_log_file(
    execution_id: str, name: str, tail_lines: int = Query(1000),
):
    """Read (the tail of) one per-run log file."""
    import os

    from app.services.program_logger import EXECUTIONS_DIR

    # Path-traversal guard: only a bare file name inside the run folder.
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=400, detail="非法的文件名")
    path = os.path.join(EXECUTIONS_DIR, execution_id, name)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail=f"日志文件不存在: {name}")
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    content = "".join(lines[-max(1, tail_lines):])
    return {
        "code": 0,
        "message": "success",
        "data": {
            "execution_id": execution_id,
            "name": name,
            "size": os.path.getsize(path),
            "content": content,
        },
    }
