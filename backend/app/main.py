"""AITestLab FastAPI application entry point.

Aligned with ARCHITECTURE.md — modular API, WebSocket, communication layer.
"""
import os
import sys
import asyncio
import logging
import subprocess
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import init_db
from app.core.exceptions import AITestLabException
from app.api import devices, ai, testcases, executions, logs, reports, plugins, dashboards, websocket

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
app.include_router(dashboards.router)

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


# ---------------------------------------------------------------------------
# System control: restart the backend process (used by the UI "Reset Software"
# button). We spawn a detached helper that kills the current server and
# relaunches it, so the HTTP request can return before the process dies.
# ---------------------------------------------------------------------------
RESTART_HELPER = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "restart_helper.py"
)


@app.post("/api/system/restart")
async def restart_system():
    if not os.path.exists(RESTART_HELPER):
        raise HTTPException(status_code=500, detail="restart helper not found")
    try:
        subprocess.Popen(
            [sys.executable, RESTART_HELPER],
            cwd=os.path.dirname(RESTART_HELPER),
            start_new_session=True,
            stdout=open("/tmp/aitestlab_restart.log", "a"),
            stderr=subprocess.STDOUT,
        )
    except Exception as e:
        logger.error(f"Failed to spawn restart helper: {e}")
        raise HTTPException(status_code=500, detail=f"restart failed: {e}")

    async def _terminate():
        # Let the response flush, then take the current process down so the
        # helper (which is in its own session) can relaunch a clean instance.
        await asyncio.sleep(0.5)
        os._exit(0)

    asyncio.create_task(_terminate())
    return {"code": 0, "message": "restarting", "data": None}
