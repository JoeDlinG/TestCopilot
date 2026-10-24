"""Help centre API.

The in-app 帮助 menu needs the same manuals that live in ``docs/``. Rather than
copying them into the frontend bundle (two copies to keep in sync, and the whole
manual would ship inside the JS), the backend serves them as markdown and the UI
renders them with ``react-markdown``.

Only an explicit whitelist is exposed — ``docs/`` also holds internal design
documents (PRD, architecture, DB design) that are not user help.

GET /api/help/docs          - list the available manuals
GET /api/help/docs/{id}     - one manual as markdown
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException

from app.core.config import settings

router = APIRouter(prefix="/api/help", tags=["help"])

# (id, title, file name, one-line description)
_HELP_DOCS: List[Tuple[str, str, str, str]] = [
    (
        "user-manual",
        "使用手册",
        "USER_MANUAL.md",
        "界面总览、设备接入、用例编写、执行与报告",
    ),
    (
        "peakcan",
        "PeakCAN 插件手册",
        "PEAKCAN_PLUGIN.md",
        "CAN 通道配置、报文收发与总线监控",
    ),
    (
        "rigol",
        "RIGOL 示波器插件手册",
        "RIGOL_OSCILLOSCOPE_PLUGIN.md",
        "SCPI 波形采集与测量项",
    ),
]


def _candidate_dirs() -> List[str]:
    """Where ``docs/`` may live, most specific first.

    * packaged build — PyInstaller puts it under ``sys._MEIPASS`` (``HELP_DIR``);
    * repo checkout — the backend is usually started from ``backend/``, so the
      manuals sit one level up;
    * anything else — walk up from this file.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    return [
        settings.HELP_DIR,
        "./docs",
        "../docs",
        os.path.abspath(os.path.join(here, "..", "..", "..", "docs")),
    ]


def _help_dir() -> Optional[str]:
    for d in _candidate_dirs():
        if d and os.path.isdir(d):
            return d
    return None


def _meta(doc_id: str) -> Optional[Tuple[str, str, str, str]]:
    for entry in _HELP_DOCS:
        if entry[0] == doc_id:
            return entry
    return None


def _updated_at(path: str) -> str:
    return datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc).isoformat()


@router.get("/docs")
async def list_docs() -> Dict:
    root = _help_dir()
    items = []
    for doc_id, title, file_name, desc in _HELP_DOCS:
        path = os.path.join(root, file_name) if root else ""
        available = bool(root) and os.path.isfile(path)
        items.append(
            {
                "id": doc_id,
                "title": title,
                "file_name": file_name,
                "description": desc,
                "available": available,
                "updated_at": _updated_at(path) if available else None,
                "size": os.path.getsize(path) if available else 0,
            }
        )
    return {"code": 0, "message": "success", "data": {"items": items, "dir": root}}


@router.get("/docs/{doc_id}")
async def get_doc(doc_id: str) -> Dict:
    meta = _meta(doc_id)
    if meta is None:
        raise HTTPException(
            status_code=404,
            detail={"code": 40401, "message": "未知的帮助文档", "detail": doc_id},
        )
    root = _help_dir()
    if root is None:
        raise HTTPException(
            status_code=404,
            detail={"code": 40402, "message": "帮助文档目录不存在"},
        )
    path = os.path.join(root, meta[2])
    if not os.path.isfile(path):
        raise HTTPException(
            status_code=404,
            detail={"code": 40403, "message": "帮助文档缺失", "detail": meta[2]},
        )
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    return {
        "code": 0,
        "message": "success",
        "data": {
            "id": meta[0],
            "title": meta[1],
            "description": meta[3],
            "markdown": text,
            "updated_at": _updated_at(path),
            "size": os.path.getsize(path),
        },
    }
