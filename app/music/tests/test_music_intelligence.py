"""
Unit & Integration Tests for NEXUS AI Music Intelligence Subsystem
Tests:
1. Natural language music intent routing in MusicAgent.
2. MusicMemory logging, history retrieval and artist frequency metrics.
3. RecommendationEngine multi-hour AI DJ playlist generation.
4. AudioController master volume adjustment and auto-ducking/restoring.
5. SleepTimerManager scheduling and cancellation.
6. FastAPI Music REST Endpoints (/api/v1/music/status, /control, /dj, /volume, /devices).
"""

import pytest
import os
from pathlib import Path
from httpx import AsyncClient, ASGITransport

from unittest.mock import patch, AsyncMock
from app.music.music_agent import music_agent_node
from app.music.music_memory import MusicMemory
from app.music.recommendation_engine import recommendation_engine
from app.music.audio_controller import audio_controller
from app.music.sleep_timer import sleep_timer_manager
from app.main import app


@pytest.mark.asyncio
async def test_music_agent_intent_routing():
    """Validates MusicAgent NLU intent classification and execution."""
    # Test 1: Volume command
    state_vol = {"raw_prompt": "Set volume to 45%"}
    res_vol = await music_agent_node(state_vol)
    assert res_vol["agent_outputs"]["music"]["status"] == "success"
    assert "45%" in res_vol["agent_outputs"]["music"]["summary"]

    # Test 2: Sleep timer command
    state_timer = {"raw_prompt": "Stop music after 20 minutes"}
    res_timer = await music_agent_node(state_timer)
    assert res_timer["agent_outputs"]["music"]["status"] == "success"
    assert "20 minutes" in res_timer["agent_outputs"]["music"]["summary"]

    # Test 3: Play song command (mock browser launch for fast unit testing)
    with patch("app.music.app_integrations.youtube_music.youtube_music_integration.play", new_callable=AsyncMock) as mock_play:
        mock_play.return_value = {"status": "success", "service": "ytmusic"}
        state_play = {"raw_prompt": "Play Tamil hits"}
        res_play = await music_agent_node(state_play)
        assert res_play["agent_outputs"]["music"]["status"] == "success"
        assert "tamil hits" in res_play["agent_outputs"]["music"]["summary"].lower()
        mock_play.assert_called_once()


def test_music_memory_tracking(tmp_path):
    """Validates listening history logging, skip recording, and top artist aggregation."""
    db_file = tmp_path / "test_music_memory.db"
    mem = MusicMemory(str(db_file))

    # Log 3 plays
    mem.log_playback(title="Arabic Kuthu", artist="Anirudh Ravichander", service="youtube_music")
    mem.log_playback(title="Hukum", artist="Anirudh Ravichander", service="youtube_music")
    mem.log_playback(title="Kesariya", artist="Arijit Singh", service="spotify")

    history = mem.get_recent_history(limit=10)
    assert len(history) == 3
    assert history[0]["title"] == "Kesariya"

    top_artists = mem.get_top_artists(limit=5)
    assert len(top_artists) >= 2
    assert top_artists[0]["artist"] == "Anirudh Ravichander"
    assert top_artists[0]["play_count"] == 2


def test_ai_dj_multi_hour_generation():
    """Validates AI personal DJ playlist generation matching prompt duration and mood."""
    prompt = "Create a two-hour playlist for studying machine learning"
    playlist = recommendation_engine.generate_ai_playlist(prompt=prompt, duration_minutes=120)

    assert playlist["status"] == "success"
    assert playlist["mood"] == "focus"
    assert playlist["target_duration_minutes"] == 120
    assert playlist["actual_duration_seconds"] >= 120 * 60
    assert playlist["track_count"] >= 10
    assert "tracks" in playlist
    assert "query" in playlist["tracks"][0]


def test_audio_controller_ducking_and_volume():
    """Validates volume setter, getter and auto-ducking state transitions."""
    original_vol = audio_controller.get_master_volume()

    # Test setting volume
    res_set = audio_controller.set_master_volume(35)
    assert res_set["volume_percent"] == 35

    # Test ducking
    duck_res = audio_controller.duck_music_volume(target_percent=12)
    assert duck_res["status"] == "ducked"

    # Test restoring
    restore_res = audio_controller.restore_music_volume()
    assert restore_res["status"] == "restored"

    # Restore baseline
    audio_controller.set_master_volume(original_vol)


def test_sleep_timer_scheduling():
    """Validates sleep timer scheduling and cancellation."""
    res_set = sleep_timer_manager.set_sleep_timer(minutes=45)
    assert res_set["status"] == "scheduled"
    assert res_set["minutes"] == 45

    status = sleep_timer_manager.get_status()
    assert status["active"] is True
    assert status["stops_at"] is not None

    cancel_res = sleep_timer_manager.cancel_sleep_timer()
    assert cancel_res["status"] == "cancelled"


@pytest.mark.asyncio
async def test_music_api_endpoints():
    """Validates FastAPI Music REST routes."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. GET /api/v1/music/status
        resp_status = await client.get("/api/v1/music/status")
        assert resp_status.status_code == 200
        data_status = resp_status.json()
        assert data_status["status"] == "success"
        assert "media" in data_status
        assert "volume" in data_status

        # 2. GET /api/v1/music/devices
        resp_dev = await client.get("/api/v1/music/devices")
        assert resp_dev.status_code == 200
        assert "devices" in resp_dev.json()

        # 3. POST /api/v1/music/volume
        resp_vol = await client.post("/api/v1/music/volume", json={"volume_percent": 40})
        assert resp_vol.status_code == 200

        # 4. POST /api/v1/music/dj
        with patch("app.music.app_integrations.youtube_music.youtube_music_integration.play", new_callable=AsyncMock):
            resp_dj = await client.post("/api/v1/music/dj", json={"prompt": "chill lo-fi beats", "duration_minutes": 30})
            assert resp_dj.status_code == 200
            data_dj = resp_dj.json()
            assert data_dj["status"] == "success"
            assert len(data_dj["tracks"]) > 0
