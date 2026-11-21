"""Health endpoint for launch and monitoring checks."""

from fastapi import APIRouter

from backend.app.core.responses import ApiResponse
from backend.app.domain.health import HealthStatus
from backend.app.settings.settings_service import get_runtime_ai_settings
from backend.app.version import APP_VERSION

router = APIRouter(tags=["health"])


@router.get("/health", response_model=ApiResponse[HealthStatus])
async def get_health() -> ApiResponse[HealthStatus]:
    """Return backend health and foundational runtime state."""
    settings = get_runtime_ai_settings()
    status = HealthStatus(
        status="ok",
        app_name=settings.app_name,
        environment=settings.environment,
        version=APP_VERSION,
        default_model=settings.default_model,
        modules=settings.enabled_foundation_modules,
    )
    return ApiResponse(
        success=True, message="MjolnirOS backend is healthy.", data=status
    )
