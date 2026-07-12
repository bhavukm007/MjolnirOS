from fastapi.testclient import TestClient

from backend.app.core.settings import AppSettings
from backend.app.main import create_app


def _client(tmp_path, monkeypatch) -> TestClient:
    settings = AppSettings(
        learning_storage_directory=tmp_path / "learning",
        automation_storage_directory=tmp_path / "automation",
        learning_suggestion_threshold=3,
    )
    monkeypatch.setattr(
        "backend.app.api.routes.learning.get_settings", lambda: settings
    )
    monkeypatch.setattr(
        "backend.app.api.routes.automation.get_settings", lambda: settings
    )
    return TestClient(create_app(settings))


def test_learning_derives_preferences_and_requires_approval_for_workflow(
    tmp_path, monkeypatch
) -> None:
    client = _client(tmp_path, monkeypatch)
    for _ in range(3):
        response = client.post(
            "/api/v1/learning/observations",
            json={"kind": "application", "value": "VS Code"},
        )
        assert response.status_code == 200
    for _ in range(3):
        response = client.post(
            "/api/v1/learning/observations", json={"kind": "browser", "value": "Edge"}
        )
        assert response.status_code == 200

    overview = client.get("/api/v1/learning/overview")
    assert overview.status_code == 200
    data = overview.json()["data"]
    assert data["observation_count"] == 6
    assert {item["value"] for item in data["preferences"]} >= {"VS Code", "Edge"}
    assert any(item["key"] == "preferred_ide" for item in data["preferences"])
    suggestion = data["suggestions"][0]
    assert suggestion["status"] == "pending"

    workflows_before = client.get("/api/v1/automation/workflows").json()["data"]
    approved = client.post(f"/api/v1/learning/suggestions/{suggestion['id']}/approve")
    assert approved.status_code == 200
    workflows_after = client.get("/api/v1/automation/workflows").json()["data"]
    assert len(workflows_after) == len(workflows_before) + 1

    updated = next(
        item
        for item in client.get("/api/v1/learning/suggestions").json()["data"]
        if item["id"] == suggestion["id"]
    )
    assert updated["status"] == "approved"
    assert updated["workflow_id"] == approved.json()["data"]["id"]


def test_learning_can_dismiss_a_pending_suggestion(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    for _ in range(3):
        client.post(
            "/api/v1/learning/observations",
            json={"kind": "startup", "value": "Docker Desktop"},
        )

    suggestion = client.get("/api/v1/learning/suggestions").json()["data"][0]
    dismissed = client.post(f"/api/v1/learning/suggestions/{suggestion['id']}/dismiss")

    assert dismissed.status_code == 200
    assert dismissed.json()["data"]["status"] == "dismissed"
