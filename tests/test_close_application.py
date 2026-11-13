"""
Unit & Integration Tests for Closing Applications via Telegram & Computer Engine.
Verifies close_application process resolution, task planning decomposition for close requests,
and Telegram bot slash commands (/close <app>) and interactive callback buttons (close:<app>).
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.tools.computer import close_application
from app.core.planner import TaskPlanner
from app.gateway.telegram_bot import TelegramGatewayBot


@pytest.mark.asyncio
async def test_close_application_process_resolution():
    """Verify close_application finds and terminates target process by alias."""
    mock_proc = MagicMock()
    mock_proc.info = {"pid": 12345, "name": "notepad.exe"}
    mock_proc.terminate = MagicMock()

    with patch("psutil.process_iter", return_value=[mock_proc]):
        res = await close_application("notepad")
        assert res["status"] == "success"
        assert res["terminated_count"] == 1
        mock_proc.terminate.assert_called_once()


@pytest.mark.asyncio
async def test_close_application_not_found():
    """Verify close_application returns not_found when no matching process exists."""
    with patch("psutil.process_iter", return_value=[]):
        res = await close_application("nonexistent_app_xyz")
        assert res["status"] == "not_found"
        assert res["terminated_count"] == 0


@pytest.mark.asyncio
async def test_planner_close_application_dag():
    """Verify TaskPlanner maps 'close <app>' prompts to ComputerAgent.close_application."""
    planner = TaskPlanner()
    for phrase in ["close notepad", "quit chrome", "close spotify", "terminate calculator"]:
        plan = await planner.generate_plan(phrase)
        assert len(plan.steps) == 1
        step = plan.steps[0]
        assert step.target_agent.value == "ComputerAgent"
        assert step.tool_name == "close_application"
        assert "process_name" in step.tool_params


@pytest.mark.asyncio
async def test_telegram_gateway_close_command():
    """Verify TelegramGatewayBot /close command terminates app and responds."""
    with patch("app.gateway.telegram_bot.close_application", AsyncMock(return_value={"status": "success", "terminated_count": 1})) as mock_close, \
         patch("app.gateway.telegram_bot.telegram_service.send_text", AsyncMock()) as mock_send, \
         patch("app.gateway.telegram_bot.TelegramGatewayBot.handle_screenshot_action", AsyncMock()):

        await TelegramGatewayBot.handle_command(chat_id="6663290532", command="/close notepad")
        mock_close.assert_called_with("notepad")
        mock_send.assert_called_once()
        assert "Closed Application" in mock_send.call_args[1]["text"]


@pytest.mark.asyncio
async def test_telegram_gateway_close_callback():
    """Verify TelegramGatewayBot handles close:<app> callback button click."""
    fake_query = {
        "id": "query_close_1",
        "from": {"id": 6663290532},
        "message": {"message_id": 101, "chat": {"id": 6663290532}},
        "data": "close:spotify",
    }

    with patch("app.gateway.telegram_bot.close_application", AsyncMock(return_value={"status": "success", "terminated_count": 1})) as mock_close, \
         patch("app.gateway.telegram_bot.telegram_service.answer_callback_query", AsyncMock()) as mock_ans, \
         patch("app.gateway.telegram_bot.telegram_service.send_text", AsyncMock()) as mock_send, \
         patch("app.gateway.telegram_bot.TelegramGatewayBot.handle_screenshot_action", AsyncMock()):

        res = await TelegramGatewayBot.handle_callback_query(fake_query)
        assert res["status"] == "closed"
        assert res["app"] == "spotify"
        mock_close.assert_called_with("spotify")
