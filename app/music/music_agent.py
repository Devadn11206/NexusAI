"""
NEXUS AI - MusicAgent LangGraph Node & NLU Router
Interprets natural language music requests (play, pause, volume, DJ playlists, timers)
and routes them through the Music Intelligence Subsystem.
"""

import re
import logging
from typing import Dict, Any, List

from app.music.music_controller import music_controller
from app.music.audio_controller import audio_controller
from app.music.recommendation_engine import recommendation_engine
from app.music.sleep_timer import sleep_timer_manager
from app.music.music_search import music_search

logger = logging.getLogger(__name__)


async def music_agent_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    First-class LangGraph node for all music and audio control requests.
    Inspects user prompt, resolves music intent, executes action, and updates state.
    """
    raw_prompt = (
        state.get("raw_prompt")
        or (state.get("messages", [])[-1].content if state.get("messages") else "")
        or ""
    ).strip()

    logger.info(f"[MusicAgent] Processing query: '{raw_prompt}'")
    p_lower = raw_prompt.lower()
    result_text = "Handled music request."
    tool_executed = "music_agent"

    # 1. Volume Control
    if "volume" in p_lower:
        match_vol = re.search(r'(\d+)\s*%', p_lower) or re.search(r'volume\s*(?:to\s*)?(\d+)', p_lower)
        if match_vol:
            target_pct = int(match_vol.group(1))
            audio_controller.set_master_volume(target_pct)
            result_text = f"Set master volume to {target_pct}%."
            tool_executed = "set_volume"
        elif "mute" in p_lower:
            audio_controller.set_mute(True)
            result_text = "Muted system audio."
            tool_executed = "set_mute"
        elif "unmute" in p_lower:
            audio_controller.set_mute(False)
            result_text = "Unmuted system audio."
            tool_executed = "set_unmute"

    # 2. Sleep Timer
    elif ("stop music" in p_lower or "pause music" in p_lower or "sleep timer" in p_lower) and any(
        w in p_lower for w in ["minute", "min", "hour", "hr", "after", "in"]
    ):
        match_mins = re.search(r'(\d+)\s*(?:min|minute)', p_lower)
        mins = int(match_mins.group(1)) if match_mins else 30
        sleep_timer_manager.set_sleep_timer(mins)
        result_text = f"Scheduled sleep timer: music will fade out and stop in {mins} minutes."
        tool_executed = "set_sleep_timer"

    # 3. AI DJ Playlist Generation
    elif any(k in p_lower for k in ["playlist", "dj", "two-hour", "hour playlist", "study music"]):
        res = recommendation_engine.generate_ai_playlist(raw_prompt)
        first_track = res["tracks"][0]["query"] if res["tracks"] else "Focus Beats"
        await music_controller.play(query=first_track)
        result_text = f"Generated {res['playlist_name']} with {res['track_count']} tracks. Playing {first_track}."
        tool_executed = "generate_ai_playlist"

    # 4. Playback Controls
    elif any(w in p_lower for w in ["pause", "hold music"]):
        await music_controller.pause()
        result_text = "Paused music playback."
        tool_executed = "pause"

    elif any(w in p_lower for w in ["resume", "continue music"]):
        await music_controller.resume()
        result_text = "Resumed music playback."
        tool_executed = "resume"

    elif any(w in p_lower for w in ["next track", "skip song", "next song", "skip"]):
        await music_controller.next_track()
        result_text = "Skipped to next track."
        tool_executed = "next_track"

    elif any(w in p_lower for w in ["previous track", "last song", "go back"]):
        await music_controller.previous_track()
        result_text = "Returned to previous track."
        tool_executed = "previous_track"

    # 5. Play Specific Song / Artist
    elif "play" in p_lower or "song" in p_lower or "track" in p_lower:
        query = (
            raw_prompt.lower()
            .replace("open youtube and play", "")
            .replace("open spotify and play", "")
            .replace("play song", "")
            .replace("play music", "")
            .replace("play", "")
            .strip()
        )
        if not query:
            query = "Trending Music"

        service = "spotify" if "spotify" in p_lower else "youtube_music"
        await music_controller.play(service=service, query=query)
        result_text = f"Playing '{query}' on {service.replace('_', ' ').title()}."
        tool_executed = "play_music"

    # Return updated agent output in LangGraph state format
    agent_outputs = dict(state.get("agent_outputs", {}))
    agent_outputs["music"] = {
        "status": "success",
        "action": tool_executed,
        "summary": result_text,
    }

    return {
        **state,
        "agent_outputs": agent_outputs,
        "is_graph_complete": True,
    }

