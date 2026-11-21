"""Local Ollama health, model discovery, and streaming chat routes."""

import json
import logging
from collections.abc import AsyncIterator
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from backend.app.ai.capability_router import (
    Capability,
    CapabilityDecision,
    CapabilityRouter,
)
from backend.app.ai.intent_router import IntentRouter
from backend.app.ai.ollama_client import OllamaClient, OllamaUnavailableError
from backend.app.ai.text_normalizer import TextNormalizer
from backend.app.api.routes.coding_ai import get_ai_coding_controller
from backend.app.api.routes.memory import get_memory_store
from backend.app.api.routes.windows import get_windows_controller
from backend.app.api.routes.agents import get_agent_runtime
from backend.app.core.coding_security import assert_coding_authorized
from backend.app.core.responses import ApiResponse
from backend.app.domain.ai import AiHealthStatus, AiModelsStatus, ChatRequest
from backend.app.memory.context_engine import ContextEngine
from backend.app.memory.service import MemoryService
from backend.app.settings.settings_service import get_runtime_ai_settings
from backend.app.tasks.lifecycle import TaskStatus
from backend.app.tasks.sqlite_store import PersistentTask

router = APIRouter(tags=["ai"])
logger = logging.getLogger(__name__)
windows_controller = get_windows_controller()
capability_router = CapabilityRouter(
    application_resolver=windows_controller.resolve_application
)
text_normalizer = TextNormalizer()


def get_ollama_client() -> OllamaClient:
    """Construct the local Ollama client from centralized configuration."""
    return OllamaClient(get_runtime_ai_settings())


@router.get("/ai/health", response_model=ApiResponse[AiHealthStatus])
async def get_ai_health() -> ApiResponse[AiHealthStatus]:
    """Return a non-failing availability check for the local Ollama runtime."""
    settings = get_runtime_ai_settings()
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
async def stream_chat(request: ChatRequest, http_request: Request) -> StreamingResponse:
    """Stream assistant content as NDJSON for the desktop chat interface."""
    settings = get_runtime_ai_settings()
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
        response = (
            "What's up, Boss?"
            if "up" in message.lower()
            else "Hello, Boss. How can I help?"
        )
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
        runtime = get_agent_runtime(http_request)
        browser_input = {
            key: value
            for key, value in {
                "action": decision.payload.action,
                "browser": decision.payload.browser,
                "url": str(decision.payload.url) if decision.payload.url else None,
                "query": decision.payload.query,
            }.items()
            if value is not None
        }
        if browser_input["action"] not in {"open", "search", "read", "summarize", "tabs"}:
            return _direct_response(
                memory, message, "That browser action is not yet available through the approved agent runtime.", decision
            )
        task = runtime.create_task(
            "browser.safe_action", browser_input, f"chat-{uuid4()}"
        )
        return _agent_task_response(memory, message, decision, runtime, task)
    if decision.capability is Capability.WINDOWS:
        capability_id, capability_input = _windows_capability_input(
            decision.payload.action,
            decision.payload.parameters,
            get_agent_runtime(http_request).settings,
        )
        if capability_id is None:
            return _direct_response(
                memory,
                message,
                "That Windows action is not available through the approved agent runtime yet.",
                decision,
            )
        runtime = get_agent_runtime(http_request)
        try:
            task = runtime.create_task(
                capability_id,
                capability_input,
                f"chat-{uuid4()}",
            )
        except (KeyError, ValueError):
            return _direct_response(
                memory, message, "The requested action could not be validated.", decision
            )
        return _agent_task_response(memory, message, decision, runtime, task)
    if decision.capability is Capability.BUILD:
        return _direct_response(
            memory,
            message,
            "Build actions are unavailable until they are routed through the approved agent runtime.",
            decision,
        )
    if decision.capability is Capability.AI_CODING:
        decision.payload.model = model
        ai_coding_result = await get_ai_coding_controller().execute(decision.payload)
        return _direct_response(
            memory,
            message,
            ai_coding_result.data.get("response", ai_coding_result.message),
            decision,
        )
    if decision.capability is Capability.CODING:
        runtime = get_agent_runtime(http_request)
        capability_id, coding_input = _coding_capability_input(
            decision.payload.action,
            decision.payload.path,
            decision.payload.command,
            runtime.settings.coding_project_roots,
        )
        if capability_id is None:
            return _direct_response(
                memory, message, "That development action is not yet available through the approved agent runtime.", decision
            )
        if capability_id in {"coding.run_flask", "coding.run_project_tests"}:
            assert_coding_authorized(http_request)
        task = runtime.create_task(capability_id, coding_input, f"chat-{uuid4()}")
        return _agent_task_response(memory, message, decision, runtime, task)
    if decision.capability is Capability.GITHUB:
        if decision.payload.action in {"status", "repository_summary"}:
            from backend.app.api.routes.github import get_github_controller

            github_result = await get_github_controller().execute(decision.payload)
            return _direct_response(memory, message, github_result.message, decision)
        return _direct_response(
            memory,
            message,
            "Git and GitHub mutations are unavailable until they use the approved agent runtime.",
            decision,
        )
    if decision.capability is Capability.PLANNER:
        return _direct_response(
            memory,
            message,
            "Natural-language workflow execution is unavailable. Use the explicit workflow or plan APIs.",
            decision,
        )

    context_engine = ContextEngine(get_memory_store())
    system_prompt = context_engine.prompt(message)
    history = context_engine.history(request.history)
    memory.ingest(message)
    memory.record_conversation("user", message)

    async def events() -> AsyncIterator[str]:
        reply = ""
        try:
            yield _event("routing_decision", **decision.event_data())
            async for content in get_ollama_client().stream_chat(
                model, history, message, system_prompt
            ):
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


