"""Plugin management API routes.

GET    /api/plugins/               - List installed plugins
GET    /api/plugins/discovered     - List discoverable plugins
POST   /api/plugins/install        - Install plugin
GET    /api/plugins/{id}           - Get plugin detail
POST   /api/plugins/{id}/enable    - Enable plugin
POST   /api/plugins/{id}/disable   - Disable plugin
DELETE /api/plugins/{id}           - Uninstall plugin
"""
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.schemas import PluginInstallRequest, PluginUpdateRequest
from app.services.plugin_service import plugin_service

router = APIRouter(prefix="/api/plugins", tags=["Plugins"])


def _plugin_to_dict(p) -> dict:
    config = None
    if p.config:
        try:
            config = json.loads(p.config) if isinstance(p.config, str) else p.config
        except (json.JSONDecodeError, TypeError):
            config = p.config

    config_schema = None
    if p.config_schema:
        try:
            config_schema = json.loads(p.config_schema) if isinstance(p.config_schema, str) else p.config_schema
        except (json.JSONDecodeError, TypeError):
            config_schema = p.config_schema

    return {
        "id": p.id, "name": p.name, "version": p.version,
        "description": p.description, "author": p.author,
        "protocol_type": p.protocol_type, "status": p.status,
        "file_path": p.file_path, "module_name": p.module_name,
        "class_name": p.class_name, "config_schema": config_schema,
        "config": config, "entry_point": p.entry_point,
        "error_message": p.error_message,
        "installed_at": p.installed_at.isoformat() if p.installed_at else None,
        "enabled_at": p.enabled_at.isoformat() if p.enabled_at else None,
        "disabled_at": p.disabled_at.isoformat() if p.disabled_at else None,
    }


@router.get("/")
async def list_plugins(db: AsyncSession = Depends(get_db)):
    plugins = await plugin_service.list_plugins(db)
    return {
        "code": 0, "message": "success",
        "data": [_plugin_to_dict(p) for p in plugins],
    }


@router.get("/discovered")
async def list_discovered_plugins():
    plugins = await plugin_service.list_discovered_plugins()
    return {"code": 0, "message": "success", "data": plugins}


@router.get("/{plugin_id}")
async def get_plugin(plugin_id: str, db: AsyncSession = Depends(get_db)):
    plugin = await plugin_service.get_plugin(db, plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail={
            "code": 40008, "message": "Plugin not found",
            "detail": f"No plugin with id={plugin_id}",
        })
    return {"code": 0, "message": "success", "data": _plugin_to_dict(plugin)}


@router.post("/install")
async def install_plugin(data: PluginInstallRequest, db: AsyncSession = Depends(get_db)):
    try:
        plugin = await plugin_service.install_plugin(db, data.model_dump())
        return {"code": 0, "message": "success", "data": _plugin_to_dict(plugin)}
    except Exception as e:
        raise HTTPException(status_code=400, detail={
            "code": 40009, "message": "Plugin installation failed", "detail": str(e),
        })


@router.post("/{plugin_id}/enable")
async def enable_plugin(plugin_id: str, db: AsyncSession = Depends(get_db)):
    try:
        plugin = await plugin_service.enable_plugin(db, plugin_id)
        return {"code": 0, "message": "success", "data": _plugin_to_dict(plugin)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail={
            "code": 40008, "message": "Plugin not found", "detail": str(e),
        })
    except Exception as e:
        raise HTTPException(status_code=400, detail={
            "code": 40009, "message": "Plugin enable failed", "detail": str(e),
        })


@router.post("/{plugin_id}/disable")
async def disable_plugin(plugin_id: str, db: AsyncSession = Depends(get_db)):
    try:
        plugin = await plugin_service.disable_plugin(db, plugin_id)
        return {"code": 0, "message": "success", "data": _plugin_to_dict(plugin)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail={
            "code": 40008, "message": "Plugin not found", "detail": str(e),
        })


@router.delete("/{plugin_id}")
async def uninstall_plugin(plugin_id: str, db: AsyncSession = Depends(get_db)):
    success = await plugin_service.uninstall_plugin(db, plugin_id)
    if not success:
        raise HTTPException(status_code=404, detail={
            "code": 40008, "message": "Plugin not found",
        })
    return {"code": 0, "message": "Plugin uninstalled", "data": None}
