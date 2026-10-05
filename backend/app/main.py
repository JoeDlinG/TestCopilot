"""AITestLab FastAPI application entry point.

Aligned with ARCHITECTURE.md — modular API, WebSocket, communication layer.
"""
import os
import sys
import asyncio
import logging
import tempfile
import subprocess
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

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


# ---------------------------------------------------------------------------
# Static frontend serving (standalone / packaged mode).
#
# When a built frontend (``static/``) is present next to the backend — or
# bundled under ``sys._MEIPASS`` in a PyInstaller build — the backend serves
# the SPA at ``/`` so a single process on :8000 exposes both UI and API. In
# dev, Vite runs on :5173 and proxies ``/api`` here, so this block is inert.
# ---------------------------------------------------------------------------
_STATIC_INDEX = os.path.join(settings.STATIC_DIR, "index.html")
_HAS_STATIC = os.path.isfile(_STATIC_INDEX)

if _HAS_STATIC:
    _assets_dir = os.path.join(settings.STATIC_DIR, "assets")
    if os.path.isdir(_assets_dir):
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="assets")


@app.get("/")
async def root():
    if _HAS_STATIC:
        return FileResponse(_STATIC_INDEX)
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "websocket": "ws://localhost:8000/ws",
    }


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": settings.APP_VERSION}


if _HAS_STATIC:

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        """Serve static assets; fall back to index.html for SPA routes."""
        candidate = os.path.join(settings.STATIC_DIR, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(_STATIC_INDEX)


# ---------------------------------------------------------------------------
# System control: restart the backend process (used by the UI "Reset Software"
# button). We spawn a detached helper that kills the current server and
# relaunches it, so the HTTP request can return before the process dies.
# ---------------------------------------------------------------------------
_FROZEN = getattr(sys, "frozen", False)
RESTART_HELPER = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "restart_helper.py"
)


@app.post("/api/system/restart")
async def restart_system():
    # Packaged build: relaunch the exe itself with a restart-helper flag.
    if _FROZEN:
        cmd = [sys.executable, "--restart-helper"]
        cwd = os.path.dirname(sys.executable)
    else:
        if not os.path.exists(RESTART_HELPER):
            raise HTTPException(status_code=500, detail="restart helper not found")
        cmd = [sys.executable, RESTART_HELPER]
        cwd = os.path.dirname(RESTART_HELPER)

    try:
        # Cross-platform detach flags: POSIX uses a new session, Windows uses a
        # new process group + detached console so the helper survives the parent.
        if os.name == "nt":
            popen_kwargs = {
                "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP
                | getattr(subprocess, "DETACHED_PROCESS", 0),
            }
        else:
            popen_kwargs = {"start_new_session": True}

        log_path = os.path.join(tempfile.gettempdir(), "aitestlab_restart.log")
        subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=open(log_path, "a"),
            stderr=subprocess.STDOUT,
            **popen_kwargs,
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
