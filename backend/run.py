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


def main() -> None:
    # Detached restart helper: kill anything on the port, then relaunch.
    if "--restart-helper" in sys.argv:
        import restart_helper
        restart_helper.main()
        sys.exit(0)

    os.chdir(_data_dir())

    import uvicorn

    if getattr(sys, "frozen", False):
        # Packaged build: pass the app object (import string won't resolve
        # inside a PyInstaller bundle) and disable reload.
        from app.main import app

        # Convenience: open the browser once the server is up.
        _open_browser_later()

        uvicorn.run(app, host="0.0.0.0", port=8000, reload=False, log_level="info")
    else:
        # Dev: import string enables reload; CWD is already backend/.
        uvicorn.run(
            "app.main:app", host="0.0.0.0", port=8000, reload=True, log_level="info"
        )


def _open_browser_later(delay: float = 2.5) -> None:
    """Open the default browser to the app after the server finishes booting."""
    import threading
    import webbrowser

    def _open():
        import time
        time.sleep(delay)
        try:
            webbrowser.open("http://localhost:8000")
        except Exception:
            pass

    threading.Thread(target=_open, daemon=True).start()


if __name__ == "__main__":
    main()
