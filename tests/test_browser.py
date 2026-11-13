from pathlib import Path
import pytest
from app.tools.browser import BrowserEngine
from app.agents.workers import browser_agent_node


@pytest.mark.asyncio
async def test_browser_search_web():
    """Verify Playwright web search executes and extracts organic results."""
    async with BrowserEngine(headless=True) as browser:
        results = await browser.search_web("FastAPI python framework", max_results=3)

    assert isinstance(results, list)
    assert len(results) > 0
    first = results[0]
    assert "title" in first
    assert "url" in first
    assert len(first["title"]) > 0


@pytest.mark.asyncio
async def test_browser_navigate_page():
    """Verify Playwright navigation and clean text extraction."""
    async with BrowserEngine(headless=True) as browser:
        page_data = await browser.navigate_page("https://example.com")

    assert page_data["status_code"] == 200
    assert "Example Domain" in page_data["title"]
    assert "Example Domain" in page_data["text_content"]
    assert "documentation examples" in page_data["text_content"] or "illustrative examples" in page_data["text_content"]


@pytest.mark.asyncio
async def test_browser_capture_screenshot():
    """Verify full-page screenshot capture and storage into ./workspace/."""
    screenshot_name = "test_example_capture.png"
    async with BrowserEngine(headless=True) as browser:
        saved_path = await browser.capture_screenshot("https://example.com", filename=screenshot_name)

    path_obj = Path(saved_path)
    assert path_obj.exists()
    assert path_obj.is_file()
    assert path_obj.stat().st_size > 1000  # Non-trivial PNG file bytes


@pytest.mark.asyncio
async def test_browser_agent_node_integration():
    """Verify browser_agent_node properly routes search_web tool and records artifacts."""
    state = {
        "user_id": "test_user",
        "chat_id": "test_chat",
        "channel": "telegram",
        "raw_prompt": "Search LangGraph documentation",
        "task_graph": {
            "steps": [
                {
                    "step_id": "step_browser_1",
                    "target_agent": "BrowserAgent",
                    "tool_name": "search_web",
                    "tool_params": {"query": "LangGraph multi-agent documentation"},
                    "depends_on": [],
                }
            ]
        },
        "current_step_id": "step_browser_1",
        "completed_steps": [],
        "failed_steps": [],
        "step_results": {},
        "agent_outputs": {},
        "artifacts": [],
    }

    updated_state = await browser_agent_node(state)

    assert "step_browser_1" in updated_state["completed_steps"]
    res = updated_state["step_results"]["step_browser_1"]
    assert res["status"] == "success"
    assert res["agent"] == "BrowserAgent"
    assert len(res["results"]) > 0

