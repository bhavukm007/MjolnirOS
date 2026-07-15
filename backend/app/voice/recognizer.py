"""Offline Vosk speech recognition sessions for desktop microphone audio."""

import base64
import json
import logging
import re
from pathlib import Path
from time import monotonic
from uuid import uuid4

from backend.app.core.settings import AppSettings
from backend.app.domain.voice import RecognitionResult, VoiceSession, VoiceState
from backend.app.voice.wake_word import WakeWordDetector
from backend.app.voice.runtime_logger import logger as voice_logger
from backend.app.voice.runtime_logger import state as log_voice_state
from backend.app.voice.speech_normalizer import SpeechNormalizer


class VoiceUnavailableError(RuntimeError):
    """Raised when offline speech recognition is not configured or unavailable."""


class VoskRecognitionSession:
    """Manage one Vosk stream and its wake-word conversation state."""

    def __init__(
        self,
        recognizer: object,
        wake_word_detector: WakeWordDetector,
        command_timeout_seconds: float = 10.0,
        wake_recognizer: object | None = None,
        speech_normalizer: SpeechNormalizer | None = None,
        wake_cooldown_seconds: float = 1.0,
    ) -> None:
        self._recognizer = recognizer
        self._wake_word_detector = wake_word_detector
        self._wake_recognizer = wake_recognizer
        self._speech_normalizer = speech_normalizer or SpeechNormalizer()
        self._pending_wake_transcript = ""
        self._state = VoiceState.LISTENING_FOR_WAKE_WORD
        self._packet_count = 0
        self._last_partial = ""
        self._command_timeout_seconds = command_timeout_seconds
        self._command_deadline: float | None = None
        self._wake_cooldown_seconds = wake_cooldown_seconds
        self._wake_cooldown_until = 0.0

    def accept_audio(self, audio: bytes) -> RecognitionResult:
        """Process PCM audio and return a completed wake-word or command event."""
        self._packet_count += 1
        if self._packet_count == 1:
            voice_logger.info(
                "voice_microphone_pcm_stream_active",
                extra={"bytes": len(audio), "state": self._state.value},
            )
        voice_logger.debug(
            "voice_recognizer_pcm_received",
            extra={
                "bytes": len(audio),
                "packet": self._packet_count,
                "state": self._state.value,
            },
        )
        if self._state is VoiceState.PROCESSING_COMMAND:
            return RecognitionResult(state=self._state)
        if (
            self._state is VoiceState.LISTENING_FOR_WAKE_WORD
            and monotonic() < self._wake_cooldown_until
        ):
            return RecognitionResult(state=self._state)
        if self._command_timed_out():
            log_voice_state("FOLLOW_UP_WINDOW_END", reason="timeout")
            voice_logger.info("voice_follow_up_timeout")
            self._state = VoiceState.LISTENING_FOR_WAKE_WORD
            self._last_partial = ""
            self._command_deadline = None
            self._reset_recognizer()
            self._wake_cooldown_until = monotonic() + self._wake_cooldown_seconds
            log_voice_state("RETURN_TO_WAKE")
            log_voice_state("WAITING_FOR_WAKE")
            return RecognitionResult(state=self._state)
        if (
            self._state is VoiceState.LISTENING_FOR_COMMAND
            and self._command_deadline is None
        ):
            self._command_deadline = monotonic() + self._command_timeout_seconds
        if self._state is VoiceState.LISTENING_FOR_WAKE_WORD:
            # The unrestricted command recognizer must never receive idle
            # audio. Production sessions use the constrained wake recognizer;
            # the fallback keeps isolated tests and degraded runtimes usable.
            wake_recognizer = self._wake_recognizer or self._recognizer
            if not wake_recognizer.AcceptWaveform(audio):
                return RecognitionResult(state=self._state)
            wake_transcript = _without_unknown(
                _extract_text(wake_recognizer.Result())
            )
            voice_logger.debug(
                "voice_vosk_final",
                extra={"text": wake_transcript, "state": self._state.value},
            )
            return self._process_transcript(wake_transcript)

        if not self._recognizer.AcceptWaveform(audio):
            partial = _extract_partial(self._recognizer.PartialResult())
            if partial:
                self._command_deadline = monotonic() + self._command_timeout_seconds
            if partial and partial != self._last_partial:
                self._last_partial = partial
                voice_logger.debug(
                    "voice_vosk_partial",
                    extra={"text": partial, "state": self._state.value},
                )
            return RecognitionResult(state=self._state)
        transcript = _extract_text(self._recognizer.Result())
        voice_logger.debug(
            "voice_vosk_final",
            extra={"text": transcript, "state": self._state.value},
        )
        return self._process_transcript(transcript)

    def finish(self) -> RecognitionResult:
        """Flush the recognizer when microphone capture ends."""
        if self._state is VoiceState.LISTENING_FOR_WAKE_WORD:
            return RecognitionResult(state=self._state)
        return self._process_transcript(_extract_text(self._recognizer.FinalResult()))

    def _process_transcript(self, transcript: str) -> RecognitionResult:
        if not transcript:
            return RecognitionResult(state=self._state)
        voice_logger.debug(
            "voice_recognizer_final",
            extra={"state": self._state.value, "transcript": transcript},
        )
        if self._state is VoiceState.LISTENING_FOR_WAKE_WORD:
            detected = self._wake_word_detector.detect(transcript)
            voice_logger.debug(
                "voice_wake_word_checked",
                extra={"transcript": transcript, "detected": detected},
            )
            if not detected:
                return RecognitionResult(state=self._state)
            self._state = VoiceState.LISTENING_FOR_COMMAND
            self._last_partial = ""
            self._pending_wake_transcript = ""
            self._command_deadline = None
            self._reset_recognizer()
            log_voice_state("WAKE_DETECTED", transcript=transcript)
            voice_logger.info(
                "voice_wake_transition",
                extra={
                    "from_state": "WAITING_FOR_WAKE",
                    "to_state": "LISTENING_FOR_COMMAND",
                    "source": "final",
                },
            )
            log_voice_state("LISTENING_FOR_COMMAND")
            return RecognitionResult(
                state=self._state,
                wake_word_detected=True,
            )
        raw_transcript = transcript
        transcript = self._speech_normalizer.normalize(transcript)
        if transcript != raw_transcript:
            voice_logger.info(
                "voice_command_stt_corrected",
                extra={
                    "raw_command": raw_transcript,
                    "corrected_command": transcript,
                },
            )
        self._state = VoiceState.PROCESSING_COMMAND
        self._command_deadline = None
        voice_logger.info("voice_vosk_final_command", extra={"text": transcript})
        voice_logger.info(
            "voice_command_recognized", extra={"command_length": len(transcript)}
        )
        log_voice_state("PROCESSING")
        return RecognitionResult(state=self._state, transcript=transcript, command=transcript)

    def _reset_recognizer(self) -> None:
        """Clear wake-utterance audio before command recognition begins."""
        reset = getattr(self._recognizer, "Reset", None)
        if callable(reset):
            reset()
            voice_logger.debug("voice_recognizer_reset")
        wake_reset = getattr(self._wake_recognizer, "Reset", None)
        if callable(wake_reset):
            wake_reset()
            voice_logger.debug("voice_wake_recognizer_reset")

    def complete_command(self) -> RecognitionResult:
        """Return to wake-word listening after the command pipeline finishes."""
        if self._state is not VoiceState.PROCESSING_COMMAND:
            raise ValueError("The voice session has no command in progress.")
        self._state = VoiceState.LISTENING_FOR_WAKE_WORD
        self._last_partial = ""
        self._pending_wake_transcript = ""
        self._command_deadline = None
        self._reset_recognizer()
        self._wake_cooldown_until = monotonic() + self._wake_cooldown_seconds
        log_voice_state("RETURN_TO_WAKE")
        log_voice_state("WAITING_FOR_WAKE")
        return RecognitionResult(state=self._state)

    def _command_timed_out(self) -> bool:
        return (
            self._state is VoiceState.LISTENING_FOR_COMMAND
            and self._command_deadline is not None
            and monotonic() >= self._command_deadline
        )


