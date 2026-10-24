"""Remote update service (issue #25).

Design rules taken from the issue:

* **Consent is mandatory** — nothing is downloaded or installed until the user
  presses 立即更新. ``auto_download`` only pre-fetches the bytes; applying still
  needs an explicit call.
* **Never execute an unverified binary** — the downloaded file must match the
  SHA256 from the manifest. A mismatch is discarded, never run.
* **Never block the app** — a failed check (offline, bad feed, 500) degrades to
  "no update" and must not surface as an error in normal use.
* **No silent churn** — an ignored version stays ignored until a newer one
  appears.

Feed format (``version.json``), or ``gh:owner/repo`` to read GitHub Releases::

    {
      "version": "2.3.0",
      "notes": "…changelog…",
      "mandatory": false,
      "published_at": "2026-11-01T00:00:00Z",
      "assets": [
        {"platform": "windows", "kind": "nsis",
         "url": "https://…/TestCopilot-Setup-v2.3.0.exe",
         "sha256": "…", "size": 12345678}
      ]
    }
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.models import SystemConfig

# ---- SystemConfig keys -----------------------------------------------------
KEY_AUTO_CHECK = "update.auto_check"
KEY_AUTO_DOWNLOAD = "update.auto_download"
KEY_IGNORED_VERSION = "update.ignored_version"
KEY_FEED_URL = "update.feed_url"

# A finished download is only handed to the installer through this token, so the
# client can never point the installer at an arbitrary file path.
_DL_STATE: Dict[str, Any] = {
    "status": "idle",          # idle | downloading | verifying | ready | error
    "received": 0,
    "total": 0,
    "error": None,
    "token": None,
    "path": None,
    "version": None,
    "kind": None,
    "started_at": None,
    "finished_at": None,
}
_DL_LOCK = threading.Lock()

_VER_RE = re.compile(r"^[vV]?(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:[-+.]?(.*))?$")


# =========================================================================== #
# version helpers
# =========================================================================== #
def parse_version(text: Any) -> Optional[Tuple[Tuple[int, int, int], str]]:
    """``"v2.3.0-rc1"`` -> ``((2, 3, 0), "rc1")``. ``None`` when unparseable."""
    if text is None:
        return None
    m = _VER_RE.match(str(text).strip())
    if not m:
        return None
    nums = tuple(int(g) if g is not None else 0 for g in m.groups()[:3])
    return nums, (m.group(4) or "").strip()


def compare_versions(a: Any, b: Any) -> int:
    """Return 1 if *a* is newer, -1 if older, 0 if equal.

    A release beats a pre-release of the same number (``2.3.0 > 2.3.0-rc1``),
    which is the behaviour the issue's "高于/等于时不提示" expects.
    """
    pa, pb = parse_version(a), parse_version(b)
    if pa is None or pb is None:
        raise ValueError(f"cannot compare {a!r} with {b!r}")
    if pa[0] != pb[0]:
        return 1 if pa[0] > pb[0] else -1
    if pa[1] == pb[1]:
        return 0
    if not pa[1]:
        return 1
    if not pb[1]:
        return -1
    return 1 if pa[1] > pb[1] else -1


def current_platform() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def _guess_kind(name: str) -> str:
    low = name.lower()
    if low.endswith(".exe") or low.endswith(".msi"):
        return "nsis"
    if low.endswith(".zip"):
        return "zip"
    return "file"


def _normalise_asset(raw: Dict[str, Any], fallback_name: str = "") -> Dict[str, Any]:
    name = raw.get("name") or os.path.basename(
        str(raw.get("url") or raw.get("browser_download_url") or fallback_name)
    )
    url = raw.get("url") or raw.get("browser_download_url") or ""
    # GitHub sends `digest: "sha256:…"`; our own manifest sends a bare hex.
    digest = raw.get("sha256") or ""
    if not digest and isinstance(raw.get("digest"), str) and raw["digest"].startswith("sha256:"):
        digest = raw["digest"].split(":", 1)[1]
    return {
        "name": name,
        "url": url,
        "sha256": (digest or "").strip().lower(),
        "size": int(raw.get("size") or 0),
        "kind": raw.get("kind") or _guess_kind(name),
        "platform": raw.get("platform") or "",
    }


# =========================================================================== #
# manifest loading
# =========================================================================== #
def _http_json(url: str, timeout: int = 15) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json, application/json",
            "User-Agent": f"TestCopilot/{settings.APP_VERSION}",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_text(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": f"TestCopilot/{settings.APP_VERSION}"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def _load_github(owner_repo: str) -> Dict[str, Any]:
    """``gh:JoeDlinG/TestCopilot`` -> the latest published release."""
    api = f"https://api.github.com/repos/{owner_repo}/releases/latest"
    rel = _http_json(api)
    assets = [_normalise_asset(a) for a in (rel.get("assets") or [])]

    # Prefer a checksum sidecar: GitHub does not always expose `digest`.
    for asset in assets:
        if asset["name"].lower().endswith(".sha256"):
            try:
                text = _http_text(asset["url"])
                target = text.split()[0].strip().lower()
                base = os.path.basename(asset["name"])[: -len(".sha256")]
                for candidate in assets:
                    if candidate["name"] == base and not candidate["sha256"]:
                        candidate["sha256"] = target
            except Exception:
                pass
            break

    return {
        "version": (rel.get("tag_name") or "").lstrip("vV"),
        "notes": rel.get("body") or "",
        "mandatory": False,
        "published_at": rel.get("published_at"),
        "assets": [a for a in assets if not a["name"].lower().endswith(".sha256")],
        "source": api,
    }


def load_manifest(feed: str) -> Dict[str, Any]:
    """Resolve the feed into a normalised manifest. Raises on any failure."""
    feed = (feed or "").strip()
    if not feed:
        raise ValueError("no feed configured")
    if feed.startswith("gh:"):
        return _load_github(feed[3:])
    raw = _http_json(feed)
    return {
        "version": str(raw.get("version") or "").lstrip("vV"),
        "notes": raw.get("notes") or raw.get("changelog") or "",
        "mandatory": bool(raw.get("mandatory")),
        "published_at": raw.get("published_at"),
        "assets": [_normalise_asset(a) for a in (raw.get("assets") or [])],
        "source": feed,
    }


def pick_asset(manifest: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    plat = current_platform()
    assets: List[Dict[str, Any]] = manifest.get("assets") or []
    for a in assets:
        if a.get("platform") == plat:
            return a
    for a in assets:
        if not a.get("platform"):
            return a
    return None


# =========================================================================== #
# settings
# =========================================================================== #
async def get_setting(db: AsyncSession, key: str, default: Optional[str] = None) -> Optional[str]:
    row = (
        await db.execute(select(SystemConfig).where(SystemConfig.key == key))
    ).scalar_one_or_none()
    return row.value if row and row.value is not None else default


async def set_setting(
    db: AsyncSession, key: str, value: Optional[str], description: str = ""
) -> None:
    row = (
        await db.execute(select(SystemConfig).where(SystemConfig.key == key))
    ).scalar_one_or_none()
    if row is None:
        db.add(SystemConfig(key=key, value=value, description=description))
    else:
        row.value = value
    await db.commit()


async def load_settings(db: AsyncSession) -> Dict[str, Any]:
    feed = await get_setting(db, KEY_FEED_URL) or settings.UPDATE_FEED_URL or ""
    return {
        "auto_check": (await get_setting(db, KEY_AUTO_CHECK, "1")) != "0",
        "auto_download": (await get_setting(db, KEY_AUTO_DOWNLOAD, "0")) == "1",
        "ignored_version": await get_setting(db, KEY_IGNORED_VERSION, "") or "",
        "feed_url": feed,
    }


# =========================================================================== #
# check
# =========================================================================== #
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def check_for_update(db: AsyncSession) -> Dict[str, Any]:
    """Never raises: a broken feed is reported as ``reason``, not an exception."""
    cfg = await load_settings(db)
    result: Dict[str, Any] = {
        "current": settings.APP_VERSION,
        "platform": current_platform(),
        "checked_at": _now_iso(),
        "feed": cfg["feed_url"],
        "auto_check": cfg["auto_check"],
        "auto_download": cfg["auto_download"],
        "ignored_version": cfg["ignored_version"],
        "available": False,
        "reason": None,
    }
    if not cfg["feed_url"]:
        result["reason"] = "no_feed"
        return result

    try:
        manifest = load_manifest(cfg["feed_url"])
    except Exception as exc:  # offline, DNS, 404, malformed JSON …
        result["reason"] = "error"
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    latest = manifest.get("version") or ""
    if parse_version(latest) is None:
        result["reason"] = "error"
        result["error"] = f"unparseable version {latest!r}"
        return result

    try:
        cmp = compare_versions(latest, settings.APP_VERSION)
    except ValueError as exc:
        result["reason"] = "error"
        result["error"] = str(exc)
        return result

    asset = pick_asset(manifest)
    result.update(
        {
            "latest": latest,
            "notes": manifest.get("notes") or "",
            "mandatory": bool(manifest.get("mandatory")),
            "published_at": manifest.get("published_at"),
            "asset": asset,
            "ignored": cfg["ignored_version"] == latest,
            "available": cmp > 0,
            "reason": None if cmp > 0 else "up_to_date",
        }
    )
    if cmp > 0 and asset is None:
        result["available"] = False
        result["reason"] = "wrong_platform"
    return result


# =========================================================================== #
# download
# =========================================================================== #
def download_state() -> Dict[str, Any]:
    with _DL_LOCK:
        return dict(_DL_STATE)


def _set_state(**kwargs: Any) -> None:
    with _DL_LOCK:
        _DL_STATE.update(kwargs)


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 256), b""):
            h.update(chunk)
    return h.hexdigest()


def _download_worker(asset: Dict[str, Any], version: str) -> None:
    name = asset.get("name") or "update.bin"
    target = os.path.join(tempfile.gettempdir(), f"testcopilot-update-{name}")
    try:
        _set_state(status="downloading", received=0, total=asset.get("size") or 0,
                   error=None, path=None, token=None, version=version,
                   kind=asset.get("kind"), started_at=_now_iso(), finished_at=None)
        req = urllib.request.Request(
            asset["url"], headers={"User-Agent": f"TestCopilot/{settings.APP_VERSION}"}
        )
        received = 0
        with urllib.request.urlopen(req, timeout=60) as resp, open(target, "wb") as out:
            total = int(resp.headers.get("Content-Length") or 0) or (asset.get("size") or 0)
            _set_state(total=total)
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                received += len(chunk)
                _set_state(received=received)

        _set_state(status="verifying", received=received)
        expected = (asset.get("sha256") or "").lower()
        actual = sha256_of(target)
        if not expected:
            # No checksum means we cannot prove what we just downloaded. Refuse.
            os.remove(target)
            _set_state(status="error", error="missing_checksum", finished_at=_now_iso())
            return
        if actual != expected:
            os.remove(target)
            _set_state(status="error", error="checksum_mismatch", finished_at=_now_iso())
            return

        token = hashlib.sha256(f"{target}|{actual}|{time.time()}".encode()).hexdigest()[:32]
        _set_state(status="ready", token=token, path=target, error=None,
                   finished_at=_now_iso(), version=version, kind=asset.get("kind"))
    except Exception as exc:
        _set_state(status="error", error=f"{type(exc).__name__}: {exc}",
                   finished_at=_now_iso())


def start_download(asset: Dict[str, Any], version: str) -> bool:
    """Kick off a background download. Returns False when one is already running."""
    with _DL_LOCK:
        if _DL_STATE["status"] in ("downloading", "verifying"):
            return False
    t = threading.Thread(target=_download_worker, args=(asset, version), daemon=True)
    t.start()
    return True


def download_ready(token: Optional[str]) -> Optional[Dict[str, Any]]:
    with _DL_LOCK:
        if token and _DL_STATE.get("token") == token and _DL_STATE["status"] == "ready":
            return dict(_DL_STATE)
    return None


# =========================================================================== #
# apply
# =========================================================================== #
def helper_command() -> Tuple[List[str], str]:
    """(argv, cwd) for the detached update helper, dev and frozen alike."""
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if getattr(sys, "frozen", False):
        return [sys.executable, "--update-helper"], os.path.dirname(sys.executable)
    helper = os.path.join(backend_dir, "update_helper.py")
    if not os.path.exists(helper):
        raise FileNotFoundError("update helper not found")
    return [sys.executable, helper], backend_dir


def apply_update(state: Dict[str, Any]) -> None:
    """Spawn the detached helper: it waits for us to exit, then swaps files."""
    pkg = state["path"]
    kind = state.get("kind") or "file"
    cmd, cwd = helper_command()
    cmd += [
        "--pid", str(os.getpid()),
        "--package", pkg,
        "--kind", kind,
        "--version", state.get("version") or "",
    ]

    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0)
        kwargs: Dict[str, Any] = {"creationflags": flags}
    else:
        kwargs = {"start_new_session": True}

    log_path = os.path.join(tempfile.gettempdir(), "testcopilot_update.log")
    subprocess.Popen(
        cmd, cwd=cwd, stdout=open(log_path, "a"), stderr=subprocess.STDOUT, **kwargs
    )
