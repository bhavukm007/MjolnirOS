"""Atomic local persistence for non-secret user preferences."""

from __future__ import annotations

import json
import os

from pydantic_settings import DotEnvSettingsSource

from backend.app.core.settings import AppSettings, get_settings
from backend.app.domain.user_settings import UserSettings, UserSettingsUpdate


class SettingsService:
    """Read and write user settings independently of deployment configuration."""

    def __init__(self, settings: AppSettings) -> None:
        self._path = settings.settings_storage_directory / "user-settings.json"
        self._defaults = UserSettings(
            model=settings.default_model, ollama_url=settings.ollama_url
        )

    def get(self) -> UserSettings:
        """Return persisted preferences or safe first-run defaults."""
        if not self._path.exists():
            return self._defaults
        return UserSettings.model_validate_json(self._path.read_text(encoding="utf-8"))

    def update(self, update: UserSettingsUpdate) -> UserSettings:
        """Merge a validated partial update and persist it atomically."""
        value = self.get().model_copy(update=update.model_dump(exclude_none=True))
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(".tmp")
        temporary.write_text(json.dumps(value.model_dump(), indent=2), encoding="utf-8")
        temporary.replace(self._path)
        return value


def get_runtime_ai_settings(settings: AppSettings | None = None) -> AppSettings:
    """Resolve AI preferences with environment overrides above persisted UI values."""
    base_settings = settings or get_settings()
    preferences = SettingsService(base_settings).get()
    dotenv_values = DotEnvSettingsSource(AppSettings)()
    env_overrides = set(dotenv_values) | {
        field_name
        for field_name in ("default_model", "ollama_url")
        if os.getenv(f"MJOLNIROS_{field_name.upper()}") is not None
    }
    updates: dict[str, str] = {}
    if "default_model" not in env_overrides:
        updates["default_model"] = preferences.model
    if "ollama_url" not in env_overrides:
        updates["ollama_url"] = preferences.ollama_url
    return base_settings.model_copy(update=updates)
