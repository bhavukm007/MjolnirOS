"""Coverage for communication confirmation, drafts, and secure-boundary behavior."""

from fastapi import HTTPException
import pytest

from backend.app.communication.communication_service import CommunicationService
from backend.app.core.settings import AppSettings
from backend.app.domain.communication import (
    CommunicationProvider,
    CredentialConnect,
    MessageDraftCreate,
)


class InMemoryStore:
    def __init__(self) -> None:
        self.value: dict[str, dict[str, object]] = {}

    def load(self) -> dict[str, dict[str, object]]:
        return self.value.copy()

    def save(self, value: dict[str, dict[str, object]]) -> None:
        self.value = value.copy()


def test_message_draft_requires_fresh_confirmation(tmp_path, monkeypatch) -> None:
    service = CommunicationService(
        AppSettings(
            communication_storage_directory=tmp_path / "communication",
            audit_storage_directory=tmp_path / "audit",
        )
    )
    service._store = InMemoryStore()  # type: ignore[assignment]
    service.connect(
        CommunicationProvider.SLACK,
        CredentialConnect(access_token="token", account_label="workspace"),
    )
    draft = service.create_draft(
        CommunicationProvider.SLACK,
        MessageDraftCreate(conversation_id="C123", content="Hello"),
    )
    with pytest.raises(HTTPException, match="Explicit confirmation"):
        service.send_draft(draft.id, False)
    monkeypatch.setattr(service, "_send", lambda **_kwargs: None)
    sent = service.send_draft(draft.id, True)
    assert sent.status == "sent"
    assert service.audit_events()[-1].action == "message_sent"


def test_connected_provider_can_read_and_search(tmp_path, monkeypatch) -> None:
    service = CommunicationService(
        AppSettings(
            communication_storage_directory=tmp_path / "communication",
            audit_storage_directory=tmp_path / "audit",
        )
    )
    service._store = InMemoryStore()  # type: ignore[assignment]
    service.connect(
        CommunicationProvider.DISCORD,
        CredentialConnect(access_token="token", account_label="account"),
    )
    monkeypatch.setattr(
        service,
        "_provider_request",
        lambda *_args, **_kwargs: {"channels": [{"id": "1"}]},
    )
    assert service.conversations(CommunicationProvider.DISCORD) == [{"id": "1"}]
    assert service.search(CommunicationProvider.DISCORD, "hello") == [{"id": "1"}]
