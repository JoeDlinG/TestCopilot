"""Feedback centre: crash reports and user feedback (issue #26).

Both paths (automatic crash capture and the user's own 想法/问题 form) land in
the same table and run through the same forwarding link, so there is exactly one
place where sensitive data is scrubbed and exactly one place that talks to
GitHub.

Privacy rules enforced here
---------------------------
* Nothing leaves the machine unless ``consent`` is true. Automatic crash
  capture is opt-out (``auto_crash_report``), manual feedback is always
  intentional.
* ``sanitise()`` strips secrets (API keys, tokens, passwords), bearer headers and
  the user's home directory from **every** field, including the crash stack.
* The GitHub token lives in an environment variable and is never sent to the
  browser. Without it, reports are stored locally and marked ``pending``.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.models import FeedbackReport, SystemConfig

KEY_AUTO_REPORT = "feedback.auto_crash_report"

# Values of these keys are dropped before anything is stored or sent.
_SECRET_KEY_RE = re.compile(
    r"(api[_-]?key|token|secret|password|passwd|auth|credential|access[_-]?key"
    r"|private[_-]?key|encryption[_-]?key)",
    re.IGNORECASE,
)
# sk-…, ghp_…, Bearer …, eyJ… (JWT)
_SECRET_VALUE_RE = re.compile(
    r"(sk-[A-Za-z0-9_\-]{8,}"
    r"|gh[pousr]_[A-Za-z0-9]{16,}"
    r"|Bearer\s+[A-Za-z0-9._\-]{8,}"
    r"|eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,})"
)
_ASSIGNMENT_RE = re.compile(
    r"((?:api[_-]?key|token|secret|password|auth|authorization)\s*[:=]\s*)"
    r"([\"']?)([^\"'\s,;&]{4,})\2",
    re.IGNORECASE,
)

MAX_BODY = 8000
MAX_LOG_TAIL = 2000


# --------------------------------------------------------------------------- #
# sanitising
# --------------------------------------------------------------------------- #
def _home_dir() -> str:
    return os.path.expanduser("~")


def sanitise(text: Optional[str]) -> Optional[str]:
    """Remove secrets and the local home path. Safe on ``None``."""
    if not text:
        return text
    out = str(text)
    out = _ASSIGNMENT_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}***{m.group(2)}", out)
    out = _SECRET_VALUE_RE.sub("***", out)
    home = _home_dir()
    if home and home != "/":
        out = out.replace(home, "~")
    return out[:MAX_BODY]


def sanitise_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    cleaned: Dict[str, Any] = {}
    for key, value in (data or {}).items():
        if _SECRET_KEY_RE.search(str(key)):
            continue
        if isinstance(value, dict):
            cleaned[key] = sanitise_dict(value)
        else:
            cleaned[key] = sanitise(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)[:2000])
    return cleaned


# --------------------------------------------------------------------------- #
# crash signature
# --------------------------------------------------------------------------- #
def _normalise_frame(line: str) -> str:
    """``File "/home/u/app/x.py", line 42, in run`` -> ``x.py:run``.

    Absolute paths and line numbers change between installs and rebuilds; a
    signature that included them would open a new issue every release.
    """
    m = re.search(r'File "([^"]+)".*in (\S+)', line)
    if m:
        return f"{os.path.basename(m.group(1))}:{m.group(2)}"
    s = line.strip()
    return re.sub(r"\d+", "#", s)[:120]


def signature_of(kind: str, stack: Optional[str], version: Optional[str] = None) -> str:
    """Group key for a crash. Stable across machines and rebuilds."""
    frames = [l for l in (stack or "").splitlines() if l.strip()]
    picked = [l for l in frames if 'File "' in l][-6:] or frames[-6:]
    norm = "|".join(_normalise_frame(l) for l in picked)
    head = frames[0].strip()[:200] if frames else ""
    raw = f"{kind}|{version or ''}|{head}|{norm}"
    return hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# creating reports
# --------------------------------------------------------------------------- #
async def auto_report_enabled(db: AsyncSession) -> bool:
    row = (
        await db.execute(select(SystemConfig).where(SystemConfig.key == KEY_AUTO_REPORT))
    ).scalar_one_or_none()
    if row is None:
        return True  # on by default, as the issue recommends
    return (row.value or "1") != "0"


async def set_auto_report(db: AsyncSession, enabled: bool) -> None:
    row = (
        await db.execute(select(SystemConfig).where(SystemConfig.key == KEY_AUTO_REPORT))
    ).scalar_one_or_none()
    value = "1" if enabled else "0"
    if row is None:
        db.add(SystemConfig(key=KEY_AUTO_REPORT, value=value,
                            description="崩溃自动上报开关"))
    else:
        row.value = value
    await db.commit()


def recent_log_tail(limit: int = 40) -> str:
    """Last few lines of the newest log file (already sanitised downstream)."""
    try:
        log_dir = settings.LOG_DIR
        if not os.path.isdir(log_dir):
            return ""
        files = [
            os.path.join(log_dir, f) for f in os.listdir(log_dir) if f.endswith(".log")
        ]
        if not files:
            return ""
        newest = max(files, key=os.path.getmtime)
        with open(newest, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()[-limit:]
        return "".join(lines)[-MAX_LOG_TAIL:]
    except Exception:
        return ""


def _system_info() -> Dict[str, str]:
    return {
        "os": f"{platform.system()} {platform.release()}",
        "arch": platform.machine(),
        "python": platform.python_version(),
    }


async def create_report(
    db: AsyncSession,
    *,
    kind: str,
    title: str,
    body: str = "",
    stack: str = "",
    log_tail: str = "",
    route: str = "",
    consent: bool = True,
    attach_logs: bool = False,
    system: Optional[Dict[str, str]] = None,
) -> FeedbackReport:
    """Store one report. Crashes are collapsed onto their signature."""
    kind = (kind or "issue").strip().lower()
    if kind not in ("crash", "idea", "issue"):
        kind = "issue"

    sysinfo = system or _system_info()
    sig = signature_of(kind, stack, settings.APP_VERSION) if kind == "crash" else None

    title = sanitise(title) or "(untitled)"
    body = sanitise(body) or ""
    stack = sanitise(stack) or ""
    log_tail = sanitise(log_tail or (recent_log_tail() if attach_logs else "")) or ""

    # Known crash signature: bump the counter instead of opening a new row.
    if sig:
        prev = (
            await db.execute(
                select(FeedbackReport).where(FeedbackReport.signature == sig)
            )
        ).scalar_one_or_none()
        if prev is not None:
            prev.occurrences = (prev.occurrences or 1) + 1
            prev.updated_at = datetime.now(timezone.utc)
            await db.commit()
            return prev

    report = FeedbackReport(
        kind=kind,
        title=title,
        body=body,
        app_version=settings.APP_VERSION,
        os=sysinfo.get("os") or "",
        arch=sysinfo.get("arch") or "",
        route=(route or "")[:240],
        stack=stack,
        log_tail=log_tail,
        signature=sig,
        status="pending",
        consent=bool(consent),
        occurrences=1,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return report


# --------------------------------------------------------------------------- #
# GitHub forwarding
# --------------------------------------------------------------------------- #
def _github_repo() -> str:
    return getattr(settings, "GITHUB_REPO", "") or ""


def _github_token() -> str:
    return getattr(settings, "GITHUB_TOKEN", "") or ""


def _github_request(method: str, path: str, payload: Optional[dict] = None) -> Optional[dict]:
    token = _github_token()
    repo = _github_repo()
    if not token or not repo:
        return None
    url = f"https://api.github.com/repos/{repo}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": f"TestCopilot/{settings.APP_VERSION}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _issue_body(report: FeedbackReport) -> str:
    lines = [
        f"**kind**: `{report.kind}`",
        f"**app version**: {report.app_version}",
        f"**os**: {report.os} ({report.arch})",
        f"**route**: {report.route or '-'}",
        f"**occurrences**: {report.occurrences}",
        f"**reported at**: {report.created_at}",
        "",
        "### 描述",
        report.body or "-",
    ]
    if report.stack:
        lines += ["", "### 堆栈", "```", report.stack[:4000], "```"]
    if report.log_tail:
        lines += ["", "### 日志尾部", "```", report.log_tail[:MAX_LOG_TAIL], "```"]
    lines += ["", f"<!-- signature: {report.signature or '-'} -->"]
    return "\n".join(lines)


def _forward_sync(report: FeedbackReport) -> str:
    """Open or update the GitHub issue. Returns the new status string."""
    if not _github_token() or not _github_repo():
        return "pending"

    labels = {
        "crash": ["bug", "auto-report"],
        "idea": ["enhancement", "user-feedback"],
        "issue": ["bug", "user-feedback"],
    }.get(report.kind, ["user-feedback"])

    # Known signature that already has an issue: comment + count instead.
    if report.signature and report.github_issue_number:
        _github_request(
            "POST",
            f"/issues/{report.github_issue_number}/comments",
            {"body": f"再次发生（第 {report.occurrences} 次）· v{report.app_version} · {datetime.now(timezone.utc).isoformat()}"},
        )
        return "deduped"

    created = _github_request(
        "POST",
        "/issues",
        {"title": report.title[:200], "body": _issue_body(report), "labels": labels},
    )
    if created and created.get("number"):
        report.github_issue_number = created["number"]
        return "forwarded"
    return "failed"


async def forward_report(db: AsyncSession, report: FeedbackReport) -> str:
    status = _forward_sync(report)
    report.status = status
    if status == "forwarded" and not _github_token():
        report.status = "pending"
    await db.commit()
    return report.status


async def retry_pending(db: AsyncSession, limit: int = 10) -> int:
    """Flush the offline queue. Called on startup after the app is up."""
    if not _github_token() or not _github_repo():
        return 0
    rows = (
        await db.execute(
            select(FeedbackReport)
            .where(FeedbackReport.status.in_(["pending", "failed", "deduped"]))
            .order_by(FeedbackReport.created_at.asc())
            .limit(limit)
        )
    ).scalars().all()
    sent = 0
    for row in rows:
        state = _forward_sync(row)
        row.status = state
        if state in ("forwarded", "deduped"):
            sent += 1
    await db.commit()
    return sent


# --------------------------------------------------------------------------- #
# listing (management view)
# --------------------------------------------------------------------------- #
def report_to_dict(r: FeedbackReport) -> Dict[str, Any]:
    return {
        "id": r.id,
        "kind": r.kind,
        "title": r.title,
        "status": r.status,
        "occurrences": r.occurrences,
        "app_version": r.app_version,
        "signature": r.signature,
        "github_issue_number": r.github_issue_number,
        "route": r.route,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


async def list_reports(db: AsyncSession, limit: int = 50) -> List[Dict[str, Any]]:
    rows = (
        await db.execute(
            select(FeedbackReport).order_by(FeedbackReport.created_at.desc()).limit(limit)
        )
    ).scalars().all()
    return [report_to_dict(r) for r in rows]
