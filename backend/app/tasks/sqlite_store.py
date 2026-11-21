"""Durable, content-minimizing task history for the local agent runtime."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict

from backend.app.tasks.lifecycle import TaskStatus
from backend.app.permissions.engine import PermissionGrant
from backend.app.domain.capability import PermissionLevel


class PersistentTask(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: UUID
    device_id: UUID
    idempotency_key: str
    capability_id: str
    permission_scope: str
    input: dict[str, object]
    input_sha256: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    result: dict[str, object] | None = None
    error_code: str | None = None


class SQLiteTaskStore:
    """Add task tables to the existing SQLite database without altering old rows."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._lock = RLock()
        database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS agent_task_migrations "
                "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS agent_tasks (
                    task_id TEXT PRIMARY KEY,
                    device_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    capability_id TEXT NOT NULL,
                    permission_scope TEXT NOT NULL,
                    input_json TEXT NOT NULL,
                    input_sha256 TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    result_json TEXT,
                    error_code TEXT,
                    UNIQUE(device_id, idempotency_key)
                )"""
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_agent_tasks_updated "
                "ON agent_tasks(updated_at DESC)"
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS agent_task_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL REFERENCES agent_tasks(task_id),
                    status TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    error_code TEXT,
                    created_at TEXT NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS agent_permission_grants (
                    grant_id TEXT PRIMARY KEY,
                    device_id TEXT NOT NULL,
                    capability_id TEXT NOT NULL,
                    permission TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    revoked INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(device_id, capability_id, scope)
                )"""
            )
            connection.execute(
                "INSERT OR IGNORE INTO agent_task_migrations(version, applied_at) VALUES(1, ?)",
                (_now(),),
            )
            connection.execute(
                "INSERT OR IGNORE INTO agent_task_migrations(version, applied_at) VALUES(2, ?)",
                (_now(),),
            )

    def create(
        self,
        *,
        device_id: UUID,
        idempotency_key: str,
        capability_id: str,
        permission_scope: str,
        input_data: dict[str, object],
        status: TaskStatus,
        input_sha256: str | None = None,
    ) -> PersistentTask:
        encoded = _canonical(input_data)
        digest = input_sha256 or hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        now = _now()
        task_id = uuid4()
        with self._lock, self._connect() as connection:
            existing = connection.execute(
                "SELECT * FROM agent_tasks WHERE device_id=? AND idempotency_key=?",
                (str(device_id), idempotency_key),
            ).fetchone()
            if existing is not None:
                task = _task(existing)
                if (
                    task.capability_id != capability_id
                    or task.permission_scope != permission_scope
                    or task.input_sha256 != digest
                ):
                    raise ValueError("Idempotency key conflicts with another task action.")
                return task
            connection.execute(
                """INSERT INTO agent_tasks
                (task_id, device_id, idempotency_key, capability_id, permission_scope,
                 input_json, input_sha256, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(task_id), str(device_id), idempotency_key, capability_id,
                    permission_scope, encoded, digest, status.value, now, now,
                ),
            )
            connection.execute(
                "INSERT INTO agent_task_events(task_id, status, event_type, created_at) VALUES(?, ?, ?, ?)",
                (str(task_id), status.value, "created", now),
            )
        return self.get(task_id)

    def get(self, task_id: UUID) -> PersistentTask:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM agent_tasks WHERE task_id=?", (str(task_id),)
            ).fetchone()
        if row is None:
            raise KeyError("Task was not found.")
        return _task(row)

    def list(self, limit: int = 50) -> list[PersistentTask]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM agent_tasks ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 200)),),
            ).fetchall()
        return [_task(row) for row in rows]

    def update(
        self,
        task_id: UUID,
        *,
        status: TaskStatus,
        result: dict[str, object] | None = None,
        error_code: str | None = None,
    ) -> PersistentTask:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """UPDATE agent_tasks SET status=?, updated_at=?, result_json=?, error_code=?
                WHERE task_id=?""",
                (
                    status.value, _now(),
                    _canonical(result) if result is not None else None,
                    error_code, str(task_id),
                ),
            )
            if cursor.rowcount != 1:
                raise KeyError("Task was not found.")
            connection.execute(
                "INSERT INTO agent_task_events(task_id, status, event_type, error_code, created_at) VALUES(?, ?, ?, ?, ?)",
                (str(task_id), status.value, "status_changed", error_code, _now()),
            )
        return self.get(task_id)

    def recover_interrupted(self) -> int:
        """Mark all unfinished work interrupted; never replay it during startup."""
        with self._connect() as connection:
            recovered_rows = connection.execute(
                """UPDATE agent_tasks SET status=?, updated_at=?, error_code=?
                WHERE status IN (?, ?, ?) OR (status=? AND capability_id='windows.create_file')
                RETURNING task_id, status, error_code, updated_at""",
                (
                    TaskStatus.INTERRUPTED.value, _now(), "host_restarted",
                    TaskStatus.QUEUED.value, TaskStatus.RUNNING.value,
                    TaskStatus.CANCEL_REQUESTED.value, TaskStatus.WAITING_APPROVAL.value,
                ),
            )
            recovered = recovered_rows.fetchall()
            if recovered:
                connection.execute(
                    "INSERT INTO agent_task_events(task_id, status, event_type, error_code, created_at) "
                    "VALUES (?, ?, 'recovered_after_restart', ?, ?)",
                    (str(recovered[0]["task_id"]), TaskStatus.INTERRUPTED.value, "host_restarted", recovered[0]["updated_at"]),
                )
                connection.executemany(
                    "INSERT INTO agent_task_events(task_id, status, event_type, error_code, created_at) "
                    "VALUES (?, ?, 'recovered_after_restart', ?, ?)",
                    [
                        (str(row["task_id"]), TaskStatus.INTERRUPTED.value, "host_restarted", row["updated_at"])
                        for row in recovered[1:]
                    ],
                )
            return len(recovered)

    def events(self, task_id: UUID) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT status, event_type, error_code, created_at FROM agent_task_events "
                "WHERE task_id=? ORDER BY event_id",
                (str(task_id),),
            ).fetchall()
        return [dict(row) for row in rows]

    def record_event(
        self, task_id: UUID, event_type: str, *, error_code: str | None = None
    ) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO agent_task_events(task_id, status, event_type, error_code, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (str(task_id), self.get(task_id).status.value, event_type[:120], error_code, _now()),
            )

    def ensure_permission_grant(
        self,
        *,
        device_id: UUID,
        capability_id: str,
        permission: PermissionLevel,
        scope: str,
    ) -> PermissionGrant:
        now = _now()
        grant_id = uuid4()
        with self._connect() as connection:
            connection.execute(
                """INSERT OR IGNORE INTO agent_permission_grants
                (grant_id, device_id, capability_id, permission, scope, revoked, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 0, ?, ?)""",
                (str(grant_id), str(device_id), capability_id, permission.value, scope, now, now),
            )
            row = connection.execute(
                "SELECT * FROM agent_permission_grants WHERE device_id=? AND capability_id=? AND scope=?",
                (str(device_id), capability_id, scope),
            ).fetchone()
        return _permission_grant(row)

    def list_permission_grants(self, device_id: UUID) -> list[PermissionGrant]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM agent_permission_grants WHERE device_id=? ORDER BY capability_id",
                (str(device_id),),
            ).fetchall()
        return [_permission_grant(row) for row in rows]

    def revoke_permission_grant(self, grant_id: UUID) -> PermissionGrant:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE agent_permission_grants SET revoked=1, updated_at=? WHERE grant_id=?",
                (_now(), str(grant_id)),
            )
            if cursor.rowcount != 1:
                raise KeyError("Permission grant was not found.")
            row = connection.execute(
                "SELECT * FROM agent_permission_grants WHERE grant_id=?", (str(grant_id),)
            ).fetchone()
        return _permission_grant(row)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _task(row: sqlite3.Row) -> PersistentTask:
    return PersistentTask(
        task_id=UUID(row["task_id"]),
        device_id=UUID(row["device_id"]),
        idempotency_key=row["idempotency_key"],
        capability_id=row["capability_id"],
        permission_scope=row["permission_scope"],
        input=json.loads(row["input_json"]),
        input_sha256=row["input_sha256"],
        status=row["status"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        result=json.loads(row["result_json"]) if row["result_json"] else None,
        error_code=row["error_code"],
    )


def _permission_grant(row: sqlite3.Row) -> PermissionGrant:
    return PermissionGrant(
        grant_id=UUID(row["grant_id"]),
        device_id=UUID(row["device_id"]),
        capability_id=row["capability_id"],
        permission=row["permission"],
        scope=row["scope"],
        revoked=bool(row["revoked"]),
    )
