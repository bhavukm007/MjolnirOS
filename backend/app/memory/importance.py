"""Deterministic importance scoring for local memory candidates."""

from __future__ import annotations

import re

from backend.app.domain.memory import MemoryCategory, MemoryType


class ImportanceScorer:
    """Score durable value without sending private text to another model."""

    _DURABLE_PATTERNS = (
        r"\bmy name is\b",
        r"\bcall me\b",
        r"\bmy favou?rite\b",
        r"\bi prefer\b",
        r"\bi study at\b",
        r"\bmy (?:college|degree|birthday|project)\b",
        r"\bi am working on\b",
        r"\bdeadline\b",
        r"\bremind me\b",
    )

    def score(
        self,
        text: str,
        *,
        explicit: bool = False,
        category: MemoryCategory | None = None,
        memory_type: MemoryType | None = None,
    ) -> float:
        if explicit:
            return 1.0
        normalized = text.lower().strip()
        if category is MemoryCategory.USER_PROFILE:
            return 0.95
        if category is MemoryCategory.TASK:
            return 0.9
        if memory_type is MemoryType.CONVERSATION:
            return 0.25
        if any(re.search(pattern, normalized) for pattern in self._DURABLE_PATTERNS):
            return 0.85
        if any(word in normalized for word in ("always", "never", "important", "remember")):
            return 0.7
        return 0.2

    @staticmethod
    def should_promote(score: float) -> bool:
        return score >= 0.65
