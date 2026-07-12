"""Local-AI page summarization with an offline extractive fallback."""

from __future__ import annotations

import asyncio
import logging

from backend.app.ai.ollama_client import OllamaClient, OllamaUnavailableError
from backend.app.core.settings import AppSettings


class PageSummarizer:
    """Summarize page content through Ollama without sending it to cloud services."""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._client = OllamaClient(settings)
        self._logger = logging.getLogger(__name__)

    async def summarize(self, text: str) -> str:
        """Use the configured local model, falling back when it is unavailable."""
        prompt = "Summarize this webpage in concise bullet points. Preserve factual uncertainty.\n\n" + text[:12_000]
        try:
            chunks: list[str] = []
            async with asyncio.timeout(self._settings.browser_summary_timeout_seconds):
                async for chunk in self._client.stream_chat(self._settings.default_model, [], prompt):
                    chunks.append(chunk)
            summary = "".join(chunks).strip()
            if summary:
                return summary
        except (OllamaUnavailableError, TimeoutError):
            self._logger.info("browser_summary_fallback_used")
        return self._extractive_summary(text)

    @staticmethod
    def _extractive_summary(text: str) -> str:
        sentences = [sentence.strip() for sentence in text.replace("\n", " ").split(".") if sentence.strip()]
        return ". ".join(sentences[:5]) + ("." if sentences else "")
