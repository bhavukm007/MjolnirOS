"""Public models for the local vision and document agent."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class DocumentType(StrEnum):
    """Document formats supported by the document agent."""

    PDF = "pdf"
    DOCX = "docx"
    XLSX = "xlsx"
    PPTX = "pptx"
    TEXT = "text"
    MARKDOWN = "markdown"


class BoundingBox(BaseModel):
    """A rectangular region in image pixels."""

    left: int
    top: int
    width: int
    height: int


class RecognizedText(BaseModel):
    """OCR text together with its source position and confidence."""

    text: str
    confidence: float
    bounds: BoundingBox


class UiElement(BaseModel):
    """A visible desktop element inferred from a screenshot."""

    kind: str
    label: str
    bounds: BoundingBox


class VisionAnalysis(BaseModel):
    """Local OCR and UI understanding result for an image."""

    width: int
    height: int
    text: str
    recognized_text: list[RecognizedText]
    ui_elements: list[UiElement]
    errors: list[str]
    summary: str


class DocumentRecord(BaseModel):
    """Persisted metadata and extracted content for an uploaded document."""

    id: str
    filename: str
    document_type: DocumentType
    size_bytes: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    text: str
    page_count: int | None = None
    sheet_names: list[str] = Field(default_factory=list)
    tables: list[list[list[str]]] = Field(default_factory=list)


class DocumentSummary(BaseModel):
    """An extractive, local summary of a document."""

    summary: str
    character_count: int
    table_count: int


class TranslationRequest(BaseModel):
    """Requested target language for local-model translation."""

    target_language: str = Field(min_length=2, max_length=64)


class TranslationResult(BaseModel):
    """Translation returned by the configured local Ollama model."""

    target_language: str
    translation: str


class QuestionRequest(BaseModel):
    """Question asked over an uploaded document."""

    question: str = Field(min_length=1, max_length=1000)


class QuestionAnswer(BaseModel):
    """Extractive answer and supporting source passages."""

    answer: str
    sources: list[str]
