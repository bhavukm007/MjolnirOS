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


def test_development_cors_allows_loopback_frontend_origins() -> None:
    client = TestClient(create_app())
    endpoints = ("/api/v1/health", "/api/v1/settings", "/api/v1/voice/health")

    for origin in ("http://127.0.0.1:5173", "http://localhost:5173"):
        for endpoint in endpoints:
            response = client.get(endpoint, headers={"Origin": origin})
            assert response.status_code == 200
            assert response.headers["access-control-allow-origin"] == origin


def test_production_cors_only_allows_configured_frontend() -> None:
    settings = get_settings().model_copy(
        update={"environment": "production", "frontend_url": "https://app.example.com"}
    )
    client = TestClient(create_app(settings))

    allowed = client.get(
        "/api/v1/health", headers={"Origin": "https://app.example.com"}
    )
    rejected = client.get(
        "/api/v1/health", headers={"Origin": "http://127.0.0.1:5173"}
    )

    assert allowed.headers["access-control-allow-origin"] == "https://app.example.com"
    assert "access-control-allow-origin" not in rejected.headers
