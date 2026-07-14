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
from backend.app.ai.capability_router import Capability, CapabilityDecision, CapabilityRouter
from backend.app.ai.text_normalizer import TextNormalizer
from backend.app.api.routes.windows import get_windows_controller
from backend.app.api.routes.browser import get_browser_controller
from backend.app.api.routes.github import get_github_controller
from backend.app.api.routes.coding import get_coding_controller
from backend.app.api.routes.coding_ai import get_ai_coding_controller
from backend.app.api.routes.build import get_build_controller
from backend.app.automation.automation_service import AutomationService
from backend.app.automation.planner_service import PlannerService

router = APIRouter(tags=["ai"])
logger = logging.getLogger(__name__)
windows_controller = get_windows_controller()
capability_router = CapabilityRouter(
    application_resolver=windows_controller.resolve_application
)
text_normalizer = TextNormalizer()


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
    normalized_message = text_normalizer.normalize(request.message)
    routed = IntentRouter(settings.voice_wake_word).classify(normalized_message)
    message = routed.message
    decision = capability_router.route(routed)
    logger.info(
        "capability_routed",
        extra={"intent": routed.intent.value, **decision.event_data()},
    )

    if decision.capability is Capability.LIVE_INFORMATION:
        return _capability_not_implemented(memory, message, decision)
    if decision.capability is Capability.MEMORY:
        response = memory.handle_command(message)
        if response:
            return _direct_response(memory, message, response, decision)
    if decision.capability is Capability.GREETING:
        response = "What's up, Boss?" if "up" in message.lower() else "Hello, Boss. How can I help?"
        return _direct_response(memory, message, response, decision)
    if decision.capability is Capability.APPLICATION_NOT_FOUND:
        target = decision.payload.parameters["name"]
        return _direct_response(
            memory,
            message,
            f"Application or website not found: {target}.",
            decision,
        )

    if decision.capability is Capability.BROWSER:
        browser_result = await get_browser_controller().execute(decision.payload)
        return _direct_response(memory, message, browser_result.message, decision)
    if decision.capability is Capability.WINDOWS:
        action_result = windows_controller.execute(
            decision.payload.action, decision.payload.parameters, False
        )
        if action_result.success and routed.intent is Intent.APPLICATION_LAUNCH:
            data = action_result.data or {}
            memory.remember_installed_application(
                message[5:].strip() if message.lower().startswith("open ") else message,
                str(data.get("resolved_executable_path")) if data.get("resolved_executable_path") else None,
            )
        return _direct_response(memory, message, action_result.message, decision)
    if decision.capability is Capability.BUILD:
        build_result = get_build_controller().execute(decision.payload)
        return _direct_response(memory, message, build_result.message, decision)
    if decision.capability is Capability.AI_CODING:
        decision.payload.model = model
        ai_coding_result = await get_ai_coding_controller().execute(decision.payload)
        return _direct_response(memory, message, ai_coding_result.data.get("response", ai_coding_result.message), decision)
    if decision.capability is Capability.CODING:
        coding_result = get_coding_controller().execute(decision.payload)
        return _direct_response(memory, message, coding_result.message, decision)
    if decision.capability is Capability.GITHUB:
        github_result = await get_github_controller().execute(decision.payload)
        return _direct_response(memory, message, github_result.message, decision)
    if decision.capability is Capability.PLANNER:
        planned_result = await PlannerService(AutomationService(settings)).execute_goal(message)
        if planned_result is not None:
            return _direct_response(memory, message, planned_result, decision)

    context_engine = ContextEngine(get_memory_store())
    system_prompt = context_engine.prompt(message)
    history = context_engine.history(request.history)
    memory.ingest(message)
    memory.record_conversation("user", message)

    async def events() -> AsyncIterator[str]:
        reply = ""
        try:
            yield _event("routing_decision", **decision.event_data())
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


def _direct_response(
    memory: MemoryService, message: str, response: str, decision: CapabilityDecision
) -> StreamingResponse:
    """Return a local answer while preserving bounded conversation continuity."""
    memory.record_conversation("user", message)
    memory.record_conversation("assistant", response)

    async def events() -> AsyncIterator[str]:
        yield _event("routing_decision", **decision.event_data())
        yield _event("token", content=response)
        yield _event("done")

    return StreamingResponse(events(), media_type="application/x-ndjson")


def _capability_not_implemented(
    memory: MemoryService, message: str, decision: CapabilityDecision
) -> StreamingResponse:
    response = "Capability Not Yet Implemented: live information is recognized but has no provider configured."
    memory.record_conversation("user", message)
    memory.record_conversation("assistant", response)

    async def events() -> AsyncIterator[str]:
        yield _event("routing_decision", **decision.event_data())
        yield _event(
            "capability_result",
            success=False,
            code="CAPABILITY_NOT_YET_IMPLEMENTED",
            capability=decision.capability.value,
            message=response,
        )
        yield _event("token", content=response)
        yield _event("done")

    return StreamingResponse(events(), media_type="application/x-ndjson")


def _event(event_type: str, **payload: object) -> str:
    """Serialize a single newline-delimited stream event."""
    return f"{json.dumps({'type': event_type, **payload}, ensure_ascii=True)}\n"
