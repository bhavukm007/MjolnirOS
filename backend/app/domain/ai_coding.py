"""Schemas for local Ollama-powered coding assistance."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


CodingAiAction = Literal[
    "generate",
    "explain",
    "debug",
    "error_explanation",
    "compile_analysis",
    "fix_suggestions",
]
CodingLanguage = Literal["python", "cpp", "java", "javascript", "sql"]


class CodingAiRequest(BaseModel):
    """A bounded local coding-assistance request."""

    action: CodingAiAction
    content: str = Field(min_length=1, max_length=12_000)
    language: CodingLanguage | None = None
    context: str | None = Field(default=None, max_length=12_000)
    model: str | None = Field(default=None, min_length=1, max_length=256)


class CodingAiResult(BaseModel):
    """Structured result generated exclusively by the configured local model."""

    success: bool
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
