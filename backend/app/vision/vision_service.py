"""Local image OCR, error detection, and lightweight UI recognition."""

from __future__ import annotations

from io import BytesIO
import re

from fastapi import HTTPException
from PIL import Image, ImageGrab, UnidentifiedImageError
import pytesseract
from pytesseract import Output, TesseractNotFoundError

from backend.app.core.settings import AppSettings
from backend.app.domain.vision import (
    BoundingBox,
    RecognizedText,
    UiElement,
    VisionAnalysis,
)

_ERROR_PATTERN = re.compile(
    r"\b(error|exception|failed|failure|fatal|traceback|not found)\b", re.IGNORECASE
)
_BUTTON_PATTERN = re.compile(
    r"^(ok|cancel|close|save|submit|continue|next|back|yes|no|retry|apply)$",
    re.IGNORECASE,
)


class VisionService:
    """Perform private, on-device screenshot understanding through Tesseract OCR."""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        if settings.tesseract_command:
            pytesseract.pytesseract.tesseract_cmd = settings.tesseract_command

    def analyze_upload(self, content: bytes) -> VisionAnalysis:
        """Decode an uploaded image and return OCR and inferred interface elements."""
        try:
            image = Image.open(BytesIO(content)).convert("RGB")
        except UnidentifiedImageError as error:
            raise HTTPException(
                status_code=415, detail="The upload is not a supported image."
            ) from error
        return self.analyze_image(image)

    def capture_and_analyze(self) -> VisionAnalysis:
        """Capture the primary desktop only when the user explicitly invokes this endpoint."""
        try:
            image = ImageGrab.grab(all_screens=False).convert("RGB")
        except OSError as error:
            raise HTTPException(
                status_code=503, detail="Desktop screenshot capture is unavailable."
            ) from error
        return self.analyze_image(image)

    def analyze_image(self, image: Image.Image) -> VisionAnalysis:
        """Extract text, probable buttons, and visible error messages from an image."""
        try:
            data = pytesseract.image_to_data(image, output_type=Output.DICT)
        except TesseractNotFoundError as error:
            raise HTTPException(
                status_code=503,
                detail="OCR is unavailable. Install Tesseract or configure MJOLNIROS_TESSERACT_COMMAND.",
            ) from error

        recognized = self._recognized_text(data)
        full_text = " ".join(item.text for item in recognized)
        ui_elements = [
            UiElement(kind="button", label=item.text, bounds=item.bounds)
            for item in recognized
            if _BUTTON_PATTERN.match(item.text.strip())
        ]
        errors = [
            sentence
            for sentence in self._sentences(full_text)
            if _ERROR_PATTERN.search(sentence)
        ]
        summary = self._summary(full_text, ui_elements, errors)
        return VisionAnalysis(
            width=image.width,
            height=image.height,
            text=full_text,
            recognized_text=recognized,
            ui_elements=ui_elements,
            errors=errors,
            summary=summary,
        )

    @staticmethod
    def _recognized_text(data: dict[str, list[object]]) -> list[RecognizedText]:
        output: list[RecognizedText] = []
        for index, raw_text in enumerate(data["text"]):
            text = str(raw_text).strip()
            confidence = float(data["conf"][index])
            if not text or confidence < 0:
                continue
            output.append(
                RecognizedText(
                    text=text,
                    confidence=confidence,
                    bounds=BoundingBox(
                        left=int(data["left"][index]),
                        top=int(data["top"][index]),
                        width=int(data["width"][index]),
                        height=int(data["height"][index]),
                    ),
                )
            )
        return output

    @staticmethod
    def _sentences(text: str) -> list[str]:
        return [
            item.strip() for item in re.split(r"(?<=[.!?])\s+", text) if item.strip()
        ]

    @staticmethod
    def _summary(text: str, elements: list[UiElement], errors: list[str]) -> str:
        if not text:
            return "No readable text was detected in this image."
        parts = [f"Detected {len(text.split())} words"]
        if elements:
            parts.append(f"{len(elements)} probable button(s)")
        if errors:
            parts.append(f"{len(errors)} possible error message(s)")
        return "; ".join(parts) + "."
