"""Schemas for persistent local memory."""
from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field

MemoryType = Literal["conversation", "preference", "note", "todo", "bookmark", "project", "workflow", "github_repository", "coding_preference", "folder_location"]

class MemoryCreate(BaseModel):
    """A local memory to persist immediately."""
    memory_type: MemoryType
    content: str = Field(min_length=1, max_length=12000)
    metadata: dict[str, Any] = Field(default_factory=dict)

class MemoryRecord(MemoryCreate):
    """Persisted memory returned from the local store."""
    id: str
    created_at: datetime
    updated_at: datetime

class PreferenceValue(BaseModel):
    """A persisted user preference."""
    value: Any

class MemorySearch(BaseModel):
    """Semantic search results."""
    results: list[MemoryRecord]
