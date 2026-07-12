"""Top-level API router."""

from fastapi import APIRouter

from backend.app.api.routes.health import router as health_router
from backend.app.api.routes.ai import router as ai_router
from backend.app.api.routes.settings import router as settings_router
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
api_router.include_router(settings_router)
api_router.include_router(voice_router)
api_router.include_router(memory_router)
api_router.include_router(windows_router)
api_router.include_router(browser_router)
api_router.include_router(github_router)
api_router.include_router(coding_router)
api_router.include_router(coding_ai_router)
api_router.include_router(build_router)
