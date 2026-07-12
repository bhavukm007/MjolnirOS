"""Deterministic local-Ollama Coding Agent tests."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from backend.app.ai.ollama_client import OllamaUnavailableError
from backend.app.api.routes import ai, coding_ai
from backend.app.coding.ai_controller import AiCodingController
from backend.app.coding.ai_natural_language import parse_ai_coding_command
from backend.app.core.settings import AppSettings
from backend.app.domain.ai_coding import CodingAiRequest, CodingAiResult
from backend.app.memory.store import MemoryStore
from backend.app.main import create_app


class LocalOllama:
    """Capture local Coding Agent prompts without accessing a network."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def stream_chat(self, model: str, history: list[object], message: str):
        self.calls.append((model, message))
        yield "Local "
        yield "coding response"


class OfflineOllama:
    """Deterministically simulate unavailable local Ollama."""

    async def stream_chat(self, model: str, history: list[object], message: str):
        raise OllamaUnavailableError("Ollama is not running or cannot be reached.")
        yield ""


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("action", "language"),
    [
        ("generate", "python"),
        ("explain", "sql"),
        ("debug", "javascript"),
        ("error_explanation", "java"),
        ("compile_analysis", "cpp"),
        ("fix_suggestions", "python"),
    ],
)
async def test_local_ollama_coding_actions_are_structured_and_persisted(tmp_path, action, language) -> None:
    """Every Phase 09B action uses only the injected local Ollama client and local memory."""
    memory = MemoryStore(tmp_path / "memory.db", tmp_path / "chroma")
    ollama = LocalOllama()
    controller = AiCodingController(AppSettings(default_model="local-model"), ollama, memory)

    result = await controller.execute(CodingAiRequest(action=action, content="example material", language=language, context="extra context"))

    assert result.success and result.data["response"] == "Local coding response"
    assert ollama.calls[0][0] == "local-model" and f"Target language: {language}" in ollama.calls[0][1]
    records = memory.list("conversation")
    assert len(records) == 2 and {record.metadata["role"] for record in records} == {"user", "assistant"}
    assert all(record.metadata["agent"] == "coding_ai" for record in records)


@pytest.mark.anyio
async def test_local_ollama_failure_and_configured_context_limit_are_structured(tmp_path) -> None:
    """Unavailable Ollama and configured prompt bounds return safe, deterministic outcomes."""
    memory = MemoryStore(tmp_path / "memory.db", tmp_path / "chroma")
    offline = await AiCodingController(AppSettings(), OfflineOllama(), memory).execute(CodingAiRequest(action="debug", content="traceback"))
    ollama = LocalOllama()
    controller = AiCodingController(AppSettings(coding_ai_max_context_chars=4), ollama, memory)
    await controller.execute(CodingAiRequest(action="explain", content="code", context="123456"))

    assert not offline.success and "not running" in offline.message
    assert "1234" in ollama.calls[0][1] and "12345" not in ollama.calls[0][1]


@pytest.mark.anyio
async def test_ai_coding_emits_structured_lifecycle_logs(tmp_path, caplog) -> None:
    """Coding AI logs action, language, and model without storing request content in logs."""
    caplog.set_level("INFO", logger="backend.app.coding.ai_controller")
    controller = AiCodingController(AppSettings(default_model="local-model"), LocalOllama(), MemoryStore(tmp_path / "memory.db", tmp_path / "chroma"))

    result = await controller.execute(CodingAiRequest(action="generate", content="secret implementation", language="python"))

    started = next(record for record in caplog.records if record.message == "coding_ai_started")
    completed = next(record for record in caplog.records if record.message == "coding_ai_completed")
    assert result.success and started.action == "generate" and started.model == "local-model"
    assert completed.language == "python" and "secret implementation" not in caplog.text


def test_ai_coding_api_and_natural_language_routes_cover_supported_examples(monkeypatch) -> None:
    """REST, typed AI, and voice-fed command text dispatch to the Coding Agent."""
    class Controller:
        async def execute(self, request: CodingAiRequest) -> CodingAiResult:
            return CodingAiResult(success=True, message="Coding routed.", data={"response": f"{request.action} result"})

    controller = Controller()
    monkeypatch.setattr(coding_ai, "get_ai_coding_controller", lambda: controller)
    monkeypatch.setattr(ai, "get_ai_coding_controller", lambda: controller)
    client = TestClient(create_app())
    api_response = client.post("/api/v1/coding/ai/actions", json={"action": "generate", "content": "a REST API", "language": "python"})
    invalid_response = client.post("/api/v1/coding/ai/actions", json={"action": "delete", "content": "x"})
    phrases = [
        "Mjolnir, explain this code.",
        "Mjolnir, debug this error.",
        "Mjolnir, generate a REST API.",
        "Mjolnir, explain this compiler error.",
        "Mjolnir, generate a Flask application.",
        "Mjolnir, explain this SQL query.",
    ]
    chats = [client.post("/api/v1/chat", json={"message": phrase}) for phrase in phrases]

    assert api_response.status_code == 200 and api_response.json()["data"]["success"]
    assert invalid_response.status_code == 422
    assert all(response.status_code == 200 and "result" in response.text for response in chats)
    assert parse_ai_coding_command("Mjolnir, generate a Flask application.").language == "python"
    assert parse_ai_coding_command("Mjolnir, explain this SQL query.").language == "sql"
    assert parse_ai_coding_command("open terminal") is None
