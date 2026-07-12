"""Persistent, cancellable execution of safe local workflows."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import json
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException

from backend.app.core.settings import AppSettings
from backend.app.domain.automation import (
    ExecutionStatus,
    ExecutionStep,
    StepAction,
    Workflow,
    WorkflowCreate,
    WorkflowExecution,
    WorkflowSource,
    WorkflowStep,
)


class AutomationService:
    """Persist workflows locally and run their safe actions with visible progress."""

    def __init__(self, settings: AppSettings) -> None:
        self._directory = settings.automation_storage_directory
        self._workflows_path = self._directory / "workflows.json"
        self._executions_path = self._directory / "executions.json"

    def list_workflows(self) -> list[Workflow]:
        """Return built-in and user-authored workflows, sorted by name."""
        workflows = self._workflows()
        return sorted(
            workflows.values(), key=lambda workflow: (workflow.source, workflow.name)
        )

    def get_workflow(self, workflow_id: str) -> Workflow:
        """Load a workflow or raise a stable not-found response."""
        try:
            return self._workflows()[workflow_id]
        except KeyError as error:
            raise HTTPException(
                status_code=404, detail="Workflow was not found."
            ) from error

    def create_workflow(self, payload: WorkflowCreate) -> Workflow:
        """Validate and persist a custom workflow definition."""
        self._validate_steps(payload.steps)
        workflow = Workflow(
            id=uuid4().hex,
            source=WorkflowSource.CUSTOM,
            name=payload.name,
            description=payload.description,
            steps=payload.steps,
        )
        workflows = self._workflows()
        workflows[workflow.id] = workflow
        self._write_workflows(workflows)
        return workflow

    def update_workflow(self, workflow_id: str, payload: WorkflowCreate) -> Workflow:
        """Update a custom workflow while preserving its identity and origin."""
        existing = self.get_workflow(workflow_id)
        if existing.source is WorkflowSource.BUILT_IN:
            raise HTTPException(
                status_code=403, detail="Built-in workflows cannot be edited."
            )
        self._validate_steps(payload.steps)
        workflow = Workflow(
            id=existing.id,
            source=existing.source,
            created_at=existing.created_at,
            updated_at=datetime.now(UTC),
            name=payload.name,
            description=payload.description,
            steps=payload.steps,
        )
        workflows = self._workflows()
        workflows[workflow.id] = workflow
        self._write_workflows(workflows)
        return workflow

    def delete_workflow(self, workflow_id: str) -> None:
        """Delete a user-authored workflow without affecting historical runs."""
        workflow = self.get_workflow(workflow_id)
        if workflow.source is WorkflowSource.BUILT_IN:
            raise HTTPException(
                status_code=403, detail="Built-in workflows cannot be deleted."
            )
        workflows = self._workflows()
        del workflows[workflow_id]
        self._write_workflows(workflows)

    def begin_execution(self, workflow_id: str) -> WorkflowExecution:
        """Create a running execution that can be processed or cancelled."""
        workflow = self.get_workflow(workflow_id)
        execution = WorkflowExecution(
            id=uuid4().hex,
            workflow_id=workflow.id,
            workflow_name=workflow.name,
            status=ExecutionStatus.RUNNING,
            steps=[
                ExecutionStep(step_id=step.id, title=step.title)
                for step in workflow.steps
            ],
        )
        executions = self._executions()
        executions[execution.id] = execution
        self._write_executions(executions)
        return execution

    async def run_execution(self, execution_id: str) -> WorkflowExecution:
        """Run ready steps in priority order and persist each progress transition."""
        execution = self.get_execution(execution_id)
        workflow = self.get_workflow(execution.workflow_id)
        steps_by_id = {step.id: step for step in workflow.steps}
        while execution.status is ExecutionStatus.RUNNING:
            ready = self._ready_steps(workflow.steps, execution.steps)
            if not ready:
                if all(
                    step.status is ExecutionStatus.COMPLETED for step in execution.steps
                ):
                    execution.status = ExecutionStatus.COMPLETED
                    execution.completed_at = datetime.now(UTC)
                    self._save_execution(execution)
                    break
                execution.status = ExecutionStatus.FAILED
                execution.completed_at = datetime.now(UTC)
                self._save_execution(execution)
                break
            for execution_step in ready:
                execution = self.get_execution(execution_id)
                if execution.status is ExecutionStatus.CANCELLED:
                    return self._view(execution)
                step = steps_by_id[execution_step.step_id]
                self._set_step_status(execution, step.id, ExecutionStatus.RUNNING)
                await self._execute_step(step, execution_id)
                execution = self.get_execution(execution_id)
                if execution.status is ExecutionStatus.CANCELLED:
                    return self._view(execution)
                self._set_step_status(
                    execution, step.id, ExecutionStatus.COMPLETED, step.message
                )
        return self._view(self.get_execution(execution_id))

    def get_execution(self, execution_id: str) -> WorkflowExecution:
        """Load a workflow execution or raise a stable not-found response."""
        try:
            return self._executions()[execution_id]
        except KeyError as error:
            raise HTTPException(
                status_code=404, detail="Workflow execution was not found."
            ) from error

    def view_execution(self, execution_id: str) -> WorkflowExecution:
        """Return one execution with the computed progress percentage."""
        return self._view(self.get_execution(execution_id))

    def list_executions(self) -> list[WorkflowExecution]:
        """Return latest workflow runs with their progress values."""
        return [
            self._view(item)
            for item in sorted(
                self._executions().values(),
                key=lambda run: run.started_at,
                reverse=True,
            )
        ]

    def cancel_execution(self, execution_id: str) -> WorkflowExecution:
        """Cancel a running workflow; completed runs are intentionally immutable."""
        execution = self.get_execution(execution_id)
        if execution.status is ExecutionStatus.RUNNING:
            execution.status = ExecutionStatus.CANCELLED
            execution.completed_at = datetime.now(UTC)
            self._save_execution(execution)
        return self._view(execution)

    async def _execute_step(self, step: WorkflowStep, execution_id: str) -> None:
        if step.action is StepAction.WAIT:
            remaining = step.duration_seconds or 0
            while remaining > 0:
                await asyncio.sleep(min(remaining, 0.1))
                if self.get_execution(execution_id).status is ExecutionStatus.CANCELLED:
                    return
                remaining -= 0.1

    @staticmethod
    def _ready_steps(
        steps: list[WorkflowStep], execution_steps: list[ExecutionStep]
    ) -> list[ExecutionStep]:
        statuses = {step.step_id: step.status for step in execution_steps}
        ready = [
            execution_step
            for step, execution_step in zip(steps, execution_steps, strict=True)
            if execution_step.status is ExecutionStatus.PENDING
            and all(
                statuses[dependency] is ExecutionStatus.COMPLETED
                for dependency in step.depends_on
            )
        ]
        return sorted(
            ready,
            key=lambda item: next(
                step.priority for step in steps if step.id == item.step_id
            ),
            reverse=True,
        )

    def _set_step_status(
        self,
        execution: WorkflowExecution,
        step_id: str,
        status: ExecutionStatus,
        message: str | None = None,
    ) -> None:
        for step in execution.steps:
            if step.step_id == step_id:
                step.status = status
                step.message = message
                break
        self._save_execution(execution)

    @staticmethod
    def _validate_steps(steps: list[WorkflowStep]) -> None:
        identifiers = [step.id for step in steps]
        if len(identifiers) != len(set(identifiers)):
            raise HTTPException(
                status_code=422, detail="Workflow step IDs must be unique."
            )
        known = set(identifiers)
        if any(
            dependency not in known for step in steps for dependency in step.depends_on
        ):
            raise HTTPException(
                status_code=422, detail="A step depends on an unknown step."
            )
        if any(step.id in step.depends_on for step in steps):
            raise HTTPException(
                status_code=422, detail="A step cannot depend on itself."
            )
        dependencies = {step.id: set(step.depends_on) for step in steps}
        resolved: set[str] = set()
        while dependencies:
            ready = {
                step_id
                for step_id, required in dependencies.items()
                if required <= resolved
            }
            if not ready:
                raise HTTPException(
                    status_code=422,
                    detail="Workflow steps cannot contain a dependency cycle.",
                )
            resolved.update(ready)
            dependencies = {
                step_id: required
                for step_id, required in dependencies.items()
                if step_id not in ready
            }

    def _workflows(self) -> dict[str, Workflow]:
        self._directory.mkdir(parents=True, exist_ok=True)
        records = self._read_records(self._workflows_path)
        workflows = {
            record["id"]: Workflow.model_validate(record) for record in records
        }
        for workflow in _built_in_workflows():
            workflows.setdefault(workflow.id, workflow)
        return workflows

    def _executions(self) -> dict[str, WorkflowExecution]:
        records = self._read_records(self._executions_path)
        return {
            record["id"]: WorkflowExecution.model_validate(record) for record in records
        }

    @staticmethod
    def _read_records(path: Path) -> list[dict[str, object]]:
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_workflows(self, workflows: dict[str, Workflow]) -> None:
        self._write_records(self._workflows_path, workflows.values())

    def _write_executions(self, executions: dict[str, WorkflowExecution]) -> None:
        self._write_records(self._executions_path, executions.values())

    def _save_execution(self, execution: WorkflowExecution) -> None:
        executions = self._executions()
        executions[execution.id] = execution
        self._write_executions(executions)

    @staticmethod
    def _write_records(path: Path, records: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps([item.model_dump(mode="json") for item in records], indent=2),
            encoding="utf-8",  # type: ignore[union-attr]
        )

    @staticmethod
    def _view(execution: WorkflowExecution) -> WorkflowExecution:
        return execution


def _built_in_workflows() -> list[Workflow]:
    """Return the Phase 11 built-ins without performing unavailable OS actions."""
    definitions = [
        ("morning_routine", "Morning Routine", "Set up a focused start to the day."),
        ("coding_mode", "Coding Mode", "Prepare a focused local coding session."),
        ("study_mode", "Study Mode", "Start a structured study session."),
        (
            "placement_preparation",
            "Placement Preparation",
            "Organize a placement-preparation session.",
        ),
        ("interview_mode", "Interview Mode", "Prepare for an interview session."),
        (
            "presentation_mode",
            "Presentation Mode",
            "Prepare for a presentation session.",
        ),
        ("gaming_mode", "Gaming Mode", "Prepare a distraction-free gaming session."),
        (
            "shutdown_routine",
            "Shutdown Routine",
            "Guide a safe end-of-session routine.",
        ),
    ]
    return [
        Workflow(
            id=identifier,
            source=WorkflowSource.BUILT_IN,
            name=name,
            description=description,
            steps=[
                WorkflowStep(
                    id="announce",
                    title="Confirm workflow start",
                    action=StepAction.NOTIFY,
                    priority=5,
                    message=f"{name} started.",
                ),
                WorkflowStep(
                    id="focus",
                    title="Set session focus",
                    action=StepAction.NOTIFY,
                    priority=4,
                    depends_on=["announce"],
                    message=description,
                ),
                WorkflowStep(
                    id="complete",
                    title="Confirm readiness",
                    action=StepAction.NOTIFY,
                    priority=3,
                    depends_on=["focus"],
                    message=f"{name} is ready.",
                ),
            ],
        )
        for identifier, name, description in definitions
    ]
