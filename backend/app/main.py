"""AITestLab FastAPI application entry point.

Aligned with ARCHITECTURE.md — modular API, WebSocket, communication layer.
"""
import os
import sys
import asyncio
import logging
import tempfile
import subprocess
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import init_db
from app.core.exceptions import AITestLabException
from app.api import (
    devices, ai, testcases, executions, logs, reports, plugins,
    plugin_editor, dashboards, websocket, plans, memory, projects, help as help_api,
    update as update_api, feedback as feedback_api,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Non-fatal problems encountered during startup. Exposed via /api/health so a
# degraded boot is visible to the UI instead of silently losing functionality.
_BOOT_WARNINGS: list = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    # Startup — timed, so a slow boot is attributable to a specific step
    # instead of being a black box.
    import time as _time

    _boot = _time.monotonic()

    def _mark(step: str) -> None:
        logger.info(f"[boot] {step}: {(_time.monotonic() - _boot) * 1000:.0f} ms")

    _BOOT_WARNINGS.clear()

    async def _startup() -> None:
        logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
        for _d in (settings.LOG_DIR, settings.EXPORT_DIR,
                   settings.REPORT_DIR, settings.PLUGIN_DIR):
            os.makedirs(_d, exist_ok=True)

        # Persist program execution logs to logs/program/ (10 MB rotation) so
        # any run can be analysed afterwards. Best-effort: a broken log sink
        # must never prevent the app from starting.
        try:
            from app.services.program_logger import install_program_logging
            install_program_logging()
            logger.info("Program logging installed (logs/program, 10MB rotation)")
        except Exception:
            logger.error("program logging not installed (startup continues):\n%s",
                         traceback.format_exc())

        # Crash capture is armed before anything else can throw (issue #26 / F5).
        try:
            from app.core.crash_trap import install_hooks

            install_hooks()
        except Exception as exc:  # pragma: no cover - diagnostics only
            logger.warning(f"crash hooks not installed: {exc}")

        try:
            await init_db()
            _mark("database initialized")
        except Exception:
            detail = traceback.format_exc()
            logger.error(f"[boot] database init FAILED (startup continues):\n{detail}")
            _BOOT_WARNINGS.append({"step": "database init", "error": detail.strip().splitlines()[-1]})

        # -------------------------------------------------------------- #
        # Best-effort recovery after an abnormal shutdown.
        #
        # Every repair runs in its OWN session and its OWN try/except. A
        # single failure (malformed row, locked DB, missing method after a
        # bad deploy) must never abort startup: users must always get the UI
        # back so they can load their project and recover.
        # -------------------------------------------------------------- #
        from app.core.database import async_session

        async def _boot_repair(label: str, fn) -> None:
            try:
                async with async_session() as db:
                    await fn(db)
                logger.info(f"[boot] {label} ok")
            except Exception:
                detail = traceback.format_exc()
                logger.error(f"[boot] {label} FAILED (startup continues):\n{detail}")
                _BOOT_WARNINGS.append(
                    {"step": label, "error": detail.strip().splitlines()[-1]})

        async def _device_connections(db):
            from app.services.device_service import device_service
            await device_service.reset_stale_connections(db)

        async def _plugin_protocols(db):
            from app.services.device_service import device_service
            await device_service.restore_plugin_protocols(db)

        async def _stale_executions(db):
            from app.services.execution_service import execution_engine
            await execution_engine.reset_stale_executions(db)

        async def _stale_plan_runs(db):
            from app.services.plan_runner import plan_runner
            await plan_runner.reset_stale_runs(db)

        await _boot_repair("reset stale device connections", _device_connections)
        await _boot_repair("restore plugin protocols", _plugin_protocols)
        await _boot_repair("reset stale executions", _stale_executions)
        await _boot_repair("reset stale plan runs", _stale_plan_runs)
        _mark("stale state reset")

        # Contract self-check: a module can be syntactically valid and
        # importable yet have lost most of its methods (e.g. a class that
        # closed early). Catch that loudly at boot instead of failing on the
        # first user action.
        try:
            from app.services.device_service import device_service
            from app.services.execution_service import execution_engine
            from app.services.plan_runner import plan_runner

            contracts = {
                "device_service": (device_service, (
                    "connect_device", "disconnect_device", "send_command",
                    "reset_stale_connections", "restore_plugin_protocols")),
                "execution_engine": (execution_engine, (
                    "start_execution", "stop_execution", "get_execution",
                    "list_executions", "reset_stale_executions")),
                "plan_runner": (plan_runner, ("reset_stale_runs",)),
            }
            for name, (obj, methods) in contracts.items():
                missing = [m for m in methods if not callable(getattr(obj, m, None))]
                if missing:
                    msg = f"{name} is missing methods: {', '.join(missing)}"
                    logger.error(f"[boot] service contract BROKEN: {msg}")
                    _BOOT_WARNINGS.append({"step": "service contract", "error": msg})
        except Exception:
            detail = traceback.format_exc()
            logger.error(f"[boot] service contract check failed:\n{detail}")
            _BOOT_WARNINGS.append(
                {"step": "service contract", "error": detail.strip().splitlines()[-1]})
        _mark("service contracts checked")

        # Feedback centre (issue #26): file crashes spooled by a previous run,
        # note an abnormal exit, and flush reports not forwarded earlier.
        try:
            async with async_session() as db:
                try:
                    from app.core.crash_trap import drain_spool, report_abnormal_exit

                    filed = await drain_spool(db)
                    abnormal = await report_abnormal_exit(db)
                    if filed or abnormal:
                        logger.info(
                            f"feedback centre: {filed} spooled crash(es), "
                            f"abnormal_exit={abnormal}"
                        )
                except Exception as exc:
                    logger.warning(f"feedback startup check failed: {exc}")
                try:
                    from app.services.feedback_service import retry_pending

                    sent = await retry_pending(db)
                    if sent:
                        logger.info(f"feedback centre: forwarded {sent} queued report(s)")
                except Exception as exc:
                    logger.warning(f"feedback flush failed: {exc}")
        except Exception:
            detail = traceback.format_exc()
            logger.error(f"[boot] feedback centre failed (startup continues):\n{detail}")
            _BOOT_WARNINGS.append(
                {"step": "feedback centre", "error": detail.strip().splitlines()[-1]})
        _mark("feedback centre ready")

    # Final safety net: no startup step — including an unforeseen one — may
    # prevent the ASGI app from yielding. A broken boot must still serve the
    # UI so the user can open their project; the failure is logged in full and
    # reported through /api/health.
    try:
        await _startup()
    except Exception:
        detail = traceback.format_exc()
        logger.error(f"[boot] UNEXPECTED startup failure (startup continues):\n{detail}")
        _BOOT_WARNINGS.append(
            {"step": "startup", "error": detail.strip().splitlines()[-1]})

    yield

    # Shutdown — mark the exit as clean so the next start can tell a restart
    # apart from a crash.
    logger.info(f"Shutting down {settings.APP_NAME}")
    try:
        from app.core.crash_trap import mark_clean_exit

        mark_clean_exit()
    except Exception:
        pass


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


# Catch-all handler (issue #13 / issue #26 F5). Until now only
# AITestLabException was handled, so every other unhandled error escaped as a
# bare traceback and neither the UI nor we ever learned about it.
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    try:
        from app.core.database import async_session
        from app.services import feedback_service as svc

        async with async_session() as db:
            report = await svc.create_report(
                db,
                kind="crash",
                title=f"[crash] {type(exc).__name__}: {exc}"[:200],
                body=f"{request.method} {request.url.path}",
                stack=traceback.format_exc(),
                route=f"{request.method} {request.url.path}",
                consent=True,
                attach_logs=True,
            )
            await svc.forward_report(db, report)
    except Exception:
        pass  # reporting must never change the response
    return JSONResponse(
        status_code=500,
        content={"code": 50000, "message": "服务器内部错误", "detail": str(exc)},
    )


# Register API routers
app.include_router(devices.router)
app.include_router(ai.router)
app.include_router(memory.router)
app.include_router(projects.router)
app.include_router(testcases.router)
app.include_router(executions.router)
app.include_router(logs.router)
app.include_router(reports.router)
app.include_router(plugins.router)
app.include_router(plugin_editor.router)
app.include_router(dashboards.router)
app.include_router(plans.plans_router)
app.include_router(plans.runs_router)
app.include_router(help_api.router)
app.include_router(update_api.router)
app.include_router(feedback_api.router)

# Register WebSocket router
app.include_router(websocket.router)


# ---------------------------------------------------------------------------
# Accept both "/api/devices" and "/api/devices/" for collection routes.
#
# FastAPI answers the slash-less form with a 307 redirect, which costs an extra
# round trip, breaks clients that do not follow redirects, and — in packaged
# mode, where the SPA catch-all lives — used to surface as index.html instead
# of JSON (issue #8).  Rewriting the path internally fixes every collection
# route at once instead of patching each router.
# ---------------------------------------------------------------------------
_API_ROUTE_PATHS = {getattr(r, "path", None) for r in app.routes}


@app.middleware("http")
async def _api_trailing_slash(request, call_next):
    path = request.scope.get("path") or ""
    if (
        path.startswith("/api/")
        and not path.endswith("/")
        and path not in _API_ROUTE_PATHS
        and f"{path}/" in _API_ROUTE_PATHS
    ):
        request.scope["path"] = f"{path}/"
        request.scope["raw_path"] = f"{path}/".encode()
    elif (
        path.startswith("/api/")
        and path.endswith("/")
        and path not in _API_ROUTE_PATHS
        and path.rstrip("/") in _API_ROUTE_PATHS
    ):
        # The opposite direction matters in packaged mode: with the SPA
        # catch-all registered, "/api/projects/" would otherwise fall through
        # to index.html and be returned as HTML with status 200 (issue #8's
        # failure mode resurfacing once static/ exists).
        bare = path.rstrip("/")
        request.scope["path"] = bare
        request.scope["raw_path"] = bare.encode()
    return await call_next(request)


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
_ASSETS_DIR = os.path.join(settings.STATIC_DIR, "assets")

# Windows registries sometimes associate .js with text/plain. Browsers apply a
# strict MIME check to ES modules, so a wrong guess yields a completely blank
# page with NO 404 and NO API calls (the classic "server logs are clean"
# white screen). Never delegate this decision to `mimetypes`.
_MEDIA_TYPES = {
    # Do NOT embed "charset=" here: Starlette appends it for text/* types and
    # a double "; charset=utf-8; charset=utf-8" was observed on /.
    ".html": "text/html",
    ".js": "application/javascript",
    ".mjs": "application/javascript",
    ".css": "text/css",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".map": "application/json; charset=utf-8",
    ".wasm": "application/wasm",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
}


def _media_type(path: str) -> str:
    """Deterministic MIME for anything we serve, independent of the OS."""
    return _MEDIA_TYPES.get(os.path.splitext(path)[1].lower(),
                            "application/octet-stream")


def _register_media_types() -> None:
    """Also fix StaticFiles' guesses (it consults the mimetypes database)."""
    import mimetypes

    for ext, mime in _MEDIA_TYPES.items():
        mimetypes.add_type(mime.split(";")[0], ext)
    # Force the two extensions that cause the white screen on Windows.
    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("application/javascript", ".mjs")


_register_media_types()

if _HAS_STATIC:
    try:
        _asset_count = len(os.listdir(_ASSETS_DIR))
    except OSError:
        _asset_count = 0
    logger.info(
        "[boot] frontend bundle: dir=%s index=%s (%d bytes) assets=%d "
        "entry_media_type=%s",
        settings.STATIC_DIR, _STATIC_INDEX,
        os.path.getsize(_STATIC_INDEX), _asset_count,
        _media_type(_STATIC_INDEX),
    )
else:
    logger.warning("[boot] frontend bundle: not found at %s (dev mode?)",
                   settings.STATIC_DIR)

# The SPA shell must never be cached: it names the content-hashed asset files,
# so a stale copy makes the browser request bundles that the new build no
# longer ships — the page then loads nothing and shows a blank screen after an
# upgrade. Hashed assets under /assets are immutable and keep default caching.
_INDEX_HEADERS = {"Cache-Control": "no-store, must-revalidate"}

if _HAS_STATIC and os.path.isdir(_ASSETS_DIR):
    app.mount("/assets", StaticFiles(directory=_ASSETS_DIR), name="assets")


@app.middleware("http")
async def _static_diagnostics(request: Request, call_next):
    """Make blank-screen incidents diagnosable from the server log."""
    path = request.scope.get("path") or ""
    response = await call_next(request)
    if path.startswith("/assets/") and response.status_code >= 400:
        logger.warning("[boot] asset %s -> %s (stale index.html?)",
                       path, response.status_code)
    elif path == "/":
        logger.info("[boot] GET / -> %s media_type=%s",
                    response.status_code, response.headers.get("content-type"))
    return response


@app.get("/api/system/diag")
async def system_diag():
    """One-call evidence bundle for blank-screen / startup incidents."""
    return {
        "version": settings.APP_VERSION,
        "static_dir": settings.STATIC_DIR,
        "has_static": _HAS_STATIC,
        "index_exists": os.path.isfile(_STATIC_INDEX),
        "index_media_type": _media_type(_STATIC_INDEX),
        "entry_media_type": _media_type("entry.js"),
        "index_headers": _INDEX_HEADERS,
        "asset_count": _asset_count if _HAS_STATIC else 0,
        "assets_dir": _ASSETS_DIR,
        "boot_guards": {
            "explicit_mime": True,
            "index_no_store": _INDEX_HEADERS.get("Cache-Control", "").startswith("no-store"),
            "health_probe": True,
        },
    }


@app.get("/")
async def root():
    if _HAS_STATIC:
        return FileResponse(
            _STATIC_INDEX,
            media_type=_media_type(_STATIC_INDEX),
            headers=_INDEX_HEADERS,
        )
    # NOTE: there is no plain "/ws" endpoint — advertising it (as the docs and
    # this response used to do) sent clients to a 403 (issue #10).
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "websocket": {
            "executions": "ws://localhost:8000/ws/executions/{execution_id}",
            "devices": "ws://localhost:8000/ws/devices/{device_id}",
        },
    }


@app.get("/api/health")
async def health_check():
    # ``status`` stays "ok" so a degraded boot is still usable; the warnings
    # tell the UI/operator which repair steps need attention.
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "degraded": bool(_BOOT_WARNINGS),
        "boot_warnings": list(_BOOT_WARNINGS),
    }


if _HAS_STATIC:

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        """Serve static assets; fall back to index.html for SPA routes."""
        if full_path == "api" or full_path.startswith("api/"):
            # Never disguise an unknown API path as a 200 HTML document: the
            # frontend would try to parse index.html as JSON and go blank.
            return JSONResponse({"detail": "API route not found"}, status_code=404)
        if full_path.startswith("assets/"):
            # A missing bundle means the client holds a stale index.html. Answer
            # 404 rather than handing back HTML, which the browser would reject
            # as a module with the wrong MIME type and render as a blank page.
            return JSONResponse({"detail": "Asset not found"}, status_code=404)
        candidate = os.path.join(settings.STATIC_DIR, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate, media_type=_media_type(candidate))
        return FileResponse(
            _STATIC_INDEX,
            media_type=_media_type(_STATIC_INDEX),
            headers=_INDEX_HEADERS,
        )


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
