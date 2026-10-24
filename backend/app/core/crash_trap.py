"""Crash capture for the feedback centre (issue #26, sub-tasks F5 and F7).

Two distinct failure modes need different mechanics:

* **A handled-but-unexpected error inside a request** — caught by the generic
  FastAPI handler in ``main.py``, which has a live DB session and can file the
  report immediately. (This also closes the gap described in issue #13.)
* **A hard process crash** (``sys.excepthook``, a worker thread, or the process
  being killed) — there is no session and no event loop to await on, so the
  report is written to a **spool directory** and drained on the next startup.

On top of that, a **run marker** distinguishes a clean shutdown from a crash:
the marker is rewritten as ``clean: false`` at startup and set to ``true`` only
when the lifespan shutdown actually runs. If the next start finds ``false``, the
previous session ended abnormally and we offer to report it with the log tail
attached.
"""
from __future__ import annotations

import json
import os
import platform
import sys
import tempfile
import threading
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services import feedback_service as svc

_SPOOL_DIR = os.path.join(tempfile.gettempdir(), "testcopilot_crash_spool")
_RUN_MARKER = os.path.join(tempfile.gettempdir(), "testcopilot_lastrun.json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _system() -> Dict[str, str]:
    return {
        "os": f"{platform.system()} {platform.release()}",
        "arch": platform.machine(),
        "python": platform.python_version(),
    }


# --------------------------------------------------------------------------- #
# spool (used when there is no event loop available)
# --------------------------------------------------------------------------- #
def spool_crash(kind: str, title: str, stack: str, route: str = "") -> None:
    try:
        os.makedirs(_SPOOL_DIR, exist_ok=True)
        path = os.path.join(_SPOOL_DIR, f"crash-{int(time.time() * 1000)}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "kind": kind,
                    "title": title[:200],
                    "stack": stack[:8000],
                    "route": route[:240],
                    "app_version": settings.APP_VERSION,
                    "system": _system(),
                    "at": _now(),
                },
                fh,
                ensure_ascii=False,
            )
    except Exception:
        pass  # crash reporting must never make things worse


async def drain_spool(db: AsyncSession) -> int:
    """File every spooled crash, then clear the directory."""
    if not os.path.isdir(_SPOOL_DIR):
        return 0
    filed = 0
    for name in sorted(os.listdir(_SPOOL_DIR)):
        path = os.path.join(_SPOOL_DIR, name)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except Exception:
            try:
                os.remove(path)
            except OSError:
                pass
            continue
        try:
            report = await svc.create_report(
                db,
                kind="crash",
                title=f"[crash] {payload.get('title') or 'unknown'}",
                body=f"捕获于 {payload.get('at')}",
                stack=payload.get("stack") or "",
                route=payload.get("route") or "",
                consent=True,
                attach_logs=True,
                system=payload.get("system") or _system(),
            )
            await svc.forward_report(db, report)
            filed += 1
        except Exception:
            pass
        try:
            os.remove(path)
        except OSError:
            pass
    return filed


# --------------------------------------------------------------------------- #
# hooks
# --------------------------------------------------------------------------- #
def install_hooks() -> None:
    """Route unhandled main-thread and worker-thread exceptions to the spool."""
    default_hook = sys.excepthook

    def _hook(exc_type, exc_value, exc_tb):
        stack = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        spool_crash("crash", f"{exc_type.__name__}: {exc_value}", stack)
        default_hook(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook

    def _thread_hook(args):
        stack = "".join(
            traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)
        )
        thread_name = getattr(args.thread, "name", "?") if args.thread else "?"
        spool_crash("crash", f"[thread {thread_name}] {args.exc_type.__name__}: {args.exc_value}", stack)

    try:
        threading.excepthook = _thread_hook
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# run marker — "did we exit cleanly last time?"
# --------------------------------------------------------------------------- #
def mark_start() -> Optional[Dict[str, Any]]:
    """Record this run as unclean; return the *previous* run's marker."""
    previous = None
    try:
        if os.path.isfile(_RUN_MARKER):
            with open(_RUN_MARKER, "r", encoding="utf-8") as fh:
                previous = json.load(fh)
    except Exception:
        previous = None
    try:
        with open(_RUN_MARKER, "w", encoding="utf-8") as fh:
            json.dump({"clean": False, "started_at": _now(),
                       "version": settings.APP_VERSION}, fh)
    except Exception:
        pass
    return previous


def mark_clean_exit() -> None:
    try:
        with open(_RUN_MARKER, "w", encoding="utf-8") as fh:
            json.dump({"clean": True, "exited_at": _now(),
                       "version": settings.APP_VERSION}, fh)
    except Exception:
        pass


async def report_abnormal_exit(db: AsyncSession) -> bool:
    """File a report when the previous session did not shut down cleanly."""
    previous = mark_start()
    if previous is None or previous.get("clean") is True:
        return False
    try:
        report = await svc.create_report(
            db,
            kind="crash",
            title="[crash] 上次异常退出",
            body=f"上一次运行开始于 {previous.get('started_at')}（版本 {previous.get('version')}），"
                 f"没有正常退出。",
            stack="",
            route="startup",
            consent=True,
            attach_logs=True,
        )
        await svc.forward_report(db, report)
        return True
    except Exception:
        return False
