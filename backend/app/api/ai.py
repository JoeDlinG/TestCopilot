"""AI model configuration, chat, and speech API routes.

GET    /api/ai/models                    - List AI models
POST   /api/ai/models                    - Create model config
GET    /api/ai/models/{id}               - Get model config
PUT    /api/ai/models/{id}               - Update model config
DELETE /api/ai/models/{id}               - Delete model config
POST   /api/ai/models/{id}/activate      - Set as default
POST   /api/ai/models/{id}/test          - Test model connection
POST   /api/ai/chat                      - Chat with AI
POST   /api/ai/generate-testcases        - Generate test cases
POST   /api/ai/query                     - Natural language query
POST   /api/ai/speech/transcribe         - Speech to text
"""
import json
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.schemas import (
    AIModelConfigCreate, AIModelConfigUpdate, AIModelConfigResponse,
    AIChatRequest, AIChatResponse,
    TestCaseGenerateRequest,
    NLQueryRequest, NLQueryResponse,
    SpeechTranscribeResponse,
)
from app.services.ai_service import ai_service

router = APIRouter(prefix="/api/ai", tags=["AI"])


def _model_to_dict(model) -> dict:
    """Convert AIModelConfig to dict with parsed JSON fields."""
    params = None
    if model.parameters:
        try:
            params = json.loads(model.parameters) if isinstance(model.parameters, str) else model.parameters
        except (json.JSONDecodeError, TypeError):
            params = model.parameters

    return {
        "id": model.id, "name": model.name,
        "provider": model.provider, "model_name": model.model_name,
        "base_url": model.base_url, "is_default": model.is_default,
        "status": model.status, "parameters": params,
        "last_tested_at": model.last_tested_at.isoformat() if model.last_tested_at else None,
        "created_at": model.created_at.isoformat() if model.created_at else None,
    }


# ============ Model CRUD ============

@router.post("/models", status_code=201)
async def create_model(data: AIModelConfigCreate, db: AsyncSession = Depends(get_db)):
    try:
        model = await ai_service.configure_model(db, data.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail={
            "code": 40008, "message": "配置验证失败", "detail": str(e),
        })
    return {"code": 0, "message": "success", "data": _model_to_dict(model)}


@router.get("/models")
async def list_models(db: AsyncSession = Depends(get_db)):
    models = await ai_service.list_models(db)
    return {
        "code": 0, "message": "success",
        "data": [_model_to_dict(m) for m in models],
    }


@router.get("/models/{model_id}")
async def get_model(model_id: str, db: AsyncSession = Depends(get_db)):
    model = await ai_service.get_model(db, model_id)
    if not model:
        raise HTTPException(status_code=404, detail={
            "code": 40006, "message": "AI model not found",
            "detail": f"No AI model with id={model_id}",
        })
    return {"code": 0, "message": "success", "data": _model_to_dict(model)}


@router.put("/models/{model_id}")
async def update_model(model_id: str, data: AIModelConfigUpdate, db: AsyncSession = Depends(get_db)):
    try:
        model = await ai_service.update_model(db, model_id, data.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(status_code=400, detail={
            "code": 40008, "message": "配置验证失败", "detail": str(e),
        })
    if not model:
        raise HTTPException(status_code=404, detail={
            "code": 40006, "message": "AI model not found",
        })
    return {"code": 0, "message": "success", "data": _model_to_dict(model)}


@router.delete("/models/{model_id}")
async def delete_model(model_id: str, db: AsyncSession = Depends(get_db)):
    success = await ai_service.delete_model(db, model_id)
    if not success:
        raise HTTPException(status_code=404, detail={
            "code": 40006, "message": "AI model not found",
        })
    return {"code": 0, "message": "Model deleted", "data": None}


@router.post("/models/{model_id}/activate")
async def activate_model(model_id: str, db: AsyncSession = Depends(get_db)):
    try:
        model = await ai_service.set_active_model(db, model_id)
        return {"code": 0, "message": "success", "data": _model_to_dict(model)}
    except Exception as e:
        raise HTTPException(status_code=404, detail={
            "code": 40006, "message": "AI model not found", "detail": str(e),
        })


@router.post("/models/{model_id}/test")
async def test_model(model_id: str, db: AsyncSession = Depends(get_db)):
    try:
        result = await ai_service.test_model(db, model_id)
        return {"code": 0, "message": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail={
            "code": 40007, "message": "Model test failed", "detail": str(e),
        })


# ============ Chat ============

@router.post("/chat")
async def chat(data: AIChatRequest, db: AsyncSession = Depends(get_db)):
    session_id = data.session_id or str(uuid.uuid4())
    try:
        result = await ai_service.chat(
            db, data.model_id, data.message, session_id,
            data.system_prompt, data.input_type,
            skill_protocols=data.skill_protocols,
        )
        return {"code": 0, "message": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail={
            "code": 40007, "message": "AI chat failed", "detail": str(e),
        })


# ============ Test Case Generation ============

@router.post("/generate-testcases")
async def generate_test_cases(data: TestCaseGenerateRequest, db: AsyncSession = Depends(get_db)):
    try:
        result = await ai_service.generate_test_cases(
            db, data.model_id, data.requirements, data.available_devices,
            skill_protocols=data.skill_protocols,
        )
        return {"code": 0, "message": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail={
            "code": 40007, "message": "Generation failed", "detail": str(e),
        })


# ============ Natural Language Query ============

@router.post("/query")
async def natural_language_query(data: NLQueryRequest, db: AsyncSession = Depends(get_db)):
    try:
        result = await ai_service.natural_language_query(db, data.model_id, data.query)
        return {"code": 0, "message": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail={
            "code": 40007, "message": "Query failed", "detail": str(e),
        })


# ============ Speech Recognition ============

@router.post("/speech/transcribe")
async def transcribe_speech(file: UploadFile = File(...)):
    try:
        import whisper
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        model = whisper.load_model("base")
        result = model.transcribe(tmp_path)
        os.unlink(tmp_path)

        return {
            "code": 0, "message": "success",
            "data": {
                "text": result["text"],
                "language": result.get("language"),
                "duration": result.get("duration"),
            },
        }
    except ImportError:
        return {
            "code": 0, "message": "success",
            "data": {
                "text": "[Speech recognition not available — install openai-whisper]",
                "language": "en",
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail={
            "code": 40007, "message": "Speech recognition failed", "detail": str(e),
        })
