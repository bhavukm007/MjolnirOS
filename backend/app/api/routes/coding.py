"""Coding Agent API endpoints."""

from fastapi import APIRouter, Depends, Request

from backend.app.api.routes.agents import get_agent_runtime
from backend.app.core.coding_security import assert_coding_authorized
from backend.app.core.responses import ApiResponse
from backend.app.domain.coding import CodingActionRequest, CodingActionResult
from pathlib import Path
from uuid import uuid4
from backend.app.tasks.lifecycle import TaskStatus

router = APIRouter(prefix="/coding", tags=["coding"])


@router.post("/actions", response_model=ApiResponse[CodingActionResult])
async def execute_action(
    request: CodingActionRequest,
    http_request: Request,
    _authorized: None = Depends(assert_coding_authorized),
) -> ApiResponse[CodingActionResult]:
    """Execute coding operations through the shared registered capability policy."""
    runtime = get_agent_runtime(http_request)
    capability_id, action_input = _capability_for(
        request, runtime.settings.coding_project_roots
    )
    if capability_id is None:
        result = CodingActionResult(
            success=False,
            message="This coding operation is not available through the approved capability registry.",
        )
        return ApiResponse(success=False, message=result.message, data=result)
    try:
        task = runtime.create_task(capability_id, action_input, f"coding-api-{uuid4()}")
        if task.status is TaskStatus.QUEUED:
            task = await runtime.execute_task(task.task_id)
    except (KeyError, ValueError):
        result = CodingActionResult(success=False, message="Coding action failed validation.")
        return ApiResponse(success=False, message=result.message, data=result)
    if task.status is TaskStatus.WAITING_APPROVAL:
        result = CodingActionResult(
            success=False,
            message="Review this exact action in Agent Activity before execution.",
            data={"task_id": str(task.task_id), "status": task.status.value},
            confirmation_required=True,
        )
        return ApiResponse(success=False, message=result.message, data=result)
    if task.status is not TaskStatus.SUCCEEDED:
        result = CodingActionResult(
            success=False,
            message=f"Coding action failed ({task.error_code or task.status.value}).",
            data={"task_id": str(task.task_id), "status": task.status.value},
        )
        return ApiResponse(success=False, message=result.message, data=result)
    raw = (task.result or {}).get("result", {})
    result = CodingActionResult(
        success=True,
        message="Coding action completed.",
        data={**(raw if isinstance(raw, dict) else {}), "task_id": str(task.task_id), "status": task.status.value},
    )
    return ApiResponse(success=result.success, message=result.message, data=result)


def _capability_for(request: CodingActionRequest, configured_roots: list[object]):
    if request.action == "list_projects":
        return "coding.list_projects", {}
    if request.action in {"open_project", "open_folder", "switch_project"}:
        return "coding.open_project", {"project": request.path or ""}
    if request.action == "open_workspace":
        path = Path(request.path).expanduser() if request.path else None
        if path is not None and path.is_file():
            return "coding.open_file", {"path": str(path)}
        return "coding.open_project", {"project": request.path or ""}
    if request.action in {"open_file", "reveal_file"}:
        return "coding.open_file", {"path": request.path or ""}
    if request.action == "run_project_tests":
        project = request.cwd or request.path or (str(configured_roots[0]) if configured_roots else "")
        return "coding.run_project_tests", {"project": project}
    if request.action == "run_command" and request.command == "flask run":
        project = request.cwd or request.path or (str(configured_roots[0]) if configured_roots else "")
        return "coding.run_flask", {"project": project}
    return None, {}
