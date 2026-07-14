"""Centralized application configuration."""

from __future__ import annotations

from functools import lru_cache
import json
import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, DotEnvSettingsSource, SettingsConfigDict


class PublicSettings(BaseSettings):
    """Non-sensitive settings returned to the frontend."""

    app_name: str
    environment: str
    api_prefix: str
    default_model: str
    voice_enabled: bool
    voice_wake_word: str
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
    development_cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ]
    )
    default_model: str = "qwen2.5:3b"
    config_file: Path = Field(default=Path("config/app.json"))
    enabled_foundation_modules: list[str] = Field(default_factory=list)
    vision_upload_directory: Path = Field(default=Path("database/documents"))
    vision_max_upload_bytes: int = 20_000_000
    vision_max_extract_characters: int = 100_000
    tesseract_command: str | None = None
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_base_url: str = "http://127.0.0.1:11434/api"
    ollama_timeout_seconds: float = 120.0
    voice_enabled: bool = True
    voice_model_path: Path = Path("assets/models/vosk-model-small-en-us-0.15")
    voice_sample_rate: int = 16_000
    voice_wake_word: str = "Mjolnir"
    voice_command_timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    voice_tts_rate: int = 185
    voice_tts_volume: float = 1.0
    voice_tts_timeout_seconds: float = Field(default=60.0, gt=0, le=300)
    database_path: Path = Path("database/mjolniros.db")
    chroma_path: Path = Path("database/chroma")
    windows_search_root: Path = Path("C:/Users")
    windows_screenshot_path: Path = Path("assets/screenshots")
    browser_session_path: Path = Path("database/browser_sessions")
    browser_chrome_user_data_path: Path = Field(
        default_factory=lambda: Path(os.environ.get("LOCALAPPDATA", ""))
        / "Google/Chrome/User Data"
    )
    browser_chrome_profile_directory: str = "Default"
    browser_incognito: bool = False
    browser_download_path: Path = Path("assets/downloads")
    browser_screenshot_path: Path = Path("assets/browser_screenshots")
    browser_headless: bool = False
    browser_summary_timeout_seconds: float = 30.0
    github_api_base_url: str = "https://api.github.com"
    github_token: str | None = None
    github_default_repository: Path = Path(".")
    coding_vscode_command: str = "code"
    coding_project_roots: list[Path] = Field(default_factory=lambda: [Path.cwd()])
    coding_command_timeout_seconds: float = 120.0
    coding_ai_max_context_chars: int = 12_000
    automation_storage_directory: Path = Field(default=Path("database/automation"))
    learning_storage_directory: Path = Field(default=Path("database/learning"))
    learning_suggestion_threshold: int = Field(default=3, ge=2, le=100)
    plugin_directory: Path = Field(default=Path("plugins"))
    plugin_catalog_file: Path = Field(default=Path("plugins/catalog.json"))
    plugin_state_file: Path = Field(default=Path("database/plugins/state.json"))
    plugin_load_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    productivity_storage_directory: Path = Field(default=Path("database/productivity"))
    communication_storage_directory: Path = Field(
        default=Path("database/communication")
    )
    settings_storage_directory: Path = Field(default=Path("database/settings"))
    audit_storage_directory: Path = Field(default=Path("database/audit"))
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: str | None = None
    google_oauth_redirect_uri: str = (
        "http://127.0.0.1:8000/api/v1/productivity/oauth/google/callback"
    )
    notion_oauth_client_id: str | None = None
    notion_oauth_client_secret: str | None = None
    notion_oauth_redirect_uri: str = (
        "http://127.0.0.1:8000/api/v1/productivity/oauth/notion/callback"
    )

    def cors_allowed_origins(self) -> list[str]:
        """Return explicit development origins without widening production CORS."""
        if self.environment.lower() == "development":
            return list(dict.fromkeys([*self.development_cors_origins, self.frontend_url]))
        return [self.frontend_url]

    def to_public_settings(self) -> PublicSettings:
        """Return frontend-safe settings."""
        return PublicSettings(
            app_name=self.app_name,
            environment=self.environment,
            api_prefix=self.api_prefix,
            default_model=self.default_model,
            voice_enabled=self.voice_enabled,
            voice_wake_word=self.voice_wake_word,
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
    dotenv_settings = DotEnvSettingsSource(AppSettings)()
    environment_settings = {
        field_name: value
        for field_name in AppSettings.model_fields
        if (value := os.getenv(f"MJOLNIROS_{field_name.upper()}")) is not None
    }
    resolved_settings = dict(file_settings)
    resolved_settings.update(dotenv_settings)
    resolved_settings.update(environment_settings)
    return AppSettings(**resolved_settings)
