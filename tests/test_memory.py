"""Memory persistence and semantic retrieval tests."""

import sqlite3
from pathlib import Path

from backend.app.domain.memory import MemoryCreate
from backend.app.memory.store import MemoryStore


def test_memory_survives_restart_and_indexes_typed_records(tmp_path: Path) -> None:
    """SQLite migrations and Chroma records persist across store instances."""
    database_path = tmp_path / "memory.db"
    chroma_path = tmp_path / "chroma"
    store = MemoryStore(database_path, chroma_path)
    memory_types = ["conversation", "preference", "note", "todo", "bookmark", "project", "workflow", "github_repository", "coding_preference", "folder_location"]
    for memory_type in memory_types:
        store.save(MemoryCreate(memory_type=memory_type, content=f"Local portfolio {memory_type}", metadata={"type": memory_type}))
    store.set_preference("theme", "dark")

    restarted_store = MemoryStore(database_path, chroma_path)
    assert len(restarted_store.list()) == len(memory_types)
    assert restarted_store.get_preference("theme") == "dark"
    assert restarted_store.search("portfolio project")

    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT version FROM schema_migrations").fetchone() == (1,)
