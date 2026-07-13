"""Top-level API router."""

from fastapi import APIRouter

from backend.app.api.routes.health import router as health_router
from backend.app.api.routes.learning import router as learning_router
from backend.app.api.routes.plugins import router as plugins_router
from backend.app.api.routes.automation import router as automation_router
from backend.app.api.routes.settings import router as settings_router
from backend.app.api.routes.vision import router as vision_router
from backend.app.api.routes.productivity import router as productivity_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(learning_router)
api_router.include_router(plugins_router)
api_router.include_router(automation_router)
api_router.include_router(settings_router)
api_router.include_router(vision_router)
api_router.include_router(productivity_router)
