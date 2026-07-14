"""Async client for the local Ollama HTTP API."""

from __future__ import annotations

from collections.abc import AsyncIterator
import json
import logging
from typing import Any

import httpx

from backend.app.core.settings import AppSettings
from backend.app.domain.ai import AiModel, ChatMessage


class OllamaUnavailableError(RuntimeError):
    """Raised when the local Ollama service cannot process a request."""


class OllamaClient:
    """Encapsulate local Ollama health, model discovery, and chat streaming."""

    def __init__(self, settings: AppSettings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._base_url = settings.ollama_base_url.rstrip("/")
        self._timeout = httpx.Timeout(settings.ollama_timeout_seconds)
        self._transport = transport
        self._logger = logging.getLogger(__name__)

    async def list_models(self) -> list[AiModel]:
        """Return models installed in the local Ollama service."""
        payload = await self._get_json("/tags")
        models = payload.get("models", [])
        if not isinstance(models, list):
            raise OllamaUnavailableError("Ollama returned an invalid model list.")
        return [self._to_model(item) for item in models if isinstance(item, dict)]

    async def stream_chat(
        self,
        model: str,
        history: list[ChatMessage],
        message: str,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        """Yield text fragments from Ollama's newline-delimited chat stream."""
        request_body = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt or (
                        "You are Mjolnir, a concise local desktop assistant. "
                        "Address the user naturally as Boss when it fits, without overusing it."
                    ),
                },
                *[{"role": entry.role, "content": entry.content} for entry in history],
                {"role": "user", "content": message},
            ],
            "stream": True,
        }
        self._logger.info("ollama_chat_stream_started", extra={"model": model})
        try:
            async with self._create_client() as client:
                async with client.stream("POST", "/chat", json=request_body) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        yield self._extract_content(line)
        except httpx.HTTPStatusError as error:
            self._logger.warning(
                "ollama_chat_http_error",
                extra={"status_code": error.response.status_code, "model": model},
            )
            raise OllamaUnavailableError("Ollama could not generate a response for this model.") from error
        except httpx.HTTPError as error:
            self._logger.warning("ollama_chat_unavailable", extra={"model": model})
            raise OllamaUnavailableError("Ollama is not running or cannot be reached.") from error

    async def _get_json(self, path: str) -> dict[str, Any]:
        try:
            async with self._create_client() as client:
                response = await client.get(path)
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPStatusError as error:
            self._logger.warning("ollama_http_error", extra={"status_code": error.response.status_code})
            raise OllamaUnavailableError("Ollama responded with an error.") from error
        except httpx.HTTPError as error:
            self._logger.info("ollama_unavailable")
            raise OllamaUnavailableError("Ollama is not running or cannot be reached.") from error

        if not isinstance(payload, dict):
            raise OllamaUnavailableError("Ollama returned an invalid response.")
        return payload

    def _create_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
            transport=self._transport,
        )

    @staticmethod
    def _extract_content(line: str) -> str:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as error:
            raise OllamaUnavailableError("Ollama returned an invalid streaming response.") from error

        message = payload.get("message", {})
        if not isinstance(message, dict):
            raise OllamaUnavailableError("Ollama returned an invalid chat message.")
        content = message.get("content", "")
        return content if isinstance(content, str) else ""

    @staticmethod
    def _to_model(payload: dict[str, Any]) -> AiModel:
        details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
        size = payload.get("size")
        return AiModel(
            name=str(payload.get("name", "")),
            size_bytes=size if isinstance(size, int) else None,
            family=details.get("family") if isinstance(details.get("family"), str) else None,
            parameter_size=details.get("parameter_size") if isinstance(details.get("parameter_size"), str) else None,
        )
