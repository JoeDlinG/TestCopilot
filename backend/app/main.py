"""AITestLab FastAPI application entry point.

Aligned with ARCHITECTURE.md — modular API, WebSocket, communication layer.
"""
import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import init_db
from app.core.exceptions import AITestLabException
from app.api import devices, ai, testcases, executions, logs, reports, plugins, websocket

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    # Startup
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    os.makedirs(settings.LOG_DIR, exist_ok=True)
    os.makedirs(settings.EXPORT_DIR, exist_ok=True)
    os.makedirs(settings.REPORT_DIR, exist_ok=True)
    os.makedirs(settings.PLUGIN_DIR, exist_ok=True)

    await init_db()
    logger.info("Database initialized")

    # Reset stale connections (in-memory state lost on restart)
    from app.core.database import async_session
    async with async_session() as db:
        from app.services.device_service import device_service
        await device_service.reset_stale_connections(db)
        logger.info("Stale device connections reset")

    yield

    # Shutdown
    logger.info(f"Shutting down {settings.APP_NAME}")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-powered test automation platform for hardware testing",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handler for AITestLab custom exceptions
@app.exception_handler(AITestLabException)
async def aitestlab_exception_handler(request: Request, exc: AITestLabException):
    return JSONResponse(
        status_code=400,
        content={
            "code": exc.code,
            "message": exc.message,
            "detail": exc.detail,
        },
    )


# Register API routers
app.include_router(devices.router)
app.include_router(ai.router)
app.include_router(testcases.router)
app.include_router(executions.router)
app.include_router(logs.router)
app.include_router(reports.router)
app.include_router(plugins.router)

# Register WebSocket router
app.include_router(websocket.router)


@app.get("/")
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "websocket": "ws://localhost:8000/ws",
    }


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": settings.APP_VERSION}
