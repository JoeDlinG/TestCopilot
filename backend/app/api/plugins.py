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
from app.schemas.schemas import (
    PluginInstallRequest, PluginUpdateRequest, DeviceCreate,
    PluginSkillSave, PluginSkillImport,
)
from app.services.plugin_service import plugin_service
from app.services.device_service import device_service

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


@router.get("/skills")
async def list_plugin_skills():
    """List available plugin skills (manual + AI test-case generation guide)."""
    skills = plugin_service.list_plugin_skills()
    return {"code": 0, "message": "success", "data": skills}


@router.get("/skills/{protocol}")
async def get_plugin_skill(protocol: str):
    """Get the full skill + manual content for a plugin protocol."""
    content = plugin_service.get_plugin_skill_content(protocol)
    if not content:
        raise HTTPException(status_code=404, detail={
            "code": 40010, "message": "Plugin skill not found",
            "detail": f"No skill for protocol '{protocol}'",
        })
    return {"code": 0, "message": "success", "data": content}


@router.post("/skills")
async def create_plugin_skill(data: PluginSkillSave):
    """Create a new plugin skill (fails when the protocol already exists)."""
    existing = plugin_service.get_plugin_skill_content(data.protocol)
    if existing:
        raise HTTPException(status_code=400, detail={
            "code": 40011, "message": "Skill already exists",
            "detail": f"protocol '{data.protocol}' 已存在，请使用 PUT 修改",
        })
    try:
        saved = plugin_service.save_plugin_skill(
            protocol=data.protocol,
            name=data.name,
            keywords=data.keywords,
            content=data.content,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={
            "code": 40012, "message": "Invalid skill", "detail": str(e),
        })
    return {"code": 0, "message": "success", "data": saved}


@router.put("/skills/{protocol}")
async def update_plugin_skill(protocol: str, data: PluginSkillSave):
    """Update an existing plugin skill (supports renaming via ``rename_from``)."""
    try:
        saved = plugin_service.save_plugin_skill(
            protocol=data.protocol or protocol,
            name=data.name,
            keywords=data.keywords,
            content=data.content,
            rename_from=data.rename_from or protocol,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={
            "code": 40012, "message": "Invalid skill", "detail": str(e),
        })
    return {"code": 0, "message": "success", "data": saved}


@router.post("/skills/import")
async def import_plugin_skill(data: PluginSkillImport):
    """Import a skill markdown file (frontmatter optional)."""
    try:
        saved = plugin_service.import_plugin_skill(
            data.filename or "", data.content or ""
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={
            "code": 40012, "message": "Invalid skill file", "detail": str(e),
        })
    return {"code": 0, "message": "success", "data": saved}


@router.delete("/skills/{protocol}")
async def delete_plugin_skill(protocol: str):
    if not plugin_service.delete_plugin_skill(protocol):
        raise HTTPException(status_code=404, detail={
            "code": 40010, "message": "Plugin skill not found",
            "detail": f"No skill for protocol '{protocol}'",
        })
    return {"code": 0, "message": "Skill deleted", "data": None}


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


@router.post("/{plugin_id}/add-device")
async def add_device_from_plugin(plugin_id: str, db: AsyncSession = Depends(get_db)):
    """Create a Device from the plugin's ``get_device_template()``."""
    plugin = await plugin_service.get_plugin(db, plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail={
            "code": 40008, "message": "Plugin not found",
            "detail": f"No plugin with id={plugin_id}",
        })

    try:
        plugin_class = await plugin_service.load_plugin_class(plugin)
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail={
            "code": 40009, "message": "Plugin file not found", "detail": str(e),
        })
    except Exception as e:
        raise HTTPException(status_code=400, detail={
            "code": 40009, "message": "Plugin load failed", "detail": str(e),
        })

    template = plugin_class().get_device_template() or {}
    if not template:
        raise HTTPException(status_code=400, detail={
            "code": 40009, "message": "Plugin provides no device template",
        })

    try:
        device = await device_service.create_device(db, DeviceCreate(**template))
    except Exception as e:
        raise HTTPException(status_code=400, detail={
            "code": 40009, "message": "Failed to create device", "detail": str(e),
        })

    return {
        "code": 0, "message": "Device created from plugin",
        "data": device_service._model_to_response(device),
    }
