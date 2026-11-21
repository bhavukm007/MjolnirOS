"""Authenticated production endpoints for the local capability runtime."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from backend.app.agent_runtime.runtime import AgentRuntime
from backend.app.core.settings import AppSettings
from backend.app.tasks.lifecycle import TaskStatus
from backend.app.tasks.sqlite_store import PersistentTask

router = APIRouter(prefix="/agents", tags=["agents", "tasks"])


class AgentTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability_id: str = Field(min_length=3, max_length=128)
    input: dict[str, object]
    idempotency_key: str = Field(
        default_factory=lambda: str(uuid4()),
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )


class AgentPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steps: list[dict[str, object]] = Field(min_length=2, max_length=20)
    idempotency_key: str = Field(
        default_factory=lambda: str(uuid4()), min_length=8, max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )


class AgentTaskView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: UUID
    capability_id: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    error_code: str | None = None
    result_summary: str | None = None
    approval_summary: str | None = None
    approval_details: dict[str, object] | None = None
    completed_steps: int = 0


def get_agent_runtime(request: Request) -> AgentRuntime:
    runtime = getattr(request.app.state, "agent_runtime", None)
    if runtime is None:
        settings: AppSettings = request.app.state.settings
        runtime = AgentRuntime(settings)
        request.app.state.agent_runtime = runtime
    return runtime


@router.get("/capabilities")
async def list_agent_capabilities(request: Request) -> dict[str, object]:
    """Discover only capabilities registered for the local Windows device."""
    return {"success": True, "data": get_agent_runtime(request).capabilities()}


@router.get("/permissions")
async def list_agent_permissions(request: Request) -> dict[str, object]:
    runtime = get_agent_runtime(request)
    return {
        "success": True,
        "data": [grant.model_dump(mode="json") for grant in runtime.store.list_permission_grants(runtime.device_id)],
    }


@router.post("/permissions/{grant_id}/revoke")
async def revoke_agent_permission(grant_id: UUID, request: Request) -> dict[str, object]:
    runtime = get_agent_runtime(request)
    try:
        grant = runtime.revoke_permission(grant_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Permission grant was not found.") from error
    return {"success": True, "data": grant.model_dump(mode="json")}


@router.post("/tasks", response_model=AgentTaskView, status_code=201)
async def create_agent_task(
    payload: AgentTaskRequest, request: Request
) -> AgentTaskView:
    runtime = get_agent_runtime(request)
    try:
        task = runtime.create_task(
            payload.capability_id, payload.input, payload.idempotency_key
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Capability is not registered.") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if task.status is TaskStatus.QUEUED:
        task = await runtime.execute_task(task.task_id)
    return _view(task, approval_input=payload.input)


@router.post("/plans", response_model=AgentTaskView, status_code=202)
async def create_agent_plan(payload: AgentPlanRequest, request: Request) -> AgentTaskView:
    runtime = get_agent_runtime(request)
    try:
        task = runtime.create_plan_task(payload.steps, payload.idempotency_key)
    except (KeyError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if task.status is TaskStatus.QUEUED:
        runtime.start_background(task.task_id)
    return _view(task)


@router.get("/tasks", response_model=list[AgentTaskView])
async def list_agent_tasks(request: Request, limit: int = 50) -> list[AgentTaskView]:
    runtime = get_agent_runtime(request)
    return [
        _view(
            task,
            completed_steps=sum(
                event["event_type"] == "step_completed"
                for event in runtime.store.events(task.task_id)
            ),
        )
        for task in runtime.store.list(limit)
    ]


@router.get("/tasks/{task_id}", response_model=AgentTaskView)
async def get_agent_task(task_id: UUID, request: Request) -> AgentTaskView:
    try:
        task = get_agent_runtime(request).store.get(task_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Task was not found.") from error
    return _view(task)


@router.get("/tasks/{task_id}/events")
async def get_agent_task_events(task_id: UUID, request: Request) -> dict[str, object]:
    runtime = get_agent_runtime(request)
    try:
        runtime.store.get(task_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Task was not found.") from error
    return {"success": True, "data": runtime.store.events(task_id)}


@router.get("/tasks/{task_id}/approval-details")
async def get_task_approval_details(task_id: UUID, request: Request) -> dict[str, object]:
    runtime = get_agent_runtime(request)
    task = runtime.store.get(task_id)
    if task.status is not TaskStatus.WAITING_APPROVAL:
        raise HTTPException(status_code=409, detail="Task is not waiting for approval.")
    details = runtime.approval_details(task_id)
    return {"success": True, "data": details}


@router.post("/tasks/{task_id}/approve", response_model=AgentTaskView)
async def approve_agent_task(task_id: UUID, request: Request) -> AgentTaskView:
    runtime = get_agent_runtime(request)
    try:
        approval = runtime.approve(task_id)
        task = await runtime.execute_task(task_id, approval)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Task was not found.") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return _view(task)


@router.post("/tasks/{task_id}/cancel", response_model=AgentTaskView)
async def cancel_agent_task(task_id: UUID, request: Request) -> AgentTaskView:
    runtime = get_agent_runtime(request)
    try:
        task = runtime.cancel(task_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Task was not found.") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return _view(task)


def _view(
    task: PersistentTask,
    *,
    approval_input: dict[str, object] | None = None,
    completed_steps: int = 0,
) -> AgentTaskView:
    if task.status is TaskStatus.SUCCEEDED:
        if task.capability_id == "windows.get_system_status":
            result_summary = "System status collected."
        elif task.capability_id in {"windows.search_files", "windows.list_directory"}:
            result_summary = "Approved folder operation completed."
        elif task.capability_id == "windows.read_file":
            result_summary = "Supported text file read. Content is hidden from task history."
        else:
            result_summary = "Capability completed successfully."
    else:
        result_summary = None
    approval_summary = None
    if task.status is TaskStatus.WAITING_APPROVAL:
        approval_summary = f"Approve the exact action for {task.capability_id}. Review its parameters before approving."
    details = _safe_approval_details(approval_input or task.input) if approval_summary else None
    return AgentTaskView(
        task_id=task.task_id,
        capability_id=task.capability_id,
        status=task.status,
        created_at=task.created_at,
        updated_at=task.updated_at,
        error_code=task.error_code,
        result_summary=result_summary,
        approval_summary=approval_summary,
        approval_details=details,
        completed_steps=completed_steps,
    )


def _safe_approval_details(input_data: dict[str, object]) -> dict[str, object]:
    """Expose the exact impact to the local approval UI without exposing full content."""
    details = {
        key: input_data[key]
        for key in ("path", "source", "destination", "name", "pid")
        if key in input_data
    }
    content = input_data.get("content")
    if isinstance(content, str):
        details["content_bytes"] = len(content.encode("utf-8"))
        details["content_preview"] = content[:240]
        details["content_truncated"] = len(content) > 240
    return details
