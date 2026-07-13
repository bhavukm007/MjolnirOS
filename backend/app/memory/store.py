"""SQLite and Chroma-backed local memory repository."""
from __future__ import annotations
import hashlib, json, logging, sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
import chromadb
from backend.app.domain.memory import MemoryCreate, MemoryRecord

class MemoryStore:
    """Persist typed assistant memories locally with schema migrations."""
    def __init__(self, database_path: Path, chroma_path: Path) -> None:
        self._database_path, self._chroma_path = database_path, chroma_path
        database_path.parent.mkdir(parents=True, exist_ok=True); chroma_path.mkdir(parents=True, exist_ok=True)
        self._migrate()
        self._collection = chromadb.PersistentClient(path=str(chroma_path)).get_or_create_collection("memories", metadata={"hnsw:space": "cosine"})
        self._logger = logging.getLogger(__name__)
    def save(self, memory: MemoryCreate) -> MemoryRecord:
        """Atomically save a memory in SQLite and its local semantic index."""
        record = MemoryRecord(id=str(uuid4()), created_at=datetime.now(UTC), updated_at=datetime.now(UTC), **memory.model_dump())
        with self._connect() as connection:
            connection.execute("INSERT INTO memories(id,type,content,metadata,created_at,updated_at) VALUES(?,?,?,?,?,?)", (record.id, record.memory_type, record.content, json.dumps(record.metadata), record.created_at.isoformat(), record.updated_at.isoformat()))
        self._collection.add(ids=[record.id], documents=[record.content], metadatas=[{"type": record.memory_type}], embeddings=[_embed(record.content)])
        self._logger.info("memory_saved", extra={"memory_id": record.id, "memory_type": record.memory_type})
        return record
    def list(self, memory_type: str | None = None) -> list[MemoryRecord]:
        """Return stored memories, optionally limited to one type."""
        query, args = "SELECT * FROM memories", []
        if memory_type: query += " WHERE type=?"; args.append(memory_type)
        query += " ORDER BY created_at DESC"
        with self._connect() as c: rows = c.execute(query, args).fetchall()
        return [_row(row) for row in rows]
    def search(self, query: str, limit: int = 8) -> list[MemoryRecord]:
        """Find related memories through the persistent Chroma vector index."""
        result = self._collection.query(query_embeddings=[_embed(query)], n_results=limit, include=[])
        ids = result.get("ids", [[]])[0]
        if not ids: return []
        placeholders = ",".join("?" for _ in ids)
        with self._connect() as c: rows = c.execute(f"SELECT * FROM memories WHERE id IN ({placeholders})", ids).fetchall()
        records = {row["id"]: _row(row) for row in rows}
        return [records[item] for item in ids if item in records]
    def set_preference(self, key: str, value: object) -> None:
        """Upsert a user preference without losing existing data."""
        now = datetime.now(UTC).isoformat()
        with self._connect() as c: c.execute("INSERT INTO preferences(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at", (key, json.dumps(value), now))
    def get_preference(self, key: str) -> object | None:
        """Read a stored preference."""
        with self._connect() as c: row = c.execute("SELECT value FROM preferences WHERE key=?", (key,)).fetchone()
        return json.loads(row["value"]) if row else None
    def _migrate(self) -> None:
        with self._connect() as c:
            c.execute("CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
            if not c.execute("SELECT 1 FROM schema_migrations WHERE version=1").fetchone():
                c.execute("CREATE TABLE memories(id TEXT PRIMARY KEY,type TEXT NOT NULL,content TEXT NOT NULL,metadata TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)")
                c.execute("CREATE TABLE preferences(key TEXT PRIMARY KEY,value TEXT NOT NULL,updated_at TEXT NOT NULL)")
                c.execute("INSERT INTO schema_migrations VALUES(1,?)", (datetime.now(UTC).isoformat(),))
    def _connect(self) -> sqlite3.Connection:
        connection=sqlite3.connect(self._database_path); connection.row_factory=sqlite3.Row; return connection
def _row(row: sqlite3.Row) -> MemoryRecord:
    return MemoryRecord(id=row["id"], memory_type=row["type"], content=row["content"], metadata=json.loads(row["metadata"]), created_at=datetime.fromisoformat(row["created_at"]), updated_at=datetime.fromisoformat(row["updated_at"]))
def _embed(text: str) -> list[float]:
    values=[0.0]*256
    for token in text.lower().split(): values[int.from_bytes(hashlib.blake2b(token.encode(),digest_size=2).digest(),"big")%256]+=1.0
    norm=sum(value*value for value in values)**0.5 or 1.0
    return [value/norm for value in values]
