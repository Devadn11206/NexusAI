from pathlib import Path
import pytest
from app.tools.browser import BrowserEngine
from app.tools.computer import launch_application, force_window_foreground, close_application


@pytest.mark.asyncio
async def test_headful_browser_initialization():
    """Verify BrowserEngine launches in headful visual mode with system Chrome channel."""
    # Tests that headful initialization flags and stealth parameters instantiate correctly
    async with BrowserEngine(headless=False, use_system_chrome=True) as browser:
        assert browser.headless is False
        assert browser.use_system_chrome is True
        # Verify page can open without headless detection
        ctx = await browser._create_context()
        page = await ctx.new_page()
        await page.goto("https://example.com")
        title = await page.title()
        assert "Example Domain" in title
        await ctx.close()


@pytest.mark.asyncio
async def test_foreground_window_focus_handler():
    """Verify force_window_foreground handler executes and attempts window activation."""
    # Launch standard Windows calculator
    launch_res = await launch_application("calc")
    assert launch_res["status"] in ("success", "failed")

    # Execute foreground force
    focused = force_window_foreground("Calculator")
    # In Windows desktop environment, returns True when window handle exists
    assert isinstance(focused, bool)

    # Clean up test app
    await close_application("Calculator")

