"""
NEXUS AI - Zero-API-Key Neural Voice Synthesizer & Speech Intelligence
Provides:
1. Streaming Neural TTS via edge-tts (Zero API Key, multi-lingual, zero GPU VRAM).
2. Offline CPU Fallback via kokoro-onnx when offline or models present.
3. Curated Voice Profiles with persistent user preference storage.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, AsyncIterator
import edge_tts

from app.core.security import resolve_safe_workspace_path

logger = logging.getLogger(__name__)

# Curated high-fidelity neural voice presets
VOICE_PROFILES: Dict[str, str] = {
    "aria": "en-US-AriaNeural",
    "guy": "en-US-GuyNeural",
    "neerja": "en-IN-NeerjaNeural",     # Indian English (Female)
    "prabhat": "en-IN-PrabhatNeural",   # Indian English (Male)
    "pallavi": "ta-IN-PallaviNeural",   # Tamil
    "shruti": "te-IN-ShrutiNeural",     # Telugu
    "swara": "hi-IN-SwaraNeural",       # Hindi
}


class VoiceSynthesizer:
    """Manages zero-cost neural speech generation and voice switching."""

    def __init__(self, prefs_path: Optional[str] = None):
        self.prefs_path = (
            Path(prefs_path) if prefs_path else resolve_safe_workspace_path("memory/user_preferences.json")
        )
        self.prefs_path.parent.mkdir(parents=True, exist_ok=True)
        self.active_voice_key: str = self._load_preferred_voice()
        self._kokoro_model = None

    def _load_preferred_voice(self) -> str:
        """Reads persisted active voice selection."""
        if self.prefs_path.exists():
            try:
                with open(self.prefs_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    val = data.get("voice_profile", "neerja")
                    if val in VOICE_PROFILES:
                        return val
            except Exception as e:
                logger.debug(f"[VoiceSynthesizer] Prefs load note: {e}")
        return "neerja"

    def set_voice_profile(self, voice_key: str) -> Dict[str, Any]:
        """Switches active voice and persists preference."""
        clean_key = voice_key.lower().strip()
        if clean_key not in VOICE_PROFILES:
            return {
                "status": "error",
                "message": f"Unknown voice '{voice_key}'. Available: {list(VOICE_PROFILES.keys())}",
            }

        self.active_voice_key = clean_key
        prefs: Dict[str, Any] = {}
        if self.prefs_path.exists():
            try:
                with open(self.prefs_path, "r", encoding="utf-8") as f:
                    prefs = json.load(f)
            except Exception:
                pass

        prefs["voice_profile"] = clean_key
        prefs["voice_name"] = VOICE_PROFILES[clean_key]
        with open(self.prefs_path, "w", encoding="utf-8") as f:
            json.dump(prefs, f, indent=2)

        logger.info(f"[VoiceSynthesizer] Switched voice profile to '{clean_key}' ({VOICE_PROFILES[clean_key]})")
        return {
            "status": "success",
            "voice_key": clean_key,
            "voice_name": VOICE_PROFILES[clean_key],
        }

    def get_current_voice_info(self) -> Dict[str, Any]:
        return {
            "active_key": self.active_voice_key,
            "active_voice": VOICE_PROFILES[self.active_voice_key],
            "available_voices": VOICE_PROFILES,
        }

    async def stream_audio_chunks(
        self,
        text: str,
        voice_key: Optional[str] = None,
        rate: str = "+0%",
    ) -> AsyncIterator[bytes]:
        """
        Asynchronously streams synthesized MP3/audio chunks via edge-tts,
        with automated kokoro-onnx offline CPU fallback.
        """
        target_key = voice_key.lower() if voice_key and voice_key.lower() in VOICE_PROFILES else self.active_voice_key
        target_voice = VOICE_PROFILES[target_key]

        try:
            communicate = edge_tts.Communicate(text=text, voice=target_voice, rate=rate)
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    yield chunk["data"]
        except Exception as exc:
            logger.warning(f"[VoiceSynthesizer] edge-tts streaming failed ({exc}); falling back to offline Kokoro engine.")
            # Trigger offline kokoro-onnx fallback
            offline_bytes = self._synthesize_kokoro_offline(text)
            if offline_bytes:
                yield offline_bytes

    def _synthesize_kokoro_offline(self, text: str) -> Optional[bytes]:
        """Offline CPU fallback using kokoro-onnx if model weights are present or mock."""
        try:
            model_path = resolve_safe_workspace_path("models/kokoro-v1.0.onnx")
            voices_path = resolve_safe_workspace_path("models/voices-v1.0.bin")
            if model_path.exists() and voices_path.exists():
                from kokoro_onnx import Kokoro
                if not self._kokoro_model:
                    self._kokoro_model = Kokoro(str(model_path), str(voices_path))
                samples, sample_rate = self._kokoro_model.create(text, voice="af_sarah", speed=1.0)
                import io
                import soundfile as sf
                buffer = io.BytesIO()
                sf.write(buffer, samples, sample_rate, format="WAV")
                return buffer.getvalue()
        except Exception as e:
            logger.debug(f"[VoiceSynthesizer] Kokoro offline note: {e}")
        return None


voice_synthesizer = VoiceSynthesizer()

