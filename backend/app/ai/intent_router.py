"""Deterministic first-pass intent classification for local routing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from backend.app.voice.wake_word import WakeWordDetector


class Intent(StrEnum):
    GREETING = "greeting"
    GENERAL_CHAT = "general_chat"
    QUESTION = "question"
    APPLICATION_LAUNCH = "application_launch"
    SYSTEM_COMMAND = "system_command"
    AUTOMATION = "automation"
    SEARCH = "search"
    MEMORY_QUERY = "memory_query"
    MEMORY_WRITE = "memory_write"
    MEMORY_FORGET = "memory_forget"
    REMINDER = "reminder"
    PRODUCTIVITY = "productivity"


@dataclass(frozen=True)
class RoutedIntent:
    intent: Intent
    message: str
    confidence: float


class IntentRouter:
    """Prefer deterministic local capabilities before invoking a planner or LLM."""

    _GREETINGS = {
        "hi",
        "hello",
        "hey",
        "what's up",
        "whats up",
        "good morning",
        "good afternoon",
        "good evening",
    }
    _MEMORY_QUERIES = (
        r"what(?:'s| is) my name",
        r"who am i",
        r"what do you know about me",
        r"what projects? am i working on",
        r"what are my preferences",
        r"what(?:'s| is) my favou?rite",
    )

    def __init__(self, wake_word: str = "Mjolnir") -> None:
        self._wake = WakeWordDetector(wake_word)

    def classify(self, message: str) -> RoutedIntent:
        _, stripped = self._wake.extract(message)
        cleaned = (stripped or message).strip()
        normalized = cleaned.lower().strip().rstrip(".?!")
        if normalized.startswith("forget "):
            return RoutedIntent(Intent.MEMORY_FORGET, cleaned, 1.0)
        if normalized.startswith("remember ") or re.match(
            r"^(?:my name is|call me|update my name to|my nickname is|my college is|my degree is|my favou?rite|i prefer|i am working on)",
            normalized,
        ):
            return RoutedIntent(Intent.MEMORY_WRITE, cleaned, 0.99)
        if any(re.match(pattern, normalized) for pattern in self._MEMORY_QUERIES):
            return RoutedIntent(Intent.MEMORY_QUERY, cleaned, 0.99)
        if normalized.startswith("remind me") or normalized.startswith("add a todo"):
            return RoutedIntent(Intent.REMINDER, cleaned, 0.99)
        if normalized in self._GREETINGS:
            return RoutedIntent(Intent.GREETING, cleaned, 0.99)
        if normalized.startswith("open ") and not normalized.endswith(" folder"):
            return RoutedIntent(Intent.APPLICATION_LAUNCH, cleaned, 0.98)
        if re.match(r"^(?:close|focus|switch to|lock|take a screenshot|open task manager|open explorer)\b", normalized):
            return RoutedIntent(Intent.SYSTEM_COMMAND, cleaned, 0.96)
        if re.match(r"^(?:search|look up|find online|google)\b", normalized):
            return RoutedIntent(Intent.SEARCH, cleaned, 0.92)
        if any(word in normalized for word in ("workflow", "routine", "automate")):
            return RoutedIntent(Intent.AUTOMATION, cleaned, 0.88)
        if any(word in normalized for word in ("calendar", "email", "notion", "task list")):
            return RoutedIntent(Intent.PRODUCTIVITY, cleaned, 0.82)
        if re.match(r"^(?:who|what|when|where|why|how|can|could|should|is|are|do|does)\b", normalized):
            return RoutedIntent(Intent.QUESTION, cleaned, 0.8)
        return RoutedIntent(Intent.GENERAL_CHAT, cleaned, 0.65)
