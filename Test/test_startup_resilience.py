#!/usr/bin/env python3
"""Boot-resilience regression guards.

Two failures motivated this file:

1. A module-level function was accidentally inserted into the middle of the
   ``ExecutionEngine`` class body. The file still compiled and imported, but
   the class closed early and 14 methods (including ``reset_stale_executions``)
   became unreachable nested functions. Startup then died with
   ``AttributeError`` and the UI could not load a project.
2. ``lifespan`` ran its startup repairs with no exception isolation, so ANY
   single failure aborted the whole ASGI startup.

Guards here verify the service contracts, run the real lifespan, and inject a
failure to prove an abnormal restart always comes back up.

Run: ``python3 Test/test_startup_resilience.py``
"""
import ast
import asyncio
import os
import sys
from typing import List
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND)

_failures: List[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("  PASS  " if ok else "  FAIL  ") + label + (f"  -> {detail}" if detail else ""))
    if not ok:
        _failures.append(label)


def text(path: str) -> str:
    return open(os.path.join(ROOT, path), encoding="utf-8").read()


# --------------------------------------------------------------------------- #
# 1. Service contracts — the exact check that would have caught the bug
# --------------------------------------------------------------------------- #
EXPECTED_ENGINE_METHODS = (
    "__init__", "_json_commands", "_python_can_commands", "_scan_commands",
    "_extract_commands", "normalize_node_commands", "_infer_protocol",
    "_desired_protocols", "_resolve_device", "_missing_device_hint",
    "_loop_bounds", "_loop_iterations", "_iterate_loop", "_branch_target",
    "start_execution", "reset_stale_executions", "stop_execution",
    "_run_execution", "_execute_flow", "get_execution", "list_executions",
    "get_step_results",
)


def contract_checks() -> None:
    from app.services.device_service import device_service
    from app.services.execution_service import execution_engine, ExecutionEngine
    from app.services.plan_runner import plan_runner

    missing = [m for m in EXPECTED_ENGINE_METHODS
               if not callable(getattr(execution_engine, m, None))]
    check("ExecutionEngine has every expected method",
          not missing, f"missing={missing}")

    check("device_service contract", all(callable(getattr(device_service, m, None))
          for m in ("connect_device", "disconnect_device", "send_command",
                    "reset_stale_connections", "restore_plugin_protocols")))
    check("plan_runner contract",
          callable(getattr(plan_runner, "reset_stale_runs", None)))

    # AST guard: no module-level function may contain nested method definitions
    # (the signature of a class that closed early).
    tree = ast.parse(text("backend/app/services/execution_service.py"))
    bad = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        nested = [x.name for x in node.body
                  if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef))]
        if nested:
            bad.append(f"{node.name}: {nested}")
    check("no module-level function swallows class methods", not bad, str(bad))

    cls = next((n for n in tree.body
                if isinstance(n, ast.ClassDef) and n.name == "ExecutionEngine"), None)
    method_count = len([m for m in cls.body
                        if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]) if cls else 0
    check("ExecutionEngine class body holds >= 22 methods",
          method_count >= 22, str(method_count))


# --------------------------------------------------------------------------- #
# 2. Real lifespan startup smoke test
# --------------------------------------------------------------------------- #
def _run_lifespan(patch_failure=False):
    """Enter/exit the real ASGI lifespan; return (ok, warnings, error).

    All external side effects (DB, crash hooks, feedback network calls) are
    stubbed so the test never touches the user's real data. Only the control
    flow of ``lifespan`` itself is under test.
    """
    import logging
    import app.main as main_mod
    from app.services.device_service import device_service
    from app.services.execution_service import execution_engine
    from app.services.plan_runner import plan_runner

    main_mod._BOOT_WARNINGS.clear()

    class _FakeSession:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *args):
            return False

    async def _noop(*_a, **_kw):
        return 0

    connection_mock = mock.AsyncMock(side_effect=RuntimeError("injected boot failure")) \
        if patch_failure else mock.AsyncMock(side_effect=_noop)

    patches = [
        mock.patch.object(main_mod, "init_db", new=mock.AsyncMock(side_effect=_noop)),
        mock.patch.object(device_service, "reset_stale_connections", new=connection_mock),
        mock.patch.object(device_service, "restore_plugin_protocols",
                          new=mock.AsyncMock(side_effect=_noop)),
        mock.patch.object(execution_engine, "reset_stale_executions",
                          new=mock.AsyncMock(side_effect=_noop)),
        mock.patch.object(plan_runner, "reset_stale_runs",
                          new=mock.AsyncMock(side_effect=_noop)),
        mock.patch("app.core.crash_trap.drain_spool", new=mock.AsyncMock(return_value=0)),
        mock.patch("app.core.crash_trap.report_abnormal_exit", new=lambda *a, **k: False),
        mock.patch("app.core.crash_trap.mark_clean_exit", new=lambda *a, **k: None),
        mock.patch("app.core.crash_trap.install_hooks", new=lambda *a, **k: None),
        mock.patch("app.services.feedback_service.retry_pending",
                   new=mock.AsyncMock(return_value=0)),
        mock.patch("app.services.program_logger.install_program_logging",
                   new=lambda *a, **k: None),
        mock.patch("app.core.database.async_session",
                   side_effect=lambda: _FakeSession()),
    ]

    async def _go():
        for p in patches:
            p.start()
        try:
            async with main_mod.lifespan(main_mod.app):
                return list(main_mod._BOOT_WARNINGS)
        finally:
            for p in reversed(patches):
                p.stop()

    old_level = logging.getLogger().level
    logging.getLogger().setLevel(logging.CRITICAL)  # expected error logs
    try:
        warnings = asyncio.run(_go())
        return True, warnings, None
    except Exception as exc:
        return False, list(main_mod._BOOT_WARNINGS), f"{type(exc).__name__}: {exc}"
    finally:
        logging.getLogger().setLevel(old_level)


def lifespan_checks() -> None:
    ok, warnings, err = _run_lifespan(patch_failure=False)
    check("real lifespan starts and shuts down cleanly", ok, err or "")
    check("healthy boot reports no warnings", not warnings, str(warnings))

    ok2, warnings2, err2 = _run_lifespan(patch_failure=True)
    check("a failing repair does NOT abort startup", ok2, err2 or "")
    check("failing repair is recorded as a boot warning",
          any("reset stale device connections" in w.get("step", "") for w in warnings2),
          str(warnings2))


# --------------------------------------------------------------------------- #
# 3. Source guards
# --------------------------------------------------------------------------- #
def source_guards() -> None:
    main = text("backend/app/main.py")
    check("startup has a final catch-all around _startup()",
          "await _startup()" in main and "UNEXPECTED startup failure" in main)
    check("each boot repair has its own session + try/except",
          "async def _boot_repair" in main and "async with async_session() as db" in main)
    check("boot warnings exposed via /api/health",
          "boot_warnings" in main and "degraded" in main)
    check("startup contract self-check present",
          "service contract BROKEN" in main)


def main() -> int:
    contract_checks()
    lifespan_checks()
    source_guards()
    if _failures:
        print(f"\nFAILED: {len(_failures)} check(s): {', '.join(_failures)}")
        return 1
    print("\nAll startup-resilience guards passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
