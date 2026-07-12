"""Offline Vosk speech recognition sessions for desktop microphone audio."""

import base64
import json
import logging
from pathlib import Path
from uuid import uuid4

from backend.app.core.settings import AppSettings
from backend.app.domain.voice import RecognitionResult, VoiceSession, VoiceState
from backend.app.voice.wake_word import WakeWordDetector


class VoiceUnavailableError(RuntimeError):
    """Raised when offline speech recognition is not configured or unavailable."""


class VoskRecognitionSession:
    """Manage one Vosk stream and its wake-word conversation state."""

    def __init__(self, recognizer: object, wake_word_detector: WakeWordDetector) -> None:
        self._recognizer = recognizer
        self._wake_word_detector = wake_word_detector
        self._state = VoiceState.LISTENING_FOR_WAKE_WORD

    def accept_audio(self, audio: bytes) -> RecognitionResult:
        """Process PCM audio and return a completed wake-word or command event."""
        if not self._recognizer.AcceptWaveform(audio):
            return RecognitionResult(state=self._state)
        return self._process_transcript(_extract_text(self._recognizer.Result()))

    def finish(self) -> RecognitionResult:
        """Flush the recognizer when microphone capture ends."""
        return self._process_transcript(_extract_text(self._recognizer.FinalResult()))

    def _process_transcript(self, transcript: str) -> RecognitionResult:
        if not transcript:
            return RecognitionResult(state=self._state)
        if self._state is VoiceState.LISTENING_FOR_WAKE_WORD:
            if not self._wake_word_detector.detect(transcript):
                return RecognitionResult(state=self._state, transcript=transcript)
            command = self._wake_word_detector.remove(transcript)
            self._state = VoiceState.LISTENING_FOR_COMMAND
            if command:
                self._state = VoiceState.LISTENING_FOR_WAKE_WORD
            return RecognitionResult(state=self._state, transcript=transcript, wake_word_detected=True, command=command or None)
        self._state = VoiceState.LISTENING_FOR_WAKE_WORD
        return RecognitionResult(state=self._state, transcript=transcript, command=transcript)


class VoiceRecognitionService:
    """Create and coordinate low-overhead offline Vosk recognition sessions."""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._sessions: dict[str, VoskRecognitionSession] = {}
        self._logger = logging.getLogger(__name__)
        self._model: object | None = None

    def health_message(self) -> str | None:
        """Return an actionable error when recognition cannot be started."""
        if not self._settings.voice_enabled:
            return "Voice interaction is disabled by configuration."
        if not self._settings.voice_model_path.is_dir():
            return f"Offline Vosk model not found at {self._settings.voice_model_path}."
        try:
            self._load_vosk()
        except VoiceUnavailableError as error:
            return str(error)
        return None

    def create_session(self) -> VoiceSession:
        """Create a recognition session that begins in wake-word mode."""
        error = self.health_message()
        if error:
            raise VoiceUnavailableError(error)
        vosk = self._load_vosk()
        recognizer = vosk.KaldiRecognizer(self._model, self._settings.voice_sample_rate)
        recognizer.SetWords(False)
        session_id = str(uuid4())
        self._sessions[session_id] = VoskRecognitionSession(recognizer, WakeWordDetector(self._settings.voice_wake_word))
        self._logger.info("voice_session_started", extra={"session_id": session_id})
        return VoiceSession(session_id=session_id, state=VoiceState.LISTENING_FOR_WAKE_WORD)

    def accept_audio(self, session_id: str, audio_base64: str) -> RecognitionResult:
        """Decode and process one signed 16-bit PCM microphone chunk."""
        session = self._get_session(session_id)
        try:
            audio = base64.b64decode(audio_base64, validate=True)
        except ValueError as error:
            raise ValueError("Audio must be valid base64 PCM data.") from error
        result = session.accept_audio(audio)
        if result.wake_word_detected:
            self._logger.info("voice_wake_word_detected", extra={"session_id": session_id})
        if result.command:
            self._logger.info("voice_command_recognized", extra={"session_id": session_id, "length": len(result.command)})
        return result

    def close_session(self, session_id: str) -> RecognitionResult:
        """Flush and discard a listening session."""
        session = self._sessions.pop(session_id, None)
        if session is None:
            raise KeyError(session_id)
        result = session.finish()
        self._logger.info("voice_session_stopped", extra={"session_id": session_id})
        return result

    def _get_session(self, session_id: str) -> VoskRecognitionSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(session_id)
        return session

    def _load_vosk(self) -> object:
        if self._model is not None:
            return _import_vosk()
        vosk = _import_vosk()
        try:
            self._model = vosk.Model(str(Path(self._settings.voice_model_path)))
        except Exception as error:
            raise VoiceUnavailableError("Unable to load the configured offline Vosk model.") from error
        return vosk


def _import_vosk() -> object:
    try:
        import vosk
    except ImportError as error:
        raise VoiceUnavailableError("Vosk is not installed. Install the backend dependencies to enable voice recognition.") from error
    return vosk


def _extract_text(result: str) -> str:
    try:
        payload = json.loads(result)
    except json.JSONDecodeError:
        return ""
    text = payload.get("text", "")
    return text.strip() if isinstance(text, str) else ""
