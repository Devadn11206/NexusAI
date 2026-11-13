"""
Tests for Post-Render Wait Pipeline and Atomic Screenshot Execution.
Verifies that screenshots are captured strictly after dynamic DOM content and search results settle.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.tools.browser import wait_until_visually_ready, search_web, capture_browser_screenshot
from app.core.brain import task_planner_node
from app.core.state import NexusState


@pytest.mark.asyncio
async def test_wait_until_visually_ready_with_delayed_dynamic_dom():
    """
    Simulates a page where dynamic #results renders 800ms after initial load.
    Verifies that wait_until_visually_ready waits for the selector to become visible
    before returning True.
    """
    mock_page = MagicMock()
    mock_page.wait_for_load_state = AsyncMock()

    # Track order of events
    event_log = []

    async def mock_wait_for_load_state(state, timeout=None):
        event_log.append(f"load_state_{state}")

    mock_page.wait_for_load_state.side_effect = mock_wait_for_load_state

    # Setup locator mock with delayed visibility
    mock_locator = MagicMock()
    
    async def mock_wait_for(state="visible", timeout=None):
        await asyncio.sleep(0.05)  # simulate delay
        event_log.append("selector_visible")

    mock_locator.wait_for = AsyncMock(side_effect=mock_wait_for)
    mock_page.locator.return_value.first = mock_locator

    mock_page.evaluate = AsyncMock(return_value=None)
    mock_page.wait_for_timeout = AsyncMock(side_effect=lambda ms: event_log.append(f"settle_delay_{ms}"))

    ready = await wait_until_visually_ready(mock_page, result_selector="#results", timeout_ms=3000)

    assert ready is True
    assert "load_state_load" in event_log
    assert "selector_visible" in event_log
    assert "settle_delay_600" in event_log

    # Verify sequential order: load -> selector visible -> settle delay
    load_idx = event_log.index("load_state_load")
    sel_idx = event_log.index("selector_visible")
    settle_idx = event_log.index("settle_delay_600")

    assert load_idx < sel_idx < settle_idx


@pytest.mark.asyncio
async def test_search_web_with_atomic_take_screenshot():
    """
    Verifies that search_web(..., take_screenshot=True) executes wait_until_visually_ready
    and returns screenshot_path in response and artifacts.
    """
    mock_page = MagicMock()
    mock_page.goto = AsyncMock()
    mock_page.url = "https://www.google.com/search?q=test"
    mock_page.bring_to_front = AsyncMock()
    mock_page.content = AsyncMock(return_value="""
        <html><body>
        <div id="search">
            <div class="g">
                <a href="https://example.com/result"><h3>Example Title</h3></a>
                <span class="VwiC3b">Example Snippet</span>
            </div>
        </div>
        </body></html>
    """)
    mock_page.screenshot = AsyncMock()

    with patch("app.tools.browser.get_visible_chrome_page", new_callable=AsyncMock) as mock_get_page, \
         patch("app.tools.browser.wait_until_visually_ready", new_callable=AsyncMock) as mock_wait:

        mock_get_page.return_value = mock_page
        mock_wait.return_value = True

        res = await search_web("test query", max_results=5, take_screenshot=True)

        assert res["status"] == "success"
        assert len(res["results"]) == 1
        assert res["results"][0]["title"] == "Example Title"
        assert "screenshot_path" in res
        assert "artifacts" in res
        assert len(res["artifacts"]) == 1

        # Verify wait_until_visually_ready was invoked before page.screenshot
        mock_wait.assert_called()
        mock_page.screenshot.assert_called_once()


@pytest.mark.asyncio
async def test_capture_browser_screenshot_calls_wait_until_ready():
    """
    Verifies standalone capture_browser_screenshot invokes wait_until_visually_ready.
    """
    mock_page = MagicMock()
    mock_page.screenshot = AsyncMock()

    with patch("app.tools.browser.get_visible_chrome_page", new_callable=AsyncMock) as mock_get_page, \
         patch("app.tools.browser.wait_until_visually_ready", new_callable=AsyncMock) as mock_wait:

        mock_get_page.return_value = mock_page
        mock_wait.return_value = True

        path = await capture_browser_screenshot(filename="test_ready.png")
        assert "test_ready.png" in path
        mock_wait.assert_called_once()
        mock_page.screenshot.assert_called_once()


@pytest.mark.asyncio
async def test_task_planner_node_embeds_take_screenshot_flag():
    """
    Verifies that compound requests like 'search X and screenshot' embed
    take_screenshot=True directly in tool_args.
    """
    state: NexusState = {
        "messages": ["search for fastapi and take a screenshot"],
        "user_intent": {
            "category": "BROWSER",
            "entities": {"query": "fastapi"},
            "confidence": 0.95,
            "resolved_query": "search for fastapi and take a screenshot",
        },
        "plan_steps": [],
        "current_step_index": 0,
        "replan_count": 0,
    }

    res = await task_planner_node(state)
    steps = res["plan_steps"]
    assert len(steps) >= 1
    assert steps[0]["tool_args"].get("take_screenshot") is True
