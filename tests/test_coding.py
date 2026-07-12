"""Deterministic Coding Agent tests without launching a real editor or shell."""

from __future__ import annotations

import subprocess

from fastapi.testclient import TestClient

from backend.app.api.routes import ai, coding
from backend.app.coding.controller import CodingController
from backend.app.core.settings import AppSettings, get_settings
from backend.app.domain.coding import CodingActionRequest, CodingActionResult
from backend.app.memory.store import MemoryStore
from backend.app.main import create_app


class Launcher:
    """Capture VS Code launches without starting external processes."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, arguments: list[str], **_: object) -> None:
        self.calls.append(arguments)


class Runner:
    """Return deterministic terminal output and exit status."""

    def __call__(self, command: str, **_: object) -> subprocess.CompletedProcess[str]:
        if command == "bad":
            return subprocess.CompletedProcess(command, 2, "partial output", "failure output")
        return subprocess.CompletedProcess(command, 0, "server started", "")


class TimeoutRunner:
    """Raise a deterministic terminal timeout."""

    def __call__(self, command: str, **_: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(command, 5)


def _controller(tmp_path):
    memory = MemoryStore(tmp_path / "memory.db", tmp_path / "chroma")
    launcher = Launcher()
    controller = CodingController(
        AppSettings(coding_project_roots=[tmp_path], coding_command_timeout_seconds=5),
        memory,
        launcher=launcher,
        runner=Runner(),
    )
    return controller, launcher, memory


def test_vscode_workspace_file_and_integrated_terminal_are_launched(tmp_path) -> None:
    """VS Code receives safe commands for projects, files, and its terminal."""
    project = tmp_path / "project"
    project.mkdir()
    (project / ".git").mkdir()
    source = project / "app.py"
    source.write_text("print('ok')", encoding="utf-8")
    controller, launcher, memory = _controller(tmp_path)

    workspace = controller.execute(CodingActionRequest(action="open_workspace", path=str(project)))
    opened_file = controller.execute(CodingActionRequest(action="open_file", path=str(source)))
    revealed = controller.execute(CodingActionRequest(action="reveal_file", path=str(source)))
    terminal = controller.execute(CodingActionRequest(action="open_terminal", path=str(project)))

    assert workspace.success and opened_file.success and revealed.success and terminal.success
    assert launcher.calls[0] == ["code", "--reuse-window", str(project.resolve())]
    assert "--goto" in launcher.calls[2]
    assert launcher.calls[3][-2:] == ["--command", "workbench.action.terminal.new"]
    assert memory.get_preference("coding.active_workspace") == str(project.resolve())


def test_open_project_and_folder_have_dedicated_vscode_launches(tmp_path) -> None:
    """Projects and ordinary folders open through their explicit Coding Agent actions."""
    project = tmp_path / "project"
    folder = tmp_path / "folder"
    project.mkdir()
    folder.mkdir()
    controller, launcher, _ = _controller(tmp_path)

    opened_project = controller.execute(CodingActionRequest(action="open_project", path=str(project)))
    opened_folder = controller.execute(CodingActionRequest(action="open_folder", path=str(folder)))

    assert opened_project.success and opened_folder.success
    assert launcher.calls == [
        ["code", "--reuse-window", str(project.resolve())],
        ["code", "--reuse-window", str(folder.resolve())],
    ]


def test_terminal_output_error_exit_code_and_confirmation_are_structured(tmp_path) -> None:
    """Commands preserve stdout, stderr, exit code, and destructive approval gates."""
    project = tmp_path / "project"
    project.mkdir()
    controller, _, _ = _controller(tmp_path)

    success = controller.execute(CodingActionRequest(action="run_command", command="flask run", cwd=str(project)))
    failure = controller.execute(CodingActionRequest(action="run_command", command="bad", cwd=str(project)))
    blocked = controller.execute(CodingActionRequest(action="run_command", command="del important.txt", cwd=str(project)))
    approved = controller.execute(CodingActionRequest(action="run_command", command="del important.txt", cwd=str(project), confirmed=True))

    assert success.success and success.data["stdout"] == "server started" and success.data["exit_code"] == 0
    assert not failure.success and failure.data["stderr"] == "failure output" and failure.data["exit_code"] == 2
    assert blocked.confirmation_required and not blocked.success
    assert approved.success


def test_remembered_workspace_survives_restart_and_is_used_for_commands(tmp_path) -> None:
    """SQLite-backed active workspace state survives a new controller and supplies command cwd."""
    project = tmp_path / "project"
    project.mkdir()
    database_path = tmp_path / "memory.db"
    chroma_path = tmp_path / "chroma"
    first_store = MemoryStore(database_path, chroma_path)
    first = CodingController(AppSettings(coding_project_roots=[tmp_path]), first_store, launcher=Launcher(), runner=Runner())
    assert first.execute(CodingActionRequest(action="switch_project", path=str(project))).success

    captured: dict[str, object] = {}
    def runner(command: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.update(kwargs)
        return subprocess.CompletedProcess(command, 0, "ok", "")
    restarted = CodingController(AppSettings(coding_project_roots=[tmp_path]), MemoryStore(database_path, chroma_path), launcher=Launcher(), runner=runner)
    result = restarted.execute(CodingActionRequest(action="run_command", command="flask run"))

    assert result.success and captured["cwd"] == str(project.resolve())


def test_timeout_invalid_path_logging_and_protected_commands_are_structured(tmp_path, caplog) -> None:
    """Timeouts, invalid paths, logging, and every protected command fail safely."""
    caplog.set_level("INFO", logger="backend.app.coding.controller")
    project = tmp_path / "project"
    project.mkdir()
    controller, _, _ = _controller(tmp_path)
    protected = ["rm file", "rmdir folder", "rd folder", "remove-item file", "shutdown /s", "reboot", "diskpart", "format c:"]

    for command in protected:
        blocked = controller.execute(CodingActionRequest(action="run_command", command=command, cwd=str(project)))
        assert blocked.confirmation_required and not blocked.success
    completed = controller.execute(CodingActionRequest(action="run_command", command="flask run", cwd=str(project)))
    invalid = controller.execute(CodingActionRequest(action="open_file", path=str(project / "missing.py")))
    timed = CodingController(AppSettings(coding_project_roots=[tmp_path]), MemoryStore(tmp_path / "timeout.db", tmp_path / "timeout-chroma"), launcher=Launcher(), runner=TimeoutRunner()).execute(CodingActionRequest(action="run_command", command="flask run", cwd=str(project)))

    confirmation_log = next(record for record in caplog.records if record.message == "coding_confirmation_required")
    completed_log = next(record for record in caplog.records if record.message == "coding_command_completed")
    failure_log = next(record for record in caplog.records if record.message == "coding_action_failed" and record.action == "run_command")
    assert completed.success and not invalid.success and invalid.data["error"] == "Path does not exist."
    assert not timed.success and confirmation_log.action == "run_command" and completed_log.exit_code == 0 and failure_log.action == "run_command"
    assert "timed out" in failure_log.error


def test_multiple_projects_switching_api_validation_and_ai_command_routing(tmp_path, monkeypatch) -> None:
    """Project discovery, active-workspace selection, REST, and chat routes are connected."""
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "pyproject.toml").write_text("", encoding="utf-8")
    (second / "package.json").write_text("{}", encoding="utf-8")
    controller, _, memory = _controller(tmp_path)

    projects = controller.execute(CodingActionRequest(action="list_projects"))
    switched = controller.execute(CodingActionRequest(action="switch_project", path=str(second)))
    assert set(projects.data["projects"]) == {str(first.resolve()), str(second.resolve())}
    assert switched.success and memory.get_preference("coding.active_workspace") == str(second.resolve())

    class ApiController:
        def execute(self, request: CodingActionRequest) -> CodingActionResult:
            return CodingActionResult(success=True, message=f"{request.action} routed.")

    monkeypatch.setattr(coding, "get_coding_controller", lambda: ApiController())
    monkeypatch.setattr(ai, "get_coding_controller", lambda: ApiController())
    client = TestClient(create_app())
    response = client.post("/api/v1/coding/actions", json={"action": "list_projects"})
    commands = {
        "Mjolnir, list my projects.": "list_projects",
        "Mjolnir, open this project in VS Code.": "open_project",
        "Mjolnir, run my Flask app.": "run_command",
        "Mjolnir, open terminal.": "open_terminal",
    }
    chats = [client.post("/api/v1/chat", json={"message": command}) for command in commands]
    invalid_action = client.post("/api/v1/coding/actions", json={"action": "delete_everything"})
    invalid_fields = client.post("/api/v1/coding/actions", json={"action": "run_command", "command": "x" * 12001})
    assert response.status_code == 200 and response.json()["data"]["success"]
    assert all(chat.status_code == 200 and "routed." in chat.text for chat in chats)
    assert invalid_action.status_code == 422 and invalid_fields.status_code == 422


def test_coding_configuration_file_and_environment_overrides(tmp_path, monkeypatch) -> None:
    """Coding configuration loads from JSON and environment values take precedence."""
    config = tmp_path / "app.json"
    config.write_text('{"coding_vscode_command":"configured-code","coding_command_timeout_seconds":7}', encoding="utf-8")
    monkeypatch.setenv("MJOLNIROS_CONFIG_FILE", str(config))
    monkeypatch.setenv("MJOLNIROS_CODING_VSCODE_COMMAND", "environment-code")
    get_settings.cache_clear()
    loaded = get_settings()
    get_settings.cache_clear()

    assert loaded.coding_vscode_command == "environment-code"
    assert loaded.coding_command_timeout_seconds == 7
