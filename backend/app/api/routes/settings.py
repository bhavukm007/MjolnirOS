"""Runtime configuration and persisted user settings endpoints."""

from fastapi import APIRouter

from backend.app.core.responses import ApiResponse
from backend.app.core.settings import PublicSettings, get_settings
from backend.app.domain.user_settings import UserSettings, UserSettingsUpdate
from backend.app.settings.settings_service import SettingsService

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


def _service() -> SettingsService:
    return SettingsService(get_settings())


@router.get("/settings/user", response_model=ApiResponse[UserSettings])
async def get_user_settings() -> ApiResponse[UserSettings]:
    """Return persisted UI preferences without exposing secrets."""
    return ApiResponse(
        success=True, message="User settings loaded.", data=_service().get()
    )


@router.put("/settings/user", response_model=ApiResponse[UserSettings])
async def update_user_settings(
    payload: UserSettingsUpdate,
) -> ApiResponse[UserSettings]:
    """Persist user preferences atomically."""
    return ApiResponse(
        success=True, message="User settings updated.", data=_service().update(payload)
    )
