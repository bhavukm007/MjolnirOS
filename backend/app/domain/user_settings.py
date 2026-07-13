"""Persisted, non-secret user preferences for the desktop application."""

from pydantic import BaseModel, Field


class UserSettings(BaseModel):
    """Settings exposed to the UI; credentials remain in DPAPI stores."""

    start_with_windows: bool = False
    launch_minimized: bool = False
    minimize_to_tray: bool = True
    theme: str = Field(default="dark", pattern="^(dark|light|system)$")
    accent_color: str = Field(default="#22d3ee", pattern=r"^#[0-9A-Fa-f]{6}$")
    model: str = Field(default="qwen2.5:3b", min_length=1, max_length=200)
    ollama_url: str = Field(
        default="http://127.0.0.1:11434", min_length=1, max_length=500
    )
    memory_enabled: bool = True
    memory_storage: str = Field(default="local", pattern="^(local)$")
    notifications_enabled: bool = True
    quiet_hours_enabled: bool = False
    quiet_hours_start: str = Field(default="22:00", pattern=r"^\d{2}:\d{2}$")
    quiet_hours_end: str = Field(default="07:00", pattern=r"^\d{2}:\d{2}$")


class UserSettingsUpdate(BaseModel):
    """Partial settings update with validated user-visible values."""

    start_with_windows: bool | None = None
    launch_minimized: bool | None = None
    minimize_to_tray: bool | None = None
    theme: str | None = Field(default=None, pattern="^(dark|light|system)$")
    accent_color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    model: str | None = Field(default=None, min_length=1, max_length=200)
    ollama_url: str | None = Field(default=None, min_length=1, max_length=500)
    memory_enabled: bool | None = None
    memory_storage: str | None = Field(default=None, pattern="^(local)$")
    notifications_enabled: bool | None = None
    quiet_hours_enabled: bool | None = None
    quiet_hours_start: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    quiet_hours_end: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
