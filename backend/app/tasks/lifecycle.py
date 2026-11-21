"""Task state transitions that never automatically repeat interrupted work."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from threading import RLock
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from backend.app.permissions.engine import ExactActionApproval


class TaskStatus(StrEnum):
    QUEUED = "queued"
    WAITING_APPROVAL = "waiting_approval"
    RUNNING = "running"
    CANCEL_REQUESTED = "cancel_requested"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class InvalidTaskTransition(RuntimeError):
    pass


class IdempotencyConflict(ValueError):
    pass


class TaskRecord(BaseModel):
    """Content-minimizing task ledger item; raw prompts and arguments are omitted."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: UUID = Field(default_factory=uuid4)
    device_id: UUID
    idempotency_key: str = Field(
        min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$"
    )
    capability_id: str
    permission_scope: str
    action_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reversible: bool
    status: TaskStatus
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    failure_type: str | None = None


class TaskLedger:
    """In-memory lifecycle foundation; durable storage is a later adapter."""

    def __init__(self) -> None:
        self._tasks: dict[UUID, TaskRecord] = {}
        self._idempotency: dict[tuple[UUID, str], UUID] = {}
        self._consumed_approvals: set[UUID] = set()
        self._lock = RLock()

    def create(
        self,
        *,
        device_id: UUID,
        idempotency_key: str,
        capability_id: str,
        permission_scope: str,
        payload: dict[str, object],
        reversible: bool,
        requires_approval: bool,
    ) -> TaskRecord:
        digest = self._digest(
            capability_id,
            permission_scope,
            payload,
            reversible=reversible,
            requires_approval=requires_approval,
        )
        action_digest = self._payload_digest(payload)
        key = (device_id, idempotency_key)
        with self._lock:
            existing_id = self._idempotency.get(key)
            if existing_id:
                existing = self._tasks[existing_id]
                if (
                    existing.capability_id != capability_id
                    or existing.request_sha256 != digest
                ):
                    raise IdempotencyConflict(
                        "Idempotency key was already used for a different action."
                    )
                return existing

            now = datetime.now(UTC)
            task = TaskRecord(
                device_id=device_id,
                idempotency_key=idempotency_key,
                capability_id=capability_id,
                permission_scope=permission_scope,
                action_sha256=action_digest,
                request_sha256=digest,
                reversible=reversible,
                status=(
                    TaskStatus.WAITING_APPROVAL
                    if requires_approval
                    else TaskStatus.QUEUED
                ),
                created_at=now,
                updated_at=now,
            )
            self._tasks[task.task_id] = task
            self._idempotency[key] = task.task_id
            return task

    def get(self, task_id: UUID) -> TaskRecord:
        with self._lock:
            try:
                return self._tasks[task_id]
            except KeyError as error:
                raise KeyError("Task was not found.") from error

    def approve(self, task_id: UUID, approval: ExactActionApproval) -> TaskRecord:
        with self._lock:
            task = self.get(task_id)
            if task.status is not TaskStatus.WAITING_APPROVAL:
                raise InvalidTaskTransition("Task is not waiting for approval.")
            self._validate_approval(task, approval)
            self._consume_approval(approval)
            return self._store(task, status=TaskStatus.QUEUED)

    def start(self, task_id: UUID) -> TaskRecord:
        return self._transition(task_id, TaskStatus.RUNNING, TaskStatus.QUEUED)

    def complete(self, task_id: UUID) -> TaskRecord:
        return self._transition(task_id, TaskStatus.SUCCEEDED, TaskStatus.RUNNING)

    def fail(self, task_id: UUID, failure_type: str) -> TaskRecord:
        if not failure_type or len(failure_type) > 120:
            raise ValueError("A bounded failure type is required.")
        return self._transition(
            task_id, TaskStatus.FAILED, TaskStatus.RUNNING, failure_type=failure_type
        )

    def cancel(self, task_id: UUID) -> TaskRecord:
        with self._lock:
            current = self.get(task_id)
            if current.status in {TaskStatus.QUEUED, TaskStatus.WAITING_APPROVAL}:
                return self._store(current, status=TaskStatus.CANCELLED)
            if current.status is TaskStatus.RUNNING:
                return self._store(current, status=TaskStatus.CANCEL_REQUESTED)
            raise InvalidTaskTransition(
                "Task cannot be cancelled from its current state."
            )

    def acknowledge_cancel(self, task_id: UUID) -> TaskRecord:
        return self._transition(
            task_id, TaskStatus.CANCELLED, TaskStatus.CANCEL_REQUESTED
        )

    def recover_interrupted(self) -> tuple[TaskRecord, ...]:
        """Mark work interrupted for review; never requeue it during recovery."""
        with self._lock:
            recovered = []
            for task in tuple(self._tasks.values()):
                if task.status in {TaskStatus.RUNNING, TaskStatus.CANCEL_REQUESTED}:
                    recovered.append(self._store(task, status=TaskStatus.INTERRUPTED))
            return tuple(recovered)

    def retry_interrupted(
        self,
        task_id: UUID,
        *,
        approval: ExactActionApproval | None = None,
    ) -> TaskRecord:
        with self._lock:
            task = self.get(task_id)
            if task.status is not TaskStatus.INTERRUPTED:
                raise InvalidTaskTransition("Only interrupted tasks can be retried.")
            if not task.reversible:
                if approval is None:
                    raise InvalidTaskTransition(
                        "Interrupted irreversible work requires a new exact-action approval."
                    )
                self._validate_approval(task, approval)
                self._consume_approval(approval)
            return self._store(task, status=TaskStatus.QUEUED)

    def _validate_approval(
        self, task: TaskRecord, approval: ExactActionApproval
    ) -> None:
        if (
            approval.device_id != task.device_id
            or approval.capability_id != task.capability_id
            or approval.scope != task.permission_scope
            or approval.payload_sha256 != task.action_sha256
            or approval.expires_at <= datetime.now(UTC).timestamp()
            or approval.approval_id in self._consumed_approvals
        ):
            raise InvalidTaskTransition(
                "Approval does not authorize this exact task action."
            )

    def _consume_approval(self, approval: ExactActionApproval) -> None:
        self._consumed_approvals.add(approval.approval_id)

    def _transition(
        self,
        task_id: UUID,
        new_status: TaskStatus,
        required_status: TaskStatus,
        *,
        failure_type: str | None = None,
    ) -> TaskRecord:
        with self._lock:
            current = self.get(task_id)
            if current.status is not required_status:
                raise InvalidTaskTransition(
                    f"Task transition from {current.status.value} is not permitted."
                )
            return self._store(current, status=new_status, failure_type=failure_type)

    def _store(
        self,
        task: TaskRecord,
        *,
        status: TaskStatus,
        failure_type: str | None = None,
    ) -> TaskRecord:
        updated = task.model_copy(
            update={
                "status": status,
                "updated_at": datetime.now(UTC),
                "failure_type": failure_type,
            }
        )
        self._tasks[task.task_id] = updated
        return updated

    @staticmethod
    def _digest(
        capability_id: str,
        permission_scope: str,
        payload: dict[str, object],
        *,
        reversible: bool,
        requires_approval: bool,
    ) -> str:
        canonical = json.dumps(
            {
                "capability_id": capability_id,
                "permission_scope": permission_scope,
                "payload": payload,
                "reversible": reversible,
                "requires_approval": requires_approval,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    @staticmethod
    def _payload_digest(payload: dict[str, object]) -> str:
        canonical = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()