def _windows_capability_input(
    action: str, parameters: dict[str, str], settings: object
) -> tuple[str | None, dict[str, object]]:
    """Translate deterministic Windows intents to registered typed capabilities."""
    direct = {
        "open_application": ("windows.launch_application", "name"),
        "search_files": ("windows.search_files", "query"),
        "open_folder": ("windows.open_directory", "path"),
        "list_directory": ("windows.list_directory", "path"),
        "read_file": ("windows.read_file", "path"),
        "create_file": ("windows.create_file", "path"),
        "create_directory": ("windows.create_directory", "path"),
        "delete_file": ("windows.delete_file", "path"),
        "copy_file": ("windows.copy_file", None),
        "move_file": ("windows.move_file", None),
        "open_explorer": ("windows.open_explorer", None),
        "system_info": ("windows.get_system_status", None),
        "processes": ("windows.list_processes", None),
    }
    mapped = direct.get(action)
    if mapped is None:
        return None, {}
    capability_id, field = mapped
    if field is None:
        if action in {"copy_file", "move_file"}:
            return capability_id, {
                "source": parameters.get("source", ""),
                "destination": parameters.get("destination", ""),
            }
        return capability_id, {}
    value = parameters.get(field, "")
    if action in {"open_folder", "list_directory", "read_file", "create_file", "create_directory", "delete_file"}:
        from pathlib import Path

        root = settings.windows_search_root.expanduser().resolve(strict=False)
        candidate = Path(value).expanduser()
        if candidate.is_absolute():
            candidate = candidate.resolve(strict=False)
            if not candidate.is_relative_to(root):
                return None, {}
            value = candidate.relative_to(root).as_posix() or "."
    result_key = "name" if action == "open_application" else "query" if action == "search_files" else "path"
    return capability_id, {result_key: value}


