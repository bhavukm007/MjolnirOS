"""Schemas for categorized, persistent local assistant memory."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class MemoryCategory(StrEnum):
    USER_PROFILE = "user_profile"
    CONVERSATION = "conversation"
    LONG_TERM = "long_term"
    SEMANTIC = "semantic"
    TASK = "task"
    RESOURCE = "resource"


class MemoryType(StrEnum):
    PROFILE = "profile"
    CONVERSATION = "conversation"
    CONVERSATION_SUMMARY = "conversation_summary"
    FACT = "fact"
    PREFERENCE = "preference"
    NOTE = "note"
    TODO = "todo"
    GOAL = "goal"
    DEADLINE = "deadline"
    PROJECT = "project"
    BOOKMARK = "bookmark"
    WORKFLOW = "workflow"
    GITHUB_REPOSITORY = "github_repository"
    CODING_PREFERENCE = "coding_preference"
    FOLDER_LOCATION = "folder_location"
    INSTALLED_APPLICATION = "installed_application"


_CATEGORY_BY_TYPE = {
    MemoryType.PROFILE: MemoryCategory.USER_PROFILE,
    MemoryType.PREFERENCE: MemoryCategory.USER_PROFILE,
    MemoryType.CODING_PREFERENCE: MemoryCategory.USER_PROFILE,
    MemoryType.INSTALLED_APPLICATION: MemoryCategory.USER_PROFILE,
    MemoryType.CONVERSATION: MemoryCategory.CONVERSATION,
    MemoryType.CONVERSATION_SUMMARY: MemoryCategory.CONVERSATION,
    MemoryType.FACT: MemoryCategory.LONG_TERM,
    MemoryType.NOTE: MemoryCategory.LONG_TERM,
    MemoryType.TODO: MemoryCategory.TASK,
    MemoryType.GOAL: MemoryCategory.TASK,
    MemoryType.DEADLINE: MemoryCategory.TASK,
    MemoryType.PROJECT: MemoryCategory.TASK,
    MemoryType.BOOKMARK: MemoryCategory.RESOURCE,
    MemoryType.WORKFLOW: MemoryCategory.RESOURCE,
    MemoryType.GITHUB_REPOSITORY: MemoryCategory.RESOURCE,
    MemoryType.FOLDER_LOCATION: MemoryCategory.RESOURCE,
}


def category_for(memory_type: MemoryType | str) -> MemoryCategory:
    """Infer a durable category for callers using the legacy subtype API."""
    resolved = MemoryType(memory_type)
    return _CATEGORY_BY_TYPE.get(resolved, MemoryCategory.SEMANTIC)


class MemoryCreate(BaseModel):
    """A candidate memory that may be persisted after importance evaluation."""

    memory_type: MemoryType
    content: str = Field(min_length=1, max_length=12_000)
    category: MemoryCategory | None = None
    key: str | None = Field(default=None, max_length=300)
    metadata: dict[str, Any] = Field(default_factory=dict)
    importance: float = Field(default=0.5, ge=0, le=1)
    source: str = Field(default="assistant", max_length=100)


class MemoryRecord(MemoryCreate):
    """Persisted memory returned from the local store."""

    id: str
    category: MemoryCategory
    active: bool = True
    relevance: float | None = Field(default=None, ge=0, le=1)
    created_at: datetime
    updated_at: datetime


class PreferenceValue(BaseModel):
    """A persisted user preference."""

    value: Any


class MemorySearch(BaseModel):
    """Semantic search results."""

    results: list[MemoryRecord]


class UserProfile(BaseModel):
    """Materialized profile fields assembled from keyed profile memories."""

    fields: dict[str, Any] = Field(default_factory=dict)
    facts: list[str] = Field(default_factory=list)


class MemoryContext(BaseModel):
    """Context selected for one assistant request."""

    profile: UserProfile
    relevant_memories: list[MemoryRecord] = Field(default_factory=list)
    conversation_summaries: list[MemoryRecord] = Field(default_factory=list)
    recent_conversation: list[MemoryRecord] = Field(default_factory=list)
    active_tasks: list[MemoryRecord] = Field(default_factory=list)
