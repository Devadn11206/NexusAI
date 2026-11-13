"""
NEXUS AI - Voice Input Transcription & Audio Response Engine
Supports Groq Whisper-large-v3 transcription and Edge-TTS audio response synthesis.
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional
import httpx

from app.config import settings
from app.core.security import resolve_safe_workspace_path

logger = logging.getLogger(__name__)


async def transcribe_voice_note(
    audio_file_path: str,
    api_key: Optional[str] = None,
    model: str = "whisper-large-v3",
) -> str:
    """
    Transcribes audio file (.ogg, .wav, .mp3, .m4a) using Groq Whisper API.
    """
    path_obj = Path(audio_file_path).resolve()
    if not path_obj.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_file_path}")

    key = api_key or settings.GROQ_API_KEY
    if not key:
        logger.warning("[VoiceEngine] GROQ_API_KEY unconfigured; returning fallback transcription.")
        return "Voice note received (Transcription offline)."

    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {key}"}

    async with httpx.AsyncClient(timeout=45.0) as client:
        with open(path_obj, "rb") as f:
            files = {"file": (path_obj.name, f, "audio/ogg")}
            data = {"model": model, "response_format": "json"}
            resp = await client.post(url, headers=headers, files=files, data=data)
            resp.raise_for_status()
            res_data = resp.json()
            return res_data.get("text", "").strip()


async def generate_voice_response(
    text: str,
    output_filename: str = "audio_response.mp3",
    voice: str = "en-US-ChristopherNeural",
) -> str:
    """
    Generates natural spoken voice note audio from text using edge-tts.
    Saves file in ./workspace/ and returns absolute path.
    """
    safe_out_path = resolve_safe_workspace_path(output_filename)
    safe_out_path.parent.mkdir(parents=True, exist_ok=True)

    clean_text = text.strip()
    if not clean_text:
        clean_text = "Task executed successfully."

    logger.info(f"[VoiceEngine] Synthesizing audio with voice '{voice}' to {safe_out_path}")

    try:
        import edge_tts
        communicate = edge_tts.Communicate(clean_text, voice)
        await communicate.save(str(safe_out_path))
        return str(safe_out_path)
    except Exception as exc:
        logger.warning(f"[VoiceEngine] edge-tts note ({exc}); generating empty stub audio.")
        with open(safe_out_path, "wb") as f:
            f.write(b"ID3\x04\x00\x00\x00\x00\x00\x00")
        return str(safe_out_path)

