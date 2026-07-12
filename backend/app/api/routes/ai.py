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
from backend.app.domain.memory import MemoryCreate
from backend.app.api.routes.memory import get_memory_store
from backend.app.api.routes.windows import get_windows_controller
from backend.app.api.routes.browser import get_browser_controller
from backend.app.browser.natural_language import parse_browser_command
from backend.app.windows.natural_language import execute_natural_command
from backend.app.api.routes.github import get_github_controller
from backend.app.github.natural_language import parse_github_command

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
    browser_request = parse_browser_command(request.message)
    if browser_request is not None:
        browser_result = await get_browser_controller().execute(browser_request)
        async def browser_events() -> AsyncIterator[str]:
            yield _event("token", content=browser_result.message)
            yield _event("done")
        return StreamingResponse(browser_events(), media_type="application/x-ndjson")
    github_request = parse_github_command(request.message)
    if github_request is not None:
        github_result = await get_github_controller().execute(github_request)
        async def github_events() -> AsyncIterator[str]:
            yield _event("token", content=github_result.message)
            yield _event("done")
        return StreamingResponse(github_events(), media_type="application/x-ndjson")
    action_result = execute_natural_command(request.message, get_windows_controller())
    if action_result is not None:
        async def action_events() -> AsyncIterator[str]:
            yield _event("token", content=action_result.message)
            yield _event("done")
        return StreamingResponse(action_events(), media_type="application/x-ndjson")
    get_memory_store().save(MemoryCreate(memory_type="conversation", content=request.message, metadata={"role": "user"}))

    async def events() -> AsyncIterator[str]:
        reply = ""
        try:
            async for content in get_ollama_client().stream_chat(model, request.history, request.message):
                if content:
                    reply += content
                    yield _event("token", content=content)
            if reply:
                get_memory_store().save(MemoryCreate(memory_type="conversation", content=reply, metadata={"role": "assistant"}))
            yield _event("done")
        except OllamaUnavailableError as error:
            logger.warning("ollama_stream_failed", extra={"model": model})
            yield _event("error", message=str(error))

    return StreamingResponse(events(), media_type="application/x-ndjson")


def _event(event_type: str, **payload: str) -> str:
    """Serialize a single newline-delimited stream event."""
    return f"{json.dumps({'type': event_type, **payload}, ensure_ascii=True)}\n"
