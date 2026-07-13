"""Application configuration settings."""
from __future__ import annotations
from pydantic_settings import BaseSettings
from typing import Optional, List


class Settings(BaseSettings):
    APP_NAME: str = "AITestLab"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./aitestlab.db"

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:3000"]

    # File Storage
    LOG_DIR: str = "./logs"
    PLUGIN_DIR: str = "./plugins"
    EXPORT_DIR: str = "./exports"
    REPORT_DIR: str = "./reports"

    # AI Model defaults
    DEFAULT_AI_PROVIDER: str = "openai"
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"

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
