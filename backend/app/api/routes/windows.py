"""Windows Control Agent API."""
from functools import lru_cache
from fastapi import APIRouter, HTTPException, Request
from backend.app.core.responses import ApiResponse
from backend.app.core.settings import get_settings
from backend.app.domain.windows import WindowsActionRequest, WindowsActionResult
from backend.app.windows.controller import WindowsController
from backend.app.api.routes.agents import get_agent_runtime
from backend.app.tasks.lifecycle import TaskStatus
from uuid import uuid4
from pathlib import Path
router=APIRouter(prefix="/windows",tags=["windows"])
@lru_cache
def get_windows_controller() -> WindowsController:
    """Return the local Windows Control Agent."""
    return WindowsController(get_settings())
@router.post("/actions",response_model=ApiResponse[WindowsActionResult])
async def execute_action(
    payload: WindowsActionRequest, http_request: Request
) -> ApiResponse[WindowsActionResult]:
    """Route supported Windows operations through registered policy checks."""
    runtime = get_agent_runtime(http_request)
    capability_id, arguments = _capability_request(payload.action, payload.arguments)
    if capability_id is None:
        raise HTTPException(
            status_code=501,
            detail="This Windows action is not yet exposed through the approved capability registry.",
        )
    arguments = _normalize_authorized_paths(arguments, runtime.settings.windows_search_root)
    if arguments is None:
        raise HTTPException(status_code=422, detail="Windows paths must remain under the configured approved folder.")
    try:
        task = runtime.create_task(
            capability_id, arguments, f"windows-api-{uuid4()}"
        )
        if task.status is TaskStatus.WAITING_APPROVAL:
            result = WindowsActionResult(
                success=False,
                message="Review and approve this exact action in Agent Activity before it executes.",
                data={"task_id": str(task.task_id), "status": task.status.value},
                confirmation_required=True,
            )
            return ApiResponse(success=False, message=result.message, data=result)
        elif task.status is TaskStatus.QUEUED:
            task = await runtime.execute_task(task.task_id)
    except (ValueError, KeyError):
        result = WindowsActionResult(success=False, message="The Windows action failed validation.")
        return ApiResponse(success=False, message=result.message, data=result)
    if task.status is not TaskStatus.SUCCEEDED:
        result = WindowsActionResult(
            success=False,
            message=f"Windows action failed ({task.error_code or task.status.value}).",
            confirmation_required=task.status is TaskStatus.WAITING_APPROVAL,
        )
        return ApiResponse(success=False, message=result.message, data=result)
    raw = (task.result or {}).get("result", {})
    result = WindowsActionResult(
        success=True,
        message=str(raw.get("message", "Windows action completed.")) if isinstance(raw, dict) else "Windows action completed.",
        data=raw if isinstance(raw, dict) else {},
    )
    return ApiResponse(success=True, message=result.message, data=result)


def _capability_request(
    action: str, arguments: dict[str, object]
) -> tuple[str | None, dict[str, object]]:
    mapping = {
        "open_application": ("windows.launch_application", {"name": arguments.get("name", "")}),
        "system_info": ("windows.get_system_status", {}),
        "processes": ("windows.list_processes", {}),
        "open_explorer": ("windows.open_explorer", {}),
        "open_task_manager": ("windows.open_task_manager", {}),
        "close_application": (
            "windows.close_process",
            {"pid": arguments.get("pid", 0)},
        ),
        "search_files": ("windows.search_files", {"query": arguments.get("query", "")}),
        "open_folder": ("windows.open_directory", {"path": arguments.get("path", "")}),
        "create_file": ("windows.create_file", {"path": arguments.get("path", ""), "content": arguments.get("content", "")}),
        "create_directory": ("windows.create_directory", {"path": arguments.get("path", "")}),
        "copy_file": ("windows.copy_file", {"source": arguments.get("source", ""), "destination": arguments.get("destination", "")}),
        "move_file": ("windows.move_file", {"source": arguments.get("source", ""), "destination": arguments.get("destination", "")}),
        "rename_file": ("windows.move_file", {"source": arguments.get("source", ""), "destination": arguments.get("destination", "")}),
        "delete_file": ("windows.delete_file", {"path": arguments.get("path", "")}),
    }
    return mapping.get(action, (None, {}))


def _normalize_authorized_paths(
    arguments: dict[str, object], approved_root: Path
) -> dict[str, object] | None:
    normalized = dict(arguments)
    root = approved_root.expanduser().resolve(strict=False)
    for field in ("path", "source", "destination"):
        raw = normalized.get(field)
        if not isinstance(raw, str) or not raw:
            continue
        candidate = Path(raw).expanduser()
        if candidate.is_absolute():
            resolved = candidate.resolve(strict=False)
            if not resolved.is_relative_to(root):
                return None
            normalized[field] = resolved.relative_to(root).as_posix() or "."
    return normalized
