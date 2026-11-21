from fastapi.testclient import TestClient
from pydantic import SecretStr
import json
import time
import asyncio

from backend.app.agent_runtime.runtime import AgentRuntime
from backend.app.api.routes import ai as ai_routes
from backend.app.core.settings import AppSettings
from backend.app.main import create_app
from backend.app.tasks.lifecycle import TaskStatus
from backend.app.windows.super_agent import WindowsSuperAgent


API_TOKEN = "test-j2-route-token-0123456789abcdef"


def _client(tmp_path, *, coding_root=None):
    settings = AppSettings(
        api_token=SecretStr(API_TOKEN),
        database_path=tmp_path / "agent-tasks.sqlite3",
        windows_search_root=tmp_path,
        coding_project_roots=[coding_root or tmp_path],
    )
    return TestClient(
        create_app(settings), headers={"Authorization": f"Bearer {API_TOKEN}"}
    )


def _stub_windows_system_reads(monkeypatch):
    """Keep route and orchestration tests independent of the host OS."""
    monkeypatch.setattr(
        WindowsSuperAgent,
        "system_status",
        staticmethod(lambda _payload: {
            "result": {
                "cpu_percent": 12.5,
                "memory_percent": 37.0,
                "disk_percent": 48.0,
                "battery_percent": None,
                "battery_plugged": None,
            }
        }),
    )
    monkeypatch.setattr(
        WindowsSuperAgent,
        "list_processes",
        staticmethod(lambda _payload: {"result": {"processes": []}}),
    )


def test_authenticated_production_capability_discovery_registers_browser_and_coding(tmp_path):
    with _client(tmp_path) as client:
        response = client.get("/api/v1/agents/capabilities")

    assert response.status_code == 200
    ids = {item["capability_id"] for item in response.json()["data"]}
    assert "browser.safe_action" in ids
    assert {
        "windows.open_task_manager",
        "coding.detect_vscode",
        "coding.list_projects",
        "coding.git_status",
        "coding.open_project",
        "coding.open_file",
        "coding.run_flask",
        "coding.run_project_tests",
    } <= ids


def test_coding_legacy_route_executes_through_registered_capability(tmp_path):
    project_root = tmp_path / "projects"
    project = project_root / "demo"
    project.mkdir(parents=True)
    (project / "package.json").write_text("{}", encoding="utf-8")
    with _client(tmp_path, coding_root=project_root) as client:
        response = client.post(
            "/api/v1/coding/actions", json={"action": "list_projects"}
        )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert str(project.resolve()) in response.json()["data"]["data"]["projects"]


def test_chat_system_health_routes_to_live_windows_capability(tmp_path, monkeypatch):
    _stub_windows_system_reads(monkeypatch)
    settings = AppSettings(
        api_token=SecretStr(API_TOKEN),
        database_path=tmp_path / "agent-tasks.sqlite3",
        windows_search_root=tmp_path,
        coding_project_roots=[tmp_path],
        settings_storage_directory=tmp_path / "settings",
    )

    class MemoryStub:
        def handle_command(self, _message):
            return None

        def record_conversation(self, _role, _content):
            return None

    monkeypatch.setattr(ai_routes, "get_memory_store", lambda: object())
    monkeypatch.setattr(ai_routes, "MemoryService", lambda _store: MemoryStub())
    monkeypatch.setattr(ai_routes, "get_runtime_ai_settings", lambda: settings)
    monkeypatch.setattr(
        ai_routes,
        "get_ollama_client",
        lambda: (_ for _ in ()).throw(AssertionError("system health fell through to Ollama")),
    )
    with TestClient(
        create_app(settings), headers={"Authorization": f"Bearer {API_TOKEN}"}
    ) as client:
        response = client.post("/api/v1/chat", json={"message": "Show system health"})
        tasks = client.get("/api/v1/agents/tasks?limit=5")

    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    assert any(event.get("type") == "tool_result" and "System status:" in event.get("content", "") for event in events)
    assert any(event.get("type") == "routing_decision" and event.get("capability") == "windows" for event in events)
    assert tasks.status_code == 200
    assert tasks.json()[0]["capability_id"] == "windows.get_system_status"
    assert tasks.json()[0]["status"] == "succeeded"


def test_browser_legacy_route_rejects_unregistered_download_action(tmp_path):
    with _client(tmp_path) as client:
        response = client.post(
            "/api/v1/browser/actions",
            json={"action": "download", "url": "https://example.com/file"},
        )

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert "not available through the approved capability registry" in response.json()["message"]


def test_browser_production_capability_blocks_local_network_target(tmp_path):
    with _client(tmp_path) as client:
        response = client.post(
            "/api/v1/browser/actions",
            json={"action": "open", "url": "http://127.0.0.1:8000/"},
        )

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert "failed" in response.json()["message"].lower()


def test_windows_legacy_confirmation_flag_cannot_approve_sensitive_operation(tmp_path):
    target = tmp_path / "protected.txt"
    target.write_text("keep this", encoding="utf-8")
    with _client(tmp_path) as client:
        response = client.post(
            "/api/v1/windows/actions",
            json={"action": "delete_file", "arguments": {"path": "protected.txt"}, "confirmed": True},
        )

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert response.json()["data"]["confirmation_required"] is True
    assert target.read_text(encoding="utf-8") == "keep this"


