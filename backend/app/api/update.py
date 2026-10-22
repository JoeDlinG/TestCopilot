"""Remote update API (issue #25).

The client never supplies a URL or a file path: it asks the server to check,
then to download **the update the server already selected**, then to apply the
**token the server issued for that download**. That keeps an attacker who can
talk to the API from aiming the installer at their own binary.

GET  /api/update/check     - current vs latest (never raises on a bad feed)
GET  /api/update/status    - download progress
POST /api/update/download  - start downloading the selected asset
POST /api/update/apply     - install {token} (only after an explicit user OK)
POST /api/update/ignore    - stop prompting for {version}
GET  /api/update/settings  - auto_check / auto_download / feed
PUT  /api/update/settings  - update the same
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.services import update_service as svc

router = APIRouter(prefix="/api/update", tags=["update"])


@router.get("/check")
async def check_update(force: bool = False, db: AsyncSession = Depends(get_db)):
    """``force`` is accepted for symmetry with the UI's 立即检查 button; the
    result is cheap enough to recompute every time, so there is no cache to
    bypass."""
    return {"code": 0, "message": "success", "data": await svc.check_for_update(db)}


@router.get("/status")
async def download_status():
    return {"code": 0, "message": "success", "data": svc.download_state()}


@router.post("/download")
async def start_download(db: AsyncSession = Depends(get_db)):
    info = await svc.check_for_update(db)
    if not info.get("available"):
        raise HTTPException(
            status_code=400,
            detail={"code": 40031, "message": "没有可下载的更新", "detail": info.get("reason")},
        )
    asset = info.get("asset")
    if not asset:
        raise HTTPException(
            status_code=400,
            detail={"code": 40032, "message": "该安装包不适合当前平台"},
        )
    if not asset.get("sha256"):
        # Refusing here is the point: an unverifiable binary never gets run.
        raise HTTPException(
            status_code=400,
            detail={
                "code": 40033,
                "message": "更新包缺少 SHA256 校验值，已拒绝下载",
                "detail": asset.get("name"),
            },
        )
    started = svc.start_download(asset, info.get("latest") or "")
    return {
        "code": 0,
        "message": "success",
        "data": {"started": started, "state": svc.download_state()},
    }


@router.post("/apply")
async def apply_update(payload: dict = Body(...)):
    state = svc.download_ready(payload.get("token"))
    if state is None:
        raise HTTPException(
            status_code=400,
            detail={"code": 40034, "message": "下载未完成或校验未通过，无法安装"},
        )
    try:
        svc.apply_update(state)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail={"code": 50031, "message": str(exc)})
    return {
        "code": 0,
        "message": "success",
        "data": {"applying": True, "version": state.get("version")},
    }


@router.post("/ignore")
async def ignore_version(payload: dict = Body(...), db: AsyncSession = Depends(get_db)):
    version = str(payload.get("version") or "").strip()
    await svc.set_setting(db, svc.KEY_IGNORED_VERSION, version,
                          "更新提示中已忽略的版本")
    return {"code": 0, "message": "success", "data": {"ignored_version": version}}


@router.get("/settings")
async def get_settings(db: AsyncSession = Depends(get_db)):
    data = await svc.load_settings(db)
    data["current_version"] = settings.APP_VERSION
    return {"code": 0, "message": "success", "data": data}


@router.put("/settings")
async def put_settings(payload: dict = Body(...), db: AsyncSession = Depends(get_db)):
    if "auto_check" in payload:
        await svc.set_setting(db, svc.KEY_AUTO_CHECK, "1" if payload["auto_check"] else "0",
                              "启动时自动检查更新")
    if "auto_download" in payload:
        await svc.set_setting(db, svc.KEY_AUTO_DOWNLOAD,
                              "1" if payload["auto_download"] else "0",
                              "发现更新后自动下载（安装仍需确认）")
    if "feed_url" in payload:
        await svc.set_setting(db, svc.KEY_FEED_URL, str(payload["feed_url"] or "").strip(),
                              "更新源（version.json 或 gh:owner/repo）")
    return {"code": 0, "message": "success", "data": await svc.load_settings(db)}
