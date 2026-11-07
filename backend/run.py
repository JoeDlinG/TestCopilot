"""AITestLab backend server launcher (cross-platform, PyInstaller-aware).

Entry point for both ``python run.py`` (dev) and the packaged ``AITestLab.exe``.

Behaviour:
  * ``--restart-helper`` — run the detached restart helper (kill old server on
    the port, then relaunch), used by the "Reset Software" button.
  * otherwise — chdir to the writable data directory and start uvicorn.

Writable data (SQLite DB, logs, reports, exports) lives in a per-user folder
in packaged builds so the app never needs write access to Program Files.
"""
import os
import sys
from pathlib import Path


def _data_dir() -> str:
    """Resolve the writable runtime data directory."""
    if getattr(sys, "frozen", False):
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        d = os.path.join(base, "AITestLab")
        os.makedirs(d, exist_ok=True)
        return d
    # Dev: run relative to the backend/ directory (where this file lives).
    return os.path.dirname(os.path.abspath(__file__))


def _port() -> int:
    """HTTP port for the UI + API.

    Defaults to 8000. ``AITESTLAB_PORT`` overrides it, which is the escape hatch
    when another copy of the app (or anything else) already owns 8000 and the
    user cannot close it.
    """
    raw = os.environ.get("AITESTLAB_PORT", "").strip()
    if raw.isdigit() and 1 <= int(raw) <= 65535:
        return int(raw)
    return 8000


def _http_opener():
    """Bypass system proxies — a proxy must never intercept localhost probes."""
    import urllib.request

    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _probe_app(port: int) -> bool:
    """True when an already-running AITestLab answers on *port*."""
    import json

    try:
        with _http_opener().open(
            f"http://127.0.0.1:{port}/api/health", timeout=1.0
        ) as resp:
            if resp.status != 200:
                return False
            return json.loads(resp.read().decode("utf-8")).get("status") == "ok"
    except Exception:
        return False


def _port_in_use(port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _negotiate_port(preferred: int) -> int:
    """Reuse an existing instance, else take the first free port.

    Starting a second uvicorn on an occupied port leaves an orphan process and
    lets an older build keep serving a stale UI (the first-launch blank page).
    """
    for port in range(preferred, preferred + 11):
        if not _port_in_use(port):
            return port
        if _probe_app(port):
            print(f"AITestLab is already running on port {port}; reusing it.")
            if os.environ.get("AITESTLAB_NO_BROWSER") != "1":
                _open_browser_now(port)
            sys.exit(0)
    raise RuntimeError(
        f"No free port in {preferred}..{preferred + 10}. "
        "Set AITESTLAB_PORT to an unused port."
    )


def _open_browser_now(port: int) -> None:
    import webbrowser

    try:
        webbrowser.open(f"http://localhost:{port}")
    except Exception:
        pass


def main() -> None:
    # Detached restart helper: kill anything on the port, then relaunch.
    if "--restart-helper" in sys.argv:
        import restart_helper
        restart_helper.main()
        sys.exit(0)

    # Detached update helper: wait for this process to exit, swap files, relaunch
    # (issue #25). Same trick as the restart helper — a frozen build has no
    # separate interpreter, so the exe re-enters here with a flag.
    if "--update-helper" in sys.argv:
        import update_helper
        rest = [a for a in sys.argv[1:] if a != "--update-helper"]
        sys.exit(update_helper.main(rest))

    os.chdir(_data_dir())

    port = _negotiate_port(_port())
    # Keep helpers (restart/update) on the same port we actually bound.
    os.environ["AITESTLAB_PORT"] = str(port)

    import uvicorn

    if getattr(sys, "frozen", False):
        # Packaged build: pass the app object (import string won't resolve
        # inside a PyInstaller bundle) and disable reload.
        from app.main import app

        # Convenience: open the browser once the server is up.
        _open_browser_later(port=port)

        uvicorn.run(app, host="0.0.0.0", port=port, reload=False, log_level="info")
    else:
        # Dev: import string enables reload; CWD is already backend/.
        uvicorn.run(
            "app.main:app", host="0.0.0.0", port=port, reload=True, log_level="info"
        )


def _open_browser_later(port: int = 8000, timeout: float = 60.0) -> None:
    """Open the browser only AFTER the backend actually answers /api/health.

    A fixed 2.5-second nap guesses at boot time: on a slow machine the browser
    opened before uvicorn was ready and showed an empty page ("refresh fixes
    it"). Probing is deterministic, and the opener bypasses system proxies.

    ``AITESTLAB_NO_BROWSER=1`` suppresses it (packaging smoke tests drive the
    UI headlessly and must not hijack the desktop).
    """
    if os.environ.get("AITESTLAB_NO_BROWSER") == "1":
        return

    import threading
    import time

    def _open():
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if _probe_app(port):
                _open_browser_now(port)
                return
            time.sleep(0.3)
        print(f"[boot] /api/health did not answer within {timeout:.0f}s; "
              "browser not opened")

    threading.Thread(target=_open, daemon=True).start()


if __name__ == "__main__":
    main()
