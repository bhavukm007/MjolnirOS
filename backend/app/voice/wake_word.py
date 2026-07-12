"""Wake-word normalization and tolerant matching for Mjolnir."""

import re
from difflib import SequenceMatcher


class WakeWordDetector:
    """Detect the configured wake word and common phonetic renderings."""

    _SIMILAR_PRONUNCIATIONS = ("mjolnir", "meolnir", "meolnear", "me oh near", "me o near", "myolnir")

    def __init__(self, wake_word: str) -> None:
        self._candidates = {self._normalize(wake_word), *map(self._normalize, self._SIMILAR_PRONUNCIATIONS)}

    def detect(self, transcript: str) -> bool:
        """Return whether a transcript contains the wake word or a close pronunciation."""
        words = self._normalize(transcript).split()
        phrases = [" ".join(words[index:index + size]) for size in range(1, min(3, len(words)) + 1) for index in range(len(words))]
        return any(self._matches(phrase) for phrase in phrases)

    def remove(self, transcript: str) -> str:
        """Remove the detected leading wake-word pronunciation from a transcript."""
        words = transcript.strip().split()
        for size in range(min(3, len(words)), 0, -1):
            if self._matches(" ".join(words[:size])):
                return " ".join(words[size:]).strip()
        return transcript.strip()

    def _matches(self, phrase: str) -> bool:
        normalized = self._normalize(phrase).replace(" ", "")
        return any(SequenceMatcher(None, normalized, candidate.replace(" ", "")).ratio() >= 0.78 for candidate in self._candidates)

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"[^a-z0-9 ]+", "", value.lower()).strip()
