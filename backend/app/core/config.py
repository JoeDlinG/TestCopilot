"""Application configuration settings."""
from __future__ import annotations
import os
import sys
from pydantic_settings import BaseSettings
from typing import Optional, List

# PyInstaller detection. When frozen, bundled read-only resources (plugins,
# static frontend) live under sys._MEIPASS, while writable runtime data
# (DB, logs, reports, exports) resolve to the process working directory which
# the entry point chdir's to a per-user folder on startup.
_IS_FROZEN = getattr(sys, "frozen", False)
_MEIPASS = getattr(sys, "_MEIPASS", None)


def _bundled_dir(name: str) -> str:
    """Path to a bundled resource directory (frozen -> _MEIPASS, else CWD-relative)."""
    if _IS_FROZEN and _MEIPASS:
        return os.path.join(_MEIPASS, name)
    return f"./{name}"


class Settings(BaseSettings):
    APP_NAME: str = "AITestLab"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./aitestlab.db"

    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]

    # File Storage (writable runtime dirs are CWD-relative)
    LOG_DIR: str = "./logs"
    PLUGIN_DIR: str = _bundled_dir("plugins")
    EXPORT_DIR: str = "./exports"
    REPORT_DIR: str = "./reports"

    # Built frontend (served by the backend in standalone/packaged mode)
    STATIC_DIR: str = _bundled_dir("static")

    # AI Model defaults
    DEFAULT_AI_PROVIDER: str = "openai"
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"

    # API key encryption (at-rest). Override via ENCRYPTION_KEY in env / .env.
    ENCRYPTION_KEY: str = "change-me-testcopilot-encryption-key"

    # Whisper
    WHISPER_MODEL: str = "base"

    # Communication defaults
    VISA_TIMEOUT: int = 5000  # ms
    CAN_BITRATE: int = 500000
    SERIAL_BAUDRATE: int = 115200
    SERIAL_TIMEOUT: float = 1.0

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
