"""Top-level API router."""

from fastapi import APIRouter

from backend.app.api.routes.health import router as health_router
from backend.app.api.routes.learning import router as learning_router
from backend.app.api.routes.plugins import router as plugins_router
from backend.app.api.routes.automation import router as automation_router
from backend.app.api.routes.settings import router as settings_router
from backend.app.api.routes.vision import router as vision_router
from backend.app.api.routes.productivity import router as productivity_router
from backend.app.api.routes.communication import router as communication_router
from backend.app.api.routes.ai import router as ai_router
from backend.app.api.routes.voice import router as voice_router
from backend.app.api.routes.memory import router as memory_router
from backend.app.api.routes.windows import router as windows_router
from backend.app.api.routes.browser import router as browser_router
from backend.app.api.routes.github import router as github_router
from backend.app.api.routes.coding import router as coding_router
from backend.app.api.routes.coding_ai import router as coding_ai_router
from backend.app.api.routes.build import router as build_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(ai_router)
api_router.include_router(voice_router)
api_router.include_router(memory_router)
api_router.include_router(windows_router)
api_router.include_router(browser_router)
api_router.include_router(github_router)
api_router.include_router(coding_router)
api_router.include_router(coding_ai_router)
api_router.include_router(build_router)
api_router.include_router(learning_router)
api_router.include_router(plugins_router)
api_router.include_router(automation_router)
api_router.include_router(settings_router)
api_router.include_router(vision_router)
api_router.include_router(productivity_router)
api_router.include_router(communication_router)
