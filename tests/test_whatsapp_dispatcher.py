"""
Unit & Integration Tests for Persistent WhatsApp Web Remote Dispatcher.
Tests target file search/resolution, persistent profile paths, and execution mock routines.
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from app.tools.whatsapp import find_target_file, send_whatsapp_file, WHATSAPP_USER_DATA_DIR


def test_find_target_file_resolution(tmp_path):
    """Verify target file search locates exact and partial workspace files."""
    test_pdf = tmp_path / "quarterly_budget.pdf"
    test_pdf.write_bytes(b"%PDF-1.4 dummy content")

    def mock_resolve(path_str):
        candidate = tmp_path / path_str
        return candidate

    with patch("app.tools.whatsapp.resolve_safe_workspace_path", side_effect=mock_resolve), \
         patch("app.tools.whatsapp.settings") as mock_settings:
        mock_settings.WORKSPACE_DIR = str(tmp_path)

        # Exact match
        found = find_target_file("quarterly_budget.pdf")
        assert found is not None
        assert found.name == "quarterly_budget.pdf"

        # Nonexistent file
        none_found = find_target_file("nonexistent_file_xyz.xlsx")
        assert none_found is None


def test_whatsapp_profile_directory_path():
    """Verify persistent user_data_dir path is standard and isolated inside workspace."""
    p = Path(WHATSAPP_USER_DATA_DIR)
    assert "sessions" in str(p)
    assert "whatsapp_profile" in str(p)


@pytest.mark.asyncio
async def test_send_whatsapp_file_missing_target(tmp_path):
    """Verify send_whatsapp_file fast-fails when target file cannot be found."""
    with patch("app.tools.whatsapp.find_target_file", return_value=None):
        res = await send_whatsapp_file(
            contact_name="Alex",
            file_query="missing_report.docx",
            caption="Here is the report"
        )
        assert res["status"] == "failed"
        assert "not found" in res["error"]


@pytest.mark.asyncio
async def test_send_whatsapp_file_mock_flow(tmp_path):
    """Verify send_whatsapp_file executes Playwright flow, attaches file, and captures proof."""
    dummy_file = tmp_path / "report.pdf"
    dummy_file.write_text("dummy pdf data")

    fake_page = MagicMock()
    fake_page.goto = AsyncMock()
    fake_page.screenshot = AsyncMock()
    fake_page.wait_for_timeout = AsyncMock()
    fake_page.keyboard.press = AsyncMock()

    # Search box locator
    mock_search = MagicMock()
    mock_search.is_visible = AsyncMock(return_value=True)
    mock_search.click = AsyncMock()
    mock_search.fill = AsyncMock()
    mock_search.press_sequentially = AsyncMock()

    # File input locator
    mock_file_input = MagicMock()
    mock_file_input.set_input_files = AsyncMock()

    # Send button locator
    mock_send = MagicMock()
    mock_send.is_visible = AsyncMock(return_value=True)
    mock_send.click = AsyncMock()

    # QR code check locator
    mock_qr = MagicMock()
    mock_qr.is_visible = AsyncMock(return_value=False)

    def mock_locator(sel):
        if "QR code" in sel:
            return mock_qr
        elif "type='file'" in sel:
            return MagicMock(first=mock_file_input)
        elif "send" in sel:
            return MagicMock(first=mock_send)
        else:
            return MagicMock(first=mock_search)

    fake_page.locator = MagicMock(side_effect=mock_locator)

    fake_context = MagicMock()
    fake_context.pages = [fake_page]
    fake_context.close = AsyncMock()

    fake_playwright = MagicMock()
    fake_playwright.chromium.launch_persistent_context = AsyncMock(return_value=fake_context)

    with patch("app.tools.whatsapp.find_target_file", return_value=dummy_file), \
         patch("app.tools.whatsapp.async_playwright") as mock_pw_ctx:
        mock_pw_ctx.return_value.__aenter__.return_value = fake_playwright

        res = await send_whatsapp_file(
            contact_name="Manager",
            file_query="report.pdf",
            caption="Quarterly Report",
            headless=True,
        )

        assert res["status"] == "success"
        assert res["contact"] == "Manager"
        mock_file_input.set_input_files.assert_called_once_with(str(dummy_file))
        fake_page.screenshot.assert_called_once()
        assert "proof_screenshot" in res
