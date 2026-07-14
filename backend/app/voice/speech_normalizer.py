"""Confidence-gated normalization for completed speech-recognition commands."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Mapping

from backend.app.voice.runtime_logger import logger as voice_logger


class SpeechNormalizer:
    """Correct likely STT variants without rewriting free-form user speech."""

    _COMMAND = re.compile(r"^(?P<verb>open|launch|close)\s+(?P<target>.+)$", re.I)
    _MIN_SCORE = 0.81
    _MIN_MARGIN = 0.08

    def __init__(self, aliases: Mapping[str, str] | None = None) -> None:
        configured_aliases = aliases or self._capability_aliases()
        self._known_phrases = {
            self._phrase_key(alias) for alias in configured_aliases if self._phrase_key(alias)
        }
        self._aliases = {
            self._comparison_key(alias): canonical.strip().lower()
            for alias, canonical in configured_aliases.items()
            if self._comparison_key(alias)
        }

    def normalize(self, transcript: str) -> str:
        """Return a conservative correction for one final STT transcript."""
        normalized = re.sub(r"\s+", " ", transcript.strip())
        normalized = re.sub(r"^(?:opened|opening)\s+", "open ", normalized, flags=re.I)
        command = self._COMMAND.fullmatch(normalized)
        if command is None:
            return normalized

        target = command.group("target").strip().rstrip(".,!?")
        if self._phrase_key(target) in self._known_phrases:
            return normalized
        key = self._comparison_key(target)
        exact = self._aliases.get(key)
        if exact is not None:
            corrected = exact
            score = 1.0
        else:
            ranked = sorted(
                (
                    (SequenceMatcher(None, key, alias).ratio(), canonical)
                    for alias, canonical in self._aliases.items()
                ),
                reverse=True,
            )
            if not ranked:
                return normalized
            score, corrected = ranked[0]
            runner_up = next(
                (candidate_score for candidate_score, candidate in ranked[1:] if candidate != corrected),
                0.0,
            )
            if score < self._MIN_SCORE or score - runner_up < self._MIN_MARGIN:
                return normalized

        if corrected == target.lower():
            return normalized
        result = f"{command.group('verb').lower()} {corrected}"
        voice_logger.info(
            "voice_speech_normalized",
            extra={
                "raw_command": transcript,
                "normalized_command": result,
                "matched_target": corrected,
                "confidence": round(score, 3),
            },
        )
        return result

    @staticmethod
    def _comparison_key(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", value.lower())

    @staticmethod
    def _phrase_key(value: str) -> str:
        return re.sub(r"\s+", " ", value.strip().lower())

    @staticmethod
    def _capability_aliases() -> dict[str, str]:
        """Reuse capability-owned vocabularies instead of duplicating them."""
        from backend.app.browser.website_resolver import WebsiteResolver
        from backend.app.windows.controller import WindowsController

        aliases = {
            alias: alias for alias in WindowsController._APPLICATION_ALIASES
        }
        for canonical, (_, website_aliases) in WebsiteResolver.DEFAULT_SITES.items():
            canonical_name = canonical.lower()
            aliases.update({alias: canonical_name for alias in website_aliases})
        aliases["browser"] = "browser"
        return aliases
