"""Persistent local-memory API routes."""

from functools import lru_cache

from fastapi import APIRouter, HTTPException

from backend.app.core.responses import ApiResponse
from backend.app.core.settings import get_settings
from backend.app.domain.memory import MemoryCategory, MemoryCreate, MemoryRecord, MemorySearch, PreferenceValue, UserProfile
from backend.app.memory.store import MemoryStore

router = APIRouter(prefix="/memory", tags=["memory"])


@lru_cache
def get_memory_store() -> MemoryStore:
    """Return the process-wide SQLite and Chroma memory service."""
    settings = get_settings()
    return MemoryStore(settings.database_path, settings.chroma_path)


@router.post("", response_model=ApiResponse[MemoryRecord])
async def create_memory(memory: MemoryCreate) -> ApiResponse[MemoryRecord]:
    """Persist a typed memory immediately."""
    return ApiResponse(success=True, message="Memory saved.", data=get_memory_store().save(memory))


@router.get("", response_model=ApiResponse[list[MemoryRecord]])
async def list_memories(memory_type: str | None = None, category: MemoryCategory | None = None) -> ApiResponse[list[MemoryRecord]]:
    """List locally persisted memories."""
    return ApiResponse(success=True, message="Memories loaded.", data=get_memory_store().list(memory_type, category=category))


@router.get("/profile", response_model=ApiResponse[UserProfile])
async def get_profile() -> ApiResponse[UserProfile]:
    """Return the current materialized local user profile."""
    return ApiResponse(success=True, message="Profile loaded.", data=get_memory_store().profile())


@router.delete("", response_model=ApiResponse[list[MemoryRecord]])
async def forget_memory(query: str) -> ApiResponse[list[MemoryRecord]]:
    """Soft-delete matching memories without erasing audit metadata."""
    forgotten = get_memory_store().forget(query)
    return ApiResponse(success=bool(forgotten), message="Memory forgotten." if forgotten else "No matching memory found.", data=forgotten)


@router.get("/search", response_model=ApiResponse[MemorySearch])
async def search_memories(query: str) -> ApiResponse[MemorySearch]:
    """Retrieve related memories using the local Chroma index."""
    return ApiResponse(success=True, message="Semantic memories loaded.", data=MemorySearch(results=get_memory_store().search(query)))


@router.put("/preferences/{key}", response_model=ApiResponse[PreferenceValue])
async def set_preference(key: str, preference: PreferenceValue) -> ApiResponse[PreferenceValue]:
    """Persist a named user preference."""
    get_memory_store().set_preference(key, preference.value)
    return ApiResponse(success=True, message="Preference saved.", data=preference)


@router.get("/preferences/{key}", response_model=ApiResponse[PreferenceValue])
async def get_preference(key: str) -> ApiResponse[PreferenceValue]:
    """Load a named user preference."""
    value = get_memory_store().get_preference(key)
    if value is None:
        raise HTTPException(status_code=404, detail="Preference was not found.")
    return ApiResponse(success=True, message="Preference loaded.", data=PreferenceValue(value=value))
