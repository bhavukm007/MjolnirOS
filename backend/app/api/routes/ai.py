"""Local Ollama health, model discovery, and streaming chat routes."""

from collections.abc import AsyncIterator
import json
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from backend.app.ai.ollama_client import OllamaClient, OllamaUnavailableError
from backend.app.core.responses import ApiResponse
from backend.app.core.settings import get_settings
from backend.app.domain.ai import AiHealthStatus, AiModelsStatus, ChatRequest

router = APIRouter(tags=["ai"])
logger = logging.getLogger(__name__)


def get_ollama_client() -> OllamaClient:
    """Construct the local Ollama client from centralized configuration."""
    return OllamaClient(get_settings())


@router.get("/ai/health", response_model=ApiResponse[AiHealthStatus])
async def get_ai_health() -> ApiResponse[AiHealthStatus]:
    """Return a non-failing availability check for the local Ollama runtime."""
    settings = get_settings()
    try:
        models = await get_ollama_client().list_models()
    except OllamaUnavailableError as error:
        return ApiResponse(
            success=True,
            message="Ollama is unavailable.",
            data=AiHealthStatus(
                available=False,
                default_model=settings.default_model,
                default_model_available=False,
                message=str(error),
            ),
        )

    model_names = {model.name for model in models}
    return ApiResponse(
        success=True,
        message="Ollama is available.",
        data=AiHealthStatus(
            available=True,
            default_model=settings.default_model,
            default_model_available=settings.default_model in model_names,
            message="Local Ollama runtime is ready.",
        ),
    )


@router.get("/ai/models", response_model=ApiResponse[AiModelsStatus])
async def get_ai_models() -> ApiResponse[AiModelsStatus]:
    """Return locally installed Ollama models without failing when offline."""
    try:
        models = await get_ollama_client().list_models()
    except OllamaUnavailableError:
        return ApiResponse(
            success=True,
            message="Ollama is unavailable.",
            data=AiModelsStatus(available=False, models=[]),
        )
    return ApiResponse(
        success=True,
        message="Local Ollama models loaded.",
        data=AiModelsStatus(available=True, models=models),
    )


@router.post("/chat")
async def stream_chat(request: ChatRequest) -> StreamingResponse:
    """Stream assistant content as NDJSON for the desktop chat interface."""
    settings = get_settings()
    model = request.model or settings.default_model

    async def events() -> AsyncIterator[str]:
        try:
            async for content in get_ollama_client().stream_chat(model, request.history, request.message):
                if content:
                    yield _event("token", content=content)
            yield _event("done")
        except OllamaUnavailableError as error:
            logger.warning("ollama_stream_failed", extra={"model": model})
            yield _event("error", message=str(error))

    return StreamingResponse(events(), media_type="application/x-ndjson")


def _event(event_type: str, **payload: str) -> str:
    """Serialize a single newline-delimited stream event."""
    return f"{json.dumps({'type': event_type, **payload}, ensure_ascii=True)}\n"
