"""Validated API models for productivity plugins."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ProductivityProvider(StrEnum):
    """OAuth providers supported by the Phase 14 integrations."""

    GOOGLE = "google"
    NOTION = "notion"


class ConnectionStatus(BaseModel):
    """Safe connection metadata; tokens are never represented here."""

    provider: ProductivityProvider
    connected: bool
    account_email: str | None = None
    expires_at: datetime | None = None
    last_sync_at: datetime | None = None
    error: str | None = None


class EmailDraftCreate(BaseModel):
    """A deliberately unsent email draft."""

    to: list[str] = Field(min_length=1)
    subject: str = Field(min_length=1, max_length=998)
    body: str = Field(min_length=1, max_length=100_000)
    reply_to_message_id: str | None = None


class SendConfirmation(BaseModel):
    """Explicit acknowledgement required to transmit a draft."""

    confirmed: bool = False


class CalendarEventCreate(BaseModel):
    """Calendar event input using ISO-8601 timestamps."""

    title: str = Field(min_length=1, max_length=250)
    starts_at: datetime
    ends_at: datetime
    timezone: str = Field(default="UTC", min_length=1, max_length=100)
    attendees: list[str] = Field(default_factory=list)
    reminder_minutes: list[int] = Field(default_factory=lambda: [10], max_length=5)
    description: str | None = Field(default=None, max_length=10_000)


class CalendarEventUpdate(BaseModel):
    """Partial event update."""

    title: str | None = Field(default=None, min_length=1, max_length=250)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=100)
    attendees: list[str] | None = None
    description: str | None = Field(default=None, max_length=10_000)


class NotionPageCreate(BaseModel):
    """Minimal page format supported by the Notion API."""

    parent_id: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(default="", max_length=100_000)


class NotionPageUpdate(BaseModel):
    """Editable Notion page fields."""

    title: str | None = Field(default=None, min_length=1, max_length=500)
    content: str | None = Field(default=None, max_length=100_000)


class MeetingNotesCreate(BaseModel):
    """A dated Notion page created for meeting notes."""

    parent_id: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=500)
    notes: str = Field(default="", max_length=100_000)


class DriveMoveRequest(BaseModel):
    """Destination folder for a Google Drive item."""

    folder_id: str = Field(min_length=1)


class DriveFolderCreate(BaseModel):
    """A new Drive folder."""

    name: str = Field(min_length=1, max_length=255)
    parent_id: str | None = None
