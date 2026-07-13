"""Local plugin discovery, installation, updates, and process-isolated loading."""

from __future__ import annotations

import json
import logging
from pathlib import Path
import shutil
import subprocess
import sys
from threading import RLock

from fastapi import HTTPException

from backend.app.core.settings import AppSettings
from backend.app.domain.plugin import (
    MarketplacePlugin,
    PluginCatalog,
    PluginManifest,
    PluginPermissions,
    PluginRecord,
    PluginStatus,
)

logger = logging.getLogger(__name__)

_REQUIRED_FILES = ("manifest.json", "permissions.json", "plugin.py", "README.md")
_ALLOWED_PERMISSIONS = {"automation", "browser", "memory", "network", "system"}
_DEFAULT_PLUGINS = (
    ("spotify", "Spotify", "Media", "Control Spotify through approved local actions."),
    (
        "weather",
        "Weather",
        "Information",
        "Retrieve weather through an approved provider.",
    ),
    ("calculator", "Calculator", "Utilities", "Perform local calculator operations."),
    ("clock", "Clock", "Utilities", "Show local time and timers."),
    ("github", "GitHub", "Development", "Extend the existing GitHub Agent safely."),
    (
        "docker",
        "Docker",
        "Development",
        "Extend the existing Development Agent safely.",
    ),
)


