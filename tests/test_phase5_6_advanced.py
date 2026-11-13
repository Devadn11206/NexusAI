"""
Unit & Integration Tests for Phase 5 (Browser Engine) & Phase 6 (OS Control) Advanced Features.
Validates session vaulting, API interception, multi-monitor geometry detection, and visual element locating.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path

from app.tools.browser import BrowserEngine
from app.tools.computer import get_screen_geometry, click_visual_element


# ============================================================================
# 1. Tests for Phase 5 Advanced Browser Capabilities
# ============================================================================

@pytest.mark.asyncio
async def test_session_state_vaulting(tmp_path):
    """Verify save_session_state and load_session_state save and restore session JSON."""
    engine = BrowserEngine(headless=True)
    fake_context = MagicMock()
    fake_context.storage_state = AsyncMock()

    # Test saving
    target_path = await engine.save_session_state(fake_context, session_id="test_session")
    assert "test_session.json" in target_path
    fake_context.storage_state.assert_called_once()

    # Create dummy session file to test loading
    session_file = Path(target_path)
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_file.write_text('{"cookies": [{"name": "auth_token", "value": "xyz123"}]}', encoding="utf-8")

    loaded_data = await engine.load_session_state("test_session")
    assert loaded_data is not None
    assert "cookies" in loaded_data
    assert loaded_data["cookies"][0]["value"] == "xyz123"


@pytest.mark.asyncio
async def test_network_api_interception():
    """Verify intercept_network_api calls intercept_api_responses with correct params."""
    engine = BrowserEngine(headless=True)
    with patch.object(engine, "intercept_api_responses", new_callable=AsyncMock) as mock_intercept:
        mock_intercept.return_value = [{"url": "https://api.example.com/v1/user", "status": 200, "payload": {"id": 1}}]

        results = await engine.intercept_network_api("https://example.com", target_url_pattern="api.example.com")
        assert len(results) == 1
        assert results[0]["status"] == 200
        mock_intercept.assert_called_once_with("https://example.com", "api.example.com", 10000)


# ============================================================================
# 2. Tests for Phase 6 Advanced OS & Desktop Control Capabilities
# ============================================================================

@pytest.mark.asyncio
async def test_screen_geometry_detection():
    """Verify get_screen_geometry returns valid resolution and monitor configuration."""
    geom = await get_screen_geometry()
    assert geom["status"] == "success"
    assert "primary_resolution" in geom
    assert geom["primary_resolution"]["width"] > 0
    assert geom["primary_resolution"]["height"] > 0
    assert geom["total_monitors"] >= 1
    assert isinstance(geom["monitors"], list)


@pytest.mark.asyncio
async def test_click_visual_element_fallback():
    """Verify click_visual_element executes anchor fallback when template is missing."""
    res = await click_visual_element(template_image_path="nonexistent_template.png", text_label="Login Button")
    assert res["status"] in ("fallback", "success")
    assert "coordinates" in res
    assert res["coordinates"]["x"] > 0
    assert res["coordinates"]["y"] > 0

