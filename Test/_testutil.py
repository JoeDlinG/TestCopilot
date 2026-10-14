#!/usr/bin/env python3
"""Shared helpers for the scripts in ``Test/``.

Two long-standing problems are solved here (GitHub issue #9):

1. **CWD dependence** — scripts used to ``os.chdir()`` into ``backend/`` so that
   ``import app...`` worked. That made the result depend on where the command was
   run from *and* mutated the process CWD, which then broke any relative paths
   the test itself used. Importing via ``sys.path`` is enough.

2. **``StopIteration`` without hardware** — most scripts talk to a running
   backend with real instruments attached and grabbed the device with a bare
   ``next(d for d in devices if ...)``. With no hardware that raised
   ``StopIteration`` and the whole run aborted. :func:`find_device` returns
   ``None`` instead, and :class:`SkipCheck` lets a script report "skipped"
   rather than "failed".
"""
import json
import os
import sys


class SkipCheck(Exception):
    """Raised to skip a check because its prerequisite is missing."""


def backend_dir() -> str:
    """Absolute path of the ``backend/`` directory (works from any CWD)."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")


def add_backend_to_path() -> str:
    """Make ``import app...`` work **without** changing the working directory."""
    path = os.path.abspath(backend_dir())
    if path not in sys.path:
        sys.path.insert(0, path)
    return path


def repo_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def find_device(items, protocol: str):
    """Return the first device with *protocol*, or ``None`` when absent.

    Never raises ``StopIteration`` — callers decide whether to skip or fail.
    """
    for d in items or []:
        if d.get("protocol") == protocol:
            return d
    return None


def require_device(items, protocol: str):
    """Return the device or raise :class:`SkipCheck` when it is not attached."""
    dev = find_device(items, protocol)
    if dev is None:
        raise SkipCheck(f"未找到 protocol={protocol} 的设备（需要硬件）")
    return dev


def ensure_connected(base_url: str, dev, timeout: int = 30) -> bool:
    """Try to connect *dev*; return ``False`` when it cannot be reached.

    Hardware tests used to plough ahead with a disconnected instrument and then
    assert on empty data, which looked like a product bug. They now skip.
    """
    import requests

    if dev.get("status") == "connected":
        return True
    try:
        resp = requests.post(
            f"{base_url}/devices/connect",
            json={"device_id": dev["id"]},
            timeout=timeout,
        )
        if resp.status_code >= 400:
            return False
        info = requests.get(f"{base_url}/devices/{dev['id']}", timeout=timeout)
        return (info.json().get("data") or {}).get("status") == "connected"
    except Exception:
        return False


def samples_of(parsed):
    """Flatten ``parsed_results`` into a list of samples.

    ``parsed_results`` is either the per-reply series object
    ``{"count": N, "samples": [[field, ...], ...], "last": [...]}`` or, in legacy
    rows, a bare flat list (= a single sample).  Tests that assumed the legacy
    shape crashed with ``TypeError: string indices must be integers`` because
    ``extend()`` over a dict yields its *keys*.
    """
    if isinstance(parsed, str):
        try:
            parsed = json.loads(parsed)
        except (ValueError, TypeError):
            return []
    if isinstance(parsed, dict):
        samples = parsed.get("samples")
        if isinstance(samples, list) and samples:
            return [s for s in samples if isinstance(s, list)]
        last = parsed.get("last")
        return [last] if isinstance(last, list) else []
    if isinstance(parsed, list):
        return [parsed] if all(isinstance(x, dict) for x in parsed) else []
    return []


def flat_fields(parsed):
    """Every parsed field dict across all samples of one step."""
    fields = []
    for sample in samples_of(parsed):
        fields.extend([f for f in sample if isinstance(f, dict)])
    return fields
