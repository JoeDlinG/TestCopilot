"""File-based communication logger with rotating log files.

Writes every sent/received message to timestamped log files.
Each file is capped at 10MB; when exceeded, a new file is created.
"""
from __future__ import annotations
import os
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

MAX_LOG_SIZE = 10 * 1024 * 1024  # 10 MB


class CommunicationFileLogger:
    """Rotating file logger for device communication.

    Logs are written to backend/logs/communication/<device_id>/
    Files are named: comm_<YYYYMMDD>_<seq>.log
    """

    def __init__(self, base_dir: str = ""):
        if base_dir:
            self._base_dir = base_dir
        else:
            self._base_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "logs", "communication",
            )
        os.makedirs(self._base_dir, exist_ok=True)

    def _get_device_dir(self, device_id: str) -> str:
        d = os.path.join(self._base_dir, device_id)
        os.makedirs(d, exist_ok=True)
        return d

    def _find_current_log(self, device_dir: str, today: str) -> tuple:
        """Find the latest log file for today. Returns (filepath, sequence_number)."""
        seq = 0
        # Look for existing files with today's date
        for fname in sorted(os.listdir(device_dir)):
            if fname.startswith(f"comm_{today}_") and fname.endswith(".log"):
                try:
                    n = int(fname.replace(f"comm_{today}_", "").replace(".log", ""))
                    if n > seq:
                        seq = n
                except ValueError:
                    pass

        if seq == 0:
            # No file yet for today
            seq = 1
            path = os.path.join(device_dir, f"comm_{today}_001.log")
            return path, seq

        # Check if the latest file exceeds max size
        latest = os.path.join(device_dir, f"comm_{today}_{seq:03d}.log")
        if os.path.getsize(latest) >= MAX_LOG_SIZE:
            seq += 1
            latest = os.path.join(device_dir, f"comm_{today}_{seq:03d}.log")

        return latest, seq

    def _format_entry(self, direction: str, data: str, timestamp: Optional[str] = None) -> str:
        """Format a log entry line."""
        ts = timestamp or datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        return f"[{ts}] {direction}: {data}\n"

    def log_sent(self, device_id: str, data: str, timestamp: Optional[str] = None):
        """Log a sent command."""
        try:
            device_dir = self._get_device_dir(device_id)
            today = datetime.utcnow().strftime("%Y%m%d")
            current_file, _ = self._find_current_log(device_dir, today)
            entry = self._format_entry("SEND", data, timestamp)
            with open(current_file, "a", encoding="utf-8") as f:
                f.write(entry)
            # Re-check size; if exceeded, next write will create a new file
        except Exception as e:
            logger.warning(f"Failed to write send log for {device_id}: {e}")

    def log_received(self, device_id: str, data: str, timestamp: Optional[str] = None):
        """Log a received response or data."""
        try:
            device_dir = self._get_device_dir(device_id)
            today = datetime.utcnow().strftime("%Y%m%d")
            current_file, _ = self._find_current_log(device_dir, today)
            entry = self._format_entry("RECV", data, timestamp)
            with open(current_file, "a", encoding="utf-8") as f:
                f.write(entry)
        except Exception as e:
            logger.warning(f"Failed to write recv log for {device_id}: {e}")

    def log_error(self, device_id: str, error_msg: str, command: str = "", timestamp: Optional[str] = None):
        """Log an error entry."""
        try:
            device_dir = self._get_device_dir(device_id)
            today = datetime.utcnow().strftime("%Y%m%d")
            current_file, _ = self._find_current_log(device_dir, today)
            entry = self._format_entry("ERROR", f"cmd='{command}' error='{error_msg}'", timestamp)
            with open(current_file, "a", encoding="utf-8") as f:
                f.write(entry)
        except Exception as e:
            logger.warning(f"Failed to write error log for {device_id}: {e}")

    def log_system(self, device_id: str, message: str, timestamp: Optional[str] = None):
        """Log a system event (connect, disconnect, etc.)."""
        try:
            device_dir = self._get_device_dir(device_id)
            today = datetime.utcnow().strftime("%Y%m%d")
            current_file, _ = self._find_current_log(device_dir, today)
            entry = self._format_entry("SYSTEM", message, timestamp)
            with open(current_file, "a", encoding="utf-8") as f:
                f.write(entry)
        except Exception as e:
            logger.warning(f"Failed to write system log for {device_id}: {e}")

    def get_log_files(self, device_id: str) -> list:
        """Get list of log files for a device, sorted by date descending."""
        device_dir = os.path.join(self._base_dir, device_id)
        if not os.path.isdir(device_dir):
            return []
        files = sorted(
            [f for f in os.listdir(device_dir) if f.endswith(".log")],
            reverse=True,
        )
        result = []
        for fname in files:
            fpath = os.path.join(device_dir, fname)
            result.append({
                "name": fname,
                "path": fpath,
                "size": os.path.getsize(fpath),
                "modified": datetime.fromtimestamp(os.path.getmtime(fpath)).isoformat(),
            })
        return result

    def read_log(self, device_id: str, filename: str, tail_lines: int = 500) -> str:
        """Read the tail of a log file."""
        fpath = os.path.join(self._base_dir, device_id, filename)
        if not os.path.isfile(fpath):
            return ""
        with open(fpath, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return "".join(lines[-tail_lines:])


# Singleton instance
com_logger = CommunicationFileLogger()
