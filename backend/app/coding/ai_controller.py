"""Local Ollama orchestration for code generation and analysis tasks."""

from __future__ import annotations

import logging

from backend.app.ai.ollama_client import OllamaClient, OllamaUnavailableError
from backend.app.core.settings import AppSettings
from backend.app.domain.ai_coding import CodingAiRequest, CodingAiResult
from backend.app.domain.memory import MemoryCreate
from backend.app.memory.store import MemoryStore


_ACTION_INSTRUCTIONS = {
    "generate": "Generate production-ready code that directly satisfies the request. Include concise setup notes when useful.",
    "explain": "Explain the code accurately, including control flow, data flow, and relevant language concepts.",
    "debug": "Identify likely defects, explain their cause, and provide a corrected version or precise edits.",
    "error_explanation": "Explain the error, its likely cause, and the smallest safe resolution steps.",
    "compile_analysis": "Analyse the compilation output, identify each actionable cause, and propose ordered fixes.",
    "fix_suggestions": "Provide concrete, safe fix suggestions with rationale and revised code where appropriate.",
}


class AiCodingController:
    """Generate and analyse code through the existing local Ollama runtime only."""

    def __init__(self, settings: AppSettings, ollama_client: OllamaClient, memory_store: MemoryStore) -> None:
        self._settings = settings
        self._ollama_client = ollama_client
        self._memory_store = memory_store
        self._logger = logging.getLogger(__name__)

    async def execute(self, request: CodingAiRequest) -> CodingAiResult:
        """Run a bounded coding task and persist the local request and response."""
        model = request.model or self._settings.default_model
        prompt = self._prompt(request)
        self._logger.info("coding_ai_started", extra={"action": request.action, "language": request.language, "model": model})
        try:
            fragments = [fragment async for fragment in self._ollama_client.stream_chat(model, [], prompt) if fragment]
        except OllamaUnavailableError as error:
            self._logger.warning("coding_ai_unavailable", extra={"action": request.action, "model": model})
            return CodingAiResult(success=False, message=str(error))

        response = "".join(fragments).strip()
        if not response:
            self._logger.warning("coding_ai_empty_response", extra={"action": request.action, "model": model})
            return CodingAiResult(success=False, message="Local Ollama returned an empty coding response.")
        metadata = {"agent": "coding_ai", "action": request.action, "language": request.language or "unspecified", "model": model}
        self._memory_store.save(MemoryCreate(memory_type="conversation", content=request.content, metadata={**metadata, "role": "user"}))
        self._memory_store.save(MemoryCreate(memory_type="conversation", content=response, metadata={**metadata, "role": "assistant"}))
        self._logger.info("coding_ai_completed", extra={"action": request.action, "language": request.language, "model": model})
        return CodingAiResult(success=True, message="Local coding assistance completed.", data={"response": response, "action": request.action, "language": request.language, "model": model})

    def _prompt(self, request: CodingAiRequest) -> str:
        language = request.language or "the most appropriate supported language"
        context = (
            f"\nAdditional context:\n{request.context[:self._settings.coding_ai_max_context_chars]}"
            if request.context
            else ""
        )
        return (
            "You are MjolnirOS, a local coding assistant. "
            f"{_ACTION_INSTRUCTIONS[request.action]} "
            f"Target language: {language}. "
            "Do not claim to execute commands or access files you were not given. "
            f"User request or material:\n{request.content}{context}"
        )
