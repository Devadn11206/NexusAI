"""
Tests for Universal Browser Intent Router and Telegram Natural Language Web requests.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from app.core.planner import TaskPlanner
from app.schemas.planner import TargetAgent, IntentCategory
from app.core.brain import intent_and_context_node, task_planner_node, dispatch_tool_call
from app.core.state import NexusState


@pytest.mark.asyncio
async def test_planner_fallback_routes_natural_browser_queries():
    planner = TaskPlanner()

    test_queries = [
        "google best laptops under 60k",
        "open youtube and play lo-fi",
        "go to github.com and screenshot",
        "find 5 ml internships and make excel",
        "download https://example.com/sample.pdf",
        "check my chrome history for leetcode",
        "open leetcode two sum",
        "open chrome and search for quantum computing",
    ]

    for q in test_queries:
        plan = planner._fallback_rule_based_plan(q)
        assert plan is not None
        assert len(plan.steps) >= 1
        assert plan.steps[0].target_agent in (TargetAgent.BrowserAgent, TargetAgent.FileAgent)
        assert plan.steps[0].tool_name in ("execute_browser_intent", "web_search")


@pytest.mark.asyncio
async def test_brain_intent_and_task_planner_node():
    state: NexusState = {
        "messages": ["google best laptops under 60k"],
        "plan_steps": [],
        "current_step_index": 0,
        "replan_count": 0,
    }

    intent_res = await intent_and_context_node(state)
    assert intent_res["user_intent"]["category"] == "BROWSER"

    state["user_intent"] = intent_res["user_intent"]
    planner_res = await task_planner_node(state)
    assert len(planner_res["plan_steps"]) >= 1
    assert planner_res["plan_steps"][0]["tool_name"] == "execute_browser_intent"


@pytest.mark.asyncio
async def test_brain_dispatch_tool_call_browser_intent():
    with patch("app.tools.browser.execute_browser_intent", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {
            "status": "success",
            "action": "search",
            "query": "fastapi docs",
            "summary": "Results found",
        }

        res = await dispatch_tool_call(
            "execute_browser_intent",
            {"instruction": "google fastapi docs"}
        )

        assert res["status"] == "success"
        mock_exec.assert_called_once()


@pytest.mark.asyncio
async def test_direct_file_download_intent():
    from app.tools.browser import execute_browser_intent

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"%PDF-1.4 dummy binary content"
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        res = await execute_browser_intent("download https://example.com/test_doc.pdf")
        assert res["status"] == "success"
        assert res["action"] == "download"
        assert "test_doc.pdf" in res["filename"]


@pytest.mark.asyncio
async def test_chrome_history_intent():
    from app.tools.browser import execute_browser_intent

    with patch("app.tools.browser.BrowserEngine.manage_browsing_history") as mock_hist:
        mock_hist.return_value = [
            {"title": "Two Sum - LeetCode", "url": "https://leetcode.com/problems/two-sum", "visit_count": 5}
        ]

        res = await execute_browser_intent("check my chrome history for leetcode")
        assert res["status"] == "success"
        assert res["action"] == "history"
        assert len(res["items"]) == 1
        assert "Two Sum" in res["summary"]
