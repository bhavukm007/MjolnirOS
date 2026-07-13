"""Public manifest, permission, and marketplace models for local plugins."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class PluginStatus(StrEnum):
    """Runtime states exposed by the plugin manager."""

    LOADED = "loaded"
    DISABLED = "disabled"
    BLOCKED = "blocked"


class PluginDependency(BaseModel):
    """A plugin dependency and its minimum compatible version."""

    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    min_version: str = Field(default="0.0.0", pattern=r"^\d+\.\d+\.\d+$")


class PluginManifest(BaseModel):
    """Versioned metadata required in every plugin's manifest.json file."""

    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    name: str = Field(min_length=1, max_length=100)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    description: str = Field(min_length=1, max_length=500)
    category: str = Field(min_length=1, max_length=50)
    entry_point: str = Field(default="plugin.py", pattern=r"^[a-zA-Z0-9_.-]+$")
    dependencies: list[PluginDependency] = Field(default_factory=list)


class PluginPermissions(BaseModel):
    """Declared capability grants, reviewed before a plugin is activated."""

    permissions: list[str] = Field(default_factory=list, max_length=20)


class PluginRecord(BaseModel):
    """A discovered plugin with resolved dependency and loading state."""

    manifest: PluginManifest
    permissions: list[str]
    status: PluginStatus
    blocked_reason: str | None = None


class MarketplacePlugin(BaseModel):
    """A locally available marketplace listing."""

    manifest: PluginManifest
    permissions: list[str]
    installed: bool
    update_available: bool = False


class PluginCatalog(BaseModel):
    """The local marketplace index shipped with MjolnirOS."""

    plugins: list[PluginManifest]

    @model_validator(mode="after")
    def validate_unique_plugin_ids(self) -> PluginCatalog:
        """Reject marketplace metadata that maps multiple entries to one plugin."""
        plugin_ids = [plugin.id for plugin in self.plugins]
        if len(plugin_ids) != len(set(plugin_ids)):
            raise ValueError("Plugin catalog contains duplicate plugin ids.")
        return self
