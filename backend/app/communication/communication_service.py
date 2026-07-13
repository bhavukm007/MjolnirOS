"""Provider-neutral communication operations with explicit send confirmation."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import logging
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi import HTTPException

from backend.app.core.settings import AppSettings
from backend.app.domain.communication import (
    AuditEvent,
    CommunicationConnection,
    CommunicationProvider,
    CredentialConnect,
    MessageDraft,
    MessageDraftCreate,
)
from backend.app.productivity.productivity_service import TokenStore

logger = logging.getLogger(__name__)

_API_BASES = {
    CommunicationProvider.DISCORD: "https://discord.com/api/v10",
    CommunicationProvider.SLACK: "https://slack.com/api",
    CommunicationProvider.WHATSAPP: "https://graph.facebook.com/v20.0",
    CommunicationProvider.TELEGRAM: "https://api.telegram.org",
    CommunicationProvider.MICROSOFT_TEAMS: "https://graph.microsoft.com/v1.0",
}


class CommunicationService:
    """Keep provider HTTP, credentials, drafts, and audit trails at the API boundary."""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._store = TokenStore(settings.communication_storage_directory)
        self._drafts_path = (
            settings.communication_storage_directory / "message-drafts.json"
        )
        self._audit_path = settings.audit_storage_directory / "events.json"

    def connections(self) -> list[CommunicationConnection]:
        """Return connection state without returning tokens or provider identifiers."""
        credentials = self._store.load()
        return [
            CommunicationConnection(
                provider=provider,
                connected=provider.value in credentials,
                account_label=(
                    str(credentials[provider.value].get("account_label"))
                    if provider.value in credentials
                    else None
                ),
                last_sync_at=self._datetime(
                    credentials.get(provider.value, {}).get("last_sync_at")
                ),
            )
            for provider in CommunicationProvider
        ]

    def connect(
        self, provider: CommunicationProvider, payload: CredentialConnect
    ) -> CommunicationConnection:
        """Store a user-authorized provider token with Windows DPAPI protection."""
        credentials = self._store.load()
        credentials[provider.value] = payload.model_dump()
        self._store.save(credentials)
        self._audit("authentication_connected", provider, outcome="success")
        return self._connection(provider)

    def disconnect(self, provider: CommunicationProvider) -> None:
        """Forget a provider credential locally."""
        credentials = self._store.load()
        credentials.pop(provider.value, None)
        self._store.save(credentials)
        self._audit("authentication_disconnected", provider, outcome="success")

    def conversations(
        self, provider: CommunicationProvider, query: str | None = None
    ) -> list[dict[str, object]]:
        """Read provider conversations where its public API permits it."""
        payload = self._provider_request(
            provider, "GET", self._conversation_path(provider, query)
        )
        self._mark_synced(provider)
        return self._items(provider, payload)

    def search(
        self, provider: CommunicationProvider, query: str
    ) -> list[dict[str, object]]:
        """Search conversations or messages using a provider's supported endpoint."""
        if not query.strip():
            raise HTTPException(422, "Search query is required.")
        path = self._search_path(provider, query)
        payload = self._provider_request(provider, "GET", path)
        self._mark_synced(provider)
        return self._items(provider, payload)

    def create_draft(
        self, provider: CommunicationProvider, payload: MessageDraftCreate
    ) -> MessageDraft:
        """Persist an unsent message; creating a draft never contacts a provider."""
        draft = MessageDraft(
            id=uuid4().hex,
            provider=provider,
            conversation_id=payload.conversation_id,
            content=payload.content,
            status="draft",
            created_at=datetime.now(UTC),
        )
        drafts = self._drafts()
        drafts[draft.id] = draft.model_dump(mode="json")
        self._save_json(self._drafts_path, drafts)
        self._audit("message_drafted", provider, payload.conversation_id, "success")
        return draft

    def send_draft(self, draft_id: str, confirmed: bool) -> MessageDraft:
        """Transmit one draft only after a fresh explicit confirmation."""
        if not confirmed:
            raise HTTPException(
                403, "Explicit confirmation is required before sending a message."
            )
        drafts = self._drafts()
        raw = drafts.get(draft_id)
        if not raw:
            raise HTTPException(404, "Message draft was not found.")
        draft = MessageDraft.model_validate(raw)
        if draft.status != "draft":
            raise HTTPException(409, "Message draft has already been sent.")
        self._send(
            provider=draft.provider,
            conversation_id=draft.conversation_id,
            content=draft.content,
        )
        sent = draft.model_copy(update={"status": "sent"})
        drafts[draft_id] = sent.model_dump(mode="json")
        self._save_json(self._drafts_path, drafts)
        self._audit("message_sent", draft.provider, draft.conversation_id, "success")
        return sent

    def audit_events(self) -> list[AuditEvent]:
        """Return newest non-secret audit events for the security UI."""
        return [
            AuditEvent.model_validate(item)
            for item in self._load_json(self._audit_path).get("events", [])
        ][-100:]

    def _connection(self, provider: CommunicationProvider) -> CommunicationConnection:
        return next(item for item in self.connections() if item.provider is provider)

    def _provider_request(
        self, provider: CommunicationProvider, method: str, path: str, **kwargs: object
    ) -> dict[str, object]:
        credential = self._credential(provider)
        endpoint = _API_BASES[provider] + path
        headers = {"Authorization": f"Bearer {credential['access_token']}"}
        if provider is CommunicationProvider.TELEGRAM:
            endpoint = f"{_API_BASES[provider]}/bot{credential['access_token']}{path}"
            headers = {}
        try:
            response = httpx.request(
                method, endpoint, headers=headers, timeout=20, **kwargs
            )
        except httpx.HTTPError as error:
            self._audit(
                "provider_request", provider, outcome="failed", detail="network error"
            )
            raise HTTPException(
                502, "Communication provider is unavailable."
            ) from error
        if response.is_error:
            self._audit(
                "provider_request",
                provider,
                outcome="failed",
                detail=str(response.status_code),
            )
            raise HTTPException(
                response.status_code, "Communication provider request failed."
            )
        return response.json() if response.content else {}

    def _send(
        self, provider: CommunicationProvider, conversation_id: str, content: str
    ) -> None:
        credential = self._credential(provider)
        if provider is CommunicationProvider.TELEGRAM:
            endpoint = f"/bot{credential['access_token']}/sendMessage"
            response = httpx.post(
                _API_BASES[provider] + endpoint,
                json={"chat_id": conversation_id, "text": content},
                timeout=20,
            )
            if response.is_error:
                raise HTTPException(
                    response.status_code, "Telegram message delivery failed."
                )
            return
        path, body = self._send_request(provider, conversation_id, content, credential)
        self._provider_request(provider, "POST", path, json=body)

    @staticmethod
    def _send_request(
        provider: CommunicationProvider,
        conversation_id: str,
        content: str,
        credential: dict[str, object],
    ) -> tuple[str, dict[str, object]]:
        if provider is CommunicationProvider.SLACK:
            return "/chat.postMessage", {"channel": conversation_id, "text": content}
        if provider is CommunicationProvider.DISCORD:
            return f"/channels/{conversation_id}/messages", {"content": content}
        if provider is CommunicationProvider.WHATSAPP:
            endpoint_id = credential.get("endpoint_id")
            if not endpoint_id:
                raise HTTPException(
                    422, "WhatsApp requires the configured phone-number endpoint id."
                )
            return f"/{endpoint_id}/messages", {
                "messaging_product": "whatsapp",
                "to": conversation_id,
                "type": "text",
                "text": {"body": content},
            }
        return f"/chats/{conversation_id}/messages", {"body": {"content": content}}

    @staticmethod
    def _conversation_path(provider: CommunicationProvider, query: str | None) -> str:
        if provider is CommunicationProvider.SLACK:
            return "/conversations.list"
        if provider is CommunicationProvider.DISCORD:
            return "/users/@me/channels"
        if provider is CommunicationProvider.TELEGRAM:
            return "/getUpdates"
        if provider is CommunicationProvider.WHATSAPP:
            return "/me/conversations"
        return "/me/chats"

    @staticmethod
    def _search_path(provider: CommunicationProvider, query: str) -> str:
        from urllib.parse import quote

        encoded = quote(query)
        if provider is CommunicationProvider.SLACK:
            return f"/search.messages?query={encoded}"
        if provider is CommunicationProvider.MICROSOFT_TEAMS:
            return f"/me/chats?$search={encoded}"
        return CommunicationService._conversation_path(provider, query)

    @staticmethod
    def _items(
        provider: CommunicationProvider, payload: dict[str, object]
    ) -> list[dict[str, object]]:
        for key in ("channels", "messages", "chats", "data", "value", "result"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload] if payload else []

    def _credential(self, provider: CommunicationProvider) -> dict[str, object]:
        value = self._store.load().get(provider.value)
        if not value:
            raise HTTPException(401, "Connect this communication provider first.")
        return value

    def _mark_synced(self, provider: CommunicationProvider) -> None:
        credentials = self._store.load()
        credentials[provider.value]["last_sync_at"] = datetime.now(UTC).isoformat()
        self._store.save(credentials)

    def _audit(
        self,
        action: str,
        provider: CommunicationProvider | None = None,
        target: str | None = None,
        outcome: str = "success",
        detail: str | None = None,
    ) -> None:
        data = self._load_json(self._audit_path)
        events = data.setdefault("events", [])
        events.append(
            AuditEvent(
                timestamp=datetime.now(UTC),
                action=action,
                provider=provider.value if provider else None,
                target=target,
                outcome=outcome,
                detail=detail,
            ).model_dump(mode="json")
        )
        self._save_json(self._audit_path, data)
        logger.info(
            "communication_audit",
            extra={
                "action": action,
                "provider": provider.value if provider else None,
                "outcome": outcome,
            },
        )

    def _drafts(self) -> dict[str, object]:
        return self._load_json(self._drafts_path)

    @staticmethod
    def _datetime(value: object) -> datetime | None:
        return datetime.fromisoformat(str(value)) if value else None

    @staticmethod
    def _load_json(path: Path) -> dict[str, object]:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    @staticmethod
    def _save_json(path: Path, value: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
        temporary.replace(path)
