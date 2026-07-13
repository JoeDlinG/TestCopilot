"""Test report API routes.

POST   /api/reports/generate       - Generate report
GET    /api/reports/               - List reports
GET    /api/reports/{id}           - Get report detail
GET    /api/reports/{id}/download  - Download report file
POST   /api/reports/templates      - Create template
GET    /api/reports/templates      - List templates
PUT    /api/reports/templates/{id} - Update template
DELETE /api/reports/templates/{id} - Delete template
"""
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.schemas import (
    ReportGenerateRequest,
    ReportTemplateCreate, ReportTemplateUpdate,
)
from app.services.report_service import report_service

router = APIRouter(prefix="/api/reports", tags=["Reports"])


def _template_to_dict(t) -> dict:
    fields = None
    if t.fields:
        try:
            fields = json.loads(t.fields) if isinstance(t.fields, str) else t.fields
        except (json.JSONDecodeError, TypeError):
            fields = t.fields
    return {
        "id": t.id, "name": t.name, "description": t.description,
        "fields": fields, "template_content": t.template_content,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


def _report_to_dict(r) -> dict:
    fields = None
    if r.fields:
        try:
            fields = json.loads(r.fields) if isinstance(r.fields, str) else r.fields
        except (json.JSONDecodeError, TypeError):
            fields = r.fields
    return {
        "id": r.id, "title": r.title, "execution_id": r.execution_id,
        "template_id": r.template_id, "format": r.format,
        "status": r.status, "file_path": r.file_path,
        "file_size": r.file_size, "fields": fields,
        "error_message": r.error_message,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "generated_at": r.generated_at.isoformat() if r.generated_at else None,
    }


# ============ Report Generation ============

@router.post("/generate")
async def generate_report(data: ReportGenerateRequest, db: AsyncSession = Depends(get_db)):
    try:
        report = await report_service.generate_report(
            db, data.title, data.execution_id,
            data.template_id, data.fields, data.format,
        )
        return {"code": 0, "message": "success", "data": _report_to_dict(report)}
    except Exception as e:
        raise HTTPException(status_code=500, detail={
            "code": 40011, "message": "Report generation failed", "detail": str(e),
        })


@router.get("/")
async def list_reports(db: AsyncSession = Depends(get_db)):
    reports = await report_service.list_reports(db)
    return {
        "code": 0, "message": "success",
        "data": [_report_to_dict(r) for r in reports],
    }


@router.get("/{report_id}")
async def get_report(report_id: str, db: AsyncSession = Depends(get_db)):
    report = await report_service.get_report(db, report_id)
    if not report:
        raise HTTPException(status_code=404, detail={
            "code": 40010, "message": "Report not found",
        })
    return {"code": 0, "message": "success", "data": _report_to_dict(report)}


@router.get("/{report_id}/download")
async def download_report(report_id: str, db: AsyncSession = Depends(get_db)):
    report = await report_service.get_report(db, report_id)
    if not report or not report.file_path:
        raise HTTPException(status_code=404, detail={
            "code": 40010, "message": "Report file not found",
        })
    import os
    if not os.path.exists(report.file_path):
        raise HTTPException(status_code=404, detail={
            "code": 40010, "message": "Report file not found on disk",
        })
    return FileResponse(report.file_path)


# ============ Templates ============

@router.post("/templates")
async def create_template(data: ReportTemplateCreate, db: AsyncSession = Depends(get_db)):
    template = await report_service.create_template(db, data.model_dump())
    return {"code": 0, "message": "success", "data": _template_to_dict(template)}


@router.get("/templates")
async def list_templates(db: AsyncSession = Depends(get_db)):
    templates = await report_service.list_templates(db)
    return {
        "code": 0, "message": "success",
        "data": [_template_to_dict(t) for t in templates],
    }


@router.put("/templates/{template_id}")
async def update_template(
    template_id: str, data: ReportTemplateUpdate, db: AsyncSession = Depends(get_db),
):
    template = await report_service.update_template(db, template_id, data.model_dump(exclude_unset=True))
    if not template:
        raise HTTPException(status_code=404, detail={
            "code": 40010, "message": "Template not found",
        })
    return {"code": 0, "message": "success", "data": _template_to_dict(template)}


@router.delete("/templates/{template_id}")
async def delete_template(template_id: str, db: AsyncSession = Depends(get_db)):
    success = await report_service.delete_template(db, template_id)
    if not success:
        raise HTTPException(status_code=404, detail={
            "code": 40010, "message": "Template not found",
        })
    return {"code": 0, "message": "Template deleted", "data": None}
