import logging
from typing import Optional
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

GROQ_TRANSCRIPTIONS_ENDPOINT = "https://api.groq.com/openai/v1/audio/transcriptions"


async def transcribe_audio(
    file_bytes: bytes,
    filename: str = "voice_note.ogg",
    model: Optional[str] = None,
) -> str:
    """
    Transcribes audio bytes into text using Groq's high-speed API (whisper-large-v3).

    Supports formats: ogg, mp3, m4a, wav, mp4, etc.
    Handles missing keys, network timeouts, and invalid audio gracefully.
    """
    if not file_bytes or len(file_bytes) == 0:
        logger.warning("Empty audio bytes supplied for Groq transcription.")
        return ""

    api_key = settings.GROQ_API_KEY or settings.OPENAI_API_KEY
    if not api_key:
        logger.error("Neither GROQ_API_KEY nor OPENAI_API_KEY is configured in settings.")
        raise ValueError("Audio transcription failed: GROQ_API_KEY is missing in settings.")

    target_model = model or settings.WHISPER_MODEL or "whisper-large-v3"
    endpoint = GROQ_TRANSCRIPTIONS_ENDPOINT

    headers = {
        "Authorization": f"Bearer {api_key}",
    }

    files = {
        "file": (filename, file_bytes, "application/octet-stream"),
    }
    data = {
        "model": target_model,
        "response_format": "json",
    }

    logger.info(
        f"Dispatching {len(file_bytes)} audio bytes ({filename}) to Groq Whisper endpoint using model '{target_model}'..."
    )

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                endpoint,
                headers=headers,
                files=files,
                data=data,
            )

            if response.status_code != 200:
                logger.error(f"Groq API error (status {response.status_code}): {response.text}")
                response.raise_for_status()

            payload = response.json()
            transcription = payload.get("text", "").strip()
            logger.info(f"Groq transcription completed successfully: '{transcription[:60]}...'")
            return transcription

    except httpx.TimeoutException as exc:
        logger.error(f"Groq API connection timed out while processing {filename}: {exc}")
        raise TimeoutError("Audio transcription request to Groq timed out.") from exc
    except httpx.HTTPStatusError as exc:
        logger.error(f"Groq API returned an HTTP error: {exc.response.status_code} - {exc.response.text}")
        raise RuntimeError(f"Groq STT failed: {exc.response.text}") from exc
    except Exception as exc:
        logger.error(f"Unexpected error during Groq audio transcription: {exc}", exc_info=True)
        raise RuntimeError(f"Voice transcription failed: {str(exc)}") from exc
