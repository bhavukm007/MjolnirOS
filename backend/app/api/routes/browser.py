"""Password-safe Browser Agent API routes."""

from functools import lru_cache

from fastapi import APIRouter, Request

from backend.app.api.routes.agents import get_agent_runtime
from backend.app.browser.controller import BrowserController
from backend.app.core.responses import ApiResponse
from backend.app.domain.browser import (
    CAPABILITY_BACKED_BROWSER_ACTIONS,
    BrowserActionRequest,
    BrowserActionResult,
)
from backend.app.settings.settings_service import get_runtime_ai_settings
from backend.app.tasks.lifecycle import TaskStatus
from uuid import uuid4

router = APIRouter(prefix="/browser", tags=["browser"])


@lru_cache
def get_browser_controller() -> BrowserController:
    """Return the process-wide Playwright Browser Agent."""
    return BrowserController(get_runtime_ai_settings())


@router.post("/actions", response_model=ApiResponse[BrowserActionResult])
async def execute_browser_action(
    request: BrowserActionRequest,
    http_request: Request,
) -> ApiResponse[BrowserActionResult]:
    """Execute registered browser operations through shared capability policy."""
    if request.action not in CAPABILITY_BACKED_BROWSER_ACTIONS:
        result = BrowserActionResult(success=False, message="This browser operation is not available through the approved capability registry.")
        return ApiResponse(success=False, message=result.message, data=result)
    runtime = get_agent_runtime(http_request)
    capability_input = {
        key: value
        for key, value in {
            "action": "open" if request.action in {"new_tab", "bookmark"} else request.action,
            "browser": request.browser,
            "url": str(request.url) if request.url else None,
            "query": request.query,
        }.items()
        if value is not None
    }
    try:
        task = runtime.create_task("browser.safe_action", capability_input, f"browser-api-{uuid4()}")
        if task.status is TaskStatus.QUEUED:
            task = await runtime.execute_task(task.task_id)
    except (KeyError, ValueError):
        result = BrowserActionResult(success=False, message="Browser action failed validation.")
        return ApiResponse(success=False, message=result.message, data=result)
    if task.status is not TaskStatus.SUCCEEDED:
        result = BrowserActionResult(success=False, message=f"Browser action failed ({task.error_code or task.status.value}).")
        return ApiResponse(success=False, message=result.message, data=result)
    nested = (task.result or {}).get("result", {})
    result_data = nested.get("data", {}) if isinstance(nested, dict) else {}
    result = BrowserActionResult(
        success=True,
        message=str(nested.get("message", "Browser action completed.")) if isinstance(nested, dict) else "Browser action completed.",
        data=result_data if isinstance(result_data, dict) else {},
    )
    return ApiResponse(success=result.success, message=result.message, data=result)


@router.post("/open", response_model=ApiResponse[BrowserActionResult])
async def open_website(
    request: BrowserActionRequest,
    http_request: Request,
) -> ApiResponse[BrowserActionResult]:
    """Compatibility endpoint for opening a website."""
    return await execute_browser_action(request.model_copy(update={"action": "open"}), http_request)


@router.post("/search", response_model=ApiResponse[BrowserActionResult])
async def search_google(
    request: BrowserActionRequest,
    http_request: Request,
) -> ApiResponse[BrowserActionResult]:
    """Compatibility endpoint for a Google search."""
    return await execute_browser_action(request.model_copy(update={"action": "search"}), http_request)


@router.post("/download", response_model=ApiResponse[BrowserActionResult])
async def download_file(
    request: BrowserActionRequest,
    http_request: Request,
) -> ApiResponse[BrowserActionResult]:
    """Compatibility endpoint for a safe browser download."""
    return await execute_browser_action(request.model_copy(update={"action": "download"}), http_request)


@router.post("/upload", response_model=ApiResponse[BrowserActionResult])
async def upload_file(
    request: BrowserActionRequest,
    http_request: Request,
) -> ApiResponse[BrowserActionResult]:
    """Compatibility endpoint for selecting a local upload file."""
    return await execute_browser_action(request.model_copy(update={"action": "upload"}), http_request)
