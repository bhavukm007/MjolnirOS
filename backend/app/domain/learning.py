"""Public models for privacy-preserving habit learning."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ObservationKind(StrEnum):
    """Non-sensitive activity categories accepted by the learning system."""

    APPLICATION = "application"
    FOLDER = "folder"
    BROWSER = "browser"
    CODING_STYLE = "coding_style"
    COMMAND = "command"
    REPOSITORY = "repository"
    STARTUP = "startup"


class LearningObservationCreate(BaseModel):
    """One user-approved local activity signal from an existing agent or UI."""

    kind: ObservationKind
    value: str = Field(min_length=1, max_length=300)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class LearningObservation(LearningObservationCreate):
    """Persisted activity signal used to derive preferences and suggestions."""

    id: str


class LearningPreference(BaseModel):
    """A preference inferred from repeated local observations."""

    key: str
    value: str
    occurrences: int
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SuggestionStatus(StrEnum):
    """Explicit approval lifecycle for a proposed automation."""

    PENDING = "pending"
    APPROVED = "approved"
    DISMISSED = "dismissed"


class LearningSuggestion(BaseModel):
    """A pending automation recommendation derived from recurring habits."""

    id: str
    signature: str
    title: str
    description: str
    items: list[str]
    occurrences: int
    status: SuggestionStatus = SuggestionStatus.PENDING
    workflow_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class LearningOverview(BaseModel):
    """Dashboard-friendly snapshot of learned local habits."""

    observation_count: int
    preferences: list[LearningPreference]
    suggestions: list[LearningSuggestion]