def test_coding_sensitive_command_waits_for_exact_agent_approval(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    with _client(tmp_path, coding_root=tmp_path) as client:
        response = client.post(
            "/api/v1/coding/actions",
            json={"action": "run_command", "command": "flask run", "cwd": str(project)},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["data"]["confirmation_required"] is True
    task_id = body["data"]["data"]["task_id"]
    with _client(tmp_path, coding_root=tmp_path) as client:
        task = client.get(f"/api/v1/agents/tasks/{task_id}")
        assert task.status_code == 200
        assert task.json()["status"] == "waiting_approval"


def test_persistent_sequential_plan_runs_and_records_step_events(tmp_path, monkeypatch):
    _stub_windows_system_reads(monkeypatch)
    with _client(tmp_path) as client:
        created = client.post(
            "/api/v1/agents/plans",
            json={
                "idempotency_key": "plan-health-check-001",
                "steps": [
                    {"capability_id": "windows.get_system_status", "input": {}},
                    {"capability_id": "windows.list_processes", "input": {}},
                ],
            },
        )
        assert created.status_code == 202
        task_id = created.json()["task_id"]
        for _ in range(100):
            current = client.get(f"/api/v1/agents/tasks/{task_id}").json()
            if current["status"] in {"succeeded", "failed", "cancelled"}:
                break
            time.sleep(0.05)
        assert current["status"] == "succeeded"
        events = client.get(f"/api/v1/agents/tasks/{task_id}/events")

    assert events.status_code == 200
    assert sum(event["event_type"] == "step_completed" for event in events.json()["data"]) == 2


def test_approval_gated_capability_cannot_be_embedded_in_plan(tmp_path):
    with _client(tmp_path) as client:
        response = client.post(
            "/api/v1/agents/plans",
            json={
                "idempotency_key": "plan-deny-sensitive-01",
                "steps": [
                    {"capability_id": "windows.get_system_status", "input": {}},
                    {"capability_id": "windows.delete_file", "input": {"path": "x.txt"}},
                ],
            },
        )

    assert response.status_code == 422


def test_permission_revocation_survives_runtime_restart(tmp_path):
    database = tmp_path / "agent-tasks.sqlite3"
    settings = AppSettings(
        api_token=SecretStr(API_TOKEN),
        database_path=database,
        windows_search_root=tmp_path,
    )
    with TestClient(create_app(settings), headers={"Authorization": f"Bearer {API_TOKEN}"}) as client:
        permissions = client.get("/api/v1/agents/permissions").json()["data"]
        grant = next(item for item in permissions if item["capability_id"] == "windows.get_system_status")
        revoked = client.post(f"/api/v1/agents/permissions/{grant['grant_id']}/revoke")
        assert revoked.status_code == 200

    with TestClient(create_app(settings), headers={"Authorization": f"Bearer {API_TOKEN}"}) as client:
        response = client.post(
            "/api/v1/agents/tasks",
            json={
                "capability_id": "windows.get_system_status",
                "input": {},
                "idempotency_key": "revoked-system-read-001",
            },
        )

    assert response.status_code == 201
    assert response.json()["status"] == "failed"
    assert response.json()["error_code"] == "permission_denied"


def test_persisted_non_content_approval_survives_runtime_restart(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    settings = AppSettings(
        api_token=SecretStr(API_TOKEN),
        database_path=tmp_path / "agent-tasks.sqlite3",
        windows_search_root=tmp_path,
        coding_project_roots=[tmp_path],
    )
    with TestClient(create_app(settings), headers={"Authorization": f"Bearer {API_TOKEN}"}) as client:
        created = client.post(
            "/api/v1/agents/tasks",
            json={
                "capability_id": "coding.run_flask",
                "input": {"project": str(project)},
                "idempotency_key": "restart-approval-test-01",
            },
        )
        assert created.status_code == 201
        task_id = created.json()["task_id"]
        assert created.json()["status"] == "waiting_approval"

    with TestClient(create_app(settings), headers={"Authorization": f"Bearer {API_TOKEN}"}) as client:
        restored = client.get(f"/api/v1/agents/tasks/{task_id}")

    assert restored.status_code == 200
    assert restored.json()["status"] == "waiting_approval"


def test_running_plan_cancellation_stops_before_the_next_step(tmp_path, monkeypatch):
    _stub_windows_system_reads(monkeypatch)
    settings = AppSettings(
        database_path=tmp_path / "agent-tasks.sqlite3",
        windows_search_root=tmp_path,
    )
    runtime = AgentRuntime(settings)
    task = runtime.create_plan_task(
        [
            {"capability_id": "windows.get_system_status", "input": {}},
            {"capability_id": "windows.list_processes", "input": {}},
        ],
        "cancel-plan-before-second-01",
    )
    execute = runtime.orchestrator.execute

    async def cancel_after_first(plan, **kwargs):
        completed_callback = kwargs["on_step_completed"]
        count = 0

        def on_step_completed(step):
            nonlocal count
            completed_callback(step)
            count += 1
            if count == 1:
                runtime.cancel(task.task_id)

        kwargs["on_step_completed"] = on_step_completed
        return await execute(plan, **kwargs)

    runtime.orchestrator.execute = cancel_after_first
    result = asyncio.run(runtime.execute_task(task.task_id))

    assert result.status.value == "cancelled"
    assert result.result == {"completed_steps": 1}
    assert sum(event["event_type"] == "step_completed" for event in runtime.store.events(task.task_id)) == 1


def test_interrupted_task_is_not_replayed_after_runtime_restart(tmp_path):
    settings = AppSettings(
        database_path=tmp_path / "agent-tasks.sqlite3",
        windows_search_root=tmp_path,
    )
    runtime = AgentRuntime(settings)
    task = runtime.create_task(
        "windows.create_file",
        {"path": "must-not-appear.txt", "content": "approved data"},
        "crash-safe-file-create-01",
    )
    runtime.store.update(task.task_id, status=TaskStatus.RUNNING)

    restarted = AgentRuntime(settings)
    recovered = restarted.store.get(task.task_id)

    assert recovered.status.value == "interrupted"
    assert not (tmp_path / "must-not-appear.txt").exists()
