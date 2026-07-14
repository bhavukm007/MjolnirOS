"""SQLite source-of-truth with a local Chroma semantic index."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from uuid import uuid4

import chromadb
from chromadb.config import Settings as ChromaSettings

from backend.app.domain.memory import (
    MemoryCategory,
    MemoryCreate,
    MemoryRecord,
    MemoryType,
    UserProfile,
    category_for,
)


class MemoryStore:
    """Persist categorized memories locally with migrations and soft deletion."""

    def __init__(self, database_path: Path, chroma_path: Path) -> None:
        self._database_path = database_path
        self._chroma_path = chroma_path
        self._lock = RLock()
        self._logger = logging.getLogger(__name__)
        database_path.parent.mkdir(parents=True, exist_ok=True)
        chroma_path.mkdir(parents=True, exist_ok=True)
        self._migrate()
        self._collection = chromadb.PersistentClient(
            path=str(chroma_path),
            settings=ChromaSettings(anonymized_telemetry=False),
        ).get_or_create_collection(
            "assistant_memories_v2", metadata={"hnsw:space": "cosine"}
        )

    def save(self, memory: MemoryCreate) -> MemoryRecord:
        """Save or update a memory and keep its semantic representation consistent."""
        category = memory.category or category_for(memory.memory_type)
        now = datetime.now(UTC)
        with self._lock:
            existing = self._find_active_by_key(category, memory.key) if memory.key else None
            if existing is not None:
                record = MemoryRecord(
                    id=existing.id,
                    category=category,
                    active=True,
                    created_at=existing.created_at,
                    updated_at=now,
                    **memory.model_dump(exclude={"category"}),
                )
                with self._connect() as connection:
                    connection.execute(
                        """UPDATE memories SET type=?,content=?,metadata=?,updated_at=?,category=?,memory_key=?,importance=?,source=?,active=1 WHERE id=?""",
                        (
                            record.memory_type.value,
                            record.content,
                            json.dumps(record.metadata),
                            record.updated_at.isoformat(),
                            record.category.value,
                            _normalize_key(record.key) if record.key else None,
                            record.importance,
                            record.source,
                            record.id,
                        ),
                    )
            else:
                record = MemoryRecord(
                    id=str(uuid4()),
                    category=category,
                    active=True,
                    created_at=now,
                    updated_at=now,
                    **memory.model_dump(exclude={"category"}),
                )
                with self._connect() as connection:
                    connection.execute(
                        """INSERT INTO memories(id,type,content,metadata,created_at,updated_at,category,memory_key,importance,source,active) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                        self._values(record),
                    )
            self._collection.upsert(
                ids=[record.id],
                documents=[record.content],
                metadatas=[
                    {
                        "category": record.category.value,
                        "type": record.memory_type.value,
                        "importance": record.importance,
                        "active": True,
                    }
                ],
                embeddings=[_embed(record.content)],
            )
        self._logger.info(
            "memory_saved",
            extra={
                "memory_id": record.id,
                "memory_category": record.category.value,
                "memory_type": record.memory_type.value,
                "importance": record.importance,
                "key": record.key,
            },
        )
        return record

    def list(
        self,
        memory_type: MemoryType | str | None = None,
        *,
        category: MemoryCategory | str | None = None,
        active_only: bool = True,
        limit: int | None = None,
    ) -> list[MemoryRecord]:
        """Return stored memories with optional category, subtype and lifecycle filters."""
        clauses: list[str] = []
        arguments: list[object] = []
        if memory_type:
            clauses.append("type=?")
            arguments.append(MemoryType(memory_type).value)
        if category:
            clauses.append("category=?")
            arguments.append(MemoryCategory(category).value)
        if active_only:
            clauses.append("active=1")
        query = "SELECT * FROM memories"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY updated_at DESC"
        if limit is not None:
            query += " LIMIT ?"
            arguments.append(limit)
        with self._connect() as connection:
            rows = connection.execute(query, arguments).fetchall()
        return [_row(row) for row in rows]

    def search(
        self,
        query: str,
        limit: int = 8,
        *,
        categories: set[MemoryCategory] | None = None,
        minimum_importance: float = 0.0,
    ) -> list[MemoryRecord]:
        """Find semantically related active memories and retain relevance ordering."""
        count = self._collection.count()
        if count == 0:
            return []
        candidate_limit = min(count, max(limit * 4, limit))
        result = self._collection.query(
            query_embeddings=[_embed(query)],
            n_results=candidate_limit,
            include=["distances"],
        )
        ids = result.get("ids", [[]])[0]
        distances = result.get("distances", [[]])[0]
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM memories WHERE active=1 AND id IN ({placeholders})", ids
            ).fetchall()
        records = {row["id"]: _row(row) for row in rows}
        selected: list[MemoryRecord] = []
        for memory_id, distance in zip(ids, distances, strict=False):
            record = records.get(memory_id)
            if record is None or record.importance < minimum_importance:
                continue
            if categories and record.category not in categories:
                continue
            relevance = max(0.0, min(1.0, 1.0 - float(distance)))
            selected.append(record.model_copy(update={"relevance": relevance}))
            if len(selected) >= limit:
                break
        return selected

    def profile(self) -> UserProfile:
        """Materialize current keyed profile fields and unkeyed profile facts."""
        fields: dict[str, object] = {}
        facts: list[str] = []
        for record in reversed(self.list(category=MemoryCategory.USER_PROFILE)):
            if record.key:
                fields[record.key] = record.metadata.get("value", record.content)
            else:
                facts.append(record.content)
        return UserProfile(fields=fields, facts=facts)

    def get_by_key(
        self, key: str, category: MemoryCategory = MemoryCategory.USER_PROFILE
    ) -> MemoryRecord | None:
        """Return the current active value for a normalized category key."""
        return self._find_active_by_key(category, _normalize_key(key))

    def recent_conversation(self, limit: int = 12) -> list[MemoryRecord]:
        """Return recent turns oldest-first for coherent prompt history."""
        return list(reversed(self.list(MemoryType.CONVERSATION, limit=limit)))

    def active_tasks(self, limit: int = 20) -> list[MemoryRecord]:
        return self.list(category=MemoryCategory.TASK, limit=limit)

    def forget(self, query: str) -> list[MemoryRecord]:
        """Soft-delete exact keyed or semantically matching user-owned memories."""
        normalized = _normalize_key(query)
        matches = [
            record
            for record in self.list()
            if record.key == normalized
            or normalized in record.content.lower()
            or (record.key and normalized in record.key)
        ]
        if not matches:
            matches = self.search(query, limit=3, minimum_importance=0.5)
            matches = [item for item in matches if (item.relevance or 0) >= 0.35]
        if not matches:
            return []
        with self._lock, self._connect() as connection:
            connection.executemany(
                "UPDATE memories SET active=0,updated_at=? WHERE id=?",
                [(datetime.now(UTC).isoformat(), item.id) for item in matches],
            )
            self._collection.delete(ids=[item.id for item in matches])
        self._logger.info("memory_forgotten", extra={"count": len(matches), "query": query})
        return matches

    def prune_conversation(self, maximum_turns: int = 100) -> None:
        """Keep recent conversation useful without retaining an unbounded transcript."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id FROM memories WHERE active=1 AND type=? ORDER BY updated_at DESC LIMIT -1 OFFSET ?",
                (MemoryType.CONVERSATION.value, maximum_turns),
            ).fetchall()
            ids = [row["id"] for row in rows]
            if ids:
                connection.executemany(
                    "UPDATE memories SET active=0 WHERE id=?", [(item,) for item in ids]
                )
        if ids:
            self._collection.delete(ids=ids)

    def set_preference(self, key: str, value: object) -> None:
        """Preserve the existing application-preference key/value API."""
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO preferences(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at""",
                (key, json.dumps(value), now),
            )

    def get_preference(self, key: str) -> object | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT value FROM preferences WHERE key=?", (key,)
            ).fetchone()
        return json.loads(row["value"]) if row else None

    def _find_active_by_key(
        self, category: MemoryCategory, key: str | None
    ) -> MemoryRecord | None:
        if not key:
            return None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM memories WHERE category=? AND memory_key=? AND active=1 ORDER BY updated_at DESC LIMIT 1",
                (category.value, _normalize_key(key)),
            ).fetchone()
        return _row(row) if row else None

    @staticmethod
    def _values(record: MemoryRecord) -> tuple[object, ...]:
        return (
            record.id,
            record.memory_type.value,
            record.content,
            json.dumps(record.metadata),
            record.created_at.isoformat(),
            record.updated_at.isoformat(),
            record.category.value,
            _normalize_key(record.key) if record.key else None,
            record.importance,
            record.source,
            int(record.active),
        )

    def _migrate(self) -> None:
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS memories(id TEXT PRIMARY KEY,type TEXT NOT NULL,content TEXT NOT NULL,metadata TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS preferences(key TEXT PRIMARY KEY,value TEXT NOT NULL,updated_at TEXT NOT NULL)"""
            )
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(memories)")}
            additions = {
                "category": "TEXT NOT NULL DEFAULT 'semantic'",
                "memory_key": "TEXT",
                "importance": "REAL NOT NULL DEFAULT 0.5",
                "source": "TEXT NOT NULL DEFAULT 'legacy'",
                "active": "INTEGER NOT NULL DEFAULT 1",
            }
            for name, declaration in additions.items():
                if name not in columns:
                    connection.execute(f"ALTER TABLE memories ADD COLUMN {name} {declaration}")
            for memory_type in MemoryType:
                connection.execute(
                    "UPDATE memories SET category=? WHERE type=? AND (category='semantic' OR category IS NULL)",
                    (category_for(memory_type).value, memory_type.value),
                )
            connection.execute(
                "UPDATE memories SET category=? WHERE type=?",
                (MemoryCategory.CONVERSATION.value, MemoryType.CONVERSATION_SUMMARY.value),
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_category_active ON memories(category,active,updated_at)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_key_active ON memories(memory_key,active)"
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES(1,?)",
                (datetime.now(UTC).isoformat(),),
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES(2,?)",
                (datetime.now(UTC).isoformat(),),
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES(3,?)",
                (datetime.now(UTC).isoformat(),),
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection


def _row(row: sqlite3.Row) -> MemoryRecord:
    return MemoryRecord(
        id=row["id"],
        memory_type=row["type"],
        content=row["content"],
        category=row["category"] or category_for(row["type"]),
        key=row["memory_key"],
        metadata=json.loads(row["metadata"]),
        importance=float(row["importance"]),
        source=row["source"],
        active=bool(row["active"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _embed(text: str) -> list[float]:
    """Deterministic local token/character embedding without a cloud dependency."""
    normalized = re.sub(r"[^a-z0-9 ]+", " ", text.lower())
    tokens = normalized.split()
    features = tokens + [
        normalized[index : index + 3]
        for index in range(max(0, len(normalized) - 2))
        if " " not in normalized[index : index + 3]
    ]
    values = [0.0] * 384
    for feature in features:
        digest = hashlib.blake2b(feature.encode(), digest_size=4).digest()
        index = int.from_bytes(digest[:2], "big") % len(values)
        sign = 1.0 if digest[2] % 2 == 0 else -1.0
        values[index] += sign
    norm = sum(value * value for value in values) ** 0.5 or 1.0
    return [value / norm for value in values]
