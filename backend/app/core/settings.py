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
    ollama_base_url: str
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
    ollama_base_url: str = "http://127.0.0.1:11434/api"
    ollama_timeout_seconds: float = 120.0
    config_file: Path = Field(default=Path("config/app.json"))
    enabled_foundation_modules: list[str] = Field(default_factory=list)

    def to_public_settings(self) -> PublicSettings:
        """Return frontend-safe settings."""
        return PublicSettings(
            app_name=self.app_name,
            environment=self.environment,
            api_prefix=self.api_prefix,
            default_model=self.default_model,
            ollama_base_url=self.ollama_base_url,
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
