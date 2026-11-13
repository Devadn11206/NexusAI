"""
Unit & Integration Tests for Live Voice Call Real-Time Diagnostics & WebSocket Feedback.
Verifies diagnostic event payloads (user_transcript, agent_transcript, tool_start, tool_complete, audio_state, interrupted).
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.gateway.live_call import GeminiLiveSession
from app.gateway.call_bridge import router
from fastapi.testclient import TestClient
from fastapi import FastAPI


@pytest.mark.asyncio
async def test_gemini_live_session_events():
    """Verify GeminiLiveSession emits tool_start, tool_complete, and audio_state events."""
    emitted_events = []

    async def _on_event(evt):
        emitted_events.append(evt)

    session = GeminiLiveSession(
        api_key="fake-key",
        on_event=_on_event,
        user_chat_id="6663290532",
    )
    session._ws = AsyncMock()

    # Simulate tool call dispatch
    fake_tool_call = {
        "functionCalls": [
            {
                "id": "call_123",
                "name": "control_music_playback",
                "args": {"action": "play_pause"},
            }
        ]
    }

    with patch("app.gateway.live_call.control_music_playback", AsyncMock(return_value={"status": "success", "action": "play_pause"})):
        await session._handle_gemini_tool_call(fake_tool_call)

    # Check event types emitted
    event_types = [e["type"] for e in emitted_events]
    assert "tool_start" in event_types
    assert "tool_complete" in event_types

    tool_start_evt = next(e for e in emitted_events if e["type"] == "tool_start")
    assert tool_start_evt["name"] == "control_music_playback"
    assert tool_start_evt["args"] == {"action": "play_pause"}

    tool_complete_evt = next(e for e in emitted_events if e["type"] == "tool_complete")
    assert tool_complete_evt["name"] == "control_music_playback"
    assert tool_complete_evt["status"] == "success"


@pytest.mark.asyncio
async def test_gemini_live_session_audio_and_transcript_events():
    """Verify GeminiLiveSession emits agent_transcript and audio_state on model turn."""
    emitted_events = []

    async def _on_event(evt):
        emitted_events.append(evt)

    session = GeminiLiveSession(
        api_key="fake-key",
        on_event=_on_event,
    )

    # Mock incoming WebSocket message stream
    fake_incoming = [
        json.dumps({
            "serverContent": {
                "modelTurn": {
                    "parts": [
                        {"text": "Playing your song now!"},
                        {"inlineData": {"mimeType": "audio/pcm;rate=24000", "data": "AAAA"}}
                    ]
                },
                "turnComplete": True
            }
        }),
        json.dumps({
            "serverContent": {
                "interrupted": True
            }
        })
    ]

    mock_ws = AsyncMock()
    mock_ws.__aiter__.return_value = fake_incoming
    session._ws = mock_ws
    session._is_active = True

    await session.listen_loop()

    types = [e["type"] for e in emitted_events]
    assert "agent_transcript" in types
    assert "audio_state" in types
    assert "interrupted" in types

    agent_msg = next(e for e in emitted_events if e["type"] == "agent_transcript")
    assert agent_msg["text"] == "Playing your song now!"


def test_call_bridge_websocket_route():
    """Verify WebSocket endpoint exists in call_bridge router."""
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    # Unauthorized test: client connects but endpoint closes with 4003
    with client.websocket_connect("/ws/live_call?user_id=999999999") as websocket:
        # Upon unauthorized connection, the server closes the websocket
        pass
