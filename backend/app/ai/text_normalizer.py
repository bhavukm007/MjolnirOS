"""Conservative, language-model-independent normalization for typed input."""

from __future__ import annotations

from difflib import SequenceMatcher
import logging
import re
from typing import Iterable, Mapping


logger = logging.getLogger(__name__)


class TextNormalizer:
    """Correct routing-relevant typos while preserving unrestricted prose."""

    DEFAULT_INTENT_TERMS = (
        "open",
        "launch",
        "remember",
        "forget",
        "explain",
        "remind",
        "automate",
        "search",
        "what",
        "whats",
    )
    DEFAULT_CONTEXT_TERMS = {
        "remember": ("birthday",),
    }

    def __init__(
        self,
        aliases: Mapping[str, str] | None = None,
        intent_terms: Iterable[str] | None = None,
        context_terms: Mapping[str, Iterable[str]] | None = None,
    ) -> None:
        configured_aliases = aliases or self._capability_aliases()
        self._aliases = {
            self._compact(alias): canonical.lower()
            for alias, canonical in configured_aliases.items()
        }
        self._known_aliases = {
            self._phrase(alias) for alias in configured_aliases
        }
        self._intent_terms = tuple(intent_terms or self.DEFAULT_INTENT_TERMS)
        configured_context = context_terms or self.DEFAULT_CONTEXT_TERMS
        self._context_terms = {
            intent: tuple(terms) for intent, terms in configured_context.items()
        }

    def normalize(self, text: str) -> str:
        """Normalize only high-confidence terms that influence routing."""
        cleaned = re.sub(r"\s+", " ", text.strip())
        if not cleaned:
            return cleaned
        words = cleaned.split(" ")
        intent = self._closest(words[0].lower().strip(".,!?"), self._intent_terms, 0.72)
        if intent is None:
            return cleaned
        words[0] = intent

        if intent in {"open", "launch"} and len(words) > 1:
            target = " ".join(words[1:]).rstrip(".,!?")
            if self._phrase(target) not in self._known_aliases:
                corrected = self._closest_alias(target)
                if corrected is not None:
                    words[1:] = corrected.split(" ")
        elif intent in self._context_terms:
            candidates = self._context_terms[intent]
            for index in range(1, len(words)):
                token = words[index].lower().strip(".,!?")
                corrected = self._closest(token, candidates, 0.8)
                if corrected is not None:
                    words[index] = corrected

        normalized = " ".join(words)
        if normalized != cleaned:
            logger.info(
                "typed_text_normalized",
                extra={"raw_text": text, "normalized_text": normalized},
            )
        return normalized

    def _closest_alias(self, target: str) -> str | None:
        key = self._compact(target)
        ranked = sorted(
            (
                (SequenceMatcher(None, key, alias).ratio(), canonical)
                for alias, canonical in self._aliases.items()
            ),
            reverse=True,
        )
        if not ranked:
            return None
        score, canonical = ranked[0]
        runner_up = next(
            (value for value, candidate in ranked[1:] if candidate != canonical),
            0.0,
        )
        return canonical if score >= 0.8 and score - runner_up >= 0.08 else None

    @staticmethod
    def _closest(value: str, candidates: Iterable[str], threshold: float) -> str | None:
        ranked = sorted(
            (SequenceMatcher(None, value, candidate).ratio(), candidate)
            for candidate in candidates
        )
        if not ranked:
            return None
        score, candidate = ranked[-1]
        runner_up = ranked[-2][0] if len(ranked) > 1 else 0.0
        return candidate if score >= threshold and score - runner_up >= 0.08 else None

    @staticmethod
    def _compact(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", value.lower())

    @staticmethod
    def _phrase(value: str) -> str:
        return re.sub(r"\s+", " ", value.strip().lower())

    @staticmethod
    def _capability_aliases() -> dict[str, str]:
        from backend.app.browser.website_resolver import WebsiteResolver
        from backend.app.windows.controller import WindowsController

        aliases = {alias: alias for alias in WindowsController._APPLICATION_ALIASES}
        for canonical, (_, website_aliases) in WebsiteResolver.DEFAULT_SITES.items():
            aliases.update({alias: canonical.lower() for alias in website_aliases})
        return aliases
