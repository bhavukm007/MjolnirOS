import base64
import logging
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.app.domain.voice import VoiceState
from backend.app.voice.recognizer import VoiceRecognitionService, VoskRecognitionSession
from backend.app.voice.runtime_logger import logger as voice_logger
from backend.app.voice.synthesizer import SpeechSynthesizer
from backend.app.voice.wake_word import WakeWordDetector


class FakeRecognizer:
    pass


class PartialWakeRecognizer:
    def __init__(self) -> None:
        self.reset = False

    def AcceptWaveform(self, _audio: bytes) -> bool:
        return False

    def PartialResult(self) -> str:
        return '{"partial":"hello me on it"}'

    def Reset(self) -> None:
        self.reset = True


class FinalWakeRecognizer:
    def __init__(self) -> None:
        self.reset = False

    def AcceptWaveform(self, _audio: bytes) -> bool:
        return True

    def Result(self) -> str:
        return '{"text":"hello mounted"}'

    def Reset(self) -> None:
        self.reset = True


class SilentRecognizer:
    def AcceptWaveform(self, _audio: bytes) -> bool:
        return False

    def PartialResult(self) -> str:
        return '{"partial":""}'

    def Reset(self) -> None:
        pass


class ConstrainedWakeRecognizer:
    def __init__(self) -> None:
        self.reset = False

    def AcceptWaveform(self, _audio: bytes) -> bool:
        return True

    def Result(self) -> str:
        return '{"text":"me on it"}'

    def Reset(self) -> None:
        self.reset = True


class DelayedFinalRecognizer(SilentRecognizer):
    def __init__(self) -> None:
        self.calls = 0

    def AcceptWaveform(self, _audio: bytes) -> bool:
        self.calls += 1
        return self.calls > 1

    def Result(self) -> str:
        return '{"text":""}'


class CountingRecognizer:
    def __init__(self) -> None:
        self.reset_count = 0

    def Reset(self) -> None:
        self.reset_count += 1


def test_command_stays_processing_until_pipeline_completes() -> None:
    session = VoskRecognitionSession(FakeRecognizer(), WakeWordDetector("Mjolnir"))

    wake = session._process_transcript("hello me on it")
    command = session._process_transcript("open chrome")

    assert wake.state is VoiceState.LISTENING_FOR_COMMAND
    assert command.state is VoiceState.PROCESSING_COMMAND
    assert command.command == "open chrome"
    assert session.complete_command().state is VoiceState.LISTENING_FOR_WAKE_WORD


def test_processing_session_rejects_early_completion() -> None:
    session = VoskRecognitionSession(FakeRecognizer(), WakeWordDetector("Mjolnir"))

    with pytest.raises(ValueError):
        session.complete_command()


def test_partial_wake_waits_for_final_hypothesis_to_preserve_inline_command() -> None:
    recognizer = PartialWakeRecognizer()
    session = VoskRecognitionSession(recognizer, WakeWordDetector("Mjolnir"))

    result = session.accept_audio(b"live microphone frame")

    assert not result.wake_word_detected
    assert result.command is None
    assert result.state is VoiceState.LISTENING_FOR_WAKE_WORD
    assert not recognizer.reset


def test_constrained_recognizer_recovers_short_standalone_wake_word() -> None:
    full = DelayedFinalRecognizer()
    wake = ConstrainedWakeRecognizer()
    session = VoskRecognitionSession(
        full,
        WakeWordDetector("Mjolnir"),
        wake_recognizer=wake,
    )

    pending = session.accept_audio(b"short wake PCM")
    result = session.accept_audio(b"trailing silence")

    assert not pending.wake_word_detected
    assert result.wake_word_detected
    assert result.state is VoiceState.LISTENING_FOR_COMMAND
    assert result.transcript == "me on it"
    assert wake.reset


@pytest.mark.parametrize(
    "transcript",
    (
        "mjolnir",
        "meonir",
        "me on it",
        "hello meonir",
        "hey meonir",
        "wake up meonir",
        "hi meonir",
        "hello mounted",
        "hey millionaire",
        "hello milan it",
        "milan it",
        "milan in",
        "male on it",
        "million it",
    ),
)
def test_common_vosk_wake_variants_are_detected(transcript: str) -> None:
    result = VoskRecognitionSession(
        FakeRecognizer(), WakeWordDetector("Mjolnir")
    )._process_transcript(transcript)

    assert result.wake_word_detected
    assert result.command is None
    assert result.state is VoiceState.LISTENING_FOR_COMMAND


def test_wake_utterance_can_include_an_inline_command() -> None:
    result = VoskRecognitionSession(
        FakeRecognizer(), WakeWordDetector("Mjolnir")
    )._process_transcript("hello me on it open chrome")

    assert result.wake_word_detected
    assert result.command == "open chrome"
    assert result.state is VoiceState.PROCESSING_COMMAND


@pytest.mark.parametrize(
    ("transcript", "command"),
    (
        ("meonir open chrome", "open chrome"),
        ("Meonir tell me a joke", "tell me a joke"),
        ("wake up meonir open chrome", "open chrome"),
    ),
)
def test_supported_inline_wake_forms_execute_from_same_final_transcript(
    transcript: str, command: str
) -> None:
    result = VoskRecognitionSession(
        FakeRecognizer(), WakeWordDetector("Mjolnir")
    )._process_transcript(transcript)

    assert result.wake_word_detected
    assert result.command == command
    assert result.state is VoiceState.PROCESSING_COMMAND


def test_inline_command_corrects_common_vosk_open_inflection() -> None:
    result = VoskRecognitionSession(
        FakeRecognizer(), WakeWordDetector("Mjolnir")
    )._process_transcript("me on it opened chrome")

    assert result.command == "open chrome"


