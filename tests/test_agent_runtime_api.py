"""Integration checks for authenticated production Windows capabilities."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import SecretStr

from backend.app.core.settings import AppSettings
from backend.app.main import create_app
from backend.app.tasks.lifecycle import TaskStatus


def _client(tmp_path: Path) -> TestClient:
    approved = tmp_path / "approved"
    approved.mkdir(exist_ok=True)
    settings = AppSettings(
        environment="test",
        config_file=tmp_path / "missing-config.json",
        api_token=SecretStr("t" * 48),
        api_token_expires_at=4_102_444_800,
        database_path=tmp_path / "mjolnir-test.db",
        chroma_path=tmp_path / "chroma-test",
        windows_search_root=approved,
        coding_project_roots=[approved],
    )
    app = create_app(settings)
    return TestClient(app)


def test_agent_api_is_authenticated_and_registers_scoped_windows_capabilities(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        assert client.get("/api/v1/agents/capabilities").status_code == 401
        response = client.get(
            "/api/v1/agents/capabilities",
            headers={"Authorization": f"Bearer {'t' * 48}"},
        )
        assert response.status_code == 200
        identifiers = {item["capability_id"] for item in response.json()["data"]}
        assert "windows.launch_application" in identifiers
        assert "windows.read_file" in identifiers
        assert "windows.delete_file" in identifiers


def test_agent_filesystem_read_is_scoped_and_persistent(tmp_path: Path) -> None:
    root = tmp_path / "approved"
    root.mkdir()
    (root / "notes.txt").write_text("approved content", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    headers = {"Authorization": f"Bearer {'t' * 48}"}

    with _client(tmp_path) as client:
        read = client.post(
            "/api/v1/agents/tasks",
            headers=headers,
            json={
                "capability_id": "windows.read_file",
                "input": {"path": "notes.txt"},
                "idempotency_key": "read-approved-001",
            },
        )
        assert read.status_code == 201
        assert read.json()["status"] == TaskStatus.SUCCEEDED.value
        assert read.json()["result_summary"] == "Supported text file read. Content is hidden from task history."
        task_id = read.json()["task_id"]
        persisted = client.get(f"/api/v1/agents/tasks/{task_id}", headers=headers)
        assert "approved content" not in persisted.text

        traversal = client.post(
            "/api/v1/agents/tasks",
            headers=headers,
            json={
                "capability_id": "windows.read_file",
                "input": {"path": "../outside.txt"},
                "idempotency_key": "read-outside-001",
            },
        )
        assert traversal.status_code == 201
        assert traversal.json()["status"] == TaskStatus.FAILED.value


def test_sensitive_file_creation_waits_for_exact_approval(tmp_path: Path) -> None:
    headers = {"Authorization": f"Bearer {'t' * 48}"}
    with _client(tmp_path) as client:
        pending = client.post(
            "/api/v1/agents/tasks",
            headers=headers,
            json={
                "capability_id": "windows.create_file",
                "input": {"path": "created.txt", "content": "reviewed payload"},
                "idempotency_key": "create-file-001",
            },
        )
        assert pending.status_code == 201
        assert pending.json()["status"] == TaskStatus.WAITING_APPROVAL.value
        assert not (tmp_path / "approved" / "created.txt").exists()

        details = client.get(
            f"/api/v1/agents/tasks/{pending.json()['task_id']}/approval-details",
            headers=headers,
        )
        assert details.status_code == 200
        assert details.json()["data"]["path"] == "created.txt"
        assert details.json()["data"]["content_preview"] == "reviewed payload"

        approved = client.post(
            f"/api/v1/agents/tasks/{pending.json()['task_id']}/approve",
            headers=headers,
        )
        assert approved.status_code == 200
        assert approved.json()["status"] == TaskStatus.SUCCEEDED.value
        assert (tmp_path / "approved" / "created.txt").read_text(encoding="utf-8") == "reviewed payload"
        history = client.get("/api/v1/agents/tasks", headers=headers)
        assert history.status_code == 200
        assert "reviewed payload" not in history.text


def test_agent_task_idempotency_rejects_reused_key_for_different_action(
    tmp_path: Path,
) -> None:
    headers = {"Authorization": f"Bearer {'t' * 48}"}
    with _client(tmp_path) as client:
        first = client.post(
            "/api/v1/agents/tasks",
            headers=headers,
            json={
                "capability_id": "windows.list_directory",
                "input": {"path": "."},
                "idempotency_key": "same-key-0001",
            },
        )
        assert first.status_code == 201
        conflict = client.post(
            "/api/v1/agents/tasks",
            headers=headers,
            json={
                "capability_id": "windows.read_file",
                "input": {"path": "notes.txt"},
                "idempotency_key": "same-key-0001",
            },
        )
        assert conflict.status_code == 409
