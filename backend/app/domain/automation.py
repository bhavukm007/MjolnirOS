"""Public models for workflow automation and local task planning."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, computed_field, model_validator


class WorkflowSource(StrEnum):
    """Whether a workflow is provided by the application or the user."""

    BUILT_IN = "built_in"
    CUSTOM = "custom"


class StepAction(StrEnum):
    """Safe actions the Phase 11 engine can execute without OS controllers."""

    NOTIFY = "notify"
    WAIT = "wait"


class ExecutionStatus(StrEnum):
    """Lifecycle states used for workflow and individual-step progress."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class WorkflowStep(BaseModel):
    """One dependency-aware, safe workflow operation."""

    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9_-]+$")
    title: str = Field(min_length=1, max_length=160)
    action: StepAction
    priority: int = Field(default=3, ge=1, le=5)
    depends_on: list[str] = Field(default_factory=list)
    message: str | None = Field(default=None, max_length=500)
    duration_seconds: float | None = Field(default=None, ge=0, le=300)

    @model_validator(mode="after")
    def validate_action_configuration(self) -> WorkflowStep:
        """Require parameters that match the selected safe action."""
        if self.action is StepAction.NOTIFY and not self.message:
            raise ValueError("Notify steps require a message.")
        if self.action is StepAction.WAIT and self.duration_seconds is None:
            raise ValueError("Wait steps require duration_seconds.")
        return self


class WorkflowCreate(BaseModel):
    """User input for creating a reusable custom workflow."""

    name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=500)
    steps: list[WorkflowStep] = Field(min_length=1, max_length=30)


class Workflow(WorkflowCreate):
    """Persisted workflow definition."""

    id: str
    source: WorkflowSource
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ExecutionStep(BaseModel):
    """Current execution state for an individual workflow step."""

    step_id: str
    title: str
    status: ExecutionStatus = ExecutionStatus.PENDING
    message: str | None = None


class WorkflowExecution(BaseModel):
    """Persisted workflow run and progress information."""

    id: str
    workflow_id: str
    workflow_name: str
    status: ExecutionStatus
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    steps: list[ExecutionStep]

    @computed_field
    @property
    def progress_percent(self) -> int:
        """Return completed-step progress as a percentage."""
        if not self.steps:
            return 100
        completed = sum(step.status is ExecutionStatus.COMPLETED for step in self.steps)
        return round((completed / len(self.steps)) * 100)


class PlanRequest(BaseModel):
    """Natural-language goal submitted to the local planner."""

    goal: str = Field(min_length=3, max_length=1000)


class PlannedTask(BaseModel):
    """A prioritized task created from a goal or selected workflow."""

    id: str
    title: str
    priority: int
    depends_on: list[str] = Field(default_factory=list)


class TaskPlan(BaseModel):
    """Dependency-aware plan for a requested user goal."""

    goal: str
    workflow_id: str | None = None
    tasks: list[PlannedTask]
