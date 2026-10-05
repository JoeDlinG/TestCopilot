"""Plugin editor API routes (plugin templates + source file editing).

GET    /api/plugin-editor/templates            - List plugin templates
GET    /api/plugin-editor/templates/{key}      - Template detail + content
GET    /api/plugin-editor/files                - List editable plugin files
POST   /api/plugin-editor/files                - Create a plugin from a template
GET    /api/plugin-editor/files/{module}       - Read a plugin source file
PUT    /api/plugin-editor/files/{module}       - Save a plugin source file
DELETE /api/plugin-editor/files/{module}       - Delete a plugin source file
POST   /api/plugin-editor/validate             - Syntax + plugin-class check
"""
from fastapi import APIRouter, HTTPException

from app.schemas.schemas import (
    PluginFileCreate, PluginFileUpdate, PluginValidateRequest,
)
from app.services.plugin_editor_service import plugin_editor_service

router = APIRouter(prefix="/api/plugin-editor", tags=["PluginEditor"])


def _bad_request(code: int, message: str, detail: str = "") -> HTTPException:
    return HTTPException(status_code=400, detail={
        "code": code, "message": message, "detail": detail,
    })


@router.get("/templates")
async def list_templates():
    return {"code": 0, "message": "success",
            "data": plugin_editor_service.list_templates()}


@router.get("/templates/{key}")
async def get_template(key: str):
    tpl = plugin_editor_service.get_template(key)
    if not tpl:
        raise HTTPException(status_code=404, detail={
            "code": 40020, "message": "Template not found",
            "detail": f"No template with key '{key}'",
        })
    return {"code": 0, "message": "success", "data": tpl}


@router.get("/files")
async def list_files():
    return {"code": 0, "message": "success",
            "data": plugin_editor_service.list_files()}


@router.post("/files")
async def create_file(data: PluginFileCreate):
    try:
        created = plugin_editor_service.create_file(
            plugin_name=data.plugin_name,
            protocol_name=data.protocol_name,
            template_key=data.template_key or "protocol_plugin",
            version=data.version or "1.0.0",
            description=data.description or "",
            author=data.author or "",
            module_name=data.module_name,
            overwrite=bool(data.overwrite),
        )
    except ValueError as e:
        raise _bad_request(40021, "Plugin creation failed", str(e))
    return {"code": 0, "message": "success", "data": created}


@router.get("/files/{module}")
async def read_file(module: str):
    data = plugin_editor_service.read_file(module)
    if not data:
        raise HTTPException(status_code=404, detail={
            "code": 40022, "message": "Plugin file not found",
            "detail": f"No plugin file '{module}.py'",
        })
    return {"code": 0, "message": "success", "data": data}


@router.put("/files/{module}")
async def write_file(module: str, data: PluginFileUpdate):
    try:
        saved = plugin_editor_service.write_file(module, data.content)
    except ValueError as e:
        raise _bad_request(40023, "Invalid plugin file", str(e))
    return {"code": 0, "message": "success", "data": saved}


@router.delete("/files/{module}")
async def delete_file(module: str):
    if not plugin_editor_service.delete_file(module):
        raise HTTPException(status_code=404, detail={
            "code": 40022, "message": "Plugin file not found",
            "detail": f"No plugin file '{module}.py'",
        })
    return {"code": 0, "message": "Plugin file deleted", "data": None}


@router.post("/validate")
async def validate_file(data: PluginValidateRequest):
    try:
        result = plugin_editor_service.validate(data.module_name, data.content)
    except ValueError as e:
        raise _bad_request(40023, "Invalid plugin file", str(e))
    return {"code": 0, "message": "success", "data": result}
