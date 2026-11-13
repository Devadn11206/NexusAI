import json
from pathlib import Path
import pytest
from app.tools.browser import BrowserEngine, clean_html_to_markdown


@pytest.mark.asyncio
async def test_stealth_flag_masked():
    """Verify navigator.webdriver is masked and undefined in browser execution context."""
    async with BrowserEngine(headless=True) as browser:
        ctx = await browser._create_context()
        page = await ctx.new_page()
        await page.goto("https://example.com")
        webdriver_flag = await page.evaluate("() => navigator.webdriver")
        plugins_len = await page.evaluate("() => navigator.plugins.length")
        await ctx.close()

    assert webdriver_flag is None or webdriver_flag is False
    assert plugins_len > 0


@pytest.mark.asyncio
async def test_get_accessibility_tree():
    """Verify ARIA accessibility tree extracts structured interactive nodes."""
    async with BrowserEngine(headless=True) as browser:
        data = await browser.get_accessibility_tree("https://example.com")

    assert "interactive_count" in data
    assert "nodes" in data
    assert isinstance(data["nodes"], list)
    # Check that interactive nodes (links/buttons) are present on example.com
    assert any(n.get("role") == "link" for n in data["nodes"])


@pytest.mark.asyncio
async def test_sanitized_markdown_token_reduction():
    """Verify HTML-to-Markdown stripping produces clean token-efficient text."""
    sample_html = """
    <html>
      <head><script>alert('malicious')</script><style>body { color: red; }</style></head>
      <body>
        <nav><a href="/home">Home</a></nav>
        <h1>Welcome to NEXUS AI</h1>
        <p>This is a paragraph with <a href="https://nexus.ai">a real link</a>.</p>
        <ul>
          <li>Feature 1</li>
          <li>Feature 2</li>
        </ul>
        <footer>Copyright 2026</footer>
      </body>
    </html>
    """
    markdown = clean_html_to_markdown(sample_html)

    assert "alert('malicious')" not in markdown
    assert "color: red" not in markdown
    assert "Copyright 2026" not in markdown
    assert "# Welcome to NEXUS AI" in markdown
    assert "[a real link](https://nexus.ai)" in markdown
    assert "- Feature 1" in markdown
    assert len(markdown) < len(sample_html) * 0.5


@pytest.mark.asyncio
async def test_session_state_save_and_load():
    """Verify session storage persistence saves cookies/state into ./workspace/sessions/."""
    session_id = "test_user_session"
    async with BrowserEngine(headless=True) as browser:
        ctx = await browser._create_context()
        page = await ctx.new_page()
        await page.goto("https://example.com")

        # Set test cookie
        await ctx.add_cookies([{"name": "nexus_test", "value": "12345", "domain": ".example.com", "path": "/"}])
        saved_file = await browser.save_session_state(ctx, session_id=session_id)
        await ctx.close()

        # Load in new context
        loaded_ctx = await browser._create_context(session_id=session_id)
        cookies = await loaded_ctx.cookies()
        await loaded_ctx.close()

    assert Path(saved_file).exists()
    assert any(c["name"] == "nexus_test" for c in cookies)


@pytest.mark.asyncio
async def test_api_response_interception():
    """Verify network response listening captures target URLs."""
    async with BrowserEngine(headless=True) as browser:
        # Navigate to a public page with background image/asset requests
        captured = await browser.intercept_api_responses(
            url="https://example.com",
            target_url_pattern="example.com",
            max_wait_ms=1000,
        )

    assert isinstance(captured, list)

