"""Domain schemas for local voice interaction."""

from enum import StrEnum

from pydantic import BaseModel, Field


class VoiceState(StrEnum):
    """States emitted by a continuous local listening session."""

    LISTENING_FOR_WAKE_WORD = "listening_for_wake_word"
    WAKE_DETECTED = "wake_detected"
    LISTENING_FOR_COMMAND = "listening_for_command"
    PROCESSING_COMMAND = "processing_command"
    SPEAKING = "speaking"


class VoiceHealthStatus(BaseModel):
    """Availability and configuration of the offline voice runtime."""

    available: bool
    tts_available: bool
    message: str
    wake_word: str
    sample_rate: int


class VoiceSession(BaseModel):
    """A created continuous recognition session."""

    session_id: str
    state: VoiceState


class AudioChunk(BaseModel):
    """Base64-encoded signed 16-bit PCM audio captured by the desktop client."""

    audio_base64: str = Field(min_length=1, max_length=1_500_000)


class RecognitionResult(BaseModel):
    """Recognition status after one microphone chunk."""

    state: VoiceState
    transcript: str = ""
    wake_word_detected: bool = False
    command: str | None = None


class SpeakRequest(BaseModel):
    """A local text-to-speech request."""

    text: str = Field(min_length=1, max_length=12_000)


class SpeechStatus(BaseModel):
    """State of local speech synthesis."""

    speaking: bool
