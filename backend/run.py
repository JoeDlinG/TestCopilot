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


def _browser_candidates() -> list:
    """Locate a Chromium-family browser able to open a dedicated app window.

    Order: explicit override, Windows App Paths registry, common install
    locations, then PATH. Chrome / Edge / Brave all support ``--app=`` and an
    isolated ``--user-data-dir``.
    """
    import shutil

    candidates = []
    override = os.environ.get("AITESTLAB_BROWSER_EXE", "").strip().strip('"')
    if override and os.path.isfile(override):
        candidates.append(override)

    if os.name == "nt":
        try:
            import winreg
            for app in ("msedge.exe", "chrome.exe", "brave.exe"):
                key = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{app}"
                for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                    try:
                        with winreg.OpenKey(root, key) as handle:
                            value, _ = winreg.QueryValueEx(handle, "")
                            if value and os.path.isfile(value):
                                candidates.append(value)
                    except OSError:
                        continue
        except Exception:
            pass
        for prefix in (
            os.environ.get("ProgramFiles(x86)", ""),
            os.environ.get("ProgramFiles", ""),
            os.environ.get("LOCALAPPDATA", ""),
        ):
            for rel in (
                r"Microsoft\Edge\Application\msedge.exe",
                r"Google\Chrome\Application\chrome.exe",
                r"BraveSoftware\Brave-Browser\Application\brave.exe",
            ):
                if prefix:
                    path = os.path.join(prefix, rel)
                    if os.path.isfile(path):
                        candidates.append(path)
    for name in ("msedge", "chrome", "google-chrome", "chromium", "brave-browser"):
        found = shutil.which(name)
        if found:
            candidates.append(found)

    seen, unique = set(), []
    for path in candidates:
        key = os.path.normcase(os.path.abspath(path))
        if key not in seen and os.path.isfile(path):
            seen.add(key)
            unique.append(path)
    return unique


def _open_app_window(url: str) -> bool:
    """Open the UI in its own window instead of a tab of the daily browser.

    ``--app=`` removes the tab strip and address bar. A private
    ``--user-data-dir`` is the important part: with the default profile,
    Windows hands the URL to an ALREADY RUNNING Chrome/Edge process, which
    simply opens another tab in the user's existing window (or reuses that
    window). A separate profile forces a separate browser process/window that
    belongs to AITestLab alone.

    Set ``AITESTLAB_BROWSER_EXE`` to pin a browser, or
    ``AITESTLAB_APP_WINDOW=0`` to keep the legacy tab behaviour.
    """
    import subprocess

    profile = os.path.join(_data_dir(), "BrowserProfile")
    try:
        os.makedirs(profile, exist_ok=True)
    except OSError:
        return False
    for exe in _browser_candidates():
        args = [
            exe,
            f"--app={url}",
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-session-crashed-bubble",
            "--window-size=1440,900",
        ]
        try:
            subprocess.Popen(
                args,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
            print(f"[boot] opened dedicated app window via {os.path.basename(exe)}: {url}")
            return True
        except OSError:
            continue
    return False


def _open_browser_now(port: int) -> None:
    """Open the UI, preferring a dedicated standalone window.

    ``127.0.0.1`` avoids the ::1 / system-proxy traps of ``localhost``. If no
    Chromium browser is available, fall back to a new window via the standard
    library, then the OS association and finally ``cmd /c start``.
    """
    import os as _os
    import subprocess
    import webbrowser

    if os.environ.get("AITESTLAB_APP_WINDOW", "1") != "0":
        if _open_app_window(f"http://127.0.0.1:{port}/"):
            return
        print("[boot] no Chromium browser found; falling back to a browser window")

    for host in ("127.0.0.1", "localhost"):
        url = f"http://{host}:{port}/"
        try:
            if webbrowser.open(url, new=1, autoraise=True):
                print(f"[boot] opened {url} in a new browser window")
                return
        except Exception:
            pass
    if _os.name == "nt":
        for url in (f"http://127.0.0.1:{port}/",):
            try:
                _os.startfile(url)  # type: ignore[attr-defined]
                print(f"[boot] opened {url} via shell association")
                return
            except Exception:
                pass
            try:
                subprocess.Popen(
                    ["cmd", "/c", "start", "", url],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                print(f"[boot] opened {url} via cmd start")
                return
            except Exception:
                pass
    print(f"[boot] could not start a browser; please open http://127.0.0.1:{port}/")


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
