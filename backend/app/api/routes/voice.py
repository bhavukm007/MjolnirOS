"""Offline voice API routes for the Electron desktop client."""

from functools import lru_cache

from fastapi import APIRouter, HTTPException, status

from backend.app.core.responses import ApiResponse
from backend.app.core.settings import get_settings
from backend.app.domain.voice import AudioChunk, RecognitionResult, SpeakRequest, SpeechStatus, VoiceHealthStatus, VoiceSession
from backend.app.voice.recognizer import VoiceRecognitionService, VoiceUnavailableError
from backend.app.voice.synthesizer import SpeechSynthesizer

router = APIRouter(prefix="/voice", tags=["voice"])


@lru_cache
def get_recognition_service() -> VoiceRecognitionService:
    """Return the configured process-wide offline recognition service."""
    return VoiceRecognitionService(get_settings())


@lru_cache
def get_speech_synthesizer() -> SpeechSynthesizer:
    """Return the configured process-wide local speech synthesizer."""
    return SpeechSynthesizer(get_settings())


@router.get("/health", response_model=ApiResponse[VoiceHealthStatus])
async def get_voice_health() -> ApiResponse[VoiceHealthStatus]:
    """Report offline STT and TTS readiness without requiring a microphone."""
    settings = get_settings()
    recognition_error = get_recognition_service().health_message()
    tts_available = get_speech_synthesizer().available()
    message = "Voice runtime is ready." if recognition_error is None else recognition_error
    return ApiResponse(success=True, message=message, data=VoiceHealthStatus(
        available=recognition_error is None,
        tts_available=tts_available,
        message=message,
        wake_word=settings.voice_wake_word,
        sample_rate=settings.voice_sample_rate,
    ))


@router.post("/sessions", response_model=ApiResponse[VoiceSession], status_code=status.HTTP_201_CREATED)
async def create_voice_session() -> ApiResponse[VoiceSession]:
    """Start continuous listening in low-cost wake-word mode."""
    try:
        session = get_recognition_service().create_session()
    except VoiceUnavailableError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    return ApiResponse(success=True, message="Voice listening started.", data=session)


@router.post("/sessions/{session_id}/audio", response_model=ApiResponse[RecognitionResult])
async def process_audio(session_id: str, chunk: AudioChunk) -> ApiResponse[RecognitionResult]:
    """Process one microphone PCM chunk and surface wake-word or command events."""
    try:
        result = get_recognition_service().accept_audio(session_id, chunk.audio_base64)
    except KeyError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice session was not found.") from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    return ApiResponse(success=True, message="Audio processed.", data=result)


@router.delete("/sessions/{session_id}", response_model=ApiResponse[RecognitionResult])
async def close_voice_session(session_id: str) -> ApiResponse[RecognitionResult]:
    """Finish recognition and release the continuous listening session."""
    try:
        result = get_recognition_service().close_session(session_id)
    except KeyError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice session was not found.") from error
    return ApiResponse(success=True, message="Voice listening stopped.", data=result)


@router.post("/speak", response_model=ApiResponse[SpeechStatus], status_code=status.HTTP_202_ACCEPTED)
async def speak(request: SpeakRequest) -> ApiResponse[SpeechStatus]:
    """Speak an assistant reply through a local operating-system voice."""
    synthesizer = get_speech_synthesizer()
    if not synthesizer.available():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Local text-to-speech is unavailable.")
    synthesizer.speak(request.text)
    return ApiResponse(success=True, message="Speech started.", data=SpeechStatus(speaking=True))


@router.delete("/speak", response_model=ApiResponse[SpeechStatus])
async def stop_speaking() -> ApiResponse[SpeechStatus]:
    """Interrupt a local assistant utterance for natural barge-in."""
    get_speech_synthesizer().stop()
    return ApiResponse(success=True, message="Speech stopped.", data=SpeechStatus(speaking=False))