class PluginService:
    """Manage local plugins without exposing plugin code to the backend process."""

    _state_lock = RLock()

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._directory = settings.plugin_directory
        self._catalog_file = settings.plugin_catalog_file
        self._state_file = settings.plugin_state_file

    def list_plugins(
        self, search: str | None = None, category: str | None = None
    ) -> list[PluginRecord]:
        """Discover installed plugins and apply optional marketplace-style filters."""
        self._ensure_default_plugins()
        records = []
        for path in self._plugin_paths():
            try:
                records.append(self._record(path))
            except ValueError:
                logger.warning(
                    "plugin_directory_invalid", extra={"plugin_path": str(path)}
                )
        query = (search or "").strip().lower()
        if query:
            records = [
                record
                for record in records
                if query in record.manifest.name.lower()
                or query in record.manifest.description.lower()
                or query in record.manifest.id
            ]
        if category:
            records = [
                record
                for record in records
                if record.manifest.category.lower() == category.lower()
            ]
        return sorted(records, key=lambda record: record.manifest.name.lower())

    def categories(self) -> list[str]:
        """Return available local marketplace categories."""
        return sorted({item.category for item in self._catalog().plugins})

    def marketplace(
        self, search: str | None = None, category: str | None = None
    ) -> list[MarketplacePlugin]:
        """Return installable catalog entries and update availability."""
        installed = {item.manifest.id: item for item in self.list_plugins()}
        listings = []
        for manifest in self._catalog().plugins:
            current = installed.get(manifest.id)
            listings.append(
                MarketplacePlugin(
                    manifest=manifest,
                    permissions=self._catalog_permissions(manifest.id),
                    installed=current is not None,
                    update_available=current is not None
                    and _version_tuple(manifest.version)
                    > _version_tuple(current.manifest.version),
                )
            )
        query = (search or "").strip().lower()
        return [
            item
            for item in listings
            if (
                not query
                or query in item.manifest.name.lower()
                or query in item.manifest.description.lower()
            )
            and (not category or item.manifest.category.lower() == category.lower())
        ]

    def install(self, plugin_id: str) -> PluginRecord:
        """Install a catalog plugin and activate it immediately after validation."""
        self._ensure_default_plugins()
        path = self._plugin_path(plugin_id)
        if not path.exists():
            if plugin_id not in {item[0] for item in _DEFAULT_PLUGINS}:
                raise HTTPException(
                    status_code=404,
                    detail="Plugin is not available in the local marketplace.",
                )
            self._materialize_default(plugin_id)
        return self.load(plugin_id)

    def uninstall(self, plugin_id: str) -> None:
        """Remove a plugin after confirming no installed plugin depends on it."""
        path = self._plugin_path(plugin_id)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Plugin was not found.")
        dependents = [
            item.manifest.name
            for item in self.list_plugins()
            if any(
                dependency.id == plugin_id for dependency in item.manifest.dependencies
            )
        ]
        if dependents:
            raise HTTPException(
                status_code=409,
                detail=f"Plugin is required by: {', '.join(dependents)}.",
            )
        shutil.rmtree(path)
        self._remove_state(plugin_id)
        logger.info("plugin_uninstalled", extra={"plugin_id": plugin_id})

    def update(self, plugin_id: str) -> PluginRecord:
        """Reload an installed plugin after validating its version and dependencies."""
        record = self._record(self._plugin_path(plugin_id))
        return self.load(record.manifest.id)

    def load(self, plugin_id: str) -> PluginRecord:
        """Dynamically activate a plugin in an isolated interpreter process."""
        path = self._plugin_path(plugin_id)
        record = self._record(path)
        if record.status is PluginStatus.BLOCKED:
            raise HTTPException(
                status_code=422, detail=record.blocked_reason or "Plugin is blocked."
            )
        entry = path / record.manifest.entry_point
        if not entry.is_file():
            raise HTTPException(
                status_code=422, detail="Plugin entry point is missing."
            )
        runner = (
            "import importlib.util,sys; "
            "spec=importlib.util.spec_from_file_location('mjolnir_plugin',sys.argv[1]); "
            "module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); "
            "activate=getattr(module,'activate',None); "
            "result=activate() if activate else None; "
            "print('ready' if result is None else str(result))"
        )
        try:
            subprocess.run(
                [sys.executable, "-I", "-c", runner, str(entry)],
                cwd=path,
                capture_output=True,
                text=True,
                check=True,
                timeout=self._settings.plugin_load_timeout_seconds,
            )
        except (
            OSError,
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
        ) as error:
            logger.warning("plugin_load_failed", extra={"plugin_id": plugin_id})
            raise HTTPException(
                status_code=422,
                detail="Plugin could not be loaded in its isolated runtime.",
            ) from error
        logger.info(
            "plugin_loaded",
            extra={"plugin_id": plugin_id, "permissions": record.permissions},
        )
        self._set_enabled(plugin_id, True)
        return record.model_copy(update={"status": PluginStatus.LOADED})

    def disable(self, plugin_id: str) -> PluginRecord:
        """Persistently disable a plugin without uninstalling its files."""
        record = self._record(self._plugin_path(plugin_id))
        if record.status is PluginStatus.BLOCKED:
            raise HTTPException(
                status_code=422, detail=record.blocked_reason or "Plugin is blocked."
            )
        self._set_enabled(plugin_id, False)
        logger.info("plugin_disabled", extra={"plugin_id": plugin_id})
        return record.model_copy(update={"status": PluginStatus.DISABLED})

    def _record(self, path: Path) -> PluginRecord:
        if not path.is_dir():
            raise HTTPException(status_code=404, detail="Plugin was not found.")
        missing = [name for name in _REQUIRED_FILES if not (path / name).is_file()]
        if missing:
            return PluginRecord(
                manifest=PluginManifest(
                    id=path.name,
                    name=path.name,
                    version="0.0.0",
                    description="Invalid plugin.",
                    category="Invalid",
                ),
                permissions=[],
                status=PluginStatus.BLOCKED,
                blocked_reason=f"Missing required files: {', '.join(missing)}.",
            )
        try:
            manifest = PluginManifest.model_validate_json(
                (path / "manifest.json").read_text(encoding="utf-8")
            )
            permissions = PluginPermissions.model_validate_json(
                (path / "permissions.json").read_text(encoding="utf-8")
            ).permissions
        except (OSError, ValueError):
            logger.warning("plugin_metadata_invalid", extra={"plugin_path": str(path)})
            return self._blocked_record(path, "Plugin metadata is invalid.")
        if manifest.id != path.name:
            return PluginRecord(
                manifest=manifest,
                permissions=permissions,
                status=PluginStatus.BLOCKED,
                blocked_reason="Plugin folder must match manifest id.",
            )
        unknown = sorted(set(permissions) - _ALLOWED_PERMISSIONS)
        if unknown:
            return PluginRecord(
                manifest=manifest,
                permissions=permissions,
                status=PluginStatus.BLOCKED,
                blocked_reason=f"Unknown permissions: {', '.join(unknown)}.",
            )
        installed = self._installed_manifests()
        missing_dependencies = [
            dependency.id
            for dependency in manifest.dependencies
            if dependency.id not in installed
            or _version_tuple(installed[dependency.id].version)
            < _version_tuple(dependency.min_version)
        ]
        if missing_dependencies:
            return PluginRecord(
                manifest=manifest,
                permissions=permissions,
                status=PluginStatus.BLOCKED,
                blocked_reason=f"Unsatisfied dependencies: {', '.join(missing_dependencies)}.",
            )
        if self._has_dependency_cycle(installed, manifest.id):
            return PluginRecord(
                manifest=manifest,
                permissions=permissions,
                status=PluginStatus.BLOCKED,
                blocked_reason="Plugin dependencies contain a cycle.",
            )
        return PluginRecord(
            manifest=manifest,
            permissions=permissions,
            status=(
                PluginStatus.LOADED
                if self._states().get(manifest.id, False)
                else PluginStatus.DISABLED
            ),
        )

    def _states(self) -> dict[str, bool]:
        """Load enabled state without storing executable plugin data in the core."""
        with self._state_lock:
            if not self._state_file.exists():
                return {}
            try:
                loaded = json.loads(self._state_file.read_text(encoding="utf-8"))
                if not isinstance(loaded, dict):
                    raise ValueError("Plugin state must be a JSON object.")
            except (OSError, ValueError) as error:
                raise HTTPException(
                    status_code=500, detail="Plugin state storage is invalid."
                ) from error
            return {
                key: value for key, value in loaded.items() if isinstance(value, bool)
            }

    def _set_enabled(self, plugin_id: str, enabled: bool) -> None:
        with self._state_lock:
            states = self._states()
            states[plugin_id] = enabled
            self._write_states(states)

    def _remove_state(self, plugin_id: str) -> None:
        """Remove a plugin's persisted state atomically with its uninstallation."""
        with self._state_lock:
            states = self._states()
            states.pop(plugin_id, None)
            self._write_states(states)

    def _write_states(self, states: dict[str, bool]) -> None:
        with self._state_lock:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._state_file.with_suffix(".tmp")
            temporary.write_text(json.dumps(states, indent=2), encoding="utf-8")
            temporary.replace(self._state_file)

    @staticmethod
    def _blocked_record(path: Path, reason: str) -> PluginRecord:
        """Return a visible blocked record for a plugin with invalid metadata."""
        return PluginRecord(
            manifest=PluginManifest(
                id=path.name,
                name=path.name,
                version="0.0.0",
                description="Invalid plugin.",
                category="Invalid",
            ),
            permissions=[],
            status=PluginStatus.BLOCKED,
            blocked_reason=reason,
        )

    @staticmethod
    def _has_dependency_cycle(
        manifests: dict[str, PluginManifest], start_id: str
    ) -> bool:
        """Detect cycles reachable from a plugin before it can be activated."""
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(plugin_id: str) -> bool:
            if plugin_id in visiting:
                return True
            if plugin_id in visited or plugin_id not in manifests:
                return False
            visiting.add(plugin_id)
            has_cycle = any(
                visit(dependency.id) for dependency in manifests[plugin_id].dependencies
            )
            visiting.remove(plugin_id)
            visited.add(plugin_id)
            return has_cycle

        return visit(start_id)

    def _installed_manifests(
        self, exclude: str | None = None
    ) -> dict[str, PluginManifest]:
        """Read peer manifests without recursively resolving their dependencies."""
        manifests = {}
        for path in self._plugin_paths():
            if path.name != exclude:
                try:
                    manifests[path.name] = PluginManifest.model_validate_json(
                        (path / "manifest.json").read_text(encoding="utf-8")
                    )
                except (OSError, ValueError):
                    continue
        return manifests

    def _plugin_paths(self) -> list[Path]:
        self._directory.mkdir(parents=True, exist_ok=True)
        return [
            path
            for path in self._directory.iterdir()
            if path.is_dir() and not path.name.startswith(".")
        ]

    def _plugin_path(self, plugin_id: str) -> Path:
        if (
            not plugin_id.replace("-", "").replace("_", "").isalnum()
            or ".." in plugin_id
        ):
            raise HTTPException(status_code=422, detail="Invalid plugin id.")
        return self._directory / plugin_id

    def _catalog(self) -> PluginCatalog:
        if self._catalog_file.exists():
            return PluginCatalog.model_validate_json(
                self._catalog_file.read_text(encoding="utf-8")
            )
        return PluginCatalog(
            plugins=[
                PluginManifest(
                    id=item[0],
                    name=item[1],
                    version="1.0.0",
                    category=item[2],
                    description=item[3],
                )
                for item in _DEFAULT_PLUGINS
            ]
        )

    def _catalog_permissions(self, plugin_id: str) -> list[str]:
        path = self._plugin_path(plugin_id) / "permissions.json"
        if path.exists():
            return PluginPermissions.model_validate_json(
                path.read_text(encoding="utf-8")
            ).permissions
        return []

    def _ensure_default_plugins(self) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        seed_marker = self._directory / ".defaults_seeded"
        if seed_marker.exists():
            return
        for plugin_id, *_ in _DEFAULT_PLUGINS:
            self._materialize_default(plugin_id)
        seed_marker.touch()

    def _materialize_default(self, plugin_id: str) -> None:
        """Create one packaged default plugin using the public SDK file layout."""
        _, name, category, description = next(
            item for item in _DEFAULT_PLUGINS if item[0] == plugin_id
        )
        path = self._directory / plugin_id
        if path.exists():
            return
        path.mkdir()
        manifest = {
            "id": plugin_id,
            "name": name,
            "version": "1.0.0",
            "description": description,
            "category": category,
            "entry_point": "plugin.py",
            "dependencies": [],
        }
        (path / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        (path / "permissions.json").write_text(
            json.dumps({"permissions": []}, indent=2), encoding="utf-8"
        )
        (path / "plugin.py").write_text(
            '"""MjolnirOS plugin entry point."""\n\ndef activate() -> str:\n    """Confirm the plugin loaded in the isolated runtime."""\n    return "ready"\n',
            encoding="utf-8",
        )
        (path / "README.md").write_text(
            f"# {name}\n\nLocal MjolnirOS plugin.\n", encoding="utf-8"
        )


def _version_tuple(value: str) -> tuple[int, int, int]:
    """Compare validated semantic versions without adding a runtime dependency."""
    return tuple(int(part) for part in value.split("."))  # type: ignore[return-value]
