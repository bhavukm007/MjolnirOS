"""Allowlisted development workflow capabilities with approved project roots."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.app.capabilities.registry import CapabilityDefinition, CapabilityRegistry
from backend.app.core.settings import AppSettings
from backend.app.domain.capability import DevicePlatform, PermissionLevel


class ProjectInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project: str = Field(min_length=1, max_length=512)


class ProjectFileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1, max_length=4096)


class NoCodingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CodingOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result: dict[str, Any]


class CodingSuperAgent:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def register(self, registry: CapabilityRegistry) -> None:
        shared = {"supported_devices": frozenset({DevicePlatform.WINDOWS})}
        registry.register(
            CapabilityDefinition.create(
                capability_id="coding.detect_vscode",
                name="Detect Visual Studio Code",
                description="Check whether VS Code is available on PATH.",
                input_model=NoCodingInput,
                output_model=CodingOutput,
                required_permission=PermissionLevel.READ,
                handler=self.detect_vscode,
                **shared,
            )
        )
        registry.register(
            CapabilityDefinition.create(
                capability_id="coding.list_projects",
                name="List approved projects",
                description="List project directories under configured development roots.",
                input_model=NoCodingInput,
                output_model=CodingOutput,
                required_permission=PermissionLevel.READ,
                handler=self.list_projects,
                **shared,
            )
        )
        registry.register(
            CapabilityDefinition.create(
                capability_id="coding.git_status",
                name="Inspect Git status",
                description="Read short Git status for a project under an approved root.",
                input_model=ProjectInput,
                output_model=CodingOutput,
                required_permission=PermissionLevel.READ,
                handler=self.git_status,
                **shared,
            )
        )
        registry.register(
            CapabilityDefinition.create(
                capability_id="coding.open_project",
                name="Open approved project in VS Code",
                description="Open one approved project directory in VS Code.",
                input_model=ProjectInput,
                output_model=CodingOutput,
                required_permission=PermissionLevel.OPERATE,
                handler=self.open_project,
                **shared,
            )
        )
        registry.register(
            CapabilityDefinition.create(
                capability_id="coding.open_file",
                name="Open file in VS Code",
                description="Open one existing file inside a configured development root.",
                input_model=ProjectFileInput,
                output_model=CodingOutput,
                required_permission=PermissionLevel.OPERATE,
                handler=self.open_file,
                **shared,
            )
        )
        registry.register(
            CapabilityDefinition.create(
                capability_id="coding.run_flask",
                name="Run approved Flask development server",
                description="Start the fixed Flask development server command in an approved project.",
                input_model=ProjectInput,
                output_model=CodingOutput,
                required_permission=PermissionLevel.SENSITIVE,
                handler=self.run_flask,
                requires_confirmation=True,
                reversible=False,
                **shared,
            )
        )
        registry.register(
            CapabilityDefinition.create(
                capability_id="coding.run_project_tests",
                name="Run approved project tests",
                description="Run the project's pytest suite using the current Python interpreter.",
                input_model=ProjectInput,
                output_model=CodingOutput,
                required_permission=PermissionLevel.SENSITIVE,
                handler=self.run_tests,
                execution_timeout_seconds=min(self.settings.coding_command_timeout_seconds, 180),
                requires_confirmation=True,
                reversible=False,
                **shared,
            )
        )

    def _project(self, value: str) -> Path:
        candidate = Path(value).expanduser().resolve(strict=True)
        roots = [path.expanduser().resolve(strict=True) for path in self.settings.coding_project_roots if path.expanduser().exists()]
        if not candidate.is_dir() or not any(candidate == root or candidate.is_relative_to(root) for root in roots):
            raise ValueError("Project is outside configured development roots.")
        return candidate

    @staticmethod
    def detect_vscode(_payload: NoCodingInput) -> dict[str, object]:
        command = shutil.which("code") or shutil.which("code.cmd")
        return {"result": {"available": bool(command), "command_found": bool(command)}}

    def list_projects(self, _payload: NoCodingInput) -> dict[str, object]:
        projects = []
        for configured_root in self.settings.coding_project_roots:
            root = configured_root.expanduser().resolve(strict=False)
            if not root.is_dir():
                continue
            if any((root / marker).exists() for marker in (".git", "pyproject.toml", "package.json")):
                projects.append(str(root))
            try:
                for child in root.iterdir():
                    if child.is_dir() and any((child / marker).exists() for marker in (".git", "pyproject.toml", "package.json")):
                        projects.append(str(child.resolve()))
                    if len(projects) >= 100:
                        break
            except OSError:
                continue
        return {"result": {"projects": list(dict.fromkeys(projects))}}

    def git_status(self, payload: ProjectInput) -> dict[str, object]:
        project = self._project(payload.project)
        if not (project / ".git").exists():
            raise ValueError("The selected project is not a Git work tree.")
        result = subprocess.run(
            ["git", "-C", str(project), "status", "--short"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
            shell=False,
        )
        if result.returncode:
            raise RuntimeError("git_status_failed")
        return {"result": {"project": project.name, "status": result.stdout[:12_000]}}

    def open_project(self, payload: ProjectInput) -> dict[str, object]:
        project = self._project(payload.project)
        command = shutil.which("code") or shutil.which("code.cmd")
        if not command:
            raise ValueError("VS Code is not available on PATH.")
        process = subprocess.Popen([command, str(project)], close_fds=True, shell=False)
        return {"result": {"opened": True, "project": project.name, "pid": process.pid}}

    def open_file(self, payload: ProjectFileInput) -> dict[str, object]:
        target = Path(payload.path).expanduser().resolve(strict=True)
        self._project(str(target.parent))
        if not target.is_file():
            raise ValueError("The selected path is not a file.")
        command = shutil.which("code") or shutil.which("code.cmd")
        if not command:
            raise ValueError("VS Code is not available on PATH.")
        process = subprocess.Popen([command, str(target)], close_fds=True, shell=False)
        return {"result": {"opened": True, "file": target.name, "pid": process.pid}}

    def run_flask(self, payload: ProjectInput) -> dict[str, object]:
        project = self._project(payload.project)
        command = shutil.which("flask") or shutil.which("flask.exe")
        if not command:
            raise ValueError("Flask is not available in the current Python environment.")
        process = subprocess.Popen(
            [command, "run"], cwd=project, close_fds=True, shell=False
        )
        return {"result": {"started": True, "project": project.name, "pid": process.pid}}

    def run_tests(self, payload: ProjectInput) -> dict[str, object]:
        project = self._project(payload.project)
        if not any((project / marker).exists() for marker in ("pytest.ini", "pyproject.toml", "tests")):
            raise ValueError("No recognized Python test configuration was found.")
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q"],
            cwd=project,
            check=False,
            capture_output=True,
            text=True,
            timeout=min(self.settings.coding_command_timeout_seconds, 180),
            shell=False,
        )
        summary = re.search(r"\d+ passed(?:, \d+ failed)?(?:, \d+ skipped)?", result.stdout + result.stderr)
        return {
            "result": {
                "project": project.name,
                "exit_code": result.returncode,
                "passed": result.returncode == 0,
                "summary": summary.group(0) if summary else "Test command completed; inspect local test output.",
            }
        }
