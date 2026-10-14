"""Project-file API — bundle the whole workspace configuration into one file.

GET    /api/projects                  list saved project files
POST   /api/projects/export           build a bundle from the current database
POST   /api/projects/import           apply a bundle to the database
POST   /api/projects/save             另存为 — export the database into a named file
GET    /api/projects/{name}           read a stored project file
PUT    /api/projects/{name}           rename a stored project file
DELETE /api/projects/{name}           delete a stored project file
POST   /api/projects/{name}/sync      overwrite a stored file with the current database
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services import project_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["Projects"])


# ---------------------------------------------------------------------- #
# Request models
# ---------------------------------------------------------------------- #

class ExportRequest(BaseModel):
    sections: Optional[List[str]] = None
    project_name: Optional[str] = None


class SaveRequest(BaseModel):
    name: str = Field(..., min_length=1, description="工程文件名（不含 Project_ 前缀）")
    sections: Optional[List[str]] = None


class ImportRequest(BaseModel):
    bundle: Dict[str, Any]
    sections: Optional[List[str]] = None
    mode: str = Field("merge", pattern="^(merge|replace)$")


class RenameRequest(BaseModel):
    new_name: str = Field(..., min_length=1)


class NewProjectRequest(BaseModel):
    """Start a brand new project: wipe the workspace, keep AI model settings."""

    sections: Optional[List[str]] = None
    keep_models: bool = True
    confirm: bool = Field(False, description="必须显式确认，避免误清空")


# ---------------------------------------------------------------------- #
# Routes
# ---------------------------------------------------------------------- #

@router.get("")
async def list_projects():
    return {"code": 0, "message": "success", "data": project_service.list_projects()}


@router.post("/export")
async def export_current(
    data: ExportRequest, db: AsyncSession = Depends(get_db),
):
    """Build a bundle from the live database (does not touch disk)."""
    try:
        bundle = await project_service.export_bundle(
            db, data.sections, data.project_name or ""
        )
    except Exception as e:
        logger.exception("project export failed")
        raise HTTPException(status_code=500, detail={
            "code": 50001, "message": "导出工程失败", "detail": str(e),
        })
    return {"code": 0, "message": "success", "data": bundle}


@router.post("/save")
async def save_project(
    data: SaveRequest, db: AsyncSession = Depends(get_db),
):
    """另存为: export the database and store it under ``Project_<name>.json``."""
    try:
        bundle = await project_service.export_bundle(
            db, data.sections, data.name
        )
        saved = project_service.save_project(data.name, bundle)
    except Exception as e:
        logger.exception("project save failed")
        raise HTTPException(status_code=500, detail={
            "code": 50001, "message": "保存工程失败", "detail": str(e),
        })
    return {"code": 0, "message": "success", "data": saved}


@router.post("/import")
async def import_project(
    data: ImportRequest, db: AsyncSession = Depends(get_db),
):
    """Apply an uploaded bundle to the database."""
    try:
        result = await project_service.import_bundle(
            db, data.bundle, data.sections, data.mode
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={
            "code": 40014, "message": "导入工程失败", "detail": str(e),
        })
    except Exception as e:
        logger.exception("project import failed")
        await db.rollback()
        raise HTTPException(status_code=500, detail={
            "code": 50002, "message": "导入工程失败", "detail": str(e),
        })
    return {"code": 0, "message": "success", "data": result}


@router.post("/new")
async def new_project(
    data: NewProjectRequest, db: AsyncSession = Depends(get_db),
):
    """清空工作区以开始一个新项目（默认保留 AI 模型配置）。"""
    if not data.confirm:
        raise HTTPException(status_code=400, detail={
            "code": 40017,
            "message": "新建项目工程会清空现有配置，请确认后重试",
        })
    try:
        result = await project_service.reset_workspace(
            db, data.sections, data.keep_models
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={
            "code": 40014, "message": "新建项目失败", "detail": str(e),
        })
    except Exception as e:
        logger.exception("new project failed")
        await db.rollback()
        raise HTTPException(status_code=500, detail={
            "code": 50008, "message": "新建项目失败", "detail": str(e),
        })
    return {"code": 0, "message": "success", "data": result}


@router.get("/{name}")
async def get_project(name: str):
    try:
        bundle = project_service.load_project(name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail={
            "code": 40004, "message": "工程文件不存在",
            "detail": f"No project named '{name}'",
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail={
            "code": 50003, "message": "读取工程文件失败", "detail": str(e),
        })
    return {"code": 0, "message": "success", "data": bundle}


@router.put("/{name}")
async def rename_project(name: str, data: RenameRequest):
    try:
        result = project_service.rename_project(name, data.new_name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail={
            "code": 40004, "message": "工程文件不存在",
            "detail": f"No project named '{name}'",
        })
    except FileExistsError:
        raise HTTPException(status_code=409, detail={
            "code": 40010, "message": "工程名称已存在",
            "detail": f"'{data.new_name}' already exists",
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail={
            "code": 50004, "message": "重命名失败", "detail": str(e),
        })
    return {"code": 0, "message": "success", "data": result}


@router.delete("/{name}")
async def delete_project(name: str):
    if not project_service.delete_project(name):
        raise HTTPException(status_code=404, detail={
            "code": 40004, "message": "工程文件不存在",
            "detail": f"No project named '{name}'",
        })
    return {"code": 0, "message": "deleted", "data": None}


@router.post("/{name}/sync")
async def sync_project(
    name: str, data: ExportRequest, db: AsyncSession = Depends(get_db),
):
    """Overwrite a stored project file with the current database state."""
    try:
        project_service.load_project(name)  # 404 when it does not exist
        bundle = await project_service.export_bundle(
            db, data.sections, data.project_name or name
        )
        saved = project_service.save_project(name, bundle)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail={
            "code": 40004, "message": "工程文件不存在",
            "detail": f"No project named '{name}'",
        })
    except Exception as e:
        logger.exception("project sync failed")
        raise HTTPException(status_code=500, detail={
            "code": 50005, "message": "同步工程失败", "detail": str(e),
        })
    return {"code": 0, "message": "success", "data": saved}