def _coding_capability_input(
    action: str,
    path: str | None,
    command: str | None,
    configured_roots: list[object],
) -> tuple[str | None, dict[str, object]]:
    if action == "list_projects":
        return "coding.list_projects", {}
    if action == "run_project_tests":
        project = path or (str(configured_roots[0]) if configured_roots else "")
        return "coding.run_project_tests", {"project": project}
    if action == "run_command" and command == "flask run":
        project = path or (str(configured_roots[0]) if configured_roots else "")
        return "coding.run_flask", {"project": project}
    if action in {"open_project", "switch_project", "open_workspace", "open_folder"}:
        project = path or (str(configured_roots[0]) if configured_roots else "")
        return "coding.open_project", {"project": project}
    if action == "open_file":
        return "coding.open_file", {"path": path or ""}
    return None, {}


def _agent_task_response(
    memory: MemoryService,
    message: str,
    decision: CapabilityDecision,
    runtime: object,
    initial_task: PersistentTask,
) -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        yield _event(
            "tool_start",
            task_id=str(initial_task.task_id),
            capability_id=initial_task.capability_id,
            status=initial_task.status.value,
            content=f"Started {initial_task.capability_id}.",
        )
        task = initial_task
        if task.status is TaskStatus.QUEUED:
            task = await runtime.execute_task(task.task_id)
        if task.status is TaskStatus.WAITING_APPROVAL:
            answer = (
                f"This action needs your approval. Review it in Agent Activity before it runs. "
                f"Task {task.task_id}."
            )
        elif task.status is TaskStatus.SUCCEEDED:
            answer = _agent_result_text(task)
        else:
            answer = f"The action failed ({task.error_code or task.status.value})."
        memory.record_conversation("user", message)
        memory.record_conversation("assistant", answer)
        event_type = "tool_result" if task.status is TaskStatus.SUCCEEDED else "tool_error" if task.status is TaskStatus.FAILED else "tool_result"
        yield _event(
            event_type,
            task_id=str(task.task_id),
            capability_id=task.capability_id,
            status=task.status.value,
            content=answer,
            message=answer,
        )
        yield _event("routing_decision", **decision.event_data())
        yield _event("token", content=answer)
        yield _event("done")

    return StreamingResponse(events(), media_type="application/x-ndjson")


def _agent_result_text(task: PersistentTask) -> str:
    result = task.result or {}
    nested = result.get("result")
    if isinstance(nested, dict):
        result = nested
    if task.capability_id == "windows.launch_application":
        return str(result.get("message", "Application launch completed."))
    if task.capability_id == "windows.get_system_status":
        return "System status: " + ", ".join(
            f"{key.replace('_', ' ')} {value}%" if value is not None else f"{key.replace('_', ' ')} unavailable"
            for key, value in result.items()
        )
    if task.capability_id == "windows.search_files":
        matches = result.get("matches", [])
        preview = ", ".join(str(path) for path in matches[:10])
        return f"Found {len(matches)} matching path(s)." + (f" {preview}" if preview else "")
    if task.capability_id == "windows.list_directory":
        entries = result.get("entries", [])
        return f"Listed {len(entries)} entries in the approved directory."
    if task.capability_id == "windows.read_file":
        return str(result.get("content", "File read successfully."))
    if task.capability_id == "browser.safe_action":
        return str(result.get("message", "Browser action completed."))
    if task.capability_id == "coding.list_projects":
        projects = result.get("projects", [])
        return f"Found {len(projects)} approved project(s)."
    if task.capability_id == "coding.git_status":
        return str(result.get("status", "Git status is clean.")) or "Git status is clean."
    if task.capability_id == "coding.open_project":
        return f"Opened {result.get('project', 'the approved project')} in VS Code."
    if task.capability_id in {"coding.run_project_tests", "coding.run_flask"}:
        return str(result.get("summary", "Approved development operation completed."))
    return "The approved Windows action completed successfully."


def _event(event_type: str, **payload: object) -> str:
    """Serialize a single newline-delimited stream event."""
    return f"{json.dumps({'type': event_type, **payload}, ensure_ascii=True)}\n"
