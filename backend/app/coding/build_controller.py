"""Build and Project Agent orchestration layer."""
from __future__ import annotations
import logging, subprocess
from pathlib import Path
from typing import Callable
from backend.app.core.settings import AppSettings
from backend.app.domain.build import BuildActionRequest, BuildActionResult
from backend.app.domain.memory import MemoryCreate
from backend.app.memory.store import MemoryStore
from backend.app.coding.build_adapters import DependencyAdapter, DockerAdapter, LanguageAdapter, TemplateGenerator

class BuildController:
    """Coordinate modular local build tools and persist registered projects."""
    def __init__(self, settings: AppSettings, memory: MemoryStore, runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run) -> None:
        self._settings, self._memory, self._runner = settings, memory, runner
        self._docker, self._dependencies, self._languages, self._templates = DockerAdapter(runner), DependencyAdapter(), LanguageAdapter(), TemplateGenerator()
        self._logger = logging.getLogger(__name__)
    def execute(self, request: BuildActionRequest) -> BuildActionResult:
        """Execute a safe local build action with structured output."""
        if (request.global_install or request.privileged) and not request.confirmed:
            return BuildActionResult(success=False, message="Confirmation is required for this privileged action.", confirmation_required=True)
        try: return self._execute(request)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            self._logger.warning("build_action_failed", extra={"action": request.action, "error": str(error)})
            return BuildActionResult(success=False, message="Build action failed.", data={"error": str(error)})
    def _execute(self, r: BuildActionRequest) -> BuildActionResult:
        path = Path(r.path or self._settings.coding_project_roots[0]).expanduser().resolve()
        if r.action == "generate_project":
            if not r.language or not r.project_name: raise ValueError("language and project_name are required.")
            files = self._templates.generate(path, r.language, r.project_name); project = path / r.project_name; self._register(project, r.language)
            return BuildActionResult(success=True, message="Project generated.", data={"path": str(project), "files": [str(item) for item in files]})
        if r.action == "register_project":
            self._register(path, r.language); return BuildActionResult(success=True, message="Project registered.", data={"path": str(path)})
        if r.action.startswith("docker_"): return self._docker_action(r, path)
        if r.action == "install_dependencies":
            if not r.package_manager: raise ValueError("package_manager is required.")
            return self._completed(self._runner(self._dependencies.command(r.package_manager, r.global_install), cwd=str(path), text=True, capture_output=True, check=False), "Dependencies resolved.")
        if r.action in {"build_project", "run_project"}:
            if not r.language: raise ValueError("language is required.")
            build, run = self._languages.commands(r.language); command = build if r.action == "build_project" else run
            if command is None: return BuildActionResult(success=True, message="No compilation is required.", data={"language": r.language})
            return self._completed(self._runner(command, cwd=str(path), text=True, capture_output=True, check=False), "Project built." if r.action == "build_project" else "Project started.")
        raise ValueError("Unsupported build action.")
    def _docker_action(self, r: BuildActionRequest, path: Path) -> BuildActionResult:
        if r.action == "docker_build": args = ["build", "-t", self._required(r.image, "image"), "."]
        elif r.action == "docker_run": args = ["run", "-d", "--name", self._required(r.container, "container"), *( ["--privileged"] if r.privileged else []), self._required(r.image, "image")]
        elif r.action == "docker_stop": args = ["stop", self._required(r.container, "container")]
        elif r.action == "docker_logs": args = ["logs", self._required(r.container, "container")]
        else: args = ["ps"]
        return self._completed(self._docker.execute(args, path), "Docker action completed.")
    def _register(self, path: Path, language: str | None) -> None:
        self._memory.save(MemoryCreate(memory_type="project", content=str(path), metadata={"agent": "build", "language": language or "unknown"}))
        self._memory.set_preference("coding.active_workspace", str(path)); self._logger.info("build_project_registered", extra={"path": str(path), "language": language})
    @staticmethod
    def _required(value: str | None, name: str) -> str:
        if not value: raise ValueError(f"{name} is required.")
        return value
    @staticmethod
    def _completed(result: subprocess.CompletedProcess[str], message: str) -> BuildActionResult:
        return BuildActionResult(success=result.returncode == 0, message=message if result.returncode == 0 else "Build command failed.", data={"stdout": result.stdout, "stderr": result.stderr, "exit_code": result.returncode})
