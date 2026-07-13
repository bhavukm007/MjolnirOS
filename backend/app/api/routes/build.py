"""Build and Project Agent API."""
from functools import lru_cache
from fastapi import APIRouter
from backend.app.api.routes.memory import get_memory_store
from backend.app.coding.build_controller import BuildController
from backend.app.core.responses import ApiResponse
from backend.app.core.settings import get_settings
from backend.app.domain.build import BuildActionRequest, BuildActionResult
router = APIRouter(prefix="/build", tags=["coding"])
@lru_cache
def get_build_controller() -> BuildController:
    """Return the process-wide Build and Project Agent."""
    return BuildController(get_settings(), get_memory_store())
@router.post("/actions", response_model=ApiResponse[BuildActionResult])
async def execute_action(request: BuildActionRequest) -> ApiResponse[BuildActionResult]:
    """Perform a local Docker, dependency, build, or project action."""
    result = get_build_controller().execute(request)
    return ApiResponse(success=result.success, message=result.message, data=result)
