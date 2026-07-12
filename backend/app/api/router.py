"""Top-level API router."""

from fastapi import APIRouter

from backend.app.api.routes.health import router as health_router
from backend.app.api.routes.ai import router as ai_router
from backend.app.api.routes.settings import router as settings_router
from backend.app.api.routes.voice import router as voice_router
from backend.app.api.routes.memory import router as memory_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(ai_router)
api_router.include_router(settings_router)
api_router.include_router(voice_router)
api_router.include_router(memory_router)
