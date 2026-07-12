"""REST API for the local plugin manager and marketplace."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Response, status

from backend.app.core.responses import ApiResponse
from backend.app.core.settings import get_settings
from backend.app.domain.plugin import MarketplacePlugin, PluginRecord
from backend.app.plugins.plugin_service import PluginService

router = APIRouter(prefix="/plugins", tags=["plugins", "marketplace"])
logger = logging.getLogger(__name__)


def _plugins() -> PluginService:
    return PluginService(get_settings())


@router.get("", response_model=ApiResponse[list[PluginRecord]])
async def list_plugins(
    search: str | None = None, category: str | None = None
) -> ApiResponse[list[PluginRecord]]:
    """List discovered local plugins without requiring a backend restart."""
    return ApiResponse(
        success=True,
        message="Plugins loaded.",
        data=_plugins().list_plugins(search, category),
    )


@router.get("/marketplace", response_model=ApiResponse[list[MarketplacePlugin]])
async def marketplace(
    search: str | None = None, category: str | None = None
) -> ApiResponse[list[MarketplacePlugin]]:
    """Search the local marketplace catalog."""
    return ApiResponse(
        success=True,
        message="Marketplace loaded.",
        data=_plugins().marketplace(search, category),
    )


@router.get("/categories", response_model=ApiResponse[list[str]])
async def categories() -> ApiResponse[list[str]]:
    """List marketplace categories for client-side filtering."""
    return ApiResponse(
        success=True, message="Plugin categories loaded.", data=_plugins().categories()
    )


@router.post("/{plugin_id}/install", response_model=ApiResponse[PluginRecord])
async def install(plugin_id: str) -> ApiResponse[PluginRecord]:
    """Install and dynamically load a local marketplace plugin."""
    plugin = _plugins().install(plugin_id)
    logger.info("plugin_installed", extra={"plugin_id": plugin_id})
    return ApiResponse(
        success=True, message="Plugin installed and loaded.", data=plugin
    )


@router.post("/{plugin_id}/load", response_model=ApiResponse[PluginRecord])
async def load(plugin_id: str) -> ApiResponse[PluginRecord]:
    """Dynamically load a plugin after permission and dependency validation."""
    return ApiResponse(
        success=True, message="Plugin loaded.", data=_plugins().load(plugin_id)
    )


@router.post("/{plugin_id}/update", response_model=ApiResponse[PluginRecord])
async def update(plugin_id: str) -> ApiResponse[PluginRecord]:
    """Validate and reload the latest locally installed plugin version."""
    return ApiResponse(
        success=True, message="Plugin updated.", data=_plugins().update(plugin_id)
    )


@router.delete("/{plugin_id}", status_code=status.HTTP_204_NO_CONTENT)
async def uninstall(plugin_id: str) -> Response:
    """Uninstall a plugin only when no installed plugin depends on it."""
    _plugins().uninstall(plugin_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
