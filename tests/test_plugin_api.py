import json

from fastapi.testclient import TestClient
import pytest

from backend.app.core.settings import AppSettings
from backend.app.domain.plugin import PluginCatalog, PluginManifest
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


def test_plugin_discovery_blocks_invalid_metadata_missing_files_and_cycles(
    tmp_path, monkeypatch
) -> None:
    client = _client(tmp_path, monkeypatch)
    plugins_directory = tmp_path / "plugins"

    invalid = plugins_directory / "invalid"
    invalid.mkdir(parents=True)
    (invalid / "manifest.json").write_text("{}", encoding="utf-8")
    (invalid / "permissions.json").write_text(
        json.dumps({"permissions": []}), encoding="utf-8"
    )
    (invalid / "plugin.py").write_text("def activate(): pass\n", encoding="utf-8")
    (invalid / "README.md").write_text("# Invalid\n", encoding="utf-8")

    incomplete = plugins_directory / "incomplete"
    incomplete.mkdir()

    for plugin_id, dependency_id in (("first", "second"), ("second", "first")):
        plugin = plugins_directory / plugin_id
        plugin.mkdir()
        (plugin / "manifest.json").write_text(
            json.dumps(
                {
                    "id": plugin_id,
                    "name": plugin_id.title(),
                    "version": "1.0.0",
                    "description": "Cycle test plugin.",
                    "category": "Testing",
                    "dependencies": [{"id": dependency_id, "min_version": "1.0.0"}],
                }
            ),
            encoding="utf-8",
        )
        (plugin / "permissions.json").write_text(
            json.dumps({"permissions": []}), encoding="utf-8"
        )
        (plugin / "plugin.py").write_text("def activate(): pass\n", encoding="utf-8")
        (plugin / "README.md").write_text(f"# {plugin_id}\n", encoding="utf-8")

    records = {
        item["manifest"]["id"]: item
        for item in client.get("/api/v1/plugins").json()["data"]
    }
    assert records["invalid"]["status"] == "blocked"
    assert records["incomplete"]["status"] == "blocked"
    assert records["first"]["blocked_reason"] == "Plugin dependencies contain a cycle."
    assert records["second"]["blocked_reason"] == "Plugin dependencies contain a cycle."


def test_plugin_catalog_rejects_duplicate_ids() -> None:
    manifest = PluginManifest(
        id="unique",
        name="Unique",
        version="1.0.0",
        description="Unique catalog entry.",
        category="Testing",
    )

    with pytest.raises(ValueError, match="duplicate plugin ids"):
        PluginCatalog(plugins=[manifest, manifest])


def test_plugin_rejects_incomplete_permissions(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    plugin = tmp_path / "plugins" / "permission-test"
    plugin.mkdir(parents=True)
    (plugin / "manifest.json").write_text(
        json.dumps(
            {
                "id": "permission-test",
                "name": "Permission test",
                "version": "1.0.0",
                "description": "Permission validation.",
                "category": "Testing",
            }
        ),
        encoding="utf-8",
    )
    (plugin / "permissions.json").write_text(
        json.dumps({"permissions": ["communication_send"]}), encoding="utf-8"
    )
    (plugin / "plugin.py").write_text("def activate(): pass\n", encoding="utf-8")
    (plugin / "README.md").write_text("# Permission test\n", encoding="utf-8")
    record = next(
        item
        for item in client.get("/api/v1/plugins").json()["data"]
        if item["manifest"]["id"] == "permission-test"
    )
    assert record["status"] == "blocked"
    assert "Missing required permissions" in record["blocked_reason"]


def test_plugin_rejects_version_conflicts_load_failures_and_dependent_removal(
    tmp_path, monkeypatch
) -> None:
    client = _client(tmp_path, monkeypatch)
    client.get("/api/v1/plugins")
    plugins_directory = tmp_path / "plugins"

    definitions = (
        ("dependent", [{"id": "calculator", "min_version": "1.0.0"}], "pass"),
        ("conflict", [{"id": "calculator", "min_version": "2.0.0"}], "pass"),
        ("load_failure", [], "raise RuntimeError('failed')"),
    )
    for plugin_id, dependencies, body in definitions:
        plugin = plugins_directory / plugin_id
        plugin.mkdir()
        (plugin / "manifest.json").write_text(
            json.dumps(
                {
                    "id": plugin_id,
                    "name": plugin_id.title(),
                    "version": "1.0.0",
                    "description": "Plugin API hardening test.",
                    "category": "Testing",
                    "dependencies": dependencies,
                }
            ),
            encoding="utf-8",
        )
        (plugin / "permissions.json").write_text(
            json.dumps({"permissions": []}), encoding="utf-8"
        )
        (plugin / "plugin.py").write_text(
            f"def activate():\n    {body}\n", encoding="utf-8"
        )
        (plugin / "README.md").write_text(f"# {plugin_id}\n", encoding="utf-8")

    records = {
        item["manifest"]["id"]: item
        for item in client.get("/api/v1/plugins").json()["data"]
    }
    assert "Unsatisfied dependencies" in records["conflict"]["blocked_reason"]
    assert client.post("/api/v1/plugins/load_failure/load").status_code == 422
    assert client.delete("/api/v1/plugins/calculator").status_code == 409
