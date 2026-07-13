"""Validated models for communication providers and safe message delivery."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class CommunicationProvider(StrEnum):
    """Communication integrations available through isolated plugins."""

    DISCORD = "discord"
    SLACK = "slack"
    WHATSAPP = "whatsapp"
    TELEGRAM = "telegram"
    MICROSOFT_TEAMS = "microsoft-teams"


class CommunicationConnection(BaseModel):
    """Safe provider connection metadata that never includes credentials."""

    provider: CommunicationProvider
    connected: bool
    account_label: str | None = None
    last_sync_at: datetime | None = None
    error: str | None = None


class CredentialConnect(BaseModel):
    """A user-supplied access token stored only through Windows DPAPI."""

    access_token: str = Field(min_length=1, max_length=10_000)
    account_label: str = Field(min_length=1, max_length=200)
    endpoint_id: str | None = Field(default=None, max_length=300)


class MessageDraftCreate(BaseModel):
    """An unsent external message draft."""

    conversation_id: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=20_000)


class SendMessageConfirmation(BaseModel):
    """Fresh acknowledgement required for every external transmission."""

    confirmed: bool = False


class MessageDraft(BaseModel):
    """A durable, user-reviewable message draft."""

    id: str
    provider: CommunicationProvider
    conversation_id: str
    content: str
    status: str
    created_at: datetime


class AuditEvent(BaseModel):
    """Non-secret audit entry for an externally visible action."""

    timestamp: datetime
    action: str
    provider: str | None = None
    target: str | None = None
    outcome: str
    detail: str | None = None
