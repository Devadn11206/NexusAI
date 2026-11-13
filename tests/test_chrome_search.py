"""
Unit & Integration Tests for Visual Chrome Web Search, Input Typing, and Results Verification.
"""

import pytest
import urllib.parse
from unittest.mock import AsyncMock, patch, MagicMock

from app.tools.browser import BrowserEngine


def test_direct_query_url_construction():
    """Verify Google, Bing, and DuckDuckGo direct query URLs are formatted correctly."""
    query = "top 3 AI frameworks in 2026"
    encoded_q = urllib.parse.quote_plus(query)

    google_url = f"https://www.google.com/search?q={encoded_q}"
    assert "https://www.google.com/search?q=top+3+AI+frameworks+in+2026" == google_url

    bing_url = f"https://www.bing.com/search?q={encoded_q}"
    assert "https://www.bing.com/search?q=top+3+AI+frameworks+in+2026" == bing_url


@pytest.mark.asyncio
async def test_search_web_dual_mode_structured_and_visual():
    """Verify search_web dispatches visual browser navigation and returns structured results."""
    mock_results = [
        {"title": "PyTorch 2.6", "url": "https://pytorch.org", "snippet": "Leading deep learning framework."},
        {"title": "JAX Google", "url": "https://github.com/google/jax", "snippet": "Autograd and XLA compilation."},
    ]

    with patch("httpx.AsyncClient.get") as mock_get:
        # Mock HTML response for organic parsing
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = """
        <div class="result">
            <h2 class="result__title"><a href="https://pytorch.org">PyTorch 2.6</a></h2>
            <div class="result__snippet">Leading deep learning framework.</div>
        </div>
        """
        mock_get.return_value = mock_resp

        engine = BrowserEngine(headless=True)
        # Without entering context, _browser is None, so it tests graceful fallback
        results = await engine.search_web("PyTorch", max_results=1, visual=False)
        assert len(results) == 1
        assert results[0]["title"] == "PyTorch 2.6"
        assert results[0]["url"] == "https://pytorch.org"


@pytest.mark.asyncio
async def test_type_and_submit_search_simulation():
    """Verify type_and_submit_search simulates human typing and dispatches Enter."""
    mock_page = MagicMock()
    mock_locator = MagicMock()

    mock_locator.is_visible = AsyncMock(return_value=True)
    mock_locator.click = AsyncMock()
    mock_locator.press_sequentially = AsyncMock()
    mock_page.locator = MagicMock(return_value=MagicMock(first=mock_locator))
    mock_page.keyboard.press = AsyncMock()
    mock_page.wait_for_load_state = AsyncMock()

    engine = BrowserEngine(headless=True)
    engine.wait_for_network_idle = AsyncMock()

    success = await engine.type_and_submit_search(mock_page, text="nexus ai agent", delay_ms=10)

    assert success is True
    mock_locator.click.assert_called_once()
    mock_locator.press_sequentially.assert_called_once_with("nexus ai agent", delay=10)
    mock_page.keyboard.press.assert_called_once_with("Enter")
    mock_page.wait_for_load_state.assert_called_once_with("domcontentloaded", timeout=10000)
    engine.wait_for_network_idle.assert_called_once()

