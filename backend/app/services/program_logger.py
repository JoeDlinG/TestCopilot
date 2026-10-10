"""Program execution & communication logging for post-mortem analysis.

Directory layout (all under ``backend/logs``)::

    logs/
      program/                        程序执行日志（全局，10MB 轮转）
        program_001.log
        program_002.log               ← 超过 10MB 自动新建
      communication/                  通信日志（全局，按设备，10MB 轮转）
        <device_id>/comm_YYYYMMDD_NNN.log
      executions/                     每次执行测试生成一个新文件夹
        <execution_id>/
          program_001.log             该次执行的程序日志（10MB 轮转）
          communication_001.log       该次执行的通信日志（10MB 轮转）

Design notes:
  * Every file rotates to a new sequence number once it exceeds ``MAX_LOG_SIZE``
    (10 MB) — nothing is ever overwritten or truncated.
  * :func:`install_program_logging` attaches a global rotating file handler to
    the root logger so *all* program logs are captured for analysis.
  * :class:`ExecutionLogger` gives each test run its own folder; the execution
    engine and device service push their entries into it explicitly.
"""
from __future__ import annotations

import logging
import os
import threading
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Dict, Optional
from app.core.timeutils import from_timestamp, utc_now

logger = logging.getLogger(__name__)

MAX_LOG_SIZE = 10 * 1024 * 1024  # 10 MB

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOGS_DIR = os.path.join(_BACKEND_DIR, "logs")
PROGRAM_DIR = os.path.join(LOGS_DIR, "program")
COMMUNICATION_DIR = os.path.join(LOGS_DIR, "communication")
EXECUTIONS_DIR = os.path.join(LOGS_DIR, "executions")


def _ts() -> str:
    return utc_now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


class RotatingTextWriter:
    """Thread-safe append-only text file that rotates after ``MAX_LOG_SIZE``.

    Files are named ``<stem>_<seq:03d>.log`` (seq starts at 1). A new file is
    created once the current one reaches 10 MB, so no entry is ever lost.
    """

    def __init__(self, directory: str, stem: str):
        self._dir = directory
        self._stem = stem
        self._lock = threading.Lock()
        try:
            os.makedirs(self._dir, exist_ok=True)
        except OSError as e:  # pragma: no cover - unwritable dir
            logger.warning(f"cannot create log dir {self._dir}: {e}")

    def _path(self, seq: int) -> str:
        return os.path.join(self._dir, f"{self._stem}_{seq:03d}.log")

    def _current_path(self) -> str:
        seq = 1
        while os.path.exists(self._path(seq)):
            try:
                if os.path.getsize(self._path(seq)) < MAX_LOG_SIZE:
                    return self._path(seq)
            except OSError:
                return self._path(seq)
            seq += 1
        return self._path(seq)

    def write(self, line: str) -> None:
        if not line.endswith("\n"):
            line += "\n"
        with self._lock:
            try:
                with open(self._current_path(), "a", encoding="utf-8") as f:
                    f.write(line)
            except Exception as e:  # pragma: no cover - best effort
                logger.warning(f"failed to write log: {e}")


# --------------------------------------------------------------------- #
# Global program log
# --------------------------------------------------------------------- #
# Routed through the standard logger so it lands in the single global
# ``logs/program/program_global.log`` (rotated at 10 MB) together with every
# other module's logs — one place to look for a full program trace.
_program_log = logging.getLogger("aitestlab.program")


def log_program(message: str, level: str = "INFO") -> None:
    """Append one entry to the global program execution log."""
    _program_log.log(getattr(logging, str(level).upper(), logging.INFO), message)


def install_program_logging(level: int = logging.INFO) -> None:
    """Attach a rotating file handler to the root logger.

    Also mirrors every record (from any module) into ``logs/program`` so the
    full program execution log is always available for analysis.
    """
    os.makedirs(PROGRAM_DIR, exist_ok=True)
    root = logging.getLogger()
    # Avoid duplicate handlers when uvicorn reloads the app.
    for h in root.handlers:
        if getattr(h, "_aitestlab_program_handler", False):
            return
    handler = RotatingFileHandler(
        os.path.join(PROGRAM_DIR, "program_global.log"),
        maxBytes=MAX_LOG_SIZE,
        backupCount=20,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    handler._aitestlab_program_handler = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    if root.level > level or root.level == logging.NOTSET:
        root.setLevel(level)


# --------------------------------------------------------------------- #
# Per-execution log
# --------------------------------------------------------------------- #
class ExecutionLogger:
    """Program + communication logs for a single test run."""

    def __init__(self, execution_id: str):
        self.execution_id = execution_id
        self.dir = os.path.join(EXECUTIONS_DIR, execution_id)
        os.makedirs(self.dir, exist_ok=True)
        self._program = RotatingTextWriter(self.dir, "program")
        self._comm = RotatingTextWriter(self.dir, "communication")

    # -- program log -------------------------------------------------- #
    def program(self, message: str, level: str = "INFO") -> None:
        self._program.write(f"[{_ts()}] {level}: {message}")

    # -- communication log -------------------------------------------- #
    def communication(self, device_id: str, direction: str, data: str) -> None:
        self._comm.write(f"[{_ts()}] [{device_id}] {direction}: {data}")


_execution_loggers: Dict[str, ExecutionLogger] = {}


def start_execution_log(execution_id: str) -> ExecutionLogger:
    """Create (or reset) the log folder for an execution."""
    el = ExecutionLogger(execution_id)
    _execution_loggers[execution_id] = el
    el.program(f"===== execution {execution_id} started =====")
    log_program(f"===== execution {execution_id} started =====")
    return el


def get_execution_log(execution_id: str) -> Optional[ExecutionLogger]:
    return _execution_loggers.get(execution_id)


def finish_execution_log(execution_id: str, summary: str = "") -> None:
    el = _execution_loggers.pop(execution_id, None)
    if el:
        el.program(f"===== execution {execution_id} finished {summary}=====")
    log_program(f"===== execution {execution_id} finished {summary}=====")


def list_execution_logs(execution_id: str) -> list:
    """List the log files produced for one execution (for the UI/API)."""
    d = os.path.join(EXECUTIONS_DIR, execution_id)
    if not os.path.isdir(d):
        return []
    return sorted(
        (
            {
                "name": f,
                "size": os.path.getsize(os.path.join(d, f)),
                "modified": from_timestamp(
                    os.path.getmtime(os.path.join(d, f))
                ).isoformat(),
            }
            for f in os.listdir(d)
            if f.endswith(".log")
        ),
        key=lambda x: x["name"],
    )


def list_program_logs() -> dict:
    """List the global program log files (rotated at 10 MB)."""
    files = []
    if os.path.isdir(PROGRAM_DIR):
        for f in sorted(os.listdir(PROGRAM_DIR)):
            if not f.endswith(".log"):
                continue
            p = os.path.join(PROGRAM_DIR, f)
            files.append({
                "name": f,
                "size": os.path.getsize(p),
                "modified": from_timestamp(os.path.getmtime(p)).isoformat(),
            })
    return {"dir": PROGRAM_DIR, "max_size_bytes": MAX_LOG_SIZE, "files": files}
