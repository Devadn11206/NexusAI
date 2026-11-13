"""Verification Suite for Chrome Search Fix and Browser Automation.
Verifies:
1. "open Chrome and search for <query>" routing directly to browser.search_web in a single atomic step.
2. Direct query-URL navigation with proper URL-encoding.
3. Automatic fallback to DuckDuckGo when Google Search simulates a /sorry/ block.
4. Top organic search results extraction (title, url, snippet).
5. launch_application delegation when called with search query or web URL.
"""

import pytest
import urllib.parse
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import HumanMessage

from app.core.brain import intent_and_context_node, task_planner_node, dispatch_tool_call
from app.tools.browser import search_web
from app.tools.computer import launch_application


@pytest.mark.asyncio
async def test_compound_chrome_search_routing():
    """Verify 'open Chrome and search for X' routes cleanly to search_web without empty launch_application."""
    user_inputs = [
        "open Chrome and search for Python FastAPI tutorials",
        "open browser and search for machine learning papers",
        "search in Chrome for best laptops 2026",
        "google quantum computing breakthroughs",
    ]

    for utterance in user_inputs:
        state = {"messages": [HumanMessage(content=utterance)]}
        intent_res = await intent_and_context_node(state)
        assert intent_res["user_intent"]["category"] == "BROWSER"
        assert len(intent_res["user_intent"]["entities"]["query"]) > 0

        state.update(intent_res)
        plan_res = await task_planner_node(state)
        assert len(plan_res["plan_steps"]) == 1
        step = plan_res["plan_steps"][0]
        assert step["tool_name"] == "search_web"
        assert "query" in step["tool_args"]
        assert len(step["tool_args"]["query"]) > 0


@pytest.mark.asyncio
async def test_search_web_direct_url_and_fallback():
    """Verify search_web navigates to encoded URL and falls back to DuckDuckGo if blocked."""
    query = "Python FastAPI tutorials"
    encoded_query = urllib.parse.quote_plus(query)

    # Mock page and browser context
    mock_page = AsyncMock()
    # Simulate first navigation hitting /sorry/ block
    mock_page.url = f"https://www.google.com/sorry/index?continue=https://www.google.com/search?q={encoded_query}"
    mock_page.content = AsyncMock(return_value="""
        <html><body>
            <article data-testid="result">
                <h2><a href="https://fastapi.tiangolo.com/tutorial/">FastAPI Tutorial - First Steps</a></h2>
                <div data-result="snippet">FastAPI is a modern, fast web framework for building APIs.</div>
            </article>
        </body></html>
    """)
    mock_page.bring_to_front = AsyncMock()
    mock_page.goto = AsyncMock()

    with patch("app.tools.browser.get_visible_chrome_page", AsyncMock(return_value=mock_page)):
        res = await search_web(query=query, max_results=5)

        assert res["status"] == "success"
        assert res["query"] == query
        assert res["engine"] == "duckduckgo"  # Successfully triggered auto-guard fallback
        assert res["count"] >= 1
        first_res = res["results"][0]
        assert "FastAPI Tutorial" in first_res["title"]
        assert "https://fastapi.tiangolo.com" in first_res["url"]
        assert "FastAPI is a modern" in first_res["snippet"]


@pytest.mark.asyncio
async def test_launch_application_delegates_to_search_web():
    """Verify launch_application('chrome', args=['search query']) delegates directly to search_web."""
    with patch("app.tools.browser.search_web", AsyncMock(return_value={"status": "success", "delegated": True})) as mock_search:
        res = await launch_application("chrome", args=["LangGraph", "multi-agent", "tutorial"])
        assert res["status"] == "success"
        assert res["delegated"] is True
        mock_search.assert_awaited_once_with(query="LangGraph multi-agent tutorial")


@pytest.mark.asyncio
async def test_brain_dispatch_search_web():
    """Verify brain step_executor dispatches search_web and returns formatted results."""
    simulated_results = {
        "status": "success",
        "query": "pytest testing",
        "engine": "google",
        "count": 1,
        "results": [{"title": "Pytest Docs", "url": "https://docs.pytest.org", "snippet": "Official pytest documentation."}],
    }
    with patch("app.tools.browser.search_web", AsyncMock(return_value=simulated_results)):
        res = await dispatch_tool_call("search_web", {"query": "pytest testing"})
        assert res["status"] == "success"
        assert res["count"] == 1
        assert res["results"][0]["url"] == "https://docs.pytest.org"

