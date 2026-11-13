"""
NEXUS AI - Music & Audio REST API Routes
Exposes:
- GET /api/v1/music/status
- POST /api/v1/music/control
- POST /api/v1/music/dj
- GET /api/v1/music/devices
- POST /api/v1/music/volume
- POST /api/v1/music/timer
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.music.music_controller import music_controller
from app.music.audio_controller import audio_controller
from app.music.recommendation_engine import recommendation_engine
from app.music.sleep_timer import sleep_timer_manager
from app.music.music_memory import music_memory

router = APIRouter(prefix="/music", tags=["Music Intelligence"])


class ControlPayload(BaseModel):
    action: str  # 'play', 'pause', 'play_pause', 'next', 'previous', 'resume'
    service: Optional[str] = "youtube_music"
    query: Optional[str] = None


class DJPayload(BaseModel):
    prompt: str
    duration_minutes: Optional[int] = 60


class VolumePayload(BaseModel):
    volume_percent: int


class TimerPayload(BaseModel):
    minutes: int


@router.get("/status")
async def get_music_status():
    """Returns currently playing media metadata, volume, and sleep timer status."""
    media_info = await music_controller.get_current_media_info()
    vol = audio_controller.get_master_volume()
    timer = sleep_timer_manager.get_status()
    history = music_memory.get_recent_history(limit=5)
    return {
        "status": "success",
        "media": media_info,
        "volume": vol,
        "sleep_timer": timer,
        "recent_history": history,
    }


@router.post("/control")
async def control_playback(payload: ControlPayload):
    """Executes media commands."""
    action = payload.action.lower()
    if action == "play":
        res = await music_controller.play(service=payload.service or "youtube_music", query=payload.query)
    elif action == "pause":
        res = await music_controller.pause()
    elif action == "resume":
        res = await music_controller.resume()
    elif action in ("play_pause", "toggle"):
        res = await music_controller.play_pause()
    elif action == "next":
        res = await music_controller.next_track()
    elif action == "previous":
        res = await music_controller.previous_track()
    else:
        return {"status": "error", "message": f"Unknown action: {action}"}

    return {"status": "success", "action": action, "result": res}


@router.post("/dj")
async def generate_ai_dj(payload: DJPayload):
    """Generates and triggers an AI DJ playlist based on natural language."""
    res = recommendation_engine.generate_ai_playlist(payload.prompt, duration_minutes=payload.duration_minutes)
    if res["tracks"]:
        first_q = res["tracks"][0]["query"]
        await music_controller.play(query=first_q)
    return res


@router.get("/devices")
async def get_audio_devices():
    """Lists available Windows audio output devices."""
    devices = audio_controller.list_audio_devices()
    return {"status": "success", "devices": devices}


@router.post("/volume")
async def set_volume(payload: VolumePayload):
    """Sets master system volume."""
    res = audio_controller.set_master_volume(payload.volume_percent)
    return res


@router.post("/timer")
async def set_timer(payload: TimerPayload):
    """Schedules a fade-out sleep timer."""
    res = sleep_timer_manager.set_sleep_timer(payload.minutes)
    return res

