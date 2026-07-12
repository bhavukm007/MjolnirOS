"""Password-safe Browser Agent API routes."""

from functools import lru_cache

from fastapi import APIRouter

from backend.app.api.routes.memory import get_memory_store
from backend.app.browser.controller import BrowserController
from backend.app.core.responses import ApiResponse
from backend.app.core.settings import get_settings
from backend.app.domain.browser import BrowserActionRequest, BrowserActionResult
from backend.app.domain.memory import MemoryCreate


router = APIRouter(prefix="/browser", tags=["browser"])


@lru_cache
def get_browser_controller() -> BrowserController:
    """Return the process-wide Playwright Browser Agent."""
    return BrowserController(get_settings())


@router.post("/actions", response_model=ApiResponse[BrowserActionResult])
async def execute_browser_action(request: BrowserActionRequest) -> ApiResponse[BrowserActionResult]:
    """Execute a safe browser action, persisting bookmarks in local memory."""
    result = await get_browser_controller().execute(request)
    if result.success and request.action == "bookmark":
        get_memory_store().save(MemoryCreate(memory_type="bookmark", content=result.data["url"], metadata={"browser": request.browser}))
        result.message = "Page bookmarked in local memory."
    return ApiResponse(success=result.success, message=result.message, data=result)


@router.post("/open", response_model=ApiResponse[BrowserActionResult])
async def open_website(request: BrowserActionRequest) -> ApiResponse[BrowserActionResult]:
    """Compatibility endpoint for opening a website."""
    return await execute_browser_action(request.model_copy(update={"action": "open"}))


@router.post("/search", response_model=ApiResponse[BrowserActionResult])
async def search_google(request: BrowserActionRequest) -> ApiResponse[BrowserActionResult]:
    """Compatibility endpoint for a Google search."""
    return await execute_browser_action(request.model_copy(update={"action": "search"}))


@router.post("/download", response_model=ApiResponse[BrowserActionResult])
async def download_file(request: BrowserActionRequest) -> ApiResponse[BrowserActionResult]:
    """Compatibility endpoint for a safe browser download."""
    return await execute_browser_action(request.model_copy(update={"action": "download"}))


@router.post("/upload", response_model=ApiResponse[BrowserActionResult])
async def upload_file(request: BrowserActionRequest) -> ApiResponse[BrowserActionResult]:
    """Compatibility endpoint for selecting a local upload file."""
    return await execute_browser_action(request.model_copy(update={"action": "upload"}))
