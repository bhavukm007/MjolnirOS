"""Offline voice API routes for the Electron desktop client."""

import asyncio
from functools import lru_cache

from fastapi import APIRouter, HTTPException, status

from backend.app.core.responses import ApiResponse
from backend.app.core.settings import get_settings
from backend.app.domain.voice import AudioChunk, RecognitionResult, SpeakRequest, SpeechStatus, VoiceHealthStatus, VoiceSession
from backend.app.voice.recognizer import VoiceRecognitionService, VoiceUnavailableError
from backend.app.voice.synthesizer import SpeechSynthesizer
from backend.app.voice.runtime_logger import logger as voice_logger

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
    voice_logger.debug("voice_endpoint_opened", extra={"endpoint": "create_session"})
    try:
        session = get_recognition_service().create_session()
    except VoiceUnavailableError as error:
        voice_logger.exception("voice_session_creation_failure")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    except Exception:
        voice_logger.exception("voice_session_creation_failure")
        raise
    return ApiResponse(success=True, message="Voice listening started.", data=session)


@router.post("/sessions/{session_id}/audio", response_model=ApiResponse[RecognitionResult])
async def process_audio(session_id: str, chunk: AudioChunk) -> ApiResponse[RecognitionResult]:
    """Process one microphone PCM chunk and surface wake-word or command events."""
    voice_logger.debug(
        "voice_endpoint_audio_packet_received",
        extra={"session_id": session_id, "encoded_bytes": len(chunk.audio_base64)},
    )
    try:
        result = get_recognition_service().accept_audio(session_id, chunk.audio_base64)
    except KeyError as error:
        voice_logger.exception("voice_audio_session_not_found", extra={"session_id": session_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice session was not found.") from error
    except ValueError as error:
        voice_logger.exception("voice_audio_payload_invalid", extra={"session_id": session_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    except Exception:
        voice_logger.exception("voice_audio_endpoint_failure", extra={"session_id": session_id})
        raise
    return ApiResponse(success=True, message="Audio processed.", data=result)


@router.delete("/sessions/{session_id}", response_model=ApiResponse[RecognitionResult])
async def close_voice_session(session_id: str) -> ApiResponse[RecognitionResult]:
    """Finish recognition and release the continuous listening session."""
    voice_logger.debug("voice_session_cleanup_started", extra={"session_id": session_id})
    try:
        result = get_recognition_service().close_session(session_id)
    except KeyError as error:
        voice_logger.exception("voice_session_cleanup_not_found", extra={"session_id": session_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice session was not found.") from error
    except Exception:
        voice_logger.exception("voice_session_cleanup_failure", extra={"session_id": session_id})
        raise
    voice_logger.debug("voice_session_cleanup_finished", extra={"session_id": session_id})
    return ApiResponse(success=True, message="Voice listening stopped.", data=result)


@router.post("/sessions/{session_id}/complete", response_model=ApiResponse[RecognitionResult])
async def complete_voice_command(session_id: str) -> ApiResponse[RecognitionResult]:
    """Resume wake-word recognition after planner, tool, and reply processing."""
    try:
        result = get_recognition_service().complete_command(session_id)
    except KeyError as error:
        voice_logger.exception("voice_command_session_not_found", extra={"session_id": session_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice session was not found.") from error
    except ValueError as error:
        voice_logger.exception("voice_command_completion_conflict", extra={"session_id": session_id})
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except Exception:
        voice_logger.exception("voice_command_completion_failure", extra={"session_id": session_id})
        raise
    return ApiResponse(success=True, message="Voice command completed.", data=result)


@router.post("/speak", response_model=ApiResponse[SpeechStatus], status_code=status.HTTP_202_ACCEPTED)
async def speak(request: SpeakRequest, wait: bool = False) -> ApiResponse[SpeechStatus]:
    """Speak an assistant reply through a local operating-system voice."""
    voice_logger.info(
        "voice_speak_invoked",
        extra={"wait": wait, "payload": request.model_dump()},
    )
    synthesizer = get_speech_synthesizer()
    if not synthesizer.available():
        voice_logger.error("voice_tts_unavailable")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Local text-to-speech is unavailable.")
    try:
        completion = await asyncio.to_thread(synthesizer.speak, request.text)
    except Exception as error:
        voice_logger.exception("voice_speak_synthesizer_entry_failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Local text-to-speech failed. See the voice runtime log.",
        ) from error
    if wait:
        try:
            await asyncio.wait_for(
                asyncio.to_thread(completion.wait),
                timeout=get_settings().voice_tts_timeout_seconds,
            )
        except TimeoutError as error:
            await asyncio.to_thread(synthesizer.stop)
            voice_logger.exception(
                "voice_tts_timeout",
                extra={"timeout_seconds": get_settings().voice_tts_timeout_seconds},
            )
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Local text-to-speech did not finish before the timeout.",
            ) from error
        if completion.error is not None:
            voice_logger.error(
                "voice_speak_failed",
                exc_info=(
                    type(completion.error),
                    completion.error,
                    completion.error.__traceback__,
                ),
                extra={
                    "engine": completion.engine,
                    "return_value": completion.return_value,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Local text-to-speech failed. See the voice runtime log.",
            ) from completion.error
    voice_logger.info(
        "voice_speak_return",
        extra={
            "wait": wait,
            "engine": completion.engine,
            "return_value": completion.return_value,
            "speaking": synthesizer.speaking,
        },
    )
    return ApiResponse(
        success=True,
        message="Speech completed." if wait else "Speech started.",
        data=SpeechStatus(speaking=synthesizer.speaking),
    )


@router.delete("/speak", response_model=ApiResponse[SpeechStatus])
async def stop_speaking() -> ApiResponse[SpeechStatus]:
    """Interrupt a local assistant utterance for natural barge-in."""
    await asyncio.to_thread(get_speech_synthesizer().stop)
    return ApiResponse(success=True, message="Speech stopped.", data=SpeechStatus(speaking=False))
