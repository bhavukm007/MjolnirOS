"""Deterministic Coding Agent tests without launching a real editor or shell."""

from __future__ import annotations

import subprocess

from fastapi.testclient import TestClient

from backend.app.api.routes import ai, coding
from backend.app.coding.controller import CodingController
from backend.app.core.settings import AppSettings
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


def test_multiple_projects_switching_and_api_and_ai_voice_routing(tmp_path, monkeypatch) -> None:
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
    chat = client.post("/api/v1/chat", json={"message": "Mjolnir, list my projects."})
    assert response.status_code == 200 and response.json()["data"]["success"]
    assert chat.status_code == 200 and "list_projects routed." in chat.text
