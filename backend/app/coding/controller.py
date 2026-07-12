"""Safe local VS Code, terminal, and workspace management controller."""

from __future__ import annotations

import logging
from pathlib import Path
import re
import subprocess
from typing import Callable

from backend.app.core.settings import AppSettings
from backend.app.domain.coding import CodingActionRequest, CodingActionResult
from backend.app.memory.store import MemoryStore


_PROJECT_MARKERS = (".git", "pyproject.toml", "package.json", ".vscode")
_DESTRUCTIVE_COMMANDS = frozenset({"rm", "del", "format", "diskpart", "shutdown", "reboot", "remove-item", "rmdir", "rd"})


class CodingController:
    """Coordinate local VS Code commands, bounded terminal execution, and project memory."""

    def __init__(
        self,
        settings: AppSettings,
        memory_store: MemoryStore,
        launcher: Callable[..., subprocess.Popen[bytes]] = subprocess.Popen,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self._settings = settings
        self._memory_store = memory_store
        self._launcher = launcher
        self._runner = runner
        self._logger = logging.getLogger(__name__)

    def execute(self, request: CodingActionRequest) -> CodingActionResult:
        """Run one Coding Agent action and always return a structured response."""
        if request.action == "run_command" and self._is_destructive(request.command or "") and not request.confirmed:
            self._logger.warning("coding_confirmation_required", extra={"action": request.action})
            return CodingActionResult(
                success=False,
                message="Confirmation is required before executing this destructive command.",
                confirmation_required=True,
            )
        try:
            return self._execute(request)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            self._logger.warning("coding_action_failed", extra={"action": request.action, "error": str(error)})
            return CodingActionResult(success=False, message="Coding action failed.", data={"error": str(error)})

    def _execute(self, request: CodingActionRequest) -> CodingActionResult:
        if request.action == "list_projects":
            projects = [str(project) for project in self._find_projects()]
            return CodingActionResult(success=True, message="Projects loaded.", data={"projects": projects, "active_project": self._active_project()})
        if request.action == "switch_project":
            project = self._project_path(request.path)
            self._remember_project(project)
            return CodingActionResult(success=True, message="Active project changed.", data={"active_project": str(project)})
        if request.action == "run_command":
            return self._run_command(request)

        path = self._required_path(request.path)
        if request.action == "open_workspace":
            self._launch([self._settings.coding_vscode_command, "--reuse-window", str(path)])
            self._remember_project(path.parent if path.is_file() else path)
            return CodingActionResult(success=True, message="VS Code workspace opened.", data={"path": str(path)})
        if request.action in {"open_project", "open_folder"}:
            project = self._project_path(str(path))
            self._launch([self._settings.coding_vscode_command, "--reuse-window", str(project)])
            self._remember_project(project)
            return CodingActionResult(success=True, message="Project opened in VS Code.", data={"path": str(project)})
        if request.action == "open_file":
            self._require_file(path)
            self._launch([self._settings.coding_vscode_command, "--reuse-window", str(path)])
            self._remember_project(path.parent)
            return CodingActionResult(success=True, message="File opened in VS Code.", data={"path": str(path)})
        if request.action == "reveal_file":
            self._require_file(path)
            self._launch([self._settings.coding_vscode_command, "--reuse-window", "--goto", str(path)])
            self._remember_project(path.parent)
            return CodingActionResult(success=True, message="File revealed in VS Code.", data={"path": str(path)})
        if request.action == "open_terminal":
            project = self._project_path(str(path))
            self._launch([self._settings.coding_vscode_command, "--reuse-window", str(project), "--command", "workbench.action.terminal.new"])
            self._remember_project(project)
            return CodingActionResult(success=True, message="VS Code integrated terminal opened.", data={"path": str(project)})
        raise ValueError("Unsupported Coding Agent action.")

    def _run_command(self, request: CodingActionRequest) -> CodingActionResult:
        if not request.command:
            raise ValueError("command is required.")
        cwd = self._project_path(request.cwd) if request.cwd else self._active_path()
        completed = self._runner(
            request.command,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            shell=True,
            timeout=self._settings.coding_command_timeout_seconds,
            check=False,
        )
        self._remember_project(cwd)
        success = completed.returncode == 0
        self._logger.info("coding_command_completed", extra={"exit_code": completed.returncode, "cwd": str(cwd)})
        return CodingActionResult(
            success=success,
            message="Command completed." if success else "Command failed.",
            data={"stdout": completed.stdout, "stderr": completed.stderr, "exit_code": completed.returncode, "cwd": str(cwd)},
        )

    def _find_projects(self) -> list[Path]:
        projects: set[Path] = set()
        for root in self._settings.coding_project_roots:
            root_path = Path(root).expanduser().resolve()
            if not root_path.is_dir():
                continue
            if self._is_project(root_path):
                projects.add(root_path)
            for child in root_path.iterdir():
                if child.is_dir() and self._is_project(child):
                    projects.add(child.resolve())
        return sorted(projects, key=lambda item: item.name.lower())

    @staticmethod
    def _is_project(path: Path) -> bool:
        return any((path / marker).exists() for marker in _PROJECT_MARKERS)

    def _active_project(self) -> str | None:
        active = self._memory_store.get_preference("coding.active_workspace")
        return active if isinstance(active, str) else None

    def _active_path(self) -> Path:
        active = self._active_project()
        return self._project_path(active) if active else Path.cwd().resolve()

    def _remember_project(self, project: Path) -> None:
        self._memory_store.set_preference("coding.active_workspace", str(project))

    def _project_path(self, path: str | None) -> Path:
        if not path:
            raise ValueError("A project path is required.")
        resolved = Path(path).expanduser().resolve()
        if not resolved.is_dir():
            raise ValueError("Project path must be an existing folder.")
        return resolved

    def _required_path(self, path: str | None) -> Path:
        if not path:
            raise ValueError("path is required.")
        resolved = Path(path).expanduser().resolve()
        if not resolved.exists():
            raise ValueError("Path does not exist.")
        return resolved

    @staticmethod
    def _require_file(path: Path) -> None:
        if not path.is_file():
            raise ValueError("Path must be an existing file.")

    def _launch(self, arguments: list[str]) -> None:
        self._launcher(arguments, cwd=str(Path.cwd()), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._logger.info("vscode_launched", extra={"arguments": arguments[1:]})

    @staticmethod
    def _is_destructive(command: str) -> bool:
        return bool(re.search(r"(?:^|[;&|]\s*|\s)(?:rm|del|format|diskpart|shutdown|reboot|remove-item|rmdir|rd)(?:\s|$)", command, flags=re.IGNORECASE))
