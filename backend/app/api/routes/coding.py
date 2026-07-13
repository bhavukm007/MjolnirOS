"""Coding Agent API endpoints."""

from functools import lru_cache

from fastapi import APIRouter

from backend.app.api.routes.memory import get_memory_store
from backend.app.coding.controller import CodingController
from backend.app.core.responses import ApiResponse
from backend.app.core.settings import get_settings
from backend.app.domain.coding import CodingActionRequest, CodingActionResult


router = APIRouter(prefix="/coding", tags=["coding"])


@lru_cache
def get_coding_controller() -> CodingController:
    """Return the process-wide local Coding Agent controller."""
    return CodingController(get_settings(), get_memory_store())


@router.post("/actions", response_model=ApiResponse[CodingActionResult])
async def execute_action(request: CodingActionRequest) -> ApiResponse[CodingActionResult]:
    """Perform one safe VS Code, terminal, or workspace action."""
    result = get_coding_controller().execute(request)
    return ApiResponse(success=result.success, message=result.message, data=result)
