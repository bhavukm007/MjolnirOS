"""Coverage for productivity confirmation, OAuth, and plugin integration boundaries."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

from backend.app.core.settings import AppSettings
from backend.app.domain.productivity import (
    CalendarEventCreate,
    EmailDraftCreate,
    ProductivityProvider,
)
from backend.app.plugins.plugin_service import PluginService
from backend.app.productivity.productivity_service import ProductivityService


class InMemoryTokenStore:
    """Token-store fake used without weakening production DPAPI behavior."""

    def __init__(self) -> None:
        self.data: dict[str, dict[str, object]] = {}

    def load(self) -> dict[str, dict[str, object]]:
        return self.data.copy()

    def save(self, value: dict[str, dict[str, object]]) -> None:
        self.data = value.copy()


def _service(tmp_path) -> ProductivityService:
    service = ProductivityService(
        AppSettings(
            productivity_storage_directory=tmp_path,
            google_oauth_client_id="client",
            google_oauth_client_secret="secret",
        )
    )
    service._store = InMemoryTokenStore()  # type: ignore[assignment]
    return service


def test_email_draft_needs_explicit_confirmation(tmp_path) -> None:
    service = _service(tmp_path)
    draft = service.create_draft(
        EmailDraftCreate(to=["user@example.com"], subject="Hello", body="Hi")
    )
    with pytest.raises(HTTPException, match="Explicit confirmation"):
        service.send_draft(draft["id"], False)


def test_google_token_refreshes_when_expired(tmp_path, monkeypatch) -> None:
    service = _service(tmp_path)
    service._store.save(
        {
            "google": {
                "access_token": "old",
                "refresh_token": "refresh",
                "expires_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
            }
        }
    )
    monkeypatch.setattr(
        service,
        "_post_token",
        lambda *_args, **_kwargs: {"access_token": "new", "expires_in": 3600},
    )
    assert service._token(ProductivityProvider.GOOGLE) == "new"
    assert service._store.load()["google"]["access_token"] == "new"


def test_calendar_conflict_blocks_creation(tmp_path, monkeypatch) -> None:
    service = _service(tmp_path)
    starts = datetime.now(UTC) + timedelta(days=1)
    payload = CalendarEventCreate(
        title="Interview", starts_at=starts, ends_at=starts + timedelta(hours=1)
    )
    monkeypatch.setattr(service, "calendar_events", lambda *_args: [{"id": "busy"}])
    with pytest.raises(HTTPException, match="conflict"):
        service.create_event(payload)


def test_productivity_plugins_load_with_declared_permissions(tmp_path) -> None:
    settings = AppSettings(
        plugin_directory=tmp_path / "plugins",
        plugin_catalog_file=tmp_path / "catalog.json",
        plugin_state_file=tmp_path / "state.json",
    )
    record = PluginService(settings).install("gmail")
    assert record.status == "loaded"
    assert set(record.permissions) == {"oauth", "network", "email"}
