"""Offline text-to-speech service backed by the operating system's local voices."""

import subprocess
import threading

from backend.app.core.settings import AppSettings
from backend.app.voice.runtime_logger import logger as voice_logger
from backend.app.voice.runtime_logger import state as log_voice_state


class SpeechSynthesisUnavailableError(RuntimeError):
    """Raised when local text-to-speech cannot be initialized."""


class SpeechInterruptedError(RuntimeError):
    """Raised when an active utterance is deliberately interrupted."""


class SpeechCompletion(threading.Event):
    """Completion signal that preserves an asynchronous synthesis failure."""

    def __init__(self) -> None:
        super().__init__()
        self.error: BaseException | None = None
        self.engine: str | None = None
        self.return_value: int | None = None


class SpeechSynthesizer:
    """Speak local assistant replies asynchronously and support interruption."""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._engine: object | None = None
        self._lock = threading.Lock()
        self._speaking = False
        self._completion = SpeechCompletion()
        self._completion.set()
        self._logger = voice_logger
        self._prefer_powershell = False

    @property
    def speaking(self) -> bool:
        """Return whether a local utterance is currently active."""
        return self._speaking

    def available(self) -> bool:
        """Return whether the local synthesis dependency can be initialized."""
        if self._prefer_powershell:
            return self._powershell_voice_available()
        try:
            import pyttsx3  # noqa: F401
        except ImportError:
            return self._powershell_voice_available()
        return True

    def speak(self, text: str) -> SpeechCompletion:
        """Start a non-blocking local utterance, replacing any active utterance."""
        self._logger.info(
            "voice_tts_synthesizer_entry",
            extra={"payload": {"text": text}, "text_length": len(text)},
        )
        if self._prefer_powershell:
            self._logger.info(
                "voice_tts_engine_selected", extra={"engine": "powershell_system_speech"}
            )
            self.stop()
            completion = self._begin_utterance(text)
            threading.Thread(
                target=self._speak_with_powershell,
                args=(text, completion),
                daemon=True,
                name="mjolniros-tts",
            ).start()
            return completion
        self.stop()
        completion = self._begin_utterance(text)
        threading.Thread(target=self._run_pyttsx3, args=(text, completion), daemon=True, name="mjolniros-tts").start()
        return completion

    def stop(self) -> None:
        """Interrupt the current local utterance immediately."""
        with self._lock:
            if not self._speaking:
                return
            engine = self._engine
            self._speaking = False
            completion = self._completion
            was_active = not completion.is_set()
            if was_active:
                completion.error = SpeechInterruptedError("Speech was interrupted.")
                completion.engine = (
                    "pyttsx3" if engine is not None else "powershell_system_speech"
                )
            completion.set()
        if engine is not None:
            try:
                engine.stop()
            except Exception:
                self._logger.exception("voice_tts_interrupt_failure")
        if was_active:
            log_voice_state("TTS_END", outcome="interrupted")
        self._logger.info("voice_tts_interrupted")

    def _begin_utterance(self, text: str) -> SpeechCompletion:
        with self._lock:
            self._completion = SpeechCompletion()
            self._speaking = True
            log_voice_state("TTS_START", text_length=len(text))
            return self._completion

    def _finish_utterance(
        self,
        completion: SpeechCompletion,
        *,
        outcome: str = "completed",
        error: BaseException | None = None,
        engine: str | None = None,
        return_value: int | None = None,
    ) -> None:
        with self._lock:
            should_log_end = not completion.is_set()
            if self._completion is completion:
                self._speaking = False
            if not completion.is_set() or completion.error is None:
                completion.error = error
                completion.engine = engine
                completion.return_value = return_value
            completion.set()
        if should_log_end:
            log_voice_state("TTS_END", outcome=outcome)

    def _run_pyttsx3(self, text: str, completion: SpeechCompletion) -> None:
        comtypes_module = None
        try:
            import comtypes

            comtypes.CoInitialize()
            comtypes_module = comtypes
            self._run_pyttsx3_initialized(text, completion)
        finally:
            if comtypes_module is not None:
                comtypes_module.CoUninitialize()

    def _run_pyttsx3_initialized(self, text: str, completion: SpeechCompletion) -> None:
        try:
            engine = self._get_engine()
        except SpeechSynthesisUnavailableError as error:
            self._logger.exception("voice_tts_pyttsx3_initialization_failure")
            if self._powershell_voice_available():
                self._prefer_powershell = True
                self._engine = None
                self._speak_with_powershell(text, completion)
            else:
                self._finish_utterance(
                    completion, outcome="failed", error=error, engine="pyttsx3"
                )
            return
        self._logger.info(
            "voice_tts_engine_selected",
            extra={
                "engine": "pyttsx3",
                "implementation": type(engine).__name__,
                "worker_thread": threading.current_thread().name,
                "output_device": "Windows default multimedia render endpoint",
            },
        )
        connect = getattr(engine, "connect", None)
        if callable(connect):
            connect(
                "started-utterance",
                lambda name: self._logger.info(
                    "voice_tts_audio_device_opened",
                    extra={"engine": "pyttsx3", "utterance": name},
                ),
            )
            connect(
                "finished-utterance",
                lambda name, completed: self._logger.info(
                    "voice_tts_completion_callback",
                    extra={"engine": "pyttsx3", "utterance": name, "completed": completed},
                ),
            )
        self._logger.info(
            "voice_tts_pyttsx3_execution",
            extra={"output_device": "Windows default multimedia render endpoint"},
        )
        try:
            self._logger.info("voice_tts_engine_say", extra={"engine": "pyttsx3"})
            engine.say(text)
            self._logger.info("voice_tts_engine_run_and_wait", extra={"engine": "pyttsx3"})
            engine.runAndWait()
        except Exception as error:
            self._logger.exception("voice_tts_failure", extra={"engine": "pyttsx3"})
            if "run loop already started" in str(error).lower() and self._powershell_voice_available():
                # pyttsx3 can leave its shared SAPI loop active after an
                # interrupted utterance. Keep the existing local Windows voice
                # path, but avoid reusing that poisoned loop for this session.
                self._prefer_powershell = True
                self._engine = None
                self._logger.info(
                    "voice_tts_engine_selected",
                    extra={"engine": "powershell_system_speech", "reason": str(error)},
                )
                self._speak_with_powershell(text, completion)
                return
            self._finish_utterance(
                completion, outcome="failed", error=error, engine="pyttsx3"
            )
            if self._engine is engine:
                self._engine = None
            return
        self._logger.info("voice_tts_pyttsx3_return", extra={"return_value": None})
        self._finish_utterance(completion, engine="pyttsx3")
        if self._engine is engine:
            self._engine = None

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

    @staticmethod
    def _powershell_voice_available() -> bool:
        """Probe Windows' built-in System.Speech voice without cloud services."""
        command = [
            "powershell",
            "-NoProfile",
            "-Command",
            "Add-Type -AssemblyName System.Speech; "
            "$voice=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "exit [int]($voice.GetInstalledVoices().Count -eq 0)",
        ]
        voice_logger.info(
            "voice_tts_fallback_probe", extra={"command": command}
        )
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            voice_logger.exception("voice_tts_fallback_probe_failure")
            return False
        voice_logger.info(
            "voice_tts_fallback_probe_return",
            extra={"return_value": completed.returncode},
        )
        return completed.returncode == 0

    def _speak_with_powershell(self, text: str, completion: SpeechCompletion) -> None:
        """Use the same installed SAPI voices through System.Speech as fallback."""
        escaped = text.replace("'", "''")
        command = (
            "Add-Type -AssemblyName System.Speech; "
            "$voice=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$voice.SetOutputToDefaultAudioDevice(); "
            f"$voice.Rate={self._settings.voice_tts_rate - 185}; "
            f"$voice.Volume={int(self._settings.voice_tts_volume * 100)}; "
            f"$voice.Speak('{escaped}')"
        )
        self._logger.info(
            "voice_tts_fallback_execution",
            extra={
                "engine": "powershell_system_speech",
                "output_device": "Windows default multimedia render endpoint",
                "command": ["powershell", "-NoProfile", "-Command", command],
            },
        )
        try:
            completed = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    command,
                ],
                check=True,
                timeout=120,
            )
        except (OSError, subprocess.SubprocessError) as error:
            self._logger.exception("voice_tts_failure", extra={"engine": "powershell"})
            self._finish_utterance(
                completion,
                outcome="failed",
                error=error,
                engine="powershell_system_speech",
                return_value=getattr(error, "returncode", None),
            )
            return
        self._logger.info(
            "voice_tts_fallback_return",
            extra={"return_value": completed.returncode},
        )
        self._finish_utterance(
            completion,
            engine="powershell_system_speech",
            return_value=completed.returncode,
        )
