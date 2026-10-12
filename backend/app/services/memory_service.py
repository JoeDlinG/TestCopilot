"""Project memory files — persist the key content of a conversation as Markdown.

A memory file is named ``Project_<name> Memory.md`` and lives in
``backend/memory/``.  It is plain Markdown so it can be read, diffed and
committed like any other document, and it is what the AI assistant writes to
when the user asks to remember something from the conversation.

File layout::

    # Project <name> Memory

    > 项目记忆：记录对话中确认的关键决策、约定与事实。

    ## 2026-10-12 14:30 · <标题>

    ...markdown body...

``append`` (default) adds a new ``##`` section; ``replace`` rewrites the file.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.timeutils import utc_now

logger = logging.getLogger(__name__)

MEMORY_DIR = Path(__file__).resolve().parents[2] / "memory"

_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

HEADER_TEMPLATE = """# Project {name} Memory

> 项目记忆：由 AI 助手维护，记录对话中确认的关键决策、约定与事实。
> 最后更新：{updated}
"""


# --------------------------------------------------------------------------- #
# Naming helpers
# --------------------------------------------------------------------------- #

def _safe_name(name: str) -> str:
    cleaned = _UNSAFE_CHARS.sub("_", (name or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned or "Default"


def _memory_path(name: str) -> Path:
    return MEMORY_DIR / f"Project_{_safe_name(name)} Memory.md"


def _display_name(path: Path) -> str:
    stem = path.stem  # "Project_xxx Memory"
    if stem.startswith("Project_") and stem.endswith(" Memory"):
        return stem[len("Project_"):-len(" Memory")]
    return stem


def _ensure_dir() -> None:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)


def _now_display() -> str:
    return utc_now().strftime("%Y-%m-%d %H:%M")


# --------------------------------------------------------------------------- #
# CRUD
# --------------------------------------------------------------------------- #

def list_memories() -> List[Dict[str, Any]]:
    """List memory files, newest first."""
    _ensure_dir()
    items: List[Dict[str, Any]] = []
    for path in sorted(
        MEMORY_DIR.glob("Project_* Memory.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    ):
        stat = path.stat()
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            text = ""
        # First non-heading, non-quote line makes a readable preview.
        preview = ""
        for line in text.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith(("#", ">", "-", "*")):
                preview = stripped[:120]
                break
        items.append({
            "name": _display_name(path),
            "file_name": path.name,
            "size": stat.st_size,
            "section_count": text.count("\n## "),
            "preview": preview,
            "updated_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })
    return items


def read_memory(name: str) -> Dict[str, Any]:
    path = _memory_path(name)
    if not path.is_file():
        raise FileNotFoundError(name)
    return {
        "name": _safe_name(name),
        "file_name": path.name,
        "content": path.read_text(encoding="utf-8"),
    }


def write_memory(
    name: str,
    content: str,
    mode: str = "append",
    title: str = "",
) -> Dict[str, Any]:
    """Create/append/replace a memory file.

    ``mode`` is one of ``append`` (default), ``replace`` or ``overwrite``.
    """
    _ensure_dir()
    path = _memory_path(name)
    safe = _safe_name(name)
    body = (content or "").strip("\n")

    if mode in ("replace", "overwrite") or not path.is_file():
        header = HEADER_TEMPLATE.format(name=safe, updated=_now_display())
        text = f"{header}\n"
        if body:
            if not body.lstrip().startswith("## "):
                text += f"\n## {_now_display()} · {title or '对话要点'}\n\n"
            text += f"{body}\n"
    else:
        text = path.read_text(encoding="utf-8")
        # Refresh the "last updated" line so the file stays self-describing.
        text = re.sub(
            r"^> 最后更新：.*$",
            f"> 最后更新：{_now_display()}",
            text,
            count=1,
            flags=re.MULTILINE,
        ).rstrip("\n")
        if body:
            if not body.lstrip().startswith("## "):
                text += f"\n\n## {_now_display()} · {title or '对话要点'}\n\n"
            else:
                text += "\n\n"
            text += f"{body}\n"

    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8")

    return {
        "name": safe,
        "file_name": path.name,
        "size": path.stat().st_size,
        "content": text,
    }


def delete_memory(name: str) -> bool:
    path = _memory_path(name)
    if not path.is_file():
        return False
    path.unlink()
    return True
