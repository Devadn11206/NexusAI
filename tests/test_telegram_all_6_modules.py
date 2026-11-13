"""
NEXUS AI - Comprehensive 6-Module Telegram Command Center Test Suite
Tests 100% zero-typing inline button control, deck rendering, callback dispatch,
telemetry header, HITL gates, music controls, developer actions, and macros.
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from app.gateway.telegram_hub import (
    load_hub_state,
    save_hub_state,
    get_live_telemetry_header,
    build_master_hub_deck,
    build_m1_deck,
    build_m2_deck,
    build_m3_deck,
    build_m4_deck,
    build_m5_deck,
    build_m6_deck,
    build_macros_deck,
    publish_or_update_master_hub,
    handle_hub_callback,
    get_persistent_bottom_keyboard,
)
from app.gateway.telegram_bot import TelegramGatewayBot


@pytest.fixture
def mock_messaging(monkeypatch):
    """Mocks telegram_service outbound methods for fast, deterministic unit testing."""
    mock_send_menu = AsyncMock(return_value={"ok": True, "result": {"message_id": 999}})
    mock_edit_markup = AsyncMock(return_value={"ok": True, "result": {"message_id": 999}})
    mock_send_text = AsyncMock(return_value={"ok": True, "result": {"message_id": 1000}})
    mock_send_image = AsyncMock(return_value={"ok": True, "result": {"message_id": 1001}})
    mock_send_voice = AsyncMock(return_value={"ok": True, "result": {"message_id": 1002}})
    mock_send_doc = AsyncMock(return_value={"ok": True, "result": {"message_id": 1003}})
    mock_pin_msg = AsyncMock(return_value={"ok": True})
    mock_answer_cb = AsyncMock(return_value={"ok": True})
    mock_menu_btn = AsyncMock(return_value={"ok": True})

    monkeypatch.setattr("app.services.messaging.telegram_service.send_menu", mock_send_menu)
    monkeypatch.setattr("app.services.messaging.telegram_service.edit_message_reply_markup", mock_edit_markup)
    monkeypatch.setattr("app.services.messaging.telegram_service.send_text", mock_send_text)
    monkeypatch.setattr("app.services.messaging.telegram_service.send_image", mock_send_image)
    monkeypatch.setattr("app.services.messaging.telegram_service.send_voice", mock_send_voice)
    monkeypatch.setattr("app.services.messaging.telegram_service.send_document", mock_send_doc)
    monkeypatch.setattr("app.services.messaging.telegram_service.pin_chat_message", mock_pin_msg)
    monkeypatch.setattr("app.services.messaging.telegram_service.answer_callback_query", mock_answer_cb)
    monkeypatch.setattr("app.services.messaging.telegram_service.set_chat_menu_button", mock_menu_btn)

    # Whitelist test user
    monkeypatch.setattr("app.core.security.is_telegram_user_whitelisted", lambda uid: True)

    return {
        "send_menu": mock_send_menu,
        "edit_markup": mock_edit_markup,
        "send_text": mock_send_text,
        "send_image": mock_send_image,
        "send_voice": mock_send_voice,
        "send_doc": mock_send_doc,
        "pin_msg": mock_pin_msg,
        "answer_cb": mock_answer_cb,
    }


@pytest.mark.asyncio
async def test_live_telemetry_header():
    """Verify live telemetry header returns active window, audio, and tasks count."""
    header = await get_live_telemetry_header()
    assert "Active" in header
    assert "Audio" in header
    assert "Async Tasks" in header
    assert "Approvals" in header


@pytest.mark.asyncio
async def test_master_hub_deck_structure():
    """Verify Master Hub deck has navigation buttons for all 6 modules and macros."""
    deck = await build_master_hub_deck()
    assert "text" in deck
    assert "reply_markup" in deck
    kb = deck["reply_markup"]["inline_keyboard"]
    all_callbacks = [btn["callback_data"] for row in kb for btn in row]

    assert "hub:m1" in all_callbacks
    assert "hub:m2" in all_callbacks
    assert "hub:m3" in all_callbacks
    assert "hub:m4" in all_callbacks
    assert "hub:m5" in all_callbacks
    assert "hub:m6" in all_callbacks
    assert "hub:macros" in all_callbacks
    assert "hub:run_clipboard" in all_callbacks


@pytest.mark.asyncio
async def test_sub_deck_generation():
    """Verify sub-deck keyboards generate cleanly with Back and Master Hub buttons."""
    m1 = await build_m1_deck()
    m2 = await build_m2_deck()
    m3 = await build_m3_deck()
    m4 = await build_m4_deck()
    m5 = await build_m5_deck()
    m6 = await build_m6_deck()
    mac = build_macros_deck()

    for d in [m1, m2, m3, m4, m5, m6, mac]:
        assert "text" in d
        assert "reply_markup" in d
        kb = d["reply_markup"]["inline_keyboard"]
        footer = kb[-1]
        footer_callbacks = [b["callback_data"] for b in footer]
        assert "hub:main" in footer_callbacks


@pytest.mark.asyncio
async def test_persistent_bottom_keyboard():
    """Verify the persistent bottom 1-tap remote keyboard configuration."""
    kb = get_persistent_bottom_keyboard()
    assert kb.get("is_persistent") is True
    assert kb.get("resize_keyboard") is True
    rows = kb.get("keyboard", [])
    assert len(rows) == 2
    button_texts = [btn["text"] for row in rows for btn in row]
    assert "🏠 Master Hub" in button_texts
    assert "⏯️ Play/Pause" in button_texts
    assert "📸 Screenshot" in button_texts


@pytest.mark.asyncio
async def test_publish_and_update_master_hub(mock_messaging):
    """Verify Master Hub publishes, pins, and updates in place."""
    chat_id = "6663290532"
    # First publication: creates message & pins it
    res1 = await publish_or_update_master_hub(chat_id=chat_id, target_deck="hub:main", edit_in_place=False)
    assert res1["status"] == "created"
    assert res1["message_id"] == 999
    assert mock_messaging["send_menu"].called
    assert mock_messaging["pin_msg"].called

    # In-place edit of existing message
    res2 = await publish_or_update_master_hub(chat_id=chat_id, target_deck="hub:m1", edit_in_place=True)
    assert res2["status"] == "edited"
    assert mock_messaging["edit_markup"].called


@pytest.mark.asyncio
async def test_callback_navigation_and_ack(mock_messaging):
    """Verify handle_hub_callback acknowledges queries instantly and navigates."""
    cb = {
        "id": "cb_test_001",
        "from": {"id": 6663290532},
        "message": {"message_id": 999, "chat": {"id": 6663290532}},
        "data": "hub:m2",
    }
    res = await handle_hub_callback(cb)
    assert res["status"] == "navigated"
    assert res["target"] == "hub:m2"
    assert mock_messaging["answer_cb"].called


@pytest.mark.asyncio
async def test_m1_voice_switching(mock_messaging):
    """Verify M1 neural voice switching updates active voice profile."""
    cb = {
        "id": "cb_v_001",
        "from": {"id": 6663290532},
        "message": {"message_id": 999, "chat": {"id": 6663290532}},
        "data": "m1:set_v:aria",
    }
    res = await handle_hub_callback(cb)
    assert res["status"] == "voice_updated"
    assert res["voice"] == "aria"


@pytest.mark.asyncio
async def test_m2_volume_and_screenshot(mock_messaging, monkeypatch):
    """Verify M2 desktop volume adjustment and screenshot callbacks."""
    cb_vol = {
        "id": "cb_vol_001",
        "from": {"id": 6663290532},
        "message": {"message_id": 999, "chat": {"id": 6663290532}},
        "data": "m2:vol_up",
    }
    res_vol = await handle_hub_callback(cb_vol)
    assert res_vol["status"] == "vol_adjusted"

    # Screenshot callback
    monkeypatch.setattr(
        "app.gateway.telegram_hub.capture_desktop_screenshot",
        AsyncMock(return_value="workspace/images/control_center_screen.png")
    )
    cb_shot = {
        "id": "cb_shot_001",
        "from": {"id": 6663290532},
        "message": {"message_id": 999, "chat": {"id": 6663290532}},
        "data": "m2:screenshot",
    }
    res_shot = await handle_hub_callback(cb_shot)
    assert res_shot["status"] == "screenshot_sent"
    assert mock_messaging["send_image"].called


@pytest.mark.asyncio
async def test_m4_media_controls_and_dj(mock_messaging):
    """Verify M4 play/pause, volume, and AI DJ playlist generation."""
    cb_play = {
        "id": "cb_play_001",
        "from": {"id": 6663290532},
        "message": {"message_id": 999, "chat": {"id": 6663290532}},
        "data": "m4:play_pause",
    }
    res_play = await handle_hub_callback(cb_play)
    assert res_play["status"] == "media_toggled"

    # DJ mix
    cb_dj = {
        "id": "cb_dj_001",
        "from": {"id": 6663290532},
        "message": {"message_id": 999, "chat": {"id": 6663290532}},
        "data": "m4:dj:tamil",
    }
    res_dj = await handle_hub_callback(cb_dj)
    assert res_dj["status"] == "dj_mix_generated"
    assert res_dj["mix"] == "tamil"


@pytest.mark.asyncio
async def test_m6_competitive_programming_solver(mock_messaging):
    """Verify M6 LeetCode/CodeChef CP solver executes and sends solution code."""
    cb_cp = {
        "id": "cb_cp_001",
        "from": {"id": 6663290532},
        "message": {"message_id": 999, "chat": {"id": 6663290532}},
        "data": "m6:cp_solve",
    }
    res_cp = await handle_hub_callback(cb_cp)
    assert res_cp["status"] == "cp_solved"
    assert mock_messaging["send_text"].called


@pytest.mark.asyncio
async def test_macros_execution(mock_messaging, monkeypatch):
    """Verify 1-Tap composite macros (ML Study, Meeting Mode, Sleep)."""
    monkeypatch.setattr("app.gateway.telegram_hub.launch_application", AsyncMock(return_value={"status": "ok"}))

    cb_macro = {
        "id": "cb_mac_001",
        "from": {"id": 6663290532},
        "message": {"message_id": 999, "chat": {"id": 6663290532}},
        "data": "macro:ml_study",
    }
    res_m = await handle_hub_callback(cb_macro)
    assert res_m["status"] == "macro_executed"
    assert res_m["macro"] == "ml_study"


@pytest.mark.asyncio
async def test_slash_command_hub_integration(mock_messaging):
    """Verify TelegramGatewayBot.handle_command('/hub') publishes master hub."""
    await TelegramGatewayBot.handle_command(chat_id="6663290532", command="/hub")
    assert mock_messaging["send_menu"].called

