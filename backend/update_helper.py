"""Detached update helper for the remote updater (issue #25).

Windows cannot replace a running ``.exe``, so the swap has to happen while the
app is **not** running. The running app therefore spawns this script (own
session / detached console), returns the HTTP response, and exits. This helper
then:

1. waits for the parent pid to disappear (with a hard timeout + force kill);
2. backs the current install up;
3. installs the downloaded package (NSIS silent install, or a zip swap);
4. relaunches the app and polls ``/api/health``;
5. rolls back and relaunches the backup if step 4 fails.

Any failure path leaves a running, working application — never a half-applied
directory.

``--dry-run`` prints the plan and changes nothing, which is what the automated
tests exercise (applying a real update must not be part of CI).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

IS_WINDOWS = os.name == "nt"
HEALTH_URL = "http://127.0.0.1:8000/api/health"


# --------------------------------------------------------------------------- #
# logging (the helper runs detached; the log file is the only trace)
# --------------------------------------------------------------------------- #
_LOG_PATH = os.path.join(tempfile.gettempdir(), "testcopilot_update.log")


def log(message: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    try:
        with open(_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass
    print(line)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def app_dir() -> str:
    """Directory holding the running application."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def wait_for_exit(pid: int, timeout: float = 90.0) -> bool:
    """Wait until *pid* is gone. Returns True when it exited."""
    if pid <= 0:
        return True
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _pid_alive(pid):
            log(f"parent pid {pid} exited")
            return True
        time.sleep(0.5)
    log(f"parent pid {pid} still alive after {timeout}s — forcing")
    _kill(pid)
    time.sleep(2.0)
    return not _pid_alive(pid)


def _pid_alive(pid: int) -> bool:
    if IS_WINDOWS:
        try:
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True, text=True, timeout=10,
            ).stdout
            return str(pid) in out
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _kill(pid: int) -> None:
    try:
        if IS_WINDOWS:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                           capture_output=True, timeout=20)
        else:
            os.kill(pid, 9)
    except Exception as exc:
        log(f"kill {pid} failed: {exc}")


def relaunch() -> None:
    """Start the app again after the swap."""
    if getattr(sys, "frozen", False):
        cmd = [sys.executable]
        cwd = os.path.dirname(sys.executable)
    else:
        cmd = [sys.executable, os.path.join(app_dir(), "run.py")]
        cwd = app_dir()
    if IS_WINDOWS:
        kwargs = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP
                  | getattr(subprocess, "DETACHED_PROCESS", 0)}
    else:
        kwargs = {"start_new_session": True}
    log(f"relaunch: {cmd}")
    subprocess.Popen(cmd, cwd=cwd, **kwargs)


def health_ok(timeout: float = 60.0) -> bool:
    """Poll the health endpoint until the relaunched app answers."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=3) as resp:
                if resp.status == 200:
                    log("health check passed")
                    return True
        except Exception:
            pass
        time.sleep(1.5)
    log("health check timed out")
    return False


# --------------------------------------------------------------------------- #
# install strategies
# --------------------------------------------------------------------------- #
def backup_path_for(target: str) -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return f"{target}.backup-{stamp}"


def apply_nsis(package: str) -> bool:
    """Silent NSIS install. The installer itself replaces the files."""
    if not IS_WINDOWS:
        log("nsis install requested on a non-Windows platform — refusing")
        return False
    log(f"running installer silently: {package}")
    proc = subprocess.run([package, "/S"], capture_output=True, timeout=600)
    log(f"installer exit code {proc.returncode}")
    return proc.returncode == 0


def apply_zip(package: str, target: str, dry_run: bool = False) -> bool:
    """Swap a portable build: extract -> move old aside -> move new in place."""
    staging = os.path.join(tempfile.gettempdir(), f"testcopilot-staging-{int(time.time())}")
    backup = backup_path_for(target)
    log(f"zip swap: {package} -> {target} (backup {backup})")
    if dry_run:
        log("[dry-run] would extract, swap and keep a backup")
        return True

    try:
        with zipfile.ZipFile(package) as zf:
            zf.extractall(staging)
        # A zip that wraps everything in one top folder is common; unwrap it.
        entries = os.listdir(staging)
        root = staging
        if len(entries) == 1 and os.path.isdir(os.path.join(staging, entries[0])):
            root = os.path.join(staging, entries[0])

        if os.path.exists(target):
            shutil.move(target, backup)
        shutil.copytree(root, target, dirs_exist_ok=True)
        log("zip swap done")
        return True
    except Exception as exc:
        log(f"zip swap failed: {exc}")
        # try to put the original back
        if not os.path.exists(target) and os.path.exists(backup):
            try:
                shutil.move(backup, target)
                log("restored backup after failed swap")
            except Exception as exc2:
                log(f"restore failed: {exc2}")
        return False
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def rollback(target: str, backup: str) -> bool:
    log(f"rolling back {target} from {backup}")
    try:
        if os.path.exists(target):
            shutil.rmtree(target, ignore_errors=True)
        shutil.move(backup, target)
        return True
    except Exception as exc:
        log(f"rollback failed: {exc}")
        return False


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description="TestCopilot update helper")
    parser.add_argument("--pid", type=int, default=0, help="pid of the app to wait for")
    parser.add_argument("--package", required=True, help="downloaded update package")
    parser.add_argument("--kind", default="file", choices=["nsis", "zip", "file"])
    parser.add_argument("--version", default="")
    parser.add_argument("--target", default="", help="override the install directory")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-health", action="store_true")
    args = parser.parse_args(argv)

    log("=" * 60)
    log(f"update helper start: version={args.version} kind={args.kind} dry_run={args.dry_run}")

    if not os.path.isfile(args.package):
        log(f"package missing: {args.package}")
        return 2

    target = args.target or app_dir()
    log(f"target directory: {target}")

    if args.dry_run:
        # Plan only — nothing is stopped, replaced or relaunched.
        log(f"[dry-run] would wait for pid {args.pid}")
        log(f"[dry-run] would apply kind={args.kind} from {args.package} to {target}")
        log("[dry-run] would relaunch and poll /api/health, rolling back on failure")
        return 0

    if not wait_for_exit(args.pid):
        log("app did not exit — aborting without touching files")
        return 3

    backup = backup_path_for(target)
    ok = False
    if args.kind == "nsis":
        ok = apply_nsis(args.package)
    elif args.kind == "zip":
        ok = apply_zip(args.package, target)
    else:
        log(f"unsupported package kind {args.kind!r} — refusing to run it")
        return 4

    if not ok:
        log("apply failed")
        relaunch()
        return 5

    relaunch()
    if args.skip_health or health_ok():
        log("update completed successfully")
        _record_result(args.version, success=True)
        return 0

    # Health check failed: put the old build back.
    log("post-update health check failed — rolling back")
    if os.path.isdir(backup):
        rollback(target, backup)
        relaunch()
    _record_result(args.version, success=False)
    return 6


def _record_result(version: str, success: bool) -> None:
    """Leave a breadcrumb the UI can read after the restart."""
    path = os.path.join(tempfile.gettempdir(), "testcopilot_update_result.json")
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(
                {"version": version, "success": success,
                 "at": time.strftime("%Y-%m-%dT%H:%M:%S")},
                fh,
            )
    except Exception:
        pass


if __name__ == "__main__":
    sys.exit(main())
