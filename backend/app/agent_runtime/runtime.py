"""Application-scoped production bridge for capabilities, policy, and tasks."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from uuid import NAMESPACE_URL, UUID, uuid5

from backend.app.capabilities.registry import CapabilityExecutionError, CapabilityRegistry
from backend.app.browser.super_agent import BrowserSuperAgent
from backend.app.coding.super_agent import CodingSuperAgent
from backend.app.core.settings import AppSettings
from backend.app.devices.registry import DeviceRegistry
from backend.app.domain.capability import DevicePlatform
from backend.app.domain.device import DeviceIdentity
from backend.app.orchestration.service import (
    ExecutionPlan,
    ExecutionStatus,
    Orchestrator,
    PlanStep,
)
from backend.app.permissions.engine import ExactActionApproval, PermissionEngine
from backend.app.tasks.lifecycle import TaskStatus
from backend.app.tasks.sqlite_store import PersistentTask, SQLiteTaskStore
from backend.app.windows.super_agent import WindowsSuperAgent


class AgentRuntime:
    """Shared runtime created per FastAPI application, never per request."""

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.store = SQLiteTaskStore(settings.database_path)
        stable_seed = str(settings.database_path.expanduser().resolve())
        self.device_id = uuid5(NAMESPACE_URL, f"mjolniros:windows:{stable_seed}")
        fingerprint = hashlib.sha256(self.device_id.bytes).hexdigest()
        self.devices = DeviceRegistry()
        self.devices.register(
            DeviceIdentity(
                device_id=self.device_id,
                display_name="This Windows device",
                platform=DevicePlatform.WINDOWS,
                public_key_fingerprint=fingerprint,
            )
        )
        self.permissions = PermissionEngine()
        self.registry = CapabilityRegistry(
            devices=self.devices, permissions=self.permissions
        )
        self.windows = WindowsSuperAgent(settings)
        self.windows.register(self.registry)
        self.browser = BrowserSuperAgent()
        self.browser.register(self.registry)
        self.coding = CodingSuperAgent(settings)
        self.coding.register(self.registry)
        for descriptor in self.registry.discover():
            grant = self.store.ensure_permission_grant(
                device_id=self.device_id,
                capability_id=descriptor.capability_id,
                permission=descriptor.required_permission,
                scope="windows.approved_root",
            )
            if not grant.revoked:
                self.permissions.grant(
                    device_id=self.device_id,
                    capability_id=descriptor.capability_id,
                    permission=grant.permission,
                    scope=grant.scope,
                    grant_id=grant.grant_id,
                )
        self.orchestrator = Orchestrator(self.registry)
        self._pending_inputs: dict[UUID, dict[str, object]] = {}
        self._background_tasks: dict[UUID, asyncio.Task[object]] = {}
        self.store.recover_interrupted()

    def capabilities(self) -> tuple[dict[str, object], ...]:
        return tuple(
            descriptor.model_dump(mode="json")
            for descriptor in self.registry.discover(device_platform=DevicePlatform.WINDOWS)
        )

    def create_task(
        self,
        capability_id: str,
        input_data: dict[str, object],
        idempotency_key: str,
    ) -> PersistentTask:
        descriptor = next(
            (item for item in self.registry.discover() if item.capability_id == capability_id),
            None,
        )
        if descriptor is None:
            raise KeyError("capability_not_registered")
        if descriptor.requires_confirmation:
            initial = TaskStatus.WAITING_APPROVAL
        else:
            initial = TaskStatus.QUEUED
        persisted_input = dict(input_data)
        original_digest = hashlib.sha256(
            json.dumps(input_data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        ).hexdigest()
        if capability_id == "windows.create_file":
            persisted_input.pop("content", None)
        task = self.store.create(
            device_id=self.device_id,
            idempotency_key=idempotency_key,
            capability_id=capability_id,
            permission_scope="windows.approved_root",
            input_data=persisted_input,
            status=initial,
            input_sha256=original_digest,
        )
        if task.status is TaskStatus.WAITING_APPROVAL:
            self._pending_inputs[task.task_id] = dict(input_data)
        return task

    def create_plan_task(
        self, steps: list[dict[str, object]], idempotency_key: str
    ) -> PersistentTask:
        """Persist a sequential plan only when every step is non-sensitive."""
        if not 2 <= len(steps) <= 20:
            raise ValueError("A sequential plan must contain between 2 and 20 steps.")
        validated_steps: list[PlanStep] = []
        for index, raw in enumerate(steps):
            step = PlanStep.model_validate(
                {
                    "step_id": raw.get("step_id", f"step_{index + 1}"),
                    "capability_id": raw.get("capability_id"),
                    "input": raw.get("input", {}),
                }
            )
            definition = next(
                (item for item in self.registry.discover() if item.capability_id == step.capability_id),
                None,
            )
            if definition is None:
                raise KeyError("capability_not_registered")
            if definition.requires_confirmation:
                raise ValueError("Approval-gated actions must be submitted as individual tasks.")
            # Validate inputs before persisting the plan; permission is still checked at execution.
            try:
                self.registry.validate_input(step.capability_id, step.input)
            except CapabilityExecutionError as error:
                raise ValueError("A sequential plan step has invalid input.") from error
            validated_steps.append(step)
        payload = {"steps": [step.model_dump(mode="json") for step in validated_steps]}
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        ).hexdigest()
        return self.store.create(
            device_id=self.device_id,
            idempotency_key=idempotency_key,
            capability_id="orchestrator.sequential_plan",
            permission_scope="windows.approved_root",
            input_data=payload,
            status=TaskStatus.QUEUED,
            input_sha256=digest,
        )

    async def execute_task(
        self, task_id: UUID, approval: ExactActionApproval | None = None
    ) -> PersistentTask:
        task = self.store.get(task_id)
        if task.status is TaskStatus.WAITING_APPROVAL and approval is None:
            return task
        if task.status not in {TaskStatus.QUEUED, TaskStatus.WAITING_APPROVAL}:
            return task
        self.store.update(task_id, status=TaskStatus.RUNNING)
        execution_input = self._pending_inputs.get(task_id, task.input)
        if task.capability_id == "orchestrator.sequential_plan":
            steps = tuple(PlanStep.model_validate(item) for item in task.input.get("steps", []))
        else:
            steps = (PlanStep(step_id="action", capability_id=task.capability_id, input=execution_input),)
        plan = ExecutionPlan(
            device_id=self.device_id,
            permission_scope=task.permission_scope,
            steps=steps,
        )
        try:
            report = await self.orchestrator.execute(
                plan,
                device_id=self.device_id,
                scope=task.permission_scope,
                approvals={"action": approval} if approval else None,
                on_step_completed=lambda _step: self.store.record_event(task_id, "step_completed"),
                cancellation_requested=lambda: self.store.get(task_id).status is TaskStatus.CANCEL_REQUESTED,
            )
        except Exception:
            self.store.update(
                task_id, status=TaskStatus.FAILED, error_code="execution_failed"
            )
            raise
        if report.status is ExecutionStatus.WAITING_APPROVAL:
            return self.store.update(
                task_id, status=TaskStatus.WAITING_APPROVAL, error_code="approval_required"
            )
        if report.status is ExecutionStatus.FAILED:
            return self.store.update(
                task_id,
                status=TaskStatus.FAILED,
                error_code=report.error_code or "execution_failed",
            )
        if report.status is ExecutionStatus.CANCELLED:
            partial = {"completed_steps": len(report.completed_steps)}
            return self.store.update(
                task_id,
                status=TaskStatus.CANCELLED,
                result=partial,
                error_code="cancelled_before_next_step",
            )
        if task.capability_id == "orchestrator.sequential_plan":
            result = {
                "steps": [
                    {
                        "capability_id": step.result.capability_id,
                        "result": _redact_persisted_result(step.result.capability_id, step.result.output),
                    }
                    for step in report.completed_steps
                ]
            }
            safe_result = result
        else:
            result = report.completed_steps[-1].result.output if report.completed_steps else {}
            safe_result = _redact_persisted_result(task.capability_id, result)
        completed = self.store.update(task_id, status=TaskStatus.SUCCEEDED, result=safe_result)
        self._pending_inputs.pop(task_id, None)
        return completed.model_copy(update={"result": result})

    def start_background(self, task_id: UUID) -> None:
        """Start one persisted task once; duplicate starts cannot run concurrently."""
        current = self._background_tasks.get(task_id)
        if current is not None and not current.done():
            return
        worker = asyncio.create_task(self.execute_task(task_id))
        self._background_tasks[task_id] = worker
        worker.add_done_callback(lambda done: self._background_finished(task_id, done))

    def _background_finished(
        self, task_id: UUID, worker: asyncio.Task[object]
    ) -> None:
        self._background_tasks.pop(task_id, None)
        if worker.cancelled():
            return
        error = worker.exception()
        if error is not None:
            logging.getLogger(__name__).error(
                "agent_background_task_raised",
                extra={"task_id": str(task_id), "error_type": type(error).__name__},
            )

    def approve(self, task_id: UUID) -> ExactActionApproval:
        task = self.store.get(task_id)
        if task.status is not TaskStatus.WAITING_APPROVAL:
            raise ValueError("Task is not waiting for approval.")
        input_data = self._pending_inputs.get(task_id)
        if input_data is None:
            input_data = task.input
        if task.capability_id == "windows.create_file" and "content" not in input_data:
            raise ValueError("Private file content is unavailable after restart; submit the action again.")
        return self.permissions.issue_exact_approval(
            device_id=task.device_id,
            capability_id=task.capability_id,
            scope=task.permission_scope,
            payload=input_data,
            lifetime_seconds=120,
        )

    def approval_details(self, task_id: UUID) -> dict[str, object]:
        task = self.store.get(task_id)
        payload = self._pending_inputs.get(task_id, task.input)
        details = {
            key: payload[key]
            for key in ("path", "source", "destination", "name", "pid")
            if key in payload
        }
        content = payload.get("content")
        if isinstance(content, str):
            details["content_bytes"] = len(content.encode("utf-8"))
            details["content_preview"] = content[:240]
            details["content_truncated"] = len(content) > 240
        return details

    def revoke_permission(self, grant_id: UUID):
        grant = self.store.revoke_permission_grant(grant_id)
        if not grant.revoked:
            raise RuntimeError("Permission revocation did not persist.")
        try:
            self.permissions.revoke(grant_id)
        except KeyError:
            # An already-revoked durable grant is intentionally absent from memory.
            pass
        return grant

    def cancel(self, task_id: UUID) -> PersistentTask:
        task = self.store.get(task_id)
        if task.status is TaskStatus.WAITING_APPROVAL or task.status is TaskStatus.QUEUED:
            return self.store.update(task_id, status=TaskStatus.CANCELLED)
        if task.status is TaskStatus.RUNNING:
            return self.store.update(
                task_id,
                status=TaskStatus.CANCEL_REQUESTED,
                error_code="cancellation_requested; active operation will finish safely",
            )
        if task.status is TaskStatus.CANCEL_REQUESTED:
            return task
        return task

    async def shutdown(self) -> None:
        workers = tuple(self._background_tasks.values())
        for worker in workers:
            worker.cancel()
        if workers:
            await asyncio.gather(*workers, return_exceptions=True)


def _redact_persisted_result(
    capability_id: str, result: dict[str, object]
) -> dict[str, object]:
    data = result.get("result")
    if not isinstance(data, dict):
        return {}
    if capability_id == "windows.read_file":
        return {"result": {"path": data.get("path"), "bytes": data.get("bytes")}}
    if capability_id == "windows.search_files":
        return {"result": {"match_count": len(data.get("matches", [])), "truncated": data.get("truncated", False)}}
    if capability_id == "windows.list_directory":
        return {"result": {"entry_count": len(data.get("entries", [])), "truncated": data.get("truncated", False)}}
    return result

