"""Build and Project Agent API."""
from fastapi import APIRouter, HTTPException
from backend.app.core.responses import ApiResponse
from backend.app.domain.build import BuildActionRequest, BuildActionResult
router = APIRouter(prefix="/build", tags=["coding"])
@router.post("/actions", response_model=ApiResponse[BuildActionResult])
async def execute_action(request: BuildActionRequest) -> ApiResponse[BuildActionResult]:
    """Reject legacy build execution until actions use the approved runtime."""
    del request
    raise HTTPException(
        status_code=501,
        detail="Build actions are unavailable until they are routed through the approved agent runtime.",
    )
