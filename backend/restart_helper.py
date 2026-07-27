"""Detached backend restart helper for the "Reset Software" UI button.

The web endpoint spawns this process (in its own session, detached from the
live server) which, after a short grace period, kills any running backend
processes and relaunches a fresh backend.

Why the port-based + pattern-based kill:
When the backend is launched with ``uvicorn.run(..., reload=True)`` (see
``run.py``), uvicorn spawns a "reloader" parent that supervises a separate
worker process. The worker is the one actually bound to port 8000. Killing
only the ``run.py`` parent therefore leaves the worker (and the port binding)
alive, so the old server never really stops and the relaunch fails with
"address already in use". To fully reset we must kill BOTH the reloader
parent and the worker, and as a final backstop free the port itself.
"""
import os
import re
import sys
import time
import signal
import subprocess

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PORT = 8000


def _configured_port() -> int:
    """Best-effort read of the configured backend port (defaults to 8000)."""
    try:
        # Import lazily so this helper never crashes the restart flow.
        sys.path.insert(0, BACKEND_DIR)
        from app.core.config import settings
        port = getattr(settings, "PORT", None) or getattr(settings, "APP_PORT", None)
        if isinstance(port, int) and 1 <= port <= 65535:
            return port
    except Exception:
        pass
    return DEFAULT_PORT


def find_pids_on_port(port: int) -> set:
    """Return PIDs currently listening on ``port`` using any available tool."""
    pids: set = set()

    # 1) ss (iproute2) — parse the users:(("prog",pid=NNN,...)) field.
    try:
        out = subprocess.run(
            ["ss", "-ltnp", f"sport = :{port}"],
            capture_output=True, text=True, timeout=5,
        ).stdout
        for line in out.splitlines():
            for m in re.findall(r"pid=(\d+)", line):
                pids.add(int(m))
    except Exception:
        pass

    # 2) lsof — simplest, returns just PIDs.
    if not pids:
        try:
            out = subprocess.run(
                ["lsof", f"-ti:{port}"],
                capture_output=True, text=True, timeout=5,
            ).stdout
            for tok in out.split():
                try:
                    pids.add(int(tok))
                except ValueError:
                    pass
        except Exception:
            pass

    # 3) fuser — last resort.
    if not pids:
        try:
            out = subprocess.run(
                ["fuser", f"{port}/tcp"],
                capture_output=True, text=True, timeout=5,
            ).stdout
            for tok in out.split():
                try:
                    pids.add(int(tok))
                except ValueError:
                    pass
        except Exception:
            pass

    return pids


def kill_pid_tree(pid: int) -> None:
    """Kill a PID and, if possible, its entire process group."""
    # Prefer killing the process group so supervisor + worker die together.
    try:
        pgid = os.getpgid(pid)
        if pgid and pgid > 1:
            os.killpg(pgid, signal.SIGKILL)
            return
    except (ProcessLookupError, PermissionError):
        pass
    try:
        os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def main() -> None:
    # Give the HTTP response time to flush and the old worker to finish.
    time.sleep(1.5)

    port = _configured_port()

    # (a) Kill the launcher / reloader parent.
    os.system("pkill -9 -f 'run.py' 2>/dev/null || true")
    # (b) Kill the uvicorn worker(s) spawned for this app.
    os.system("pkill -9 -f 'app.main:app' 2>/dev/null || true")

    # (c) Backstop: explicitly free the listening port so the relaunch
    #     cannot fail with "address already in use".
    for pid in find_pids_on_port(port):
        kill_pid_tree(pid)

    # Small settle so the OS releases the socket.
    time.sleep(1.0)

    # Relaunch a fresh backend instance.
    log_path = os.path.join("/tmp", "aitestlab_backend.log")
    with open(log_path, "a") as logf:
        subprocess.Popen(
            [sys.executable, "run.py"],
            cwd=BACKEND_DIR,
            start_new_session=True,
            stdout=logf,
            stderr=subprocess.STDOUT,
        )


if __name__ == "__main__":
    main()
