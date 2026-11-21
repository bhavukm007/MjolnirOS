"""Permissioned Windows capabilities with canonical filesystem scopes."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import psutil
from pydantic import BaseModel, ConfigDict, Field

from backend.app.capabilities.registry import CapabilityDefinition, CapabilityRegistry
from backend.app.core.settings import AppSettings
from backend.app.domain.capability import DevicePlatform, PermissionLevel
from backend.app.windows.controller import WindowsController

_SUPPORTED_TEXT = {".txt", ".md", ".json", ".csv", ".log", ".py", ".toml", ".yaml", ".yml"}
_MAX_READ_BYTES = 1_000_000


class _Output(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result: dict[str, Any]


class _LaunchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80, pattern=r"^[\w .+-]+$")


class _NoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _SearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=160)
    limit: int = Field(default=50, ge=1, le=100)


class _PathInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1, max_length=512)


class _CreateFileInput(_PathInput):
    content: str = Field(max_length=1_000_000)


class _TransferInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = Field(min_length=1, max_length=512)
    destination: str = Field(min_length=1, max_length=512)


class _ReadInput(_PathInput):
    max_bytes: int = Field(default=100_000, ge=1, le=_MAX_READ_BYTES)


class _ProcessInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pid: int = Field(gt=0)


class _ApplicationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80, pattern=r"^[\w .+-]+$")


class WindowsSuperAgent:
    """Expose only typed, scoped actions through the shared capability registry."""

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.controller = WindowsController(settings)

    def register(self, registry: CapabilityRegistry) -> None:
        shared = {"supported_devices": frozenset({DevicePlatform.WINDOWS})}
        registry.register(
            CapabilityDefinition.create(
                capability_id="windows.launch_application",
                name="Launch installed application",
                description="Launch an application resolved by the Windows application resolver.",
                input_model=_LaunchInput,
                output_model=_Output,
                required_permission=PermissionLevel.OPERATE,
                handler=self.launch_application,
                **shared,
            )
        )
        registry.register(
            CapabilityDefinition.create(
                capability_id="windows.get_system_status",
                name="Read system status",
                description="Read CPU, memory, disk, and battery status.",
                input_model=_NoInput,
                output_model=_Output,
                required_permission=PermissionLevel.READ,
                handler=self.system_status,
                **shared,
            )
        )
        registry.register(
            CapabilityDefinition.create(
                capability_id="windows.list_processes",
                name="List visible processes",
                description="Read a bounded list of visible process identifiers and names.",
                input_model=_NoInput,
                output_model=_Output,
                required_permission=PermissionLevel.READ,
                handler=self.list_processes,
                **shared,
            )
        )
        registry.register(
            CapabilityDefinition.create(
                capability_id="windows.get_application_status",
                name="Get application status",
                description="Check whether an installed application has a running process.",
                input_model=_ApplicationInput,
                output_model=_Output,
                required_permission=PermissionLevel.READ,
                handler=self.application_status,
                **shared,
            )
        )
        registry.register(
            CapabilityDefinition.create(
                capability_id="windows.get_network_status",
                name="Get network status",
                description="Read active network interface names and link state.",
                input_model=_NoInput,
                output_model=_Output,
                required_permission=PermissionLevel.READ,
                handler=self.network_status,
                **shared,
            )
        )
        registry.register(
            CapabilityDefinition.create(
                capability_id="windows.open_explorer",
                name="Open File Explorer",
                description="Open Windows File Explorer without a shell command.",
                input_model=_NoInput,
                output_model=_Output,
                required_permission=PermissionLevel.OPERATE,
                handler=self.open_explorer,
                **shared,
            )
        )
        registry.register(
            CapabilityDefinition.create(
                capability_id="windows.open_task_manager",
                name="Open Windows Task Manager",
                description="Launch the fixed Windows Task Manager executable.",
                input_model=_NoInput,
                output_model=_Output,
                required_permission=PermissionLevel.OPERATE,
                handler=self.open_task_manager,
                **shared,
            )
        )
        registry.register(
            CapabilityDefinition.create(
                capability_id="windows.open_directory",
                name="Open approved directory",
                description="Open an approved directory in File Explorer.",
                input_model=_PathInput,
                output_model=_Output,
                required_permission=PermissionLevel.OPERATE,
                handler=self.open_directory,
                **shared,
            )
        )
        registry.register(
            CapabilityDefinition.create(
                capability_id="windows.search_files",
                name="Search approved folder",
                description="Search names beneath the configured approved Windows folder.",
                input_model=_SearchInput,
                output_model=_Output,
                required_permission=PermissionLevel.READ,
                handler=self.search_files,
                execution_timeout_seconds=15,
                **shared,
            )
        )
        registry.register(
            CapabilityDefinition.create(
                capability_id="windows.list_directory",
                name="List approved directory",
                description="List entries in the configured approved Windows folder.",
                input_model=_PathInput,
                output_model=_Output,
                required_permission=PermissionLevel.READ,
                handler=self.list_directory,
                **shared,
            )
        )
        registry.register(
            CapabilityDefinition.create(
                capability_id="windows.read_file",
                name="Read supported text file",
                description="Read a bounded supported text file in the approved folder.",
                input_model=_ReadInput,
                output_model=_Output,
                required_permission=PermissionLevel.READ,
                handler=self.read_file,
                **shared,
            )
        )
        registry.register(
            CapabilityDefinition.create(
                capability_id="windows.create_file",
                name="Create file without overwrite",
                description="Create a new supported text file in the approved folder.",
                input_model=_CreateFileInput,
                output_model=_Output,
                required_permission=PermissionLevel.MODIFY,
                handler=self.create_file,
                requires_confirmation=True,
                reversible=True,
                **shared,
            )
        )
        registry.register(
            CapabilityDefinition.create(
                capability_id="windows.create_directory",
                name="Create directory",
                description="Create a new directory in the approved folder.",
                input_model=_PathInput,
                output_model=_Output,
                required_permission=PermissionLevel.MODIFY,
                handler=self.create_directory,
                requires_confirmation=True,
                reversible=True,
                **shared,
            )
        )
        registry.register(
            CapabilityDefinition.create(
                capability_id="windows.copy_file",
                name="Copy file",
                description="Copy a file within the approved folder without overwrite.",
                input_model=_TransferInput,
                output_model=_Output,
                required_permission=PermissionLevel.MODIFY,
                handler=self.copy_file,
                requires_confirmation=True,
                reversible=True,
                **shared,
            )
        )
        registry.register(
            CapabilityDefinition.create(
                capability_id="windows.move_file",
                name="Move file",
                description="Move a file within the approved folder without overwrite.",
                input_model=_TransferInput,
                output_model=_Output,
                required_permission=PermissionLevel.MODIFY,
                handler=self.move_file,
                requires_confirmation=True,
                reversible=False,
                **shared,
            )
        )
        registry.register(
            CapabilityDefinition.create(
                capability_id="windows.delete_file",
                name="Delete file",
                description="Delete one file in the approved folder after exact-action approval.",
                input_model=_PathInput,
                output_model=_Output,
                required_permission=PermissionLevel.SENSITIVE,
                handler=self.delete_file,
                requires_confirmation=True,
                reversible=False,
                **shared,
            )
        )
        registry.register(
            CapabilityDefinition.create(
                capability_id="windows.close_process",
                name="Close owned application process",
                description="Request graceful shutdown of a process owned by the current user.",
                input_model=_ProcessInput,
                output_model=_Output,
                required_permission=PermissionLevel.SENSITIVE,
                handler=self.close_process,
                requires_confirmation=True,
                reversible=False,
                **shared,
            )
        )

    def _path(self, relative: str, *, must_exist: bool = False) -> Path:
        root = self.settings.windows_search_root.expanduser().resolve(strict=True)
        if not root.is_dir():
            raise ValueError("The configured approved folder is unavailable.")
        candidate_input = Path(relative)
        if candidate_input.is_absolute() or any(part == ".." for part in candidate_input.parts):
            raise ValueError("Path must remain inside the configured approved folder.")
        candidate = (root / candidate_input).resolve(strict=must_exist)
        if not candidate.is_relative_to(root):
            raise ValueError("Path must remain inside the configured approved folder.")
        return candidate

    def launch_application(self, payload: _LaunchInput) -> dict[str, object]:
        result = self.controller.execute("open_application", {"name": payload.name}, False)
        if not result.success:
            raise RuntimeError("application_launch_failed")
        return {"result": {"success": True, "message": result.message}}

    @staticmethod
    def system_status(_payload: _NoInput) -> dict[str, object]:
        battery = psutil.sensors_battery()
        return {
            "result": {
                "cpu_percent": psutil.cpu_percent(interval=0.1),
                "memory_percent": psutil.virtual_memory().percent,
                "disk_percent": psutil.disk_usage(os.environ.get("SystemDrive", "C:") + "\\").percent,
                "battery_percent": battery.percent if battery else None,
                "battery_plugged": battery.power_plugged if battery else None,
            }
        }

    def search_files(self, payload: _SearchInput) -> dict[str, object]:
        root = self.settings.windows_search_root.expanduser().resolve(strict=True)
        matches: list[str] = []
        visited = 0
        for current, directories, files in os.walk(root, followlinks=False):
            directories[:] = [
                name for name in directories
                if (Path(current) / name).resolve().is_relative_to(root)
            ]
            for name in [*directories, *files]:
                candidate = Path(current) / name
                if payload.query.casefold() in name.casefold():
                    matches.append(candidate.relative_to(root).as_posix())
                    if len(matches) >= payload.limit:
                        return {"result": {"matches": matches, "truncated": True}}
            visited += len(directories) + len(files)
            if visited >= 20_000:
                break
        return {"result": {"matches": matches, "truncated": visited >= 20_000}}

    @staticmethod
    def list_processes(_payload: _NoInput) -> dict[str, object]:
        visible = []
        for process in psutil.process_iter(["pid", "name"]):
            try:
                visible.append({"pid": process.info["pid"], "name": process.info["name"]})
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                continue
            if len(visible) >= 200:
                break
        return {"result": {"processes": visible}}

    def application_status(self, payload: _ApplicationInput) -> dict[str, object]:
        resolution = self.controller.resolve_application(payload.name)
        if resolution is None:
            return {"result": {"installed": False, "running": False}}
        expected = Path(resolution.command[0]).name.casefold()
        matches = []
        for process in psutil.process_iter(["pid", "name", "exe"]):
            try:
                process_name = (process.info.get("name") or "").casefold()
                executable = Path(process.info.get("exe") or process_name).name.casefold()
                if process_name == expected or executable == expected:
                    matches.append({"pid": process.info["pid"], "name": process.info.get("name")})
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                continue
        return {"result": {"installed": True, "running": bool(matches), "processes": matches[:20]}}

    @staticmethod
    def network_status(_payload: _NoInput) -> dict[str, object]:
        interfaces = psutil.net_if_stats()
        return {
            "result": {
                "interfaces": [
                    {"name": name, "up": stats.isup, "speed_mbps": stats.speed}
                    for name, stats in interfaces.items()
                ]
            }
        }

    @staticmethod
    def open_explorer(_payload: _NoInput) -> dict[str, object]:
        subprocess.Popen(["explorer.exe"], close_fds=True)
        return {"result": {"opened": True}}

    @staticmethod
    def open_task_manager(_payload: _NoInput) -> dict[str, object]:
        if os.name != "nt":
            raise RuntimeError("windows_only_capability")
        process = subprocess.Popen(["taskmgr.exe"], close_fds=True)
        return {"result": {"opened": True, "pid": process.pid}}

    def open_directory(self, payload: _PathInput) -> dict[str, object]:
        target = self._path(payload.path, must_exist=True)
        if not target.is_dir():
            raise ValueError("The requested path is not a directory.")
        subprocess.Popen(["explorer.exe", str(target)], close_fds=True)
        return {"result": {"opened": True, "path": target.relative_to(self.settings.windows_search_root.resolve()).as_posix()}}

    @staticmethod
    def close_process(payload: _ProcessInput) -> dict[str, object]:
        try:
            process = psutil.Process(payload.pid)
            if process.username() != psutil.Process().username():
                raise PermissionError("Only a process owned by the current user can be closed.")
            process_name = process.name()
            process.terminate()
            try:
                process.wait(timeout=3)
            except psutil.TimeoutExpired:
                raise TimeoutError("The application did not exit after a graceful close request.")
        except psutil.NoSuchProcess as error:
            raise ValueError("The selected process is no longer running.") from error
        return {"result": {"closed": True, "pid": payload.pid, "name": process_name}}

    def list_directory(self, payload: _PathInput) -> dict[str, object]:
        target = self._path(payload.path or ".", must_exist=True)
        if not target.is_dir():
            raise ValueError("The requested path is not a directory.")
        entries = []
        for child in sorted(target.iterdir(), key=lambda item: item.name.casefold())[:200]:
            resolved = child.resolve()
            if not resolved.is_relative_to(self.settings.windows_search_root.resolve()):
                continue
            entries.append({"name": child.name, "kind": "directory" if child.is_dir() else "file"})
        return {"result": {"entries": entries, "truncated": len(entries) == 200}}

    def read_file(self, payload: _ReadInput) -> dict[str, object]:
        target = self._path(payload.path, must_exist=True)
        if target.suffix.lower() not in _SUPPORTED_TEXT or not target.is_file():
            raise ValueError("Only supported text files can be read.")
        size = target.stat().st_size
        if size > min(payload.max_bytes, _MAX_READ_BYTES):
            raise ValueError("The file exceeds the configured read limit.")
        return {"result": {"path": target.relative_to(self.settings.windows_search_root.resolve()).as_posix(), "content": target.read_text(encoding="utf-8"), "bytes": size}}

    def create_file(self, payload: _CreateFileInput) -> dict[str, object]:
        target = self._path(payload.path)
        if target.suffix.lower() not in _SUPPORTED_TEXT or not target.parent.is_dir():
            raise ValueError("The target must be a supported file in an existing approved directory.")
        with target.open("x", encoding="utf-8", newline="") as stream:
            stream.write(payload.content)
        return {"result": {"created": True, "path": target.relative_to(self.settings.windows_search_root.resolve()).as_posix()}}

    def create_directory(self, payload: _PathInput) -> dict[str, object]:
        target = self._path(payload.path)
        target.mkdir(exist_ok=False)
        return {"result": {"created": True, "path": target.relative_to(self.settings.windows_search_root.resolve()).as_posix()}}

    def _transfer_paths(self, payload: _TransferInput) -> tuple[Path, Path]:
        source = self._path(payload.source, must_exist=True)
        destination = self._path(payload.destination)
        if not source.is_file() or not destination.parent.is_dir() or destination.exists():
            raise ValueError("Source must be a file and destination must be new in an existing approved directory.")
        return source, destination

    def copy_file(self, payload: _TransferInput) -> dict[str, object]:
        source, destination = self._transfer_paths(payload)
        shutil.copy2(source, destination)
        return {"result": {"copied": True, "destination": destination.relative_to(self.settings.windows_search_root.resolve()).as_posix()}}

    def move_file(self, payload: _TransferInput) -> dict[str, object]:
        source, destination = self._transfer_paths(payload)
        source.rename(destination)
        return {"result": {"moved": True, "destination": destination.relative_to(self.settings.windows_search_root.resolve()).as_posix()}}

    def delete_file(self, payload: _PathInput) -> dict[str, object]:
        target = self._path(payload.path, must_exist=True)
        if not target.is_file():
            raise ValueError("Only a single file can be deleted by this capability.")
        target.unlink()
        return {"result": {"deleted": True, "path": target.relative_to(self.settings.windows_search_root.resolve()).as_posix()}}
