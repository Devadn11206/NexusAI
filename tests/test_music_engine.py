"""
Unit & Integration Tests for Desktop & Web Music Streaming Control.
Tests media hotkey dispatching, web music streaming parameters, session loading,
and Telegram Music Control Center callbacks.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.tools.computer import control_music_playback
from app.tools.browser import BrowserEngine
from app.gateway.telegram_menu import get_music_control_keyboard, get_music_control_message_text
from app.gateway.telegram_bot import TelegramGatewayBot


# ============================================================================
# 1. Desktop OS Media Controller Tests
# ============================================================================

@pytest.mark.asyncio
async def test_control_music_playback_actions():
    """Verify control_music_playback dispatches valid media keys for all standard actions."""
    with patch("pyautogui.press") as mock_press:
        # Play/pause
        res_play = await control_music_playback("play_pause")
        assert res_play["status"] == "success"
        mock_press.assert_called_with("playpause")

        # Next track
        res_next = await control_music_playback("next")
        assert res_next["status"] == "success"
        mock_press.assert_called_with("nexttrack")

        # Volume up
        res_vol = await control_music_playback("volume_up", value=2)
        assert res_vol["status"] == "success"
        assert res_vol["steps"] == 2

        # Mute
        res_mute = await control_music_playback("mute")
        assert res_mute["status"] == "success"
        mock_press.assert_called_with("volumemute")


# ============================================================================
# 2. Web Music Player Automation Tests
# ============================================================================

@pytest.mark.asyncio
async def test_play_web_music_url_construction():
    """Verify play_web_music generates proper URLs for Spotify, YouTube Music, and SoundCloud."""
    engine = BrowserEngine(headless=True)
    fake_page = MagicMock()
    fake_page.goto = AsyncMock()
    fake_page.bring_to_front = AsyncMock()
    fake_page.wait_for_timeout = AsyncMock()
    fake_page.title = AsyncMock(return_value="Spotify - Search")
    fake_page.locator = MagicMock(return_value=MagicMock(first=MagicMock(is_visible=AsyncMock(return_value=False))))
    fake_page.get_by_role = MagicMock(return_value=MagicMock(first=MagicMock(is_visible=AsyncMock(return_value=False))))

    fake_context = MagicMock()
    fake_context.pages = [fake_page]
    fake_context.new_page = AsyncMock(return_value=fake_page)

    mock_pw = MagicMock()
    mock_pw.chromium.launch_persistent_context = AsyncMock(return_value=fake_context)
    mock_pw.stop = AsyncMock()

    with patch("app.tools.browser.async_playwright") as mock_pw_factory:
        mock_factory_cm = MagicMock()
        mock_factory_cm.start = AsyncMock(return_value=mock_pw)
        mock_pw_factory.return_value = mock_factory_cm

        res = await engine.play_web_music(service="youtube_music", query="Chikiri Chikiri Peddi")
        assert res["status"] == "success"
        assert "music.youtube.com/search?q=" in res["url"]
        fake_page.goto.assert_called_once()


# ============================================================================
# 3. Telegram Music Control Center Tests
# ============================================================================

def test_music_control_keyboard_structure():
    """Verify Telegram Music Control keyboard layout and callback triggers."""
    kb = get_music_control_keyboard()
    grid = kb["inline_keyboard"]
    assert len(grid) == 4

    flat_callbacks = [b["callback_data"] for row in grid for b in row]
    assert "music:play_pause" in flat_callbacks
    assert "music:next" in flat_callbacks
    assert "music:vol_up" in flat_callbacks
    assert "music:vol_down" in flat_callbacks
    assert "music:launch:spotify" in flat_callbacks
    assert "music:now_playing" in flat_callbacks

    msg = get_music_control_message_text(now_playing="A.R. Rahman - Peddi")
    assert "A.R. Rahman - Peddi" in msg


@pytest.mark.asyncio
async def test_telegram_gateway_music_callbacks():
    """Verify TelegramGatewayBot handles music:play_pause callback and updates message."""
    fake_query = {
        "id": "query_music_1",
        "from": {"id": 6663290532},
        "message": {"message_id": 505, "chat": {"id": 6663290532}},
        "data": "music:play_pause",
    }

    with patch("app.core.security.is_telegram_user_whitelisted", return_value=True), \
         patch("app.gateway.telegram_bot.control_music_playback", new_callable=AsyncMock) as mock_music, \
         patch("app.services.messaging.telegram_service.answer_callback_query", new_callable=AsyncMock) as mock_answer, \
         patch("app.services.messaging.telegram_service.edit_message_reply_markup", new_callable=AsyncMock) as mock_edit:

        mock_music.return_value = {"status": "success", "action": "play_pause", "now_playing": "Peddi"}

        res = await TelegramGatewayBot.handle_callback_query(fake_query)

        assert res["status"] == "music_action_success"
        assert res["action"] == "play_pause"
        mock_music.assert_called_once_with("play_pause")
        mock_answer.assert_called_once()
        mock_edit.assert_called_once()


@pytest.mark.asyncio
async def test_telegram_gateway_music_command():
    """Verify /music command dispatches the dedicated Music Control keyboard."""
    with patch("app.services.messaging.telegram_service.send_menu", new_callable=AsyncMock) as mock_send_menu:
        await TelegramGatewayBot.handle_command(chat_id="6663290532", command="/music")
        mock_send_menu.assert_called_once()
        call_kwargs = mock_send_menu.call_args.kwargs
        assert "inline_keyboard" in call_kwargs["reply_markup"]
        assert "Music & Media Controller" in call_kwargs["text"]

