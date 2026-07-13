from fastapi.testclient import TestClient

from backend.app.core.settings import get_settings
from backend.app.main import create_app


def test_health_endpoint_returns_standard_response() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["status"] == "ok"
    assert payload["data"]["default_model"] == "qwen2.5:3b"


def test_settings_endpoint_exposes_non_sensitive_configuration() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/settings")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["api_prefix"] == "/api/v1"
    assert "enabled_foundation_modules" in payload["data"]


def test_environment_settings_override_json_configuration(
    tmp_path, monkeypatch
) -> None:
    config_file = tmp_path / "app.json"
    config_file.write_text('{"default_model": "file-model"}', encoding="utf-8")
    monkeypatch.setenv("MJOLNIROS_CONFIG_FILE", str(config_file))
    monkeypatch.setenv("MJOLNIROS_DEFAULT_MODEL", "environment-model")
    get_settings.cache_clear()
    try:
        assert get_settings().default_model == "environment-model"
    finally:
        get_settings.cache_clear()
