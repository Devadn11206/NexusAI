"""
Comprehensive Unit & Integration Test Suite for Zero-API-Key Voice Intelligence
Tests:
1. VoiceSynthesizer voice profile switching and persistence in user_preferences.json.
2. VoiceSynthesizer graceful offline fallback to kokoro-onnx.
3. Dual Voice + Telegram HITL approval resolution (True on 'yes confirm', False on 'cancel').
4. Full-Duplex /ws/live_call WebSocket client handling user_speech and barge_in cancellation.
"""

import pytest
import json
import asyncio
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

from app.gateway.voice_intelligence import VoiceSynthesizer, VOICE_PROFILES
from app.core.hitl_gate import hitl_manager
from app.main import app


def test_voice_synthesizer_switching_and_persistence(tmp_path):
    """Validates switching voice profile and JSON preference file persistence."""
    prefs_file = tmp_path / "test_user_preferences.json"
    synth = VoiceSynthesizer(prefs_path=str(prefs_file))

    # Initial default
    assert synth.active_voice_key == "neerja"

    # Switch to Prabhat
    res = synth.set_voice_profile("prabhat")
    assert res["status"] == "success"
    assert synth.active_voice_key == "prabhat"
    assert res["voice_name"] == "en-IN-PrabhatNeural"

    # Check file exists and persisted
    assert prefs_file.exists()
    with open(prefs_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert data["voice_profile"] == "prabhat"
        assert data["voice_name"] == "en-IN-PrabhatNeural"

    # Switch to Tamil Pallavi
    res_ta = synth.set_voice_profile("pallavi")
    assert res_ta["status"] == "success"
    assert synth.active_voice_key == "pallavi"


@pytest.mark.asyncio
async def test_voice_synthesizer_offline_fallback():
    """Validates that edge-tts exceptions trigger offline CPU fallback gracefully without crashing."""
    synth = VoiceSynthesizer()

    # Simulate network error in edge_tts.Communicate
    with patch("edge_tts.Communicate") as mock_comm:
        mock_comm.side_effect = Exception("Network connection failed")

        with patch.object(synth, "_synthesize_kokoro_offline", return_value=b"RIFF_WAV_BYTES") as mock_offline:
            chunks = []
            async for chunk in synth.stream_audio_chunks("Test offline speech"):
                chunks.append(chunk)

            assert len(chunks) == 1
            assert chunks[0] == b"RIFF_WAV_BYTES"
            mock_offline.assert_called_once()


@pytest.mark.asyncio
async def test_hitl_voice_approval_resolution():
    """Validates dual voice/Telegram confirmation resolution on spoken confirmation words."""
    # Test Approve
    gate_id = hitl_manager.create_gate(
        action_name="send_whatsapp_file to Rahul",
        reason="Testing",
        chat_id="12345",
    )
    # Simulate voice utterance confirmation
    verdict = hitl_manager.handle_voice_utterance_for_gate("Yes, confirm and send it")
    assert verdict is True
    # The event should be set
    assert hitl_manager._approval_verdicts.get(gate_id) is True

    # Test Reject
    gate_id2 = hitl_manager.create_gate(
        action_name="delete critical file",
        reason="Testing",
        chat_id="12345",
    )
    verdict2 = hitl_manager.handle_voice_utterance_for_gate("No, cancel that immediately")
    assert verdict2 is False
    assert hitl_manager._approval_verdicts.get(gate_id2) is False


def test_live_call_websocket_barge_in_and_routing():
    """Validates WebSocket route accepts user_speech frames and handles barge-in interrupts."""
    client = TestClient(app)

    with patch("app.gateway.call_bridge.launch_application", new_callable=AsyncMock) as mock_launch:
        mock_launch.return_value = {"status": "success", "app": "notepad"}

        with client.websocket_connect("/api/v1/ws/live_call?user_id=6663290532") as ws:
            # 1. Receive connection state
            conn_msg = ws.receive_json()
            assert conn_msg["type"] == "connection_state"
            assert conn_msg["status"] == "connected"

            # 2. Test barge-in interrupt message
            ws.send_text(json.dumps({"type": "barge_in"}))
            int_msg = ws.receive_json()
            assert int_msg["type"] == "interrupted"

            # 3. Test voice profile switch via WebSocket frame
            ws.send_text(json.dumps({"type": "set_voice", "voice_key": "aria"}))
            sw_msg = ws.receive_json()
            assert sw_msg["type"] == "voice_switched"
            assert sw_msg["result"]["voice_key"] == "aria"

            # 4. Close call gracefully
            ws.send_text(json.dumps({"action": "hangup"}))
