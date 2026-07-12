"""Top-level API router."""

from fastapi import APIRouter

from backend.app.api.routes.health import router as health_router
from backend.app.api.routes.automation import router as automation_router
from backend.app.api.routes.settings import router as settings_router
from backend.app.api.routes.vision import router as vision_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(automation_router)
api_router.include_router(settings_router)
api_router.include_router(vision_router)
