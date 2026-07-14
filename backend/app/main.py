"""FastAPI entry point for the MjolnirOS backend."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.router import api_router
from backend.app.api.routes.browser import get_browser_controller
from backend.app.core.logging import configure_logging
from backend.app.core.settings import AppSettings, get_settings
from backend.app.plugins.plugin_service import PluginService


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Configure application services for startup and shutdown."""
    settings: AppSettings = app.state.settings
    configure_logging(settings)
    PluginService(settings).load_enabled_plugins()
    logging.getLogger(__name__).info(
        "backend_started",
        extra={"app_name": settings.app_name, "environment": settings.environment},
    )
    try:
        yield
    finally:
        await get_browser_controller().close()
        get_browser_controller.cache_clear()
        logging.getLogger(__name__).info("backend_stopped")


def create_app(settings: AppSettings | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    app_settings = settings or get_settings()
    app = FastAPI(
        title=app_settings.app_name,
        version="1.0.0",
        docs_url=f"{app_settings.api_prefix}/docs",
        openapi_url=f"{app_settings.api_prefix}/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = app_settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_allowed_origins(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix=app_settings.api_prefix)
    return app


app = create_app()
