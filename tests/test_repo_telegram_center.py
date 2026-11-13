"""
Unit & Integration Tests for RepoAppScanner, Telegram Menu Builder, and Gateway Callback Router.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.core.repo_scanner import RepoAppScanner
from app.gateway.telegram_menu import build_dynamic_control_center, get_control_center_message_text
from app.gateway.telegram_bot import TelegramGatewayBot


# ============================================================================
# 1. Tests for RepoAppScanner
# ============================================================================

def test_repo_scanner_discovers_applications():
    """Verify scanner extracts apps with mandatory metadata keys."""
    apps = RepoAppScanner.get_all_registered_apps()
    assert isinstance(apps, list)
    assert len(apps) >= 5, "Expected scanner to discover standard registered applications"

    aliases = [a["alias_key"] for a in apps]
    # Check essential apps
    assert any(a in aliases for a in ["chrome", "spotify", "notepad", "calculator", "explorer"])

    for item in apps:
        assert "alias_key" in item
        assert "display_name" in item
        assert "emoji" in item
        assert "category" in item
        assert len(item["display_name"]) > 0


def test_repo_scanner_deduplication():
    """Verify duplicate entries like 'calc' and 'calculator' are grouped cleanly."""
    apps = RepoAppScanner.get_all_registered_apps()
    calc_entries = [a for a in apps if a["alias_key"] in ("calc", "calculator")]
    assert len(calc_entries) <= 1, "Expected 'calc' and 'calculator' to be deduplicated"


# ============================================================================
# 2. Tests for Dynamic Telegram Menu Builder
# ============================================================================

def test_telegram_menu_builder_grid_layout():
    """Verify inline keyboard generates a 2-column grid with proper callback data."""
    mock_apps = [
        {"alias_key": "notepad", "display_name": "Notepad", "emoji": "📝", "category": "IDEs"},
        {"alias_key": "calc", "display_name": "Calculator", "emoji": "🔢", "category": "Utilities"},
        {"alias_key": "spotify", "display_name": "Spotify", "emoji": "🎵", "category": "Media"},
        {"alias_key": "chrome", "display_name": "Chrome", "emoji": "🌐", "category": "Browsers"},
    ]

    kb = build_dynamic_control_center(page=1, per_page=4, columns=2, custom_apps=mock_apps)
    grid = kb["inline_keyboard"]

    assert len(grid) >= 3  # 2 app rows + 1 action row
    # Row 1 has 2 buttons
    assert len(grid[0]) == 2
    assert grid[0][0]["callback_data"] == "launch:notepad"
    assert "📝" in grid[0][0]["text"]
    assert grid[0][1]["callback_data"] == "launch:calc"

    # Row 2 has 2 buttons
    assert len(grid[1]) == 2
    assert grid[1][0]["callback_data"] == "launch:spotify"
    assert grid[1][1]["callback_data"] == "launch:chrome"

    # Action row at the end
    action_row = grid[-1]
    callbacks = [b["callback_data"] for b in action_row]
    assert "action:screenshot" in callbacks
    assert "action:rescan" in callbacks


def test_telegram_menu_pagination():
    """Verify pagination controls render when apps exceed per_page."""
    mock_apps = [{"alias_key": f"app_{i}", "display_name": f"App {i}", "emoji": "🚀", "category": "General"} for i in range(12)]

    # Page 1 of 2 (6 per page)
    kb_p1 = build_dynamic_control_center(page=1, per_page=6, columns=2, custom_apps=mock_apps)
    grid_p1 = kb_p1["inline_keyboard"]

    # Check for nav row
    nav_found = False
    for r in grid_p1:
        cbs = [b["callback_data"] for b in r]
        if any("menu:page:" in cb for cb in cbs):
            nav_found = True
            assert any(b["callback_data"] == "menu:page:2" for b in r)
            break
    assert nav_found, "Pagination navigation row was not found on page 1"

    # Page 2 of 2
    kb_p2 = build_dynamic_control_center(page=2, per_page=6, columns=2, custom_apps=mock_apps)
    grid_p2 = kb_p2["inline_keyboard"]
    nav_found_p2 = False
    for r in grid_p2:
        cbs = [b["callback_data"] for b in r]
        if any("menu:page:1" in cb for cb in cbs):
            nav_found_p2 = True
            break
    assert nav_found_p2, "Pagination previous link was not found on page 2"


# ============================================================================
# 3. Tests for TelegramGatewayBot Callback Router
# ============================================================================

@pytest.mark.asyncio
async def test_telegram_gateway_handle_command():
    """Verify /menu command dispatches send_menu."""
    with patch("app.services.messaging.telegram_service.send_menu", new_callable=AsyncMock) as mock_send_menu:
        await TelegramGatewayBot.handle_command(chat_id="12345", command="/menu")
        mock_send_menu.assert_called_once()
        call_kwargs = mock_send_menu.call_args.kwargs
        assert call_kwargs["chat_id"] == "12345"
        assert "inline_keyboard" in call_kwargs["reply_markup"]


@pytest.mark.asyncio
async def test_telegram_gateway_callback_launch():
    """Verify callback 'launch:notepad' invokes launch_application and captures screenshot."""
    fake_query = {
        "id": "query_999",
        "from": {"id": 6663290532},  # authorized chat id in settings
        "message": {"message_id": 101, "chat": {"id": 6663290532}},
        "data": "launch:notepad",
    }

    with patch("app.core.security.is_telegram_user_whitelisted", return_value=True), \
         patch("app.gateway.telegram_bot.launch_application", new_callable=AsyncMock) as mock_launch, \
         patch("app.gateway.telegram_bot.capture_desktop_screenshot", new_callable=AsyncMock) as mock_shot, \
         patch("app.services.messaging.telegram_service.answer_callback_query", new_callable=AsyncMock) as mock_answer, \
         patch("app.services.messaging.telegram_service.send_text", new_callable=AsyncMock) as mock_send_text, \
         patch("app.services.messaging.telegram_service.send_image", new_callable=AsyncMock) as mock_send_image:

        mock_launch.return_value = {"status": "success", "app": "notepad", "message": "Notepad launched"}
        mock_shot.return_value = "workspace/test_proof.png"

        res = await TelegramGatewayBot.handle_callback_query(fake_query)

        assert res["status"] == "launched"
        assert res["app"] == "notepad"
        mock_launch.assert_called_once_with("notepad")
        mock_shot.assert_called_once()
        mock_answer.assert_called_once()
        mock_send_text.assert_called_once()
        mock_send_image.assert_called_once()


@pytest.mark.asyncio
async def test_telegram_gateway_callback_pagination():
    """Verify menu:page:2 updates reply markup."""
    fake_query = {
        "id": "query_100",
        "from": {"id": 6663290532},
        "message": {"message_id": 202, "chat": {"id": 6663290532}},
        "data": "menu:page:2",
    }

    with patch("app.core.security.is_telegram_user_whitelisted", return_value=True), \
         patch("app.services.messaging.telegram_service.edit_message_reply_markup", new_callable=AsyncMock) as mock_edit, \
         patch("app.services.messaging.telegram_service.answer_callback_query", new_callable=AsyncMock) as mock_answer:

        res = await TelegramGatewayBot.handle_callback_query(fake_query)

        assert res["status"] == "page_changed"
        assert res["page"] == 2
        mock_edit.assert_called_once()
        mock_answer.assert_called_once()


@pytest.mark.asyncio
async def test_telegram_gateway_callback_rescan():
    """Verify action:rescan triggers repository rescan and updates message."""
    fake_query = {
        "id": "query_101",
        "from": {"id": 6663290532},
        "message": {"message_id": 303, "chat": {"id": 6663290532}},
        "data": "action:rescan",
    }

    with patch("app.core.security.is_telegram_user_whitelisted", return_value=True), \
         patch("app.services.messaging.telegram_service.edit_message_reply_markup", new_callable=AsyncMock) as mock_edit, \
         patch("app.services.messaging.telegram_service.answer_callback_query", new_callable=AsyncMock) as mock_answer:

        res = await TelegramGatewayBot.handle_callback_query(fake_query)

        assert res["status"] == "rescanned"
        assert res["total_apps"] >= 5
        mock_edit.assert_called_once()
        mock_answer.assert_called_once()

