"""Wake-word normalization and tolerant matching for Mjolnir."""

import re
from difflib import SequenceMatcher

from backend.app.voice.runtime_logger import logger as voice_logger


class WakeWordDetector:
    """Detect the configured wake word and common phonetic renderings."""

    _SIMILAR_PRONUNCIATIONS = (
        "mjolnir",
        "meonir",
        "me on it",
        "me oh neer",
        "mee oh neer",
        "myolnir",
        "mjolner",
        "mjolnear",
        "meolnir",
        "meolnear",
        "me oh near",
        "me o near",
        "me all near",
        "meal near",
        "mill near",
        "hello meonir",
        "hello me on it",
        "hey meonir",
        "hey me on it",
        "hi meonir",
        "hi me on it",
        "wake up mjolnir",
        "wake up meonir",
        "wake up me on it",
    )

    _VOSK_NORMALIZATIONS = (
        (r"\bme on it\b", "meonir"),
        (r"\bme on in\b", "meonir"),
        (r"\bme on ear\b", "meonir"),
        (r"\bme oh near\b", "meonir"),
        (r"\bme oh neer\b", "meonir"),
        (r"\b(?:me all near|meal near|mill near)\b", "meonir"),
        # Variants observed from the configured small English Vosk model with
        # live microphone input.  Keep single-word substitutions gated by a
        # greeting to avoid waking on ordinary mentions of those words.
        (r"\b(hello|hey|hi) (?:my )?(?:mounted|million|millionaire|millenium)\b", r"\1 meonir"),
        (r"\b(hello|hey|hi) known it\b", r"\1 meonir"),
        (r"\b(?:milan it|milan in|male on it|million it)\b", "meonir"),
    )

    def __init__(self, wake_word: str) -> None:
        self._candidates = {self._normalize(wake_word), *map(self._normalize, self._SIMILAR_PRONUNCIATIONS)}

    @property
    def grammar_phrases(self) -> list[str]:
        """Return vocabulary-safe phrases for Vosk's parallel wake recognizer."""
        return sorted({
            "me on it",
            "me oh near",
            "me all near",
            "hello me on it",
            "hey me on it",
            "wake up me on it",
            "hello me oh near",
            "hey me oh near",
            "wake up me oh near",
        })

    def detect(self, transcript: str) -> bool:
        """Return whether a transcript contains the wake word or a close pronunciation."""
        normalized = self._normalize(transcript)
        voice_logger.debug(
            "voice_wake_normalized",
            extra={"transcript": transcript, "normalized": normalized},
        )
        words = normalized.split()
        # A wake word is only valid at the beginning of an utterance. Searching
        # every interior n-gram caused ordinary speech to wake the assistant.
        phrases = [" ".join(words[:size]) for size in range(1, min(5, len(words)) + 1)]
        best_phrase = ""
        best_candidate = ""
        best_score = 0.0
        for phrase in phrases:
            normalized_phrase = phrase.replace(" ", "")
            for candidate in self._candidates:
                score = SequenceMatcher(
                    None, normalized_phrase, candidate.replace(" ", "")
                ).ratio()
                if score > best_score:
                    best_phrase = phrase
                    best_candidate = candidate
                    best_score = score
        detected = best_score >= 0.82
        (voice_logger.info if detected else voice_logger.debug)(
            "voice_wake_matcher",
            extra={
                "normalized": normalized,
                "matched": detected,
                "best_phrase": best_phrase,
                "best_candidate": best_candidate,
                "best_score": best_score,
            },
        )
        return detected

    def remove(self, transcript: str) -> str:
        """Remove the detected leading wake-word pronunciation from a transcript."""
        words = transcript.strip().split()
        # Prefer an exact normalized pronunciation prefix before fuzzy matching;
        # this preserves every trailing inline command word.
        for size in range(1, min(5, len(words)) + 1):
            normalized = self._normalize(" ".join(words[:size]))
            if normalized in self._candidates:
                return " ".join(words[size:]).strip()
        for size in range(1, min(5, len(words)) + 1):
            if self._matches(" ".join(words[:size])):
                return " ".join(words[size:]).strip()
        # Vosk can split the greeting form into an extra phonetic word, such as
        # "hello me any ear".  Keep the fuzzy wake detector authoritative and
        # consume that greeting prefix before handing the remainder to commands.
        if words and self._normalize(words[0]) == "hello":
            for size in range(min(4, len(words)), 1, -1):
                if self._matches(" ".join(words[1:size])):
                    return " ".join(words[size:]).strip()
        return transcript.strip()

    def extract(self, transcript: str) -> tuple[bool, str]:
        """Return detection and any inline command following a leading wake phrase."""
        detected = self.detect(transcript)
        return detected, self.remove(transcript) if detected else transcript.strip()

    def align_correlated_transcript(self, transcript: str) -> str | None:
        """Align a full transcript after a constrained wake recognizer confirms it.

        Vosk occasionally prefixes short wake audio with one or two filler words
        (for example, "I got me on it open Chrome"). This relaxed alignment is
        never used without independent constrained-wake confirmation.
        """
        words = transcript.strip().split()
        for offset in range(min(3, len(words))):
            candidate = " ".join(words[offset:])
            if self.detect(candidate):
                return candidate
        return None

    def _matches(self, phrase: str) -> bool:
        normalized = self._normalize(phrase).replace(" ", "")
        return any(SequenceMatcher(None, normalized, candidate.replace(" ", "")).ratio() >= 0.82 for candidate in self._candidates)

    @staticmethod
    def _normalize(value: str) -> str:
        normalized = re.sub(r"[^a-z0-9 ]+", "", value.lower()).strip()
        for pattern, replacement in WakeWordDetector._VOSK_NORMALIZATIONS:
            normalized = re.sub(pattern, replacement, normalized)
        return re.sub(r"\s+", " ", normalized).strip()
