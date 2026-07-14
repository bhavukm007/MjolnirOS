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
from backend.app.api.routes.memory import get_memory_store
from backend.app.memory.service import MemoryService
from backend.app.memory.context_engine import ContextEngine
from backend.app.ai.intent_router import Intent, IntentRouter
from backend.app.api.routes.windows import get_windows_controller
from backend.app.api.routes.browser import get_browser_controller
from backend.app.browser.natural_language import parse_browser_command
from backend.app.windows.natural_language import execute_natural_command
from backend.app.api.routes.github import get_github_controller
from backend.app.github.natural_language import parse_github_command
from backend.app.api.routes.coding import get_coding_controller
from backend.app.coding.natural_language import parse_coding_command
from backend.app.api.routes.coding_ai import get_ai_coding_controller
from backend.app.coding.ai_natural_language import parse_ai_coding_command
from backend.app.api.routes.build import get_build_controller
from backend.app.coding.build_natural_language import parse_build_command
from backend.app.automation.automation_service import AutomationService
from backend.app.automation.planner_service import PlannerService

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
    memory = MemoryService(get_memory_store())
    routed = IntentRouter(settings.voice_wake_word).classify(request.message)
    message = routed.message
    logger.info("intent_routed", extra={"intent": routed.intent.value, "confidence": routed.confidence})

    if routed.intent in {Intent.MEMORY_QUERY, Intent.MEMORY_WRITE, Intent.MEMORY_FORGET, Intent.REMINDER}:
        response = memory.handle_command(message)
        if response:
            return _direct_response(memory, message, response)
    if routed.intent is Intent.GREETING:
        response = "What's up, Boss?" if "up" in message.lower() else "Hello, Boss. How can I help?"
        return _direct_response(memory, message, response)

    # Deterministic local tools run before any generative planner.
    # Website-shaped open commands must be decomposed before generic app launch.
    browser_request = parse_browser_command(message)
    if browser_request is not None:
        browser_result = await get_browser_controller().execute(browser_request)
        return _direct_response(memory, message, browser_result.message)
    action_result = execute_natural_command(message, get_windows_controller())
    if action_result is not None:
        if action_result.success and routed.intent is Intent.APPLICATION_LAUNCH:
            data = action_result.data or {}
            memory.remember_installed_application(
                message[5:].strip() if message.lower().startswith("open ") else message,
                str(data.get("resolved_executable_path")) if data.get("resolved_executable_path") else None,
            )
        return _direct_response(memory, message, action_result.message)
    build_request = parse_build_command(message)
    if build_request is not None:
        build_result = get_build_controller().execute(build_request)
        async def build_events() -> AsyncIterator[str]:
            yield _event("token", content=build_result.message)
            yield _event("done")
        return _direct_response(memory, message, build_result.message)
    ai_coding_request = parse_ai_coding_command(message)
    if ai_coding_request is not None:
        ai_coding_request.model = model
        ai_coding_result = await get_ai_coding_controller().execute(ai_coding_request)
        return _direct_response(memory, message, ai_coding_result.data.get("response", ai_coding_result.message))
    coding_request = parse_coding_command(message)
    if coding_request is not None:
        coding_result = get_coding_controller().execute(coding_request)
        return _direct_response(memory, message, coding_result.message)
    github_request = parse_github_command(message)
    if github_request is not None:
        github_result = await get_github_controller().execute(github_request)
        return _direct_response(memory, message, github_result.message)
    if routed.intent is Intent.AUTOMATION:
        planned_result = await PlannerService(AutomationService(settings)).execute_goal(message)
        if planned_result is not None:
            return _direct_response(memory, message, planned_result)

    context_engine = ContextEngine(get_memory_store())
    system_prompt = context_engine.prompt(message)
    history = context_engine.history(request.history)
    memory.ingest(message)
    memory.record_conversation("user", message)

    async def events() -> AsyncIterator[str]:
        reply = ""
        try:
            async for content in get_ollama_client().stream_chat(model, history, message, system_prompt):
                if content:
                    reply += content
                    yield _event("token", content=content)
            if reply:
                memory.record_conversation("assistant", reply)
            yield _event("done")
        except OllamaUnavailableError as error:
            logger.warning("ollama_stream_failed", extra={"model": model})
            yield _event("error", message=str(error))

    return StreamingResponse(events(), media_type="application/x-ndjson")


def _direct_response(memory: MemoryService, message: str, response: str) -> StreamingResponse:
    """Return a local answer while preserving bounded conversation continuity."""
    memory.record_conversation("user", message)
    memory.record_conversation("assistant", response)

    async def events() -> AsyncIterator[str]:
        yield _event("token", content=response)
        yield _event("done")

    return StreamingResponse(events(), media_type="application/x-ndjson")


def _event(event_type: str, **payload: str) -> str:
    """Serialize a single newline-delimited stream event."""
    return f"{json.dumps({'type': event_type, **payload}, ensure_ascii=True)}\n"
