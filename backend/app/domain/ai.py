"""Domain schemas for the local AI runtime."""

from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """A single local conversation turn accepted by the Ollama client."""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=12_000)


class ChatRequest(BaseModel):
    """A request to stream a reply from a selected local model."""

    message: str = Field(min_length=1, max_length=12_000)
    model: str | None = Field(default=None, min_length=1, max_length=256)
    history: list[ChatMessage] = Field(default_factory=list, max_length=30)


class AiModel(BaseModel):
    """A locally installed Ollama model exposed to the desktop client."""

    name: str
    size_bytes: int | None = None
    family: str | None = None
    parameter_size: str | None = None


class AiHealthStatus(BaseModel):
    """Ollama connectivity and default-model availability."""

    available: bool
    default_model: str
    default_model_available: bool
    message: str


class AiModelsStatus(BaseModel):
    """The locally available models and Ollama availability state."""

    available: bool
    models: list[AiModel]
