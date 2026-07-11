"""Read-only runtime configuration endpoint for Phase 01."""

from fastapi import APIRouter

from backend.app.core.responses import ApiResponse
from backend.app.core.settings import PublicSettings, get_settings

router = APIRouter(tags=["settings"])


@router.get("/settings", response_model=ApiResponse[PublicSettings])
async def get_public_settings() -> ApiResponse[PublicSettings]:
    """Return non-sensitive centralized settings used by the dashboard."""
    settings = get_settings()
    return ApiResponse(
        success=True,
        message="Configuration loaded successfully.",
        data=settings.to_public_settings(),
    )
