"""Local AI Coding Agent API endpoints."""

from functools import lru_cache

from fastapi import APIRouter

from backend.app.ai.ollama_client import OllamaClient
from backend.app.api.routes.memory import get_memory_store
from backend.app.coding.ai_controller import AiCodingController
from backend.app.core.responses import ApiResponse
from backend.app.core.settings import get_settings
from backend.app.domain.ai_coding import CodingAiRequest, CodingAiResult


router = APIRouter(prefix="/coding/ai", tags=["coding"])


@lru_cache
def get_ai_coding_controller() -> AiCodingController:
    """Return the process-wide local Ollama Coding Agent."""
    settings = get_settings()
    return AiCodingController(settings, OllamaClient(settings), get_memory_store())


@router.post("/actions", response_model=ApiResponse[CodingAiResult])
async def execute_action(request: CodingAiRequest) -> ApiResponse[CodingAiResult]:
    """Generate or analyse code with the configured local Ollama model."""
    result = await get_ai_coding_controller().execute(request)
    return ApiResponse(success=result.success, message=result.message, data=result)
