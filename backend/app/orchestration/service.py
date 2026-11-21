"""Small orchestration seam; interpretation and durable scheduling remain separate."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Callable
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from backend.app.capabilities.registry import (
    CapabilityExecutionContext,
    CapabilityExecutionError,
    CapabilityRegistry,
    CapabilityRunResult,
)
from backend.app.permissions.engine import (
    ApprovalRequired,
    ExactActionApproval,
    PermissionDenied,
)


class PlanStep(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    step_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    capability_id: str = Field(min_length=2, max_length=128)
    input: dict[str, Any]


class ExecutionPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    plan_id: UUID = Field(default_factory=uuid4)
    device_id: UUID
    permission_scope: str = Field(min_length=1, max_length=128)
    steps: tuple[PlanStep, ...] = Field(min_length=1, max_length=50)


class ExecutionStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    WAITING_APPROVAL = "waiting_approval"
    CANCELLED = "cancelled"


class ExecutedStep(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    step_id: str
    result: CapabilityRunResult


class ExecutionReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    plan_id: UUID
    status: ExecutionStatus
    completed_steps: tuple[ExecutedStep, ...]
    failed_step_id: str | None = None
    error_code: str | None = None


class Orchestrator:
    """Execute a validated plan in order, stopping on the first unverified result."""

    def __init__(self, registry: CapabilityRegistry) -> None:
        self._registry = registry

    async def execute(
        self,
        plan: ExecutionPlan,
        *,
        device_id: UUID,
        scope: str,
        approvals: dict[str, ExactActionApproval] | None = None,
        on_step_completed: Callable[[ExecutedStep], None] | None = None,
        cancellation_requested: Callable[[], bool] | None = None,
    ) -> ExecutionReport:
        if plan.device_id != device_id or plan.permission_scope != scope:
            return ExecutionReport(
                plan_id=plan.plan_id,
                status=ExecutionStatus.FAILED,
                completed_steps=(),
                error_code="execution_context_mismatch",
            )
        completed: list[ExecutedStep] = []
        for step in plan.steps:
            if cancellation_requested is not None and cancellation_requested():
                return ExecutionReport(
                    plan_id=plan.plan_id,
                    status=ExecutionStatus.CANCELLED,
                    completed_steps=tuple(completed),
                    failed_step_id=step.step_id,
                    error_code="cancellation_requested",
                )
            try:
                result = await self._registry.execute(
                    step.capability_id,
                    step.input,
                    CapabilityExecutionContext(
                        device_id=device_id,
                        scope=scope,
                        approval=(approvals or {}).get(step.step_id),
                    ),
                )
            except ApprovalRequired:
                return ExecutionReport(
                    plan_id=plan.plan_id,
                    status=ExecutionStatus.WAITING_APPROVAL,
                    completed_steps=tuple(completed),
                    failed_step_id=step.step_id,
                    error_code="approval_required",
                )
            except PermissionDenied:
                return ExecutionReport(
                    plan_id=plan.plan_id,
                    status=ExecutionStatus.FAILED,
                    completed_steps=tuple(completed),
                    failed_step_id=step.step_id,
                    error_code="permission_denied",
                )
            except CapabilityExecutionError as error:
                return ExecutionReport(
                    plan_id=plan.plan_id,
                    status=ExecutionStatus.FAILED,
                    completed_steps=tuple(completed),
                    failed_step_id=step.step_id,
                    error_code=error.code,
                )
            executed = ExecutedStep(step_id=step.step_id, result=result)
            completed.append(executed)
            if on_step_completed is not None:
                on_step_completed(executed)
        return ExecutionReport(
            plan_id=plan.plan_id,
            status=ExecutionStatus.COMPLETED,
            completed_steps=tuple(completed),
        )
