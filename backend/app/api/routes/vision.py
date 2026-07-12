"""REST endpoints for the Phase 10 vision and document agent."""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, File, HTTPException, UploadFile

from backend.app.core.responses import ApiResponse
from backend.app.core.settings import get_settings
from backend.app.domain.vision import (
    DocumentRecord,
    DocumentSummary,
    QuestionAnswer,
    QuestionRequest,
    TranslationRequest,
    TranslationResult,
    VisionAnalysis,
)
from backend.app.vision.document_service import DocumentService
from backend.app.vision.vision_service import VisionService

router = APIRouter(tags=["vision", "documents"])
logger = logging.getLogger(__name__)


def _documents() -> DocumentService:
    return DocumentService(get_settings())


@router.post("/vision/analyze", response_model=ApiResponse[VisionAnalysis])
async def analyze_image(file: UploadFile = File(...)) -> ApiResponse[VisionAnalysis]:
    """Run local OCR, UI recognition, and error detection on an uploaded screenshot."""
    settings = get_settings()
    content = await file.read(settings.vision_max_upload_bytes + 1)
    if len(content) > settings.vision_max_upload_bytes:
        raise HTTPException(
            status_code=413, detail="Image exceeds the upload size limit."
        )
    analysis = VisionService(settings).analyze_upload(content)
    return ApiResponse(
        success=True, message="Screenshot analyzed locally.", data=analysis
    )


@router.post("/vision/capture", response_model=ApiResponse[VisionAnalysis])
async def capture_desktop() -> ApiResponse[VisionAnalysis]:
    """Capture and analyze the current desktop after an explicit user request."""
    analysis = VisionService(get_settings()).capture_and_analyze()
    return ApiResponse(
        success=True, message="Desktop captured and analyzed locally.", data=analysis
    )


@router.post("/documents", response_model=ApiResponse[DocumentRecord])
async def upload_document(file: UploadFile = File(...)) -> ApiResponse[DocumentRecord]:
    """Persist a document locally and extract its readable content and tables."""
    record = await _documents().upload(file)
    logger.info(
        "document_uploaded",
        extra={"document_id": record.id, "document_type": record.document_type},
    )
    return ApiResponse(success=True, message="Document processed locally.", data=record)


@router.get("/documents", response_model=ApiResponse[list[DocumentRecord]])
async def list_documents() -> ApiResponse[list[DocumentRecord]]:
    """List locally processed documents."""
    return ApiResponse(
        success=True, message="Documents loaded.", data=_documents().list()
    )


@router.get("/documents/{document_id}", response_model=ApiResponse[DocumentRecord])
async def get_document(document_id: str) -> ApiResponse[DocumentRecord]:
    """Return extracted content and formatting metadata for one document."""
    return ApiResponse(
        success=True, message="Document loaded.", data=_documents().get(document_id)
    )


@router.get(
    "/documents/{document_id}/tables", response_model=ApiResponse[list[list[list[str]]]]
)
async def extract_tables(document_id: str) -> ApiResponse[list[list[list[str]]]]:
    """Return extracted document tables while preserving their row and column structure."""
    return ApiResponse(
        success=True,
        message="Document tables extracted.",
        data=_documents().get(document_id).tables,
    )


@router.post(
    "/documents/{document_id}/summarize", response_model=ApiResponse[DocumentSummary]
)
async def summarize_document(document_id: str) -> ApiResponse[DocumentSummary]:
    """Summarize a document with an offline extractive algorithm."""
    service = _documents()
    return ApiResponse(
        success=True,
        message="Document summarized locally.",
        data=service.summarize(service.get(document_id)),
    )


@router.post(
    "/documents/{document_id}/questions", response_model=ApiResponse[QuestionAnswer]
)
async def answer_question(
    document_id: str, request: QuestionRequest
) -> ApiResponse[QuestionAnswer]:
    """Answer a question using document passages selected locally."""
    service = _documents()
    return ApiResponse(
        success=True,
        message="Question answered from extracted text.",
        data=service.answer(service.get(document_id), request.question),
    )


@router.post(
    "/documents/{document_id}/translate", response_model=ApiResponse[TranslationResult]
)
async def translate_document(
    document_id: str, request: TranslationRequest
) -> ApiResponse[TranslationResult]:
    """Translate via the configured local Ollama instance without sending document data to the cloud."""
    record = _documents().get(document_id)
    settings = get_settings()
    prompt = (
        f"Translate the following document into {request.target_language}. Preserve headings, lists, and tables. "
        "Return only the translation.\n\n" + record.text
    )
    try:
        async with httpx.AsyncClient(
            base_url=settings.ollama_url, timeout=120.0
        ) as client:
            response = await client.post(
                "/api/generate",
                json={
                    "model": settings.default_model,
                    "prompt": prompt,
                    "stream": False,
                },
            )
            response.raise_for_status()
            translation = response.json().get("response", "").strip()
    except httpx.HTTPError as error:
        logger.warning(
            "local_translation_unavailable", extra={"document_id": document_id}
        )
        raise HTTPException(
            status_code=503, detail="Local Ollama translation is unavailable."
        ) from error
    return ApiResponse(
        success=True,
        message="Document translated with the local model.",
        data=TranslationResult(
            target_language=request.target_language, translation=translation
        ),
    )
