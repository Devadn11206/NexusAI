"""
Unit & Integration Tests for Gemini Multimodal Live API Voice Calling Subsystem.
Validates setup payload framing, PCM chunk streaming, function calling, tool response formatting,
and barge-in interruption handling.
"""

import pytest
import asyncio
import json
import base64
from unittest.mock import AsyncMock, patch, MagicMock

from app.gateway.live_call import (
    build_live_setup_payload,
    build_audio_chunk_payload,
    build_tool_response_payload,
    GeminiLiveSession,
    LAPTOP_TOOL_DECLARATIONS,
)


def test_live_setup_payload_structure():
    """Verify setup payload adheres strictly to Gemini Multimodal Live API schema."""
    payload = build_live_setup_payload(model="models/gemini-2.5-flash", voice_name="Puck")
    assert "setup" in payload
    setup = payload["setup"]
    assert setup["model"] == "models/gemini-2.5-flash"
    assert setup["generationConfig"]["responseModalities"] == ["AUDIO"]
    assert setup["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Puck"

    # Verify tool declarations
    assert "tools" in setup
    tools = setup["tools"][0]["functionDeclarations"]
    tool_names = [t["name"] for t in tools]
    assert "launch_application" in tool_names
    assert "search_web" in tool_names
    assert "control_music_playback" in tool_names
    assert "capture_desktop_screenshot" in tool_names


def test_audio_chunk_payload_framing():
    """Verify raw PCM bytes are base64-encoded inside realtimeInput.mediaChunks."""
    raw_pcm = b"\x00\x01\x02\x03" * 100
    chunk = build_audio_chunk_payload(raw_pcm)

    assert "realtimeInput" in chunk
    media_chunks = chunk["realtimeInput"]["mediaChunks"]
    assert len(media_chunks) == 1
    assert media_chunks[0]["mimeType"] == "audio/pcm;rate=16000"
    decoded = base64.b64decode(media_chunks[0]["data"])
    assert decoded == raw_pcm


def test_tool_response_payload_framing():
    """Verify toolResponse is formatted correctly for upstream Gemini acknowledgment."""
    resp_payload = build_tool_response_payload(
        call_id="call_123",
        function_name="launch_application",
        response_data={"status": "success", "app": "spotify"},
    )
    assert "toolResponse" in resp_payload
    func_resps = resp_payload["toolResponse"]["functionResponses"]
    assert len(func_resps) == 1
    assert func_resps[0]["id"] == "call_123"
    assert func_resps[0]["response"]["output"]["status"] == "success"


@pytest.mark.asyncio
async def test_gemini_live_session_tool_dispatch():
    """Verify GeminiLiveSession intercepts toolCall, executes function, and returns toolResponse."""
    mock_ws = MagicMock()
    mock_ws.send = AsyncMock()

    session = GeminiLiveSession(api_key="test_key", user_chat_id="6663290532")
    session._ws = mock_ws
    session._is_active = True

    tool_call_payload = {
        "functionCalls": [
            {
                "id": "call_abc",
                "name": "control_music_playback",
                "args": {"action": "play_pause"},
            }
        ]
    }

    with patch("app.gateway.live_call.control_music_playback", new_callable=AsyncMock) as mock_control, \
         patch("app.gateway.live_call.capture_desktop_screenshot", new_callable=AsyncMock) as mock_shot:

        mock_control.return_value = {"status": "success", "action": "play_pause"}
        mock_shot.return_value = "workspace/test_shot.png"

        await session._handle_gemini_tool_call(tool_call_payload)

        mock_control.assert_called_once_with("play_pause")
        mock_ws.send.assert_called_once()
        sent_data = json.loads(mock_ws.send.call_args[0][0])
        assert "toolResponse" in sent_data
        assert sent_data["toolResponse"]["functionResponses"][0]["id"] == "call_abc"


@pytest.mark.asyncio
async def test_gemini_live_session_barge_in_interruption():
    """Verify user barge-in triggers the on_interrupted callback."""
    interrupted_called = False

    def handle_barge_in():
        nonlocal interrupted_called
        interrupted_called = True

    session = GeminiLiveSession(
        api_key="test_key",
        on_interrupted=handle_barge_in,
    )

    fake_ws_messages = [
        json.dumps({"serverContent": {"interrupted": True}}),
    ]

    mock_ws = MagicMock()
    mock_ws.__aiter__.return_value = fake_ws_messages
    session._ws = mock_ws
    session._is_active = True

    # Run listen loop with 1 message
    listen_task = asyncio.create_task(session.listen_loop())
    await asyncio.sleep(0.05)
    listen_task.cancel()

    assert interrupted_called is True
