"""Test execution API routes.

POST   /api/executions/run              - Start execution
POST   /api/executions/{id}/stop        - Stop execution
GET    /api/executions/{id}             - Get execution detail (with step results)
GET    /api/executions/                 - List executions
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.schemas import ExecutionStartRequest
from app.services.execution_service import execution_engine

router = APIRouter(prefix="/api/executions", tags=["Executions"])


@router.post("/run")
async def start_execution(data: ExecutionStartRequest, db: AsyncSession = Depends(get_db)):
    try:
        execution = await execution_engine.start_execution(
            db, data.test_case_id, data.options,
        )
        return {
            "code": 0, "message": "success",
            "data": {
                "id": execution.id, "testcase_id": execution.testcase_id,
                "status": execution.status, "result": execution.result,
                "options": execution.options, "total_steps": execution.total_steps,
                "passed_steps": execution.passed_steps,
                "failed_steps": execution.failed_steps,
                "error_message": execution.error_message,
                "started_at": execution.started_at.isoformat() if execution.started_at else None,
                "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
                "duration_ms": execution.duration_ms,
                "created_at": execution.created_at.isoformat() if execution.created_at else None,
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail={
            "code": 40004, "message": "Test case not found", "detail": str(e),
        })


@router.get("/")
async def list_executions(
    test_case_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    executions, total = await execution_engine.list_executions(
        db, testcase_id=test_case_id, status=status, page=page, page_size=page_size,
    )

    items = []
    for e in executions:
        items.append({
            "id": e.id, "testcase_id": e.testcase_id,
            "status": e.status, "result": e.result,
            "options": e.options, "total_steps": e.total_steps,
            "passed_steps": e.passed_steps, "failed_steps": e.failed_steps,
            "error_message": e.error_message,
            "started_at": e.started_at.isoformat() if e.started_at else None,
            "completed_at": e.completed_at.isoformat() if e.completed_at else None,
            "duration_ms": e.duration_ms,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        })

    return {
        "code": 0, "message": "success",
        "data": {"items": items, "total": total, "page": page, "page_size": page_size},
    }


@router.get("/{execution_id}")
async def get_execution(execution_id: str, db: AsyncSession = Depends(get_db)):
    execution = await execution_engine.get_execution(db, execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail={
            "code": 40005, "message": "Execution not found",
            "detail": f"No execution with id={execution_id}",
        })

    # Get step results
    steps = await execution_engine.get_step_results(db, execution_id)
    step_items = []
    for s in steps:
        step_items.append({
            "id": s.id, "execution_id": s.execution_id,
            "step_index": s.step_index, "node_id": s.node_id,
            "node_type": s.node_type, "label": s.label,
            "status": s.status, "command": s.command,
            "expected": s.expected, "actual": s.actual,
            "error_message": s.error_message,
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "completed_at": s.completed_at.isoformat() if s.completed_at else None,
            "duration_ms": s.duration_ms,
        })

    return {
        "code": 0, "message": "success",
        "data": {
            "id": execution.id, "testcase_id": execution.testcase_id,
            "status": execution.status, "result": execution.result,
            "options": execution.options, "total_steps": execution.total_steps,
            "passed_steps": execution.passed_steps,
            "failed_steps": execution.failed_steps,
            "error_message": execution.error_message,
            "started_at": execution.started_at.isoformat() if execution.started_at else None,
            "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
            "duration_ms": execution.duration_ms,
            "created_at": execution.created_at.isoformat() if execution.created_at else None,
            "step_results": step_items,
        },
    }


@router.post("/{execution_id}/stop")
async def stop_execution(execution_id: str, db: AsyncSession = Depends(get_db)):
    try:
        result = await execution_engine.stop_execution(db, execution_id)
        return {"code": 0, "message": "success", "data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail={
            "code": 40005, "message": "Execution not found", "detail": str(e),
        })
