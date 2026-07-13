import json

from fastapi.testclient import TestClient

from backend.app.core.settings import AppSettings
from backend.app.main import create_app


def _client(tmp_path, monkeypatch) -> TestClient:
    settings = AppSettings(
        plugin_directory=tmp_path / "plugins",
        plugin_catalog_file=tmp_path / "catalog.json",
        plugin_state_file=tmp_path / "plugin-state.json",
    )
    monkeypatch.setattr("backend.app.api.routes.plugins.get_settings", lambda: settings)
    return TestClient(create_app(settings))


def test_plugin_marketplace_install_load_update_and_uninstall(
    tmp_path, monkeypatch
) -> None:
    client = _client(tmp_path, monkeypatch)

    marketplace = client.get("/api/v1/plugins/marketplace")
    assert marketplace.status_code == 200
    assert {item["manifest"]["id"] for item in marketplace.json()["data"]} >= {
        "spotify",
        "weather",
        "calculator",
        "clock",
        "github",
        "docker",
    }

    loaded = client.post("/api/v1/plugins/calculator/load")
    assert loaded.status_code == 200
    assert loaded.json()["data"]["status"] == "loaded"

    disabled = client.post("/api/v1/plugins/calculator/disable")
    assert disabled.status_code == 200
    assert disabled.json()["data"]["status"] == "disabled"
    assert (
        next(
            item
            for item in client.get("/api/v1/plugins").json()["data"]
            if item["manifest"]["id"] == "calculator"
        )["status"]
        == "disabled"
    )

    updated = client.post("/api/v1/plugins/calculator/update")
    assert updated.status_code == 200
    assert updated.json()["data"]["status"] == "loaded"

    removed = client.delete("/api/v1/plugins/calculator")
    assert removed.status_code == 204
    assert (
        client.get("/api/v1/plugins/marketplace").json()["data"][2]["installed"]
        is False
    )

    installed = client.post("/api/v1/plugins/calculator/install")
    assert installed.status_code == 200
    assert installed.json()["data"]["status"] == "loaded"


def test_plugin_permissions_and_dependencies_are_validated(
    tmp_path, monkeypatch
) -> None:
    client = _client(tmp_path, monkeypatch)
    plugin = tmp_path / "plugins" / "restricted"
    plugin.mkdir(parents=True)
    (plugin / "manifest.json").write_text(
        json.dumps(
            {
                "id": "restricted",
                "name": "Restricted",
                "version": "1.0.0",
                "description": "Requires a reviewed capability.",
                "category": "Testing",
                "dependencies": [{"id": "missing", "min_version": "1.0.0"}],
            }
        ),
        encoding="utf-8",
    )
    (plugin / "permissions.json").write_text(
        json.dumps({"permissions": ["registry"]}), encoding="utf-8"
    )
    (plugin / "plugin.py").write_text(
        "def activate():\n    return 'ready'\n", encoding="utf-8"
    )
    (plugin / "README.md").write_text("# Restricted\n", encoding="utf-8")

    plugins = client.get("/api/v1/plugins")
    restricted = next(
        item
        for item in plugins.json()["data"]
        if item["manifest"]["id"] == "restricted"
    )
    assert restricted["status"] == "blocked"
    assert "Unknown permissions" in restricted["blocked_reason"]
    assert client.post("/api/v1/plugins/restricted/load").status_code == 422
