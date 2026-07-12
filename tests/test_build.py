"""Deterministic Build and Project Agent coverage."""
from __future__ import annotations
import subprocess
import pytest
from fastapi.testclient import TestClient
from backend.app.api.routes import ai, build
from backend.app.coding.build_controller import BuildController
from backend.app.core.settings import AppSettings
from backend.app.domain.build import BuildActionRequest, BuildActionResult
from backend.app.memory.store import MemoryStore
from backend.app.main import create_app

class Runner:
    """Capture local tool invocations without running Docker or package managers."""
    def __init__(self) -> None: self.calls: list[list[str]] = []
    def __call__(self, args, **kwargs):
        self.calls.append(args); return subprocess.CompletedProcess(args, 0, "ok", "")

def controller(tmp_path):
    runner = Runner(); memory = MemoryStore(tmp_path / "memory.db", tmp_path / "chroma")
    return BuildController(AppSettings(coding_project_roots=[tmp_path]), memory, runner), runner, memory

def test_docker_and_dependency_adapters_are_local_and_safe(tmp_path) -> None:
    """All Docker and supported dependency commands are structured and deterministic."""
    service, runner, _ = controller(tmp_path)
    for action, payload in [("docker_build", {"image":"demo"}), ("docker_run", {"image":"demo","container":"demo"}), ("docker_stop", {"container":"demo"}), ("docker_logs", {"container":"demo"}), ("docker_list", {})]:
        assert service.execute(BuildActionRequest(action=action, path=str(tmp_path), **payload)).success
    for manager, expected in [("pip", ["python","-m","pip","install","-r","requirements.txt"]), ("npm", ["npm","install"]), ("maven", ["mvn","dependency:resolve"]), ("gradle", ["gradle","dependencies"])]:
        assert service.execute(BuildActionRequest(action="install_dependencies", path=str(tmp_path), package_manager=manager)).success
        assert expected in runner.calls
    assert runner.calls[0] == ["docker","build","-t","demo","."] and ["docker","ps"] in runner.calls

def test_build_confirmation_gates_and_project_templates_and_memory(tmp_path) -> None:
    """Privileged Docker and global installs require approval; every template registers locally."""
    service, _, memory = controller(tmp_path)
    assert service.execute(BuildActionRequest(action="docker_run", path=str(tmp_path), image="demo", container="demo", privileged=True)).confirmation_required
    assert service.execute(BuildActionRequest(action="install_dependencies", path=str(tmp_path), package_manager="npm", global_install=True)).confirmation_required
    for language in ["python", "flask", "fastapi", "cpp", "java", "javascript", "sql"]:
        result = service.execute(BuildActionRequest(action="generate_project", path=str(tmp_path), language=language, project_name=f"{language}_project"))
        assert result.success and (tmp_path / f"{language}_project" / "README.md").exists()
    assert len(memory.list("project")) == 7

@pytest.mark.parametrize("language", ["python", "flask", "fastapi", "cpp", "java", "javascript", "sql"])
def test_language_build_and_run_adapters(language, tmp_path) -> None:
    """Each supported language exposes deterministic build and run adapter behavior."""
    service, runner, _ = controller(tmp_path)
    built = service.execute(BuildActionRequest(action="build_project", path=str(tmp_path), language=language))
    ran = service.execute(BuildActionRequest(action="run_project", path=str(tmp_path), language=language))
    assert built.success and ran.success
    if language in {"cpp", "java"}: assert runner.calls

def test_build_api_ai_and_voice_command_text_route(monkeypatch) -> None:
    """Structured REST and shared typed/voice chat command routing reach the Build Agent."""
    class Controller:
        def execute(self, request): return BuildActionResult(success=True, message=f"{request.action} routed.")
    monkeypatch.setattr(build, "get_build_controller", lambda: Controller())
    monkeypatch.setattr(ai, "get_build_controller", lambda: Controller())
    client = TestClient(create_app())
    api_response = client.post("/api/v1/build/actions", json={"action":"docker_list"})
    phrases = ["Mjolnir, create a Flask project.", "Mjolnir, create a FastAPI project.", "Mjolnir, install dependencies.", "Mjolnir, build Docker image.", "Mjolnir, run this project.", "Mjolnir, show Docker logs."]
    responses = [client.post("/api/v1/chat", json={"message": phrase}) for phrase in phrases]
    assert api_response.status_code == 200 and api_response.json()["data"]["success"]
    assert all(response.status_code == 200 and "routed." in response.text for response in responses)
