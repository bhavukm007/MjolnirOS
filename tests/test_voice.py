import base64

from fastapi.testclient import TestClient

from backend.app.api.routes import voice
from backend.app.domain.voice import RecognitionResult, SpeechStatus, VoiceSession, VoiceState
from backend.app.main import create_app
from backend.app.voice.wake_word import WakeWordDetector


class RecognitionService:
    """Deterministic offline recognition replacement for route tests."""

    def health_message(self) -> None:
        return None

    def create_session(self) -> VoiceSession:
        return VoiceSession(session_id="voice-session", state=VoiceState.LISTENING_FOR_WAKE_WORD)

    def accept_audio(self, session_id: str, audio_base64: str) -> RecognitionResult:
        assert session_id == "voice-session"
        assert base64.b64decode(audio_base64) == b"pcm"
        return RecognitionResult(state=VoiceState.LISTENING_FOR_WAKE_WORD, wake_word_detected=True, command="what time is it")

    def close_session(self, session_id: str) -> RecognitionResult:
        return RecognitionResult(state=VoiceState.LISTENING_FOR_WAKE_WORD)


class SpeechSynthesizer:
    """Deterministic local TTS replacement for route tests."""

    def __init__(self) -> None:
        self.text = ""
        self.stopped = False

    def available(self) -> bool:
        return True

    def speak(self, text: str) -> None:
        self.text = text

    def stop(self) -> None:
        self.stopped = True


def test_wake_word_accepts_configured_and_similar_pronunciations() -> None:
    detector = WakeWordDetector("Mjolnir")

    assert detector.detect("Mjolnir, what time is it")
    assert detector.detect("me oh near open settings")
    assert detector.detect("myolnir")
    assert not detector.detect("open settings")
    assert detector.remove("me oh near open settings") == "open settings"


def test_voice_routes_support_continuous_audio_and_speech(monkeypatch) -> None:
    recognizer = RecognitionService()
    synthesizer = SpeechSynthesizer()
    monkeypatch.setattr(voice, "get_recognition_service", lambda: recognizer)
    monkeypatch.setattr(voice, "get_speech_synthesizer", lambda: synthesizer)
    client = TestClient(create_app())

    session = client.post("/api/v1/voice/sessions")
    audio = client.post("/api/v1/voice/sessions/voice-session/audio", json={"audio_base64": base64.b64encode(b"pcm").decode()})
    speech = client.post("/api/v1/voice/speak", json={"text": "The time is noon."})
    stop = client.delete("/api/v1/voice/speak")

    assert session.status_code == 201
    assert audio.json()["data"]["wake_word_detected"] is True
    assert audio.json()["data"]["command"] == "what time is it"
    assert speech.status_code == 202
    assert synthesizer.text == "The time is noon."
    assert stop.json()["data"] == SpeechStatus(speaking=False).model_dump()
    assert synthesizer.stopped is True
