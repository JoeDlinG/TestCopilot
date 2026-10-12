"""Project memory API — ``Project_<name> Memory.md`` files.

GET    /api/memory               list memory files
GET    /api/memory/{name}        read one memory file
POST   /api/memory               write (append / replace) a memory file
DELETE /api/memory/{name}        delete a memory file
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services import memory_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/memory", tags=["Memory"])


class MemoryWriteRequest(BaseModel):
    name: str = Field(..., min_length=1, description="项目名（文件名中的 <name>）")
    content: str = Field("", description="Markdown 内容")
    mode: str = Field("append", pattern="^(append|replace|overwrite)$")
    title: str = Field("", description="Append 模式下小标题的后缀")


@router.get("")
async def list_memories():
    return {"code": 0, "message": "success", "data": memory_service.list_memories()}


@router.post("")
async def write_memory(data: MemoryWriteRequest):
    try:
        result = memory_service.write_memory(
            data.name, data.content, data.mode, data.title
        )
    except Exception as e:
        logger.exception("memory write failed")
        raise HTTPException(status_code=500, detail={
            "code": 50006, "message": "写入记忆文件失败", "detail": str(e),
        })
    return {"code": 0, "message": "success", "data": result}


@router.get("/{name}")
async def read_memory(name: str):
    try:
        return {"code": 0, "message": "success", "data": memory_service.read_memory(name)}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail={
            "code": 40004, "message": "记忆文件不存在",
            "detail": f"No memory for project '{name}'",
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail={
            "code": 50007, "message": "读取记忆文件失败", "detail": str(e),
        })


@router.delete("/{name}")
async def delete_memory(name: str):
    if not memory_service.delete_memory(name):
        raise HTTPException(status_code=404, detail={
            "code": 40004, "message": "记忆文件不存在",
            "detail": f"No memory for project '{name}'",
        })
    return {"code": 0, "message": "deleted", "data": None}
