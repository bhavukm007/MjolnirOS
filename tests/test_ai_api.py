import json

from fastapi.testclient import TestClient

from backend.app.ai.ollama_client import OllamaUnavailableError
from backend.app.api.routes import ai
from backend.app.domain.ai import AiModel
from backend.app.main import create_app


class AvailableOllamaClient:
    """Deterministic local Ollama substitute for API integration tests."""

    def __init__(self) -> None:
        self.requested_models: list[str] = []

    async def list_models(self) -> list[AiModel]:
        return [AiModel(name="qwen2.5:3b", family="qwen2", parameter_size="3B")]

    async def stream_chat(self, model: str, history: list[object], message: str):
        self.requested_models.append(model)
        assert message == "Hello"
        yield "Hello"
        yield " from Ollama"


class UnavailableOllamaClient:
    """Ollama substitute that exercises the offline behavior."""

    async def list_models(self) -> list[AiModel]:
        raise OllamaUnavailableError("Ollama is not running or cannot be reached.")

    async def stream_chat(self, model: str, history: list[object], message: str):
        raise OllamaUnavailableError("Ollama is not running or cannot be reached.")
        yield ""


def test_ai_health_and_models_report_local_runtime(monkeypatch) -> None:
    monkeypatch.setattr(ai, "get_ollama_client", lambda: AvailableOllamaClient())
    client = TestClient(create_app())

    health_response = client.get("/api/v1/ai/health")
    models_response = client.get("/api/v1/ai/models")

    assert health_response.status_code == 200
    assert health_response.json()["data"]["available"] is True
    assert health_response.json()["data"]["default_model_available"] is True
    assert models_response.json()["data"]["models"][0]["name"] == "qwen2.5:3b"


def test_chat_streams_ollama_tokens(monkeypatch) -> None:
    ollama_client = AvailableOllamaClient()
    monkeypatch.setattr(ai, "get_ollama_client", lambda: ollama_client)
    client = TestClient(create_app())

    response = client.post("/api/v1/chat", json={"message": "Hello"})
    events = [json.loads(line) for line in response.text.splitlines()]

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert events == [
        {"type": "token", "content": "Hello"},
        {"type": "token", "content": " from Ollama"},
        {"type": "done"},
    ]
    assert ollama_client.requested_models == ["qwen2.5:3b"]


def test_chat_forwards_the_model_selected_by_the_user(monkeypatch) -> None:
    ollama_client = AvailableOllamaClient()
    monkeypatch.setattr(ai, "get_ollama_client", lambda: ollama_client)
    client = TestClient(create_app())

    response = client.post("/api/v1/chat", json={"message": "Hello", "model": "llama3.2:3b"})

    assert response.status_code == 200
    assert ollama_client.requested_models == ["llama3.2:3b"]


def test_ai_routes_report_offline_ollama_without_server_error(monkeypatch) -> None:
    monkeypatch.setattr(ai, "get_ollama_client", lambda: UnavailableOllamaClient())
    client = TestClient(create_app())

    health_response = client.get("/api/v1/ai/health")
    chat_response = client.post("/api/v1/chat", json={"message": "Hello"})
    chat_events = [json.loads(line) for line in chat_response.text.splitlines()]

    assert health_response.status_code == 200
    assert health_response.json()["data"]["available"] is False
    assert chat_events == [
        {"type": "error", "message": "Ollama is not running or cannot be reached."}
    ]
