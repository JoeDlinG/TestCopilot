"""FastAPI dependency injection utilities."""
from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AITestLabException


async def handle_aitestlab_exception(request: Request, call_next):
    """Global exception handler middleware alternative — call from route handlers."""
    try:
        return await call_next(request)
    except AITestLabException as e:
        raise HTTPException(status_code=400, detail={
            "code": e.code,
            "message": e.message,
            "detail": e.detail,
        })