class VoiceRecognitionService:
    """Create and coordinate low-overhead offline Vosk recognition sessions."""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._sessions: dict[str, VoskRecognitionSession] = {}
        self._logger = voice_logger
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
        # Word timing/confidence metadata improves runtime diagnostics without
        # constraining the open command vocabulary.
        recognizer.SetWords(True)
        detector = WakeWordDetector(self._settings.voice_wake_word)
        wake_grammar = [*detector.grammar_phrases, "[unk]"]
        wake_recognizer = vosk.KaldiRecognizer(
            self._model,
            self._settings.voice_sample_rate,
            json.dumps(wake_grammar),
        )
        wake_recognizer.SetWords(False)
        self._logger.debug(
            "voice_recognizer_initialized",
            extra={"sample_rate": self._settings.voice_sample_rate},
        )
        session_id = str(uuid4())
        self._sessions[session_id] = VoskRecognitionSession(
            recognizer,
            detector,
            self._settings.voice_command_timeout_seconds,
            wake_recognizer,
        )
        self._logger.info("voice_session_created", extra={"session_id": session_id})
        log_voice_state("WAITING_FOR_WAKE", session_id=session_id)
        return VoiceSession(session_id=session_id, state=VoiceState.LISTENING_FOR_WAKE_WORD)

    def accept_audio(self, session_id: str, audio_base64: str) -> RecognitionResult:
        """Decode and process one signed 16-bit PCM microphone chunk."""
        session = self._get_session(session_id)
        try:
            audio = base64.b64decode(audio_base64, validate=True)
        except ValueError as error:
            raise ValueError("Audio must be valid base64 PCM data.") from error
        if self._logger.isEnabledFor(logging.DEBUG):
            self._logger.debug(
                "voice_audio_packet_received",
                extra={
                    "session_id": session_id,
                    "bytes": len(audio),
                    "packets": session._packet_count + 1,
                },
            )
        try:
            result = session.accept_audio(audio)
        except Exception:
            self._logger.exception(
                "voice_recognizer_failure", extra={"session_id": session_id}
            )
            raise
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
        self._logger.info("voice_session_destroyed", extra={"session_id": session_id})
        return result

    def complete_command(self, session_id: str) -> RecognitionResult:
        """Release a processed command back to follow-up command listening."""
        return self._get_session(session_id).complete_command()

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


def _extract_partial(result: str) -> str:
    try:
        payload = json.loads(result)
    except json.JSONDecodeError:
        return ""
    text = payload.get("partial", "")
    return text.strip() if isinstance(text, str) else ""


def _without_unknown(transcript: str) -> str:
    return transcript.replace("[unk]", " ").strip()
