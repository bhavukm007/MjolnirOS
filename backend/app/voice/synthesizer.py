"""Offline text-to-speech service backed by the operating system's local voices."""

import logging
import threading

from backend.app.core.settings import AppSettings


class SpeechSynthesisUnavailableError(RuntimeError):
    """Raised when local text-to-speech cannot be initialized."""


class SpeechSynthesizer:
    """Speak local assistant replies asynchronously and support interruption."""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._engine: object | None = None
        self._lock = threading.Lock()
        self._speaking = False
        self._logger = logging.getLogger(__name__)

    @property
    def speaking(self) -> bool:
        """Return whether a local utterance is currently active."""
        return self._speaking

    def available(self) -> bool:
        """Return whether the local synthesis dependency can be initialized."""
        try:
            self._get_engine()
        except SpeechSynthesisUnavailableError:
            return False
        return True

    def speak(self, text: str) -> None:
        """Start a non-blocking local utterance, replacing any active utterance."""
        engine = self._get_engine()
        self.stop()
        threading.Thread(target=self._run, args=(engine, text), daemon=True, name="mjolniros-tts").start()

    def stop(self) -> None:
        """Interrupt the current local utterance immediately."""
        with self._lock:
            if self._engine is not None:
                self._engine.stop()
            self._speaking = False
        self._logger.info("voice_speech_interrupted")

    def _run(self, engine: object, text: str) -> None:
        with self._lock:
            self._speaking = True
            try:
                engine.say(text)
                engine.runAndWait()
            except Exception:
                self._logger.exception("voice_speech_failed")
            finally:
                self._speaking = False

    def _get_engine(self) -> object:
        if self._engine is not None:
            return self._engine
        try:
            import pyttsx3

            engine = pyttsx3.init()
            engine.setProperty("rate", self._settings.voice_tts_rate)
            engine.setProperty("volume", self._settings.voice_tts_volume)
        except Exception as error:
            raise SpeechSynthesisUnavailableError("Local text-to-speech is unavailable on this system.") from error
        self._engine = engine
        return engine
