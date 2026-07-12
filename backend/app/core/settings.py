"""Centralized application configuration."""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class PublicSettings(BaseSettings):
    """Non-sensitive settings returned to the frontend."""

    app_name: str
    environment: str
    api_prefix: str
    default_model: str
    enabled_foundation_modules: list[str]


class AppSettings(BaseSettings):
    """Application settings loaded from config files and environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="MJOLNIROS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "MjolnirOS"
    environment: str = "development"
    host: str = "127.0.0.1"
    port: int = 8000
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"
    log_file: str = "logs/mjolniros.log"
    frontend_url: str = "http://localhost:5173"
    default_model: str = "qwen2.5:3b"
    config_file: Path = Field(default=Path("config/app.json"))
    enabled_foundation_modules: list[str] = Field(default_factory=list)
    vision_upload_directory: Path = Field(default=Path("database/documents"))
    vision_max_upload_bytes: int = 20_000_000
    vision_max_extract_characters: int = 100_000
    tesseract_command: str | None = None
    ollama_url: str = "http://127.0.0.1:11434"
    automation_storage_directory: Path = Field(default=Path("database/automation"))

    def to_public_settings(self) -> PublicSettings:
        """Return frontend-safe settings."""
        return PublicSettings(
            app_name=self.app_name,
            environment=self.environment,
            api_prefix=self.api_prefix,
            default_model=self.default_model,
            enabled_foundation_modules=self.enabled_foundation_modules,
        )


def _load_file_settings(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as settings_file:
        loaded = json.load(settings_file)
    if not isinstance(loaded, dict):
        raise ValueError("Configuration file must contain a JSON object.")
    return loaded


@lru_cache
def get_settings() -> AppSettings:
    """Load settings from config/app.json and environment variables."""
    base_settings = AppSettings()
    file_settings = _load_file_settings(base_settings.config_file)
    return AppSettings(**file_settings)