def test_constrained_wake_can_align_vosk_leading_filler_without_global_matching() -> None:
    detector = WakeWordDetector("Mjolnir")
    aligned = detector.align_correlated_transcript("i got me on it opened chrome")
    assert aligned == "me on it opened chrome"


def test_wake_word_is_not_matched_inside_ordinary_speech() -> None:
    detector = WakeWordDetector("Mjolnir")
    assert not detector.detect("please ask meonir about this")


def test_live_vosk_variant_logs_every_wake_detection_stage(caplog) -> None:
    caplog.set_level(logging.DEBUG, logger="mjolniros.voice")
    recognizer = FinalWakeRecognizer()
    session = VoskRecognitionSession(recognizer, WakeWordDetector("Mjolnir"))
    service = VoiceRecognitionService.__new__(VoiceRecognitionService)
    service._sessions = {"live-session": session}
    service._logger = voice_logger

    result = service.accept_audio(
        "live-session", base64.b64encode(b"live microphone pcm").decode("ascii")
    )

    events = [record.message for record in caplog.records]
    states = [
        record.voice_state
        for record in caplog.records
        if hasattr(record, "voice_state")
    ]
    assert result.wake_word_detected
    assert recognizer.reset
    assert events.index("voice_audio_packet_received") < events.index(
        "voice_recognizer_pcm_received"
    )
    assert events.index("voice_recognizer_pcm_received") < events.index(
        "voice_vosk_final"
    )
    assert events.index("voice_vosk_final") < events.index("voice_wake_normalized")
    assert events.index("voice_wake_normalized") < events.index("voice_wake_matcher")
    assert "voice_wake_transition" in events
    assert states == ["WAKE_DETECTED", "LISTENING_FOR_COMMAND"]


def test_partial_callback_logs_before_wake_transition(caplog) -> None:
    caplog.set_level(logging.DEBUG, logger="mjolniros.voice")
    session = VoskRecognitionSession(
        PartialWakeRecognizer(), WakeWordDetector("Mjolnir")
    )

    result = session.accept_audio(b"live microphone pcm")

    events = [record.message for record in caplog.records]
    assert not result.wake_word_detected
    assert events.index("voice_recognizer_pcm_received") < events.index(
        "voice_vosk_partial"
    )
    assert "voice_wake_normalized" not in events


def test_command_listening_timeout_returns_to_wake(monkeypatch) -> None:
    now = [10.0]
    monkeypatch.setattr("backend.app.voice.recognizer.monotonic", lambda: now[0])
    session = VoskRecognitionSession(
        SilentRecognizer(), WakeWordDetector("Mjolnir"), command_timeout_seconds=2
    )
    session._process_transcript("hello meonir")

    assert session.accept_audio(b"silence").state is VoiceState.LISTENING_FOR_COMMAND
    now[0] = 13.0

    assert session.accept_audio(b"silence").state is VoiceState.LISTENING_FOR_WAKE_WORD


def test_recognizer_resets_before_follow_up_window() -> None:
    recognizer = CountingRecognizer()
    session = VoskRecognitionSession(recognizer, WakeWordDetector("Mjolnir"))

    session._process_transcript("hello meonir")
    session._process_transcript("open chrome")
    session.complete_command()

    assert recognizer.reset_count == 2


class InterruptibleEngine:
    def __init__(self) -> None:
        self.finished = Event()

    def say(self, _text: str) -> None:
        pass

    def runAndWait(self) -> None:
        self.finished.wait(2)

    def stop(self) -> None:
        self.finished.set()


def test_tts_interrupt_does_not_wait_on_utterance_lock() -> None:
    synthesizer = SpeechSynthesizer(SimpleNamespace(voice_tts_rate=185, voice_tts_volume=1.0))
    synthesizer._engine = InterruptibleEngine()

    completion = synthesizer.speak("Yes, Boss.")
    synthesizer.stop()

    assert completion.wait(0.5)
    assert not synthesizer.speaking


class FailedRunLoopEngine:
    def say(self, _text: str) -> None:
        pass

    def runAndWait(self) -> None:
        raise RuntimeError("run loop already started")

    def stop(self) -> None:
        pass


def test_failed_pyttsx3_loop_uses_existing_powershell_fallback(caplog) -> None:
    caplog.set_level(logging.INFO, logger="mjolniros.voice")
    synthesizer = SpeechSynthesizer(
        SimpleNamespace(voice_tts_rate=185, voice_tts_volume=1.0)
    )
    synthesizer._engine = FailedRunLoopEngine()

    with patch(
        "backend.app.voice.synthesizer.subprocess.run",
        return_value=SimpleNamespace(returncode=0),
    ):
        completion = synthesizer.speak("Yes, Boss.")
        assert completion.wait(1)

    states = [
        record.voice_state
        for record in caplog.records
        if hasattr(record, "voice_state")
    ]
    assert synthesizer._prefer_powershell
    assert completion.error is None
    assert completion.engine == "powershell_system_speech"
    assert completion.return_value == 0
    assert states == ["TTS_START", "TTS_END"]


def test_unrecoverable_tts_exception_is_returned_to_caller(caplog) -> None:
    caplog.set_level(logging.ERROR, logger="mjolniros.voice")
    synthesizer = SpeechSynthesizer(
        SimpleNamespace(voice_tts_rate=185, voice_tts_volume=1.0)
    )
    failure = RuntimeError("audio device unavailable")
    engine = FailedRunLoopEngine()
    engine.runAndWait = lambda: (_ for _ in ()).throw(failure)
    synthesizer._engine = engine

    completion = synthesizer.speak("Yes, Boss.")

    assert completion.wait(1)
    assert completion.error is failure
    assert any(record.exc_info for record in caplog.records)
