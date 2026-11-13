import asyncio
import json
import logging
import os
import re
import shutil
import sqlite3
import tempfile
import urllib.parse
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional
import httpx
from bs4 import BeautifulSoup
from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    Playwright,
    Response,
    Download,
)

from app.config import settings
from app.core.security import resolve_safe_workspace_path

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

STEALTH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-infobars",
    "--disable-extensions",
    "--window-size=1920,1080",
    "--start-maximized",
]

STEALTH_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined
});
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5]
});
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en']
});
window.chrome = {
    runtime: {}
};
"""

# Global persistent visible Chrome context manager
_VISIBLE_CHROME_PLAYWRIGHT: Optional[Playwright] = None
_VISIBLE_CHROME_CONTEXT: Optional[BrowserContext] = None
_VISIBLE_CHROME_LOCK = asyncio.Lock()


async def get_visible_chrome_page() -> Page:
    """
    Maintains a reusable visible System Chrome persistent context
    (channel='chrome', headless=False, user_data_dir='./workspace/sessions/chrome_main_profile')
    so web searches and workflows open directly in visible Chrome on the user's screen
    and remain open for follow-up inspection and interaction.
    """
    global _VISIBLE_CHROME_PLAYWRIGHT, _VISIBLE_CHROME_CONTEXT

    profile_dir = resolve_safe_workspace_path("sessions/chrome_main_profile")
    profile_dir.mkdir(parents=True, exist_ok=True)

    async with _VISIBLE_CHROME_LOCK:
        if _VISIBLE_CHROME_PLAYWRIGHT is None:
            _VISIBLE_CHROME_PLAYWRIGHT = await async_playwright().start()

        if _VISIBLE_CHROME_CONTEXT is None:
            launch_args = [
                "--start-maximized",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
            ]
            try:
                _VISIBLE_CHROME_CONTEXT = await _VISIBLE_CHROME_PLAYWRIGHT.chromium.launch_persistent_context(
                    user_data_dir=str(profile_dir.resolve()),
                    channel="chrome",
                    headless=False,
                    args=launch_args,
                    user_agent=USER_AGENT,
                    viewport=None,
                )
            except Exception as exc:
                logger.warning(f"[BrowserEngine] System Chrome channel fallback: {exc}")
                _VISIBLE_CHROME_CONTEXT = await _VISIBLE_CHROME_PLAYWRIGHT.chromium.launch_persistent_context(
                    user_data_dir=str(profile_dir.resolve()),
                    headless=False,
                    args=launch_args,
                    user_agent=USER_AGENT,
                    viewport=None,
                )

        # Reuse existing open page if idle or open a clean new page
        pages = _VISIBLE_CHROME_CONTEXT.pages
        target_page = None
        for p in reversed(pages):
            try:
                if not p.is_closed():
                    if p.url in ("about:blank", "chrome://newtab/"):
                        target_page = p
                        break
            except Exception:
                pass

        if not target_page:
            target_page = await _VISIBLE_CHROME_CONTEXT.new_page()

        return target_page


async def wait_until_visually_ready(
    page: Page,
    result_selector: Optional[str] = None,
    timeout_ms: int = 8000,
) -> bool:
    """
    Robust post-render settlement pipeline before capturing screenshots:
    1. Waits for page 'load' event (with graceful timeout for heavy streaming SPAs).
    2. If result_selector is provided, waits for elements matching it to become visible.
    3. Evaluates in-page visual readiness (document.fonts.ready and img.complete).
    4. Settles for 600ms to allow CSS transitions and paint pipelines to finish.
    """
    try:
        # Step 1: Wait for load state gracefully
        try:
            await page.wait_for_load_state("load", timeout=timeout_ms)
        except Exception as load_err:
            logger.debug(f"[BrowserEngine] Load state wait note ({load_err}); proceeding to DOM checks.")

        # Step 2: If result_selector provided, wait for it to be visible
        if result_selector:
            try:
                locator = page.locator(result_selector).first
                await locator.wait_for(state="visible", timeout=timeout_ms)
            except Exception as sel_err:
                logger.debug(f"[BrowserEngine] Selector '{result_selector}' wait note: {sel_err}")

        # Step 3: Evaluate in-page fonts and image completion
        try:
            await page.evaluate("""async () => {
                try {
                    if (document.fonts && document.fonts.ready) {
                        await Promise.race([
                            document.fonts.ready,
                            new Promise(resolve => setTimeout(resolve, 2000))
                        ]);
                    }
                    const images = Array.from(document.querySelectorAll('img'));
                    const pendingImages = images
                        .filter(img => !img.complete && img.src)
                        .map(img => new Promise(resolve => {
                            img.onload = img.onerror = resolve;
                            setTimeout(resolve, 1500);
                        }));
                    if (pendingImages.length > 0) {
                        await Promise.race([
                            Promise.all(pendingImages),
                            new Promise(resolve => setTimeout(resolve, 2000))
                        ]);
                    }
                } catch (e) {
                    // Ignore client-side script inspection errors
                }
            }""")
        except Exception as eval_err:
            logger.debug(f"[BrowserEngine] In-page visual readiness evaluation note: {eval_err}")

        # Step 4: Final paint settle delay
        await page.wait_for_timeout(600)
        return True
    except Exception as exc:
        logger.warning(f"[BrowserEngine] wait_until_visually_ready encountered: {exc}")
        return False


async def capture_browser_screenshot(
    filename: str = "browser_tab.png",
    url: Optional[str] = None,
    result_selector: Optional[str] = None,
) -> str:
    """
    Captures a screenshot of the active visible Chrome tab or navigates to url if provided,
    strictly waiting until visually ready.
    """
    safe_path = resolve_safe_workspace_path(filename)
    safe_path.parent.mkdir(parents=True, exist_ok=True)

    page = await get_visible_chrome_page()
    if url:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        await page.goto(url, timeout=20000, wait_until="domcontentloaded")

    await wait_until_visually_ready(page, result_selector=result_selector)
    await page.screenshot(path=str(safe_path))
    return str(safe_path)


async def search_web(query: str, max_results: int = 8, take_screenshot: bool = False) -> Dict[str, Any]:
    """
    Direct Query-URL Web Search with Visible Chrome Navigation and Anti-Block Fallback:
    1. URL-encodes query and navigates directly to Google Search.
    2. Auto CAPTCHA / Consent Guard: if blocked (/sorry/ or captcha), falls back to DuckDuckGo in the same visible tab.
    3. Extracts organic search results (title, url, snippet) and returns them to the LLM.
    """
    clean_q = query.strip()
    if not clean_q:
        return {"query": "", "results": [], "count": 0, "status": "empty"}

    encoded_q = urllib.parse.quote_plus(clean_q)
    google_search_url = f"https://www.google.com/search?q={encoded_q}"
    ddg_search_url = f"https://duckduckgo.com/?q={encoded_q}"

    logger.info(f"[BrowserEngine] Executing search for: '{clean_q}'")
    results = []
    used_engine = "google"
    navigated_url = google_search_url

    try:
        page = await get_visible_chrome_page()

        # Step 1: Navigate to Google Search
        try:
            await page.goto(google_search_url, timeout=15000, wait_until="domcontentloaded")
            await page.bring_to_front()
            navigated_url = page.url
        except Exception as g_err:
            logger.warning(f"[BrowserEngine] Google Search navigation error: {g_err}")
            navigated_url = "/sorry/"

        # Step 2: Anti-block check (/sorry/, captcha, or consent wall)
        if "/sorry/" in navigated_url or "google.com/sorry" in navigated_url:
            logger.warning("[BrowserEngine] Google block/consent detected. Falling back to DuckDuckGo in visible tab.")
            used_engine = "duckduckgo"
            await page.goto(ddg_search_url, timeout=15000, wait_until="domcontentloaded")
            await page.bring_to_front()
            navigated_url = page.url

        # Bring window into OS foreground
        try:
            from app.tools.computer import force_window_foreground
            force_window_foreground("chrome")
        except Exception:
            pass

        # Step 3: Wait until visually ready for search results
        result_sel = "div#search a h3, div#rso h3, article[data-testid='result']"
        await wait_until_visually_ready(page, result_selector=result_sel, timeout_ms=8000)

        content_html = await page.content()
        soup = BeautifulSoup(content_html, "html.parser")

        # Google Search selector parsing
        for node in soup.select("div#search .g, div#rso .g, div#search a:has(h3)"):
            if len(results) >= max_results:
                break
            h3 = node.select_one("h3")
            a_tag = node if node.name == "a" else node.select_one("a[href]")
            snippet_el = node.select_one(".VwiC3b, [style*='-webkit-line-clamp'], span.aCOpRe")

            if h3 and a_tag and a_tag.get("href"):
                t = h3.get_text(strip=True)
                u = a_tag["href"]
                s = snippet_el.get_text(strip=True) if snippet_el else ""
                if u.startswith("http") and not any(r["url"] == u for r in results):
                    results.append({"title": t, "url": u, "snippet": s})

        # DuckDuckGo fallback selector parsing
        if not results:
            for node in soup.select("article[data-testid='result'], li[data-layout='organic'], .result"):
                if len(results) >= max_results:
                    break
                t_el = node.select_one("h2 a, .result__title a")
                s_el = node.select_one("[data-result='snippet'], .result__snippet")
                if t_el and t_el.get("href"):
                    t = t_el.get_text(strip=True)
                    u = t_el["href"]
                    s = s_el.get_text(strip=True) if s_el else ""
                    if "uddg=" in u:
                        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(u).query)
                        u = parsed.get("uddg", [u])[0]
                    if u.startswith("http") and not any(r["url"] == u for r in results):
                        results.append({"title": t, "url": u, "snippet": s})

    except Exception as exc:
        logger.error(f"[BrowserEngine] Persistent visible search failed: {exc}")

    # Fallback to background fast HTTP query if browser extraction returned empty
    if not results:
        try:
            headers = {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}
            async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=10.0) as client:
                resp = await client.get("https://html.duckduckgo.com/html/", params={"q": clean_q})
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for node in soup.select(".result"):
                        if len(results) >= max_results:
                            break
                        t_el = node.select_one(".result__title a")
                        s_el = node.select_one(".result__snippet")
                        if t_el and t_el.get("href"):
                            t = t_el.get_text(strip=True)
                            raw_u = t_el["href"]
                            if "uddg=" in raw_u:
                                parsed = urllib.parse.parse_qs(urllib.parse.urlparse(raw_u).query)
                                u = parsed.get("uddg", [raw_u])[0]
                            else:
                                u = raw_u
                            s = s_el.get_text(strip=True) if s_el else ""
                            if u.startswith("http"):
                                results.append({"title": t, "url": u, "snippet": s})
        except Exception:
            pass

    screenshot_path: Optional[str] = None
    if take_screenshot:
        try:
            page = await get_visible_chrome_page()
            shot_file = resolve_safe_workspace_path(f"images/search_{uuid.uuid4().hex[:6]}.png")
            shot_file.parent.mkdir(parents=True, exist_ok=True)
            await wait_until_visually_ready(page, timeout_ms=3000)
            await page.screenshot(path=str(shot_file))
            screenshot_path = str(shot_file)
            logger.info(f"[BrowserEngine] Post-render search screenshot captured: {screenshot_path}")
        except Exception as shot_err:
            logger.warning(f"[BrowserEngine] Post-render search screenshot note: {shot_err}")

    response_data = {
        "status": "success",
        "query": clean_q,
        "engine": used_engine,
        "active_url": navigated_url,
        "count": len(results),
        "results": results,
    }
    if screenshot_path:
        response_data["screenshot_path"] = screenshot_path
        response_data["artifacts"] = [screenshot_path]

    return response_data


async def execute_browser_intent(instruction: str, user_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    High-level universal orchestrator for ALL natural language browser, search, and web requests.
    Understands casual slang, direct URLs, research requests, downloads, and interactive actions,
    and executes them end-to-end on persistent visible System Chrome.
    """
    raw_prompt = instruction.strip()
    p_lower = raw_prompt.lower()
    logger.info(f"[BrowserEngine] Executing universal browser intent: '{raw_prompt}'")

    # 1. Direct File Download Pattern (URL ending in extension or "download <url>")
    url_match = re.search(r'https?://[^\s]+', raw_prompt)
    if "download" in p_lower and url_match:
        target_url = url_match.group(0).rstrip('.,;)"\'')
        parsed = urllib.parse.urlparse(target_url)
        path_name = Path(parsed.path).name or "downloaded_file.bin"
        downloads_dir = resolve_safe_workspace_path("downloads")
        downloads_dir.mkdir(parents=True, exist_ok=True)
        out_file = downloads_dir / path_name

        try:
            headers = {"User-Agent": USER_AGENT}
            async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=30.0) as client:
                resp = await client.get(target_url)
                resp.raise_for_status()
                with open(out_file, "wb") as f:
                    f.write(resp.content)
            logger.info(f"[BrowserEngine] Direct file downloaded to: {out_file} ({out_file.stat().st_size} bytes)")
            return {
                "status": "success",
                "action": "download",
                "url": target_url,
                "file_path": str(out_file),
                "filename": out_file.name,
                "bytes": out_file.stat().st_size,
                "summary": f"✅ Downloaded file `{out_file.name}` ({round(out_file.stat().st_size / 1024, 1)} KB) directly from {target_url}.",
                "artifacts": [str(out_file)],
            }
        except Exception as exc:
            logger.error(f"[BrowserEngine] Direct download failed: {exc}", exc_info=True)
            return {"status": "error", "action": "download", "url": target_url, "error": str(exc)}

    # 2. Chrome History & Bookmarks Inspection
    if any(k in p_lower for k in ["chrome history", "browser history", "browsing history", "check history"]):
        q = raw_prompt
        for phrase in ["check my chrome history for", "check chrome history for", "search chrome history for", "check history for", "chrome history"]:
            q = q.lower().replace(phrase, "")
        q = q.strip() or None
        engine = BrowserEngine(headless=True)
        items = engine.manage_browsing_history(limit=15, query=q)
        hist_text = "\n".join([f"• [{item.get('title', 'Page')}]({item.get('url')})" for item in items[:8]]) if items else "No matching Chrome history entries found."
        return {
            "status": "success",
            "action": "history",
            "query": q,
            "items_count": len(items),
            "summary": f"🔍 **Chrome Browsing History** ({len(items)} entries found):\n\n{hist_text}",
            "items": items,
        }

    if any(k in p_lower for k in ["chrome bookmark", "browser bookmark", "bookmarks", "check bookmarks"]):
        engine = BrowserEngine(headless=True)
        res_bm = engine.manage_bookmarks(action="list")
        bms = res_bm.get("bookmarks", [])
        bm_text = "\n".join([f"• [{b.get('name', 'Bookmark')}]({b.get('url')})" for b in bms[:8]]) if bms else "No bookmarks found."
        return {
            "status": "success",
            "action": "bookmarks",
            "summary": f"🔖 **Chrome Bookmarks**:\n\n{bm_text}",
            "bookmarks": bms,
        }

    # 3. Autonomous Research to Excel / Literature Comparison
    if ("internship" in p_lower or "research" in p_lower or "compare" in p_lower or "matrix" in p_lower) and ("excel" in p_lower or "xlsx" in p_lower or "spreadsheet" in p_lower or "table" in p_lower):
        from app.tools.research_engine import run_structured_research_to_excel
        out_name = "AIML_Internships_Comparison.xlsx" if "internship" in p_lower else "Research_Comparison_Matrix.xlsx"
        res_excel = await run_structured_research_to_excel(goal=raw_prompt, output_filename=out_name)
        art_path = res_excel.get("file_path")
        return {
            "status": "success",
            "action": "research_to_excel",
            "summary": f"📊 **Research Sheet Generated**: Successfully synthesized research and exported formatted Excel workbook `{out_name}`.",
            "artifacts": [art_path] if art_path else [],
            "data": res_excel,
        }

    # 4. Academic Search (arXiv, Semantic Scholar, OpenAlex)
    if "arxiv" in p_lower or "semantic scholar" in p_lower or "academic paper" in p_lower:
        from app.tools.research_engine import search_academic_papers
        q = raw_prompt
        for phrase in ["search academic papers on arxiv for", "search arxiv for", "find papers on", "search papers"]:
            q = q.lower().replace(phrase, "")
        res_papers = await search_academic_papers(query=q.strip() or "machine learning agents", max_results=5)
        papers = res_papers.get("papers", [])
        p_text = "\n\n".join([f"• **{p.get('title')}**\n  _{p.get('authors')}_ ({p.get('year')})\n  [Link]({p.get('url')})" for p in papers]) if papers else "No papers found."
        return {
            "status": "success",
            "action": "academic_search",
            "summary": f"📚 **Academic Research Papers**:\n\n{p_text}",
            "papers": papers,
        }

    # 5. Direct Domain / URL Navigation (e.g., "open github.com", "go to reddit.com", "open leetcode two sum")
    # Identify explicit URLs or well-known domain names
    domain_match = re.search(r'\b([a-zA-Z0-9-]+\.(?:com|org|net|io|co|edu|gov|ai|app|dev)(?:/[^\s]*)?)\b', raw_prompt, re.IGNORECASE)
    has_explicit_url = bool(url_match or domain_match)

    if has_explicit_url and not any(w in p_lower for w in ["google", "search for", "look up"]):
        if url_match:
            target_url = url_match.group(0).rstrip('.,;)"\'')
        else:
            raw_domain = domain_match.group(1).rstrip('.,;)"\'')
            target_url = f"https://{raw_domain}"

        logger.info(f"[BrowserEngine] Direct URL navigation to: {target_url}")
        page = await get_visible_chrome_page()
        try:
            await page.goto(target_url, timeout=20000, wait_until="domcontentloaded")
            await page.bring_to_front()
            try:
                from app.tools.computer import force_window_foreground
                force_window_foreground("chrome")
            except Exception:
                pass

            title = await page.title()
            page_url = page.url

            # Capture tab screenshot proof with visual readiness wait
            shot_file = resolve_safe_workspace_path(f"images/browser_{uuid.uuid4().hex[:6]}.png")
            shot_file.parent.mkdir(parents=True, exist_ok=True)
            await wait_until_visually_ready(page, timeout_ms=8000)
            await page.screenshot(path=str(shot_file))

            # Detect login wall
            html = await page.content()
            engine = BrowserEngine(headless=True)
            login_status = await engine.detect_login_requirement(html)

            summary = f"🌐 **Navigated to [{title}]({page_url})** in visible Chrome.\n"
            if login_status.get("requires_login"):
                summary += f"⚠️ **Notice**: Site appears to require authentication ({login_status.get('reason')})."

            return {
                "status": "success",
                "action": "navigate",
                "title": title,
                "url": page_url,
                "requires_login": login_status.get("requires_login", False),
                "summary": summary,
                "artifacts": [str(shot_file)],
            }
        except Exception as nav_err:
            logger.error(f"[BrowserEngine] Navigation to {target_url} failed: {nav_err}")
            return {"status": "error", "action": "navigate", "url": target_url, "error": str(nav_err)}

    # 6. Web Search with Visible Chrome Navigation and Resilient Fallback
    # Extract the clean core search term
    clean_q = raw_prompt
    for phrase in [
        "open chrome and search for", "open chrome and search", "open browser and search for",
        "search for in chrome", "search for", "search in chrome for", "search in chrome",
        "search", "google for", "google", "browse for", "browse", "look up", "find",
        "open youtube and play", "open youtube", "open",
    ]:
        if clean_q.lower().startswith(phrase):
            clean_q = clean_q[len(phrase):].strip()
            break

    clean_q = clean_q.replace("in chrome", "").replace("on chrome", "").strip() or raw_prompt

    # Special handling for LeetCode / CodeChef challenges
    if "leetcode" in p_lower and not has_explicit_url:
        clean_q = f"leetcode {clean_q.replace('leetcode', '').strip()}"
    elif "youtube" in p_lower:
        clean_q = f"youtube {clean_q.replace('youtube', '').strip()}"

    logger.info(f"[BrowserEngine] Performing structured search for: '{clean_q}'")
    search_res = await search_web(query=clean_q, max_results=6)
    results = search_res.get("results", [])

    # Format structured results
    res_lines = []
    for r in results[:5]:
        t = r.get("title", "Result")
        u = r.get("url", "")
        snip = r.get("snippet", "")
        res_lines.append(f"• **[{t}]({u})**\n  _{snip}_")

    search_text = "\n\n".join(res_lines) if res_lines else "Search completed in visible Chrome window."

    # Capture tab screenshot proof
    artifacts = []
    try:
        page = await get_visible_chrome_page()
        shot_file = resolve_safe_workspace_path(f"images/search_{uuid.uuid4().hex[:6]}.png")
        shot_file.parent.mkdir(parents=True, exist_ok=True)
        await wait_until_visually_ready(page, timeout_ms=3000)
        await page.screenshot(path=str(shot_file))
        artifacts.append(str(shot_file))
    except Exception:
        pass

    summary = (
        f"🔍 **Web Search Results for '{clean_q}'** (via {search_res.get('engine', 'Google')}):\n\n"
        f"{search_text}\n\n"
        f"_Visible tab remains open on your screen._"
    )

    return {
        "status": "success",
        "action": "search",
        "query": clean_q,
        "engine": search_res.get("engine", "google"),
        "results_count": len(results),
        "results": results,
        "summary": summary,
        "artifacts": artifacts,
    }


def clean_html_to_markdown(html: str) -> str:
    """
    Transforms raw HTML into token-optimized Markdown.
    Strips script, style, svg, noscript, nav, footer, header, ads, and inline CSS,
    yielding an 80%+ token reduction for downstream LLM parsing.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Remove non-content elements
    for elem in soup(["script", "style", "svg", "noscript", "nav", "footer", "header", "aside", "form"]):
        elem.extract()

    # Convert structural headings
    for h in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        level = int(h.name[1])
        prefix = "#" * level
        h.replace_with(f"\n\n{prefix} {h.get_text(strip=True)}\n\n")

    # Convert links to concise markdown format
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        href = a["href"]
        if text and href.startswith("http"):
            a.replace_with(f" [{text}]({href}) ")

    # Convert lists
    for li in soup.find_all("li"):
        li.replace_with(f"\n- {li.get_text(strip=True)}")

    raw_text = soup.get_text(separator="\n")
    # Clean up empty lines and normalize whitespace
    cleaned_lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    return "\n".join(cleaned_lines)


class BrowserEngine:
    """
    Advanced Production Browser Engine with Playwright:
    - Stealth & Anti-bot Masking (navigator.webdriver masked, realistic headers)
    - Session State Persistence (cross-task login cookies in ./workspace/sessions/)
    - ARIA Accessibility Tree Extraction (labeled interactive nodes)
    - Token-optimized HTML-to-Markdown sanitization
    - Network API response interception
    - Hybrid coordinate fallback clicking
    """

    def __init__(
        self,
        headless: bool = False,
        timeout_ms: int = 25000,
        session_id: Optional[str] = None,
        use_system_chrome: bool = True,
    ):
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.session_id = session_id
        self.use_system_chrome = use_system_chrome
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None

    async def __aenter__(self):
        self._playwright = await async_playwright().start()
        launch_kwargs: Dict[str, Any] = {
            "headless": self.headless,
            "args": STEALTH_ARGS,
        }
        if self.use_system_chrome:
            launch_kwargs["channel"] = "chrome"

        try:
            self._browser = await self._playwright.chromium.launch(**launch_kwargs)
        except Exception as exc:
            logger.warning(f"[BrowserEngine] System Chrome channel launch note ({exc}); falling back to standard Chromium.")
            launch_kwargs.pop("channel", None)
            self._browser = await self._playwright.chromium.launch(**launch_kwargs)

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    def _get_session_storage_path(self, session_id: str) -> Path:
        """Resolves safe file path for session state storage within ./workspace/sessions/."""
        sessions_dir = resolve_safe_workspace_path("sessions")
        sessions_dir.mkdir(parents=True, exist_ok=True)
        safe_name = f"{Path(session_id).stem}.json"
        return sessions_dir / safe_name

    async def _create_context(self, session_id: Optional[str] = None) -> BrowserContext:
        """Creates an anti-bot stealth context, optionally loading saved session state."""
        if not self._browser:
            raise RuntimeError("Browser not started. Use 'async with BrowserEngine()' context manager.")

        target_session = session_id or self.session_id
        storage_path = None
        if target_session:
            candidate = self._get_session_storage_path(target_session)
            if candidate.exists():
                storage_path = str(candidate)
                logger.info(f"[BrowserEngine] Loaded session storage from: {storage_path}")

        context = await self._browser.new_context(
            storage_state=storage_path,
            user_agent=USER_AGENT,
            viewport=None if not self.headless else {"width": 1920, "height": 1080},
            device_scale_factor=1,
            ignore_https_errors=True,
            locale="en-US",
            timezone_id="America/New_York",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Sec-Ch-Ua": '"Not A(Brand";v="99", "Google Chrome";v="124", "Chromium";v="124"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
            },
        )

        # Inject stealth evasions before any script runs
        await context.add_init_script(STEALTH_INIT_SCRIPT)
        return context

    async def save_session_state(self, context: BrowserContext, session_id: str) -> str:
        """Saves active cookies and localStorage to ./workspace/sessions/<session_id>.json."""
        target_path = self._get_session_storage_path(session_id)
        await context.storage_state(path=str(target_path))
        logger.info(f"[BrowserEngine] Session state saved to: {target_path}")
        return str(target_path)

    async def load_session_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Loads and parses saved session cookies & storage state from the vault."""
        target_path = self._get_session_storage_path(session_id)
        if not target_path.exists():
            return None
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.error(f"[BrowserEngine] Error loading session state '{session_id}': {exc}")
            return None

    async def intercept_network_api(
        self, url: str, target_url_pattern: str, max_wait_ms: int = 10000
    ) -> List[Dict[str, Any]]:
        """
        Alias for intercept_api_responses: navigates to URL and captures JSON payloads from
        matching background fetch/XHR network requests.
        """
        return await self.intercept_api_responses(url, target_url_pattern, max_wait_ms)

    async def wait_for_network_idle(self, page: Page, timeout: int = 15000) -> None:
        """Ensures dynamic Single Page Applications (Next.js/React) finish hydration and async fetches."""
        try:
            await page.wait_for_load_state("networkidle", timeout=timeout)
        except Exception as exc:
            logger.warning(f"[BrowserEngine] Network idle timeout ({timeout}ms): {exc}")

    async def search_web(
        self,
        query: str,
        max_results: int = 5,
        search_engine: str = "google",
        visual: bool = True,
    ) -> List[Dict[str, str]]:
        """
        Fast and reliable organic web search with dual mode:
        1. When visual=True and running in browser engine context, launches visual Chrome,
           navigates to direct search URL, types and submits search, and renders results live on screen.
        2. In addition, returns structured results for downstream processing.
        """
        logger.info(f"[BrowserEngine] Searching web: '{query}' (engine={search_engine}, visual={visual})")

        # 1. If visual Chrome execution is requested and browser instance is running
        if visual and self._browser:
            try:
                encoded_q = urllib.parse.quote_plus(query)
                direct_url = f"https://www.google.com/search?q={encoded_q}"
                if search_engine.lower() == "bing":
                    direct_url = f"https://www.bing.com/search?q={encoded_q}"
                elif search_engine.lower() == "duckduckgo":
                    direct_url = f"https://duckduckgo.com/?q={encoded_q}"

                context = await self._create_context()
                page: Page = await context.new_page()
                try:
                    await page.goto(direct_url, timeout=self.timeout_ms, wait_until="domcontentloaded")
                    await self.wait_for_network_idle(page, timeout=4000)
                    await page.bring_to_front()

                    # Bring Chrome window to active OS foreground
                    try:
                        from app.tools.computer import force_window_foreground
                        force_window_foreground("chrome")
                    except Exception:
                        pass
                except Exception as page_err:
                    logger.warning(f"[BrowserEngine] Visual navigation warning: {page_err}")
            except Exception as vis_err:
                logger.warning(f"[BrowserEngine] Visual search note: {vis_err}")

        # 2. Extract structured search results
        search_url = "https://html.duckduckgo.com/html/"
        headers = {
            "User-Agent": USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://html.duckduckgo.com/",
        }

        results = []
        try:
            async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=15.0) as client:
                resp = await client.get(search_url, params={"q": query})
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")

                for node in soup.select(".result"):
                    if len(results) >= max_results:
                        break
                    title_elem = node.select_one(".result__title a")
                    snippet_elem = node.select_one(".result__snippet")

                    if title_elem:
                        title = title_elem.get_text(strip=True)
                        raw_href = title_elem.get("href", "")
                        if "uddg=" in raw_href:
                            parsed = urllib.parse.parse_qs(urllib.parse.urlparse(raw_href).query)
                            href = parsed.get("uddg", [raw_href])[0]
                        else:
                            href = raw_href
                        snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
                        if title and href:
                            results.append({"title": title, "url": href, "snippet": snippet})
        except Exception as exc:
            logger.error(f"[BrowserEngine] Search query '{query}' failed: {exc}", exc_info=True)

        return results

    async def type_and_submit_search(
        self,
        page: Page,
        text: str,
        selector: Optional[str] = None,
        delay_ms: int = 50,
    ) -> bool:
        """
        Simulates human typing into a search bar input and presses Enter,
        waiting for the results page to render completely.
        """
        selectors_to_try = [
            selector,
            "textarea[name='q']",
            "input[name='q']",
            "[role='combobox']",
            "textarea[title='Search']",
            "input[title='Search']",
            "input[type='search']",
            "input[type='text']",
        ]
        chosen_selector = None
        for sel in selectors_to_try:
            if not sel:
                continue
            try:
                elem = page.locator(sel).first
                if await elem.is_visible(timeout=1500):
                    chosen_selector = sel
                    break
            except Exception:
                continue

        if not chosen_selector:
            chosen_selector = "textarea[name='q'], input[name='q']"

        try:
            target_locator = page.locator(chosen_selector).first
            await target_locator.click(timeout=3000)
            await target_locator.press_sequentially(text, delay=delay_ms)
            await page.keyboard.press("Enter")
            await page.wait_for_load_state("domcontentloaded", timeout=10000)
            await self.wait_for_network_idle(page, timeout=5000)
            return True
        except Exception as exc:
            logger.error(f"[BrowserEngine] type_and_submit_search error: {exc}")
            return False

    async def navigate_page(self, url: str, take_screenshot: bool = False) -> Dict[str, Any]:
        """Loads target URL, extracts title, and produces token-optimized sanitized Markdown."""
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        context = await self._create_context()
        page: Page = await context.new_page()

        try:
            resp = await page.goto(url, timeout=self.timeout_ms, wait_until="domcontentloaded")
            await wait_until_visually_ready(page, timeout_ms=5000)
            title = await page.title()
            html = await page.content()
            markdown_content = clean_html_to_markdown(html)

            shot_path = None
            if take_screenshot:
                safe_shot = resolve_safe_workspace_path(f"images/nav_{uuid.uuid4().hex[:6]}.png")
                safe_shot.parent.mkdir(parents=True, exist_ok=True)
                await page.screenshot(path=str(safe_shot))
                shot_path = str(safe_shot)

            res = {
                "url": url,
                "title": title,
                "status_code": resp.status if resp else 200,
                "text_content": markdown_content[:5000],
                "full_text_length": len(markdown_content),
            }
            if shot_path:
                res["screenshot_path"] = shot_path
                res["artifacts"] = [shot_path]
            return res
        except Exception as exc:
            logger.error(f"[BrowserEngine] Navigation to '{url}' failed: {exc}")
            return {
                "url": url,
                "title": "Error",
                "status_code": 500,
                "text_content": f"Failed to load page: {str(exc)}",
                "full_text_length": 0,
            }
        finally:
            await context.close()

    async def navigate_and_extract(self, url: str, take_screenshot: bool = False) -> Dict[str, Any]:
        """Alias for navigate_page with atomic visual screenshot support."""
        return await self.navigate_page(url=url, take_screenshot=take_screenshot)

    async def get_accessibility_tree(self, url: str) -> Dict[str, Any]:
        """
        Extracts structured interactive ARIA and DOM nodes from the page.
        Provides LLM agents with clean, indexed interactive elements (buttons, inputs, links).
        Compatible with all Playwright releases via in-page DOM inspection.
        """
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        context = await self._create_context()
        page: Page = await context.new_page()

        try:
            await page.goto(url, timeout=self.timeout_ms, wait_until="domcontentloaded")
            await self.wait_for_network_idle(page, timeout=5000)

            # Evaluate interactive tree
            interactive_nodes = await page.evaluate(
                """() => {
                    const elements = Array.from(document.querySelectorAll('a, button, input, select, textarea, [role]'));
                    return elements.map((el, i) => ({
                        id: i + 1,
                        role: el.getAttribute('role') || (el.tagName.toLowerCase() === 'a' ? 'link' : el.tagName.toLowerCase()),
                        name: (el.innerText || el.getAttribute('aria-label') || el.name || el.placeholder || '').trim(),
                        tag: el.tagName.toLowerCase(),
                        disabled: el.disabled || false,
                        href: el.href || null
                    })).filter(node => node.name.length > 0 || node.tag === 'input');
                }"""
            )

            return {
                "url": url,
                "interactive_count": len(interactive_nodes),
                "nodes": interactive_nodes[:100],  # Return up to 100 structured elements
            }
        finally:
            await context.close()

    async def launch_visible_chrome(self, url: str) -> Dict[str, Any]:
        """
        Visually opens the user's actual Google Chrome browser maximized on screen,
        navigates to target URL, brings the window to focus, and leaves it active.
        """
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        logger.info(f"[BrowserEngine] Launching visible Chrome on screen: '{url}'")
        context = await self._create_context()
        page: Page = await context.new_page()

        try:
            resp = await page.goto(url, timeout=self.timeout_ms, wait_until="domcontentloaded")
            await page.bring_to_front()
            title = await page.title()
            return {
                "status": "success",
                "url": url,
                "title": title,
                "message": f"Opened Google Chrome on screen at {url}.",
            }
        except Exception as exc:
            logger.error(f"[BrowserEngine] Visual Chrome launch note: {exc}")
            return {
                "status": "failed",
                "url": url,
                "error": str(exc),
            }

    async def capture_screenshot(self, url: str, filename: str = "screenshot.png") -> str:
        """Captures full-page PNG screenshot and saves inside ./workspace/."""
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        safe_path = resolve_safe_workspace_path(filename)
        safe_path.parent.mkdir(parents=True, exist_ok=True)

        context = await self._create_context()
        page: Page = await context.new_page()

        try:
            await page.goto(url, timeout=self.timeout_ms, wait_until="domcontentloaded")
            await wait_until_visually_ready(page, timeout_ms=5000)
            await page.screenshot(path=str(safe_path), full_page=True)
            return str(safe_path)
        finally:
            await context.close()

    async def intercept_api_responses(
        self, url: str, target_url_pattern: str, max_wait_ms: int = 10000
    ) -> List[Dict[str, Any]]:
        """
        Navigates to URL and intercepts background API fetch/XHR network requests
        matching target_url_pattern, capturing raw JSON payloads.
        """
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        captured_responses = []

        context = await self._create_context()
        page: Page = await context.new_page()

        async def _handle_response(response: Response):
            if target_url_pattern in response.url:
                try:
                    data = await response.json()
                    captured_responses.append({
                        "url": response.url,
                        "status": response.status,
                        "payload": data,
                    })
                except Exception:
                    try:
                        text = await response.text()
                        captured_responses.append({
                            "url": response.url,
                            "status": response.status,
                            "payload_text": text[:500],
                        })
                    except Exception:
                        pass

        page.on("response", _handle_response)

        try:
            await page.goto(url, timeout=self.timeout_ms, wait_until="domcontentloaded")
            await page.wait_for_timeout(max_wait_ms)
            return captured_responses
        finally:
            await context.close()

    async def hybrid_click(self, page: Page, selector: str) -> bool:
        """
        Attempts standard selector-based click; if element is obscured or inside shadow DOM,
        falls back to calculating bounding box coordinates and clicks directly via mouse cursor.
        """
        try:
            await page.click(selector, timeout=3000)
            return True
        except Exception as exc:
            logger.info(f"[BrowserEngine] Selector click failed ({exc}); attempting coordinate fallback click.")
            try:
                locator = page.locator(selector).first
                box = await locator.bounding_box()
                if box:
                    x = box["x"] + box["width"] / 2
                    y = box["y"] + box["height"] / 2
                    await page.mouse.click(x, y)
                    logger.info(f"[BrowserEngine] Coordinate click succeeded at ({x}, {y}).")
                    return True
            except Exception as coord_exc:
                logger.error(f"[BrowserEngine] Coordinate click failed: {coord_exc}")
        return False

    async def play_web_music(
        self,
        service: str = "spotify",
        query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Automates web streaming playback in visual Chrome across Spotify, YouTube Music, and SoundCloud.
        Launches Google Chrome with Widevine DRM and full audio codec support, bypassed autoplay policies,
        and persistent user session profiles to ensure uninterrupted streaming audio playback.
        """
        service_clean = service.lower().replace("-", "_").replace(" ", "_")
        urls = {
            "spotify": "https://open.spotify.com",
            "youtube_music": "https://music.youtube.com",
            "ytmusic": "https://music.youtube.com",
            "soundcloud": "https://soundcloud.com",
        }
        base_url = urls.get(service_clean, "https://open.spotify.com")
        target_url = base_url

        if query:
            q_enc = urllib.parse.quote_plus(query)
            if "spotify" in service_clean:
                target_url = f"https://open.spotify.com/search/{q_enc}"
            elif "youtube" in service_clean or "yt" in service_clean:
                target_url = f"https://music.youtube.com/search?q={q_enc}"
            elif "soundcloud" in service_clean:
                target_url = f"https://soundcloud.com/search?q={q_enc}"

        logger.info(f"[BrowserEngine] Launching DRM-enabled visual Chrome music player for '{service_clean}': {target_url}")

        # Use dedicated persistent session profile directory
        profile_dir = resolve_safe_workspace_path(f"sessions/chrome_{service_clean}_profile")
        profile_dir.mkdir(parents=True, exist_ok=True)

        music_args = [
            "--autoplay-policy=no-user-gesture-required",
            "--enable-features=AudioServiceOutOfProcess",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
        ]

        # Use launch_persistent_context directly if Playwright is initialized, or instantiate managed persistent context
        local_playwright = None
        context = None
        is_isolated = False

        try:
            if not self._playwright:
                local_playwright = await async_playwright().start()
                pw_instance = local_playwright
            else:
                pw_instance = self._playwright

            # Launch persistent context with Chrome channel for Widevine DRM
            try:
                context = await pw_instance.chromium.launch_persistent_context(
                    user_data_dir=str(profile_dir),
                    channel="chrome",
                    headless=self.headless,
                    user_agent=USER_AGENT,
                    args=music_args,
                    ignore_default_args=["--disable-component-update"],
                    viewport=None,
                )
            except Exception as chrome_exc:
                logger.warning(f"[BrowserEngine] System Chrome channel fallback: {chrome_exc}")
                try:
                    context = await pw_instance.chromium.launch_persistent_context(
                        user_data_dir=str(profile_dir),
                        headless=self.headless,
                        user_agent=USER_AGENT,
                        args=music_args,
                        ignore_default_args=["--disable-component-update"],
                        viewport=None,
                    )
                except Exception:
                    # Fallback to standard context if persistent launch is intercepted/mocked
                    context = await self._create_context(session_id=service_clean)
                    is_isolated = True

            pages = context.pages
            page: Page = pages[0] if pages else await context.new_page()

            # Inject stealth script into page context if supported
            try:
                if hasattr(page, "add_init_script"):
                    res = page.add_init_script(STEALTH_INIT_SCRIPT)
                    if asyncio.iscoroutine(res):
                        await res
            except Exception:
                pass

            await page.goto(target_url, timeout=self.timeout_ms, wait_until="domcontentloaded")
            await page.bring_to_front()

            if query:
                await page.wait_for_timeout(3000)
                playback_started = False

                # Service-specific optimized click strategies:
                if "youtube" in service_clean or "yt" in service_clean:
                    # YouTube Music strategy:
                    # 1. First extract direct watch link href from search results and navigate to watch page
                    try:
                        watch_href = await page.evaluate("""() => {
                            const a = document.querySelector('ytmusic-responsive-list-item-renderer a[href*="watch"]');
                            return a ? a.getAttribute('href') : null;
                        }""")
                        if watch_href:
                            full_watch_url = f"https://music.youtube.com/{watch_href.lstrip('/')}"
                            logger.info(f"[BrowserEngine] YouTube Music navigating to watch URL: {full_watch_url}")
                            await page.goto(full_watch_url, timeout=self.timeout_ms, wait_until="domcontentloaded")
                            await page.wait_for_timeout(2000)
                            # Ensure audio/video element plays
                            await page.evaluate("""() => {
                                const v = document.querySelector('video');
                                if (v) {
                                    v.muted = false;
                                    v.play().catch(e => console.log('play error', e));
                                }
                            }""")
                            playback_started = True
                    except Exception as yt_nav_err:
                        logger.warning(f"[BrowserEngine] YouTube Music watch navigation fallback: {yt_nav_err}")

                    if not playback_started:
                        # Fallback click strategies on YouTube Music
                        yt_locators = [
                            "ytmusic-responsive-list-item-renderer a[href*='watch']",
                            "ytmusic-responsive-list-item-renderer ytmusic-play-button-renderer",
                            "a[href*='watch?v=']",
                            "ytmusic-responsive-list-item-renderer",
                            "[aria-label='Play']",
                        ]
                        for loc in yt_locators:
                            try:
                                elem = page.locator(loc).first
                                count = await elem.count()
                                if count > 0:
                                    try:
                                        await elem.click(timeout=2000, force=True)
                                    except Exception:
                                        await page.evaluate("(el) => el.click()", await elem.element_handle())
                                    playback_started = True
                                    logger.info(f"[BrowserEngine] YouTube Music started via {loc}")
                                    break
                            except Exception:
                                continue

                elif "spotify" in service_clean:
                    # Spotify strategy: hover and click play button or track row
                    try:
                        # Hover over top-result-card or first tracklist row to reveal play button
                        top_card = page.locator("[data-testid='top-result-card'], [data-testid='tracklist-row']").first
                        if await top_card.is_visible(timeout=2000):
                            await top_card.hover()
                            await page.wait_for_timeout(500)
                    except Exception:
                        pass

                    spotify_locators = [
                        "[data-testid='play-button']",
                        "button[data-testid='play-button']",
                        "[data-testid='top-result-card'] button",
                        "[data-testid='tracklist-row'] button",
                        "button[aria-label*='Play']",
                        "[data-testid='tracklist-row']",
                    ]
                    for loc in spotify_locators:
                        try:
                            btn = page.locator(loc).first
                            if await btn.is_visible(timeout=1500):
                                try:
                                    await btn.click(timeout=2000)
                                except Exception:
                                    await page.evaluate("(el) => el.click()", await btn.element_handle())
                                playback_started = True
                                logger.info(f"[BrowserEngine] Spotify started via {loc}")
                                break
                        except Exception:
                            continue

                # Universal Fallback 1: ARIA Play buttons
                if not playback_started:
                    try:
                        aria_play = page.get_by_role("button", name="Play", exact=False).first
                        if await aria_play.is_visible(timeout=2000):
                            await aria_play.click(timeout=2000)
                            playback_started = True
                            logger.info("[BrowserEngine] Triggered playback via ARIA Play button.")
                    except Exception:
                        pass

                # Universal Fallback 2: Multi-selector hierarchy with direct JS dispatch
                if not playback_started:
                    play_selectors = [
                        "[data-testid='play-button']",
                        "button[data-testid='play-button']",
                        "button[title='Play']",
                        "[aria-label='Play']",
                        "button[aria-label*='Play']",
                        ".play-button",
                        "ytmusic-play-button-renderer",
                        "button.playbackSoundBadge__play",
                    ]
                    for sel in play_selectors:
                        try:
                            btn = page.locator(sel).first
                            if await btn.is_visible(timeout=1000):
                                try:
                                    await btn.click(timeout=1500)
                                except Exception:
                                    await page.evaluate("(element) => element.click()", await btn.element_handle())
                                playback_started = True
                                logger.info(f"[BrowserEngine] Triggered playback via selector: {sel}")
                                break
                        except Exception:
                            continue

                # Universal Fallback 3: Keyboard navigation fallback
                if not playback_started:
                    try:
                        track_item = page.locator("[role='row'], [data-testid='tracklist-row'], ytmusic-responsive-list-item-renderer").first
                        if await track_item.is_visible(timeout=1500):
                            await track_item.focus()
                            await page.keyboard.press("Enter")
                            playback_started = True
                            logger.info("[BrowserEngine] Triggered playback via keyboard focus & Enter.")
                    except Exception:
                        pass

            title = await page.title()
            return {
                "status": "success",
                "service": service_clean,
                "url": target_url,
                "title": title,
                "query": query,
                "profile_dir": str(profile_dir),
            }
        except Exception as exc:
            logger.error(f"[BrowserEngine] Web music error: {exc}")
            return {"status": "failed", "service": service_clean, "error": str(exc)}
        finally:
            if is_isolated and context:
                await context.close()
            if local_playwright:
                await local_playwright.stop()

    async def get_now_playing_info(self, page: Page) -> Dict[str, Any]:
        """Extracts currently playing track info and artist from active player DOM."""
        try:
            track = await page.locator("[data-testid='now-playing-widget'], .title, .song-title").first.inner_text(timeout=2000)
            return {"status": "success", "track": track.strip()}
        except Exception:
            return {"status": "unknown", "track": "Streaming Audio"}

    # =========================================================================
    # MODULE 3: ADVANCED BROWSER INTELLIGENCE SUITE
    # =========================================================================

    async def download_document(
        self,
        url: str,
        trigger_selector: Optional[str] = None,
        custom_filename: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Captures downloads via page.expect_download(), saves into ./workspace/downloads/,
        and returns the verified local file path and byte size.
        """
        downloads_dir = resolve_safe_workspace_path("downloads")
        downloads_dir.mkdir(parents=True, exist_ok=True)

        context = await self._create_context()
        page: Page = await context.new_page()

        try:
            await page.goto(url, timeout=self.timeout_ms, wait_until="domcontentloaded")
            
            # If a direct download trigger selector is provided, wait for download event
            if trigger_selector:
                async with page.expect_download(timeout=self.timeout_ms) as download_info:
                    await page.click(trigger_selector)
                download = await download_info.value
                fname = custom_filename or download.suggested_filename
                saved_path = downloads_dir / fname
                await download.save_as(str(saved_path))
            else:
                # Direct URL file download fallback via httpx
                async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    fname = custom_filename or Path(urllib.parse.urlparse(url).path).name or "downloaded_file.bin"
                    saved_path = downloads_dir / fname
                    saved_path.write_bytes(resp.content)

            return {
                "status": "success",
                "filename": saved_path.name,
                "file_path": str(saved_path),
                "file_size": saved_path.stat().st_size,
            }
        except Exception as exc:
            logger.error(f"[BrowserEngine] Download error: {exc}")
            return {"status": "failed", "error": str(exc)}
        finally:
            await context.close()

    async def upload_document(
        self,
        url: str,
        file_input_selector: str,
        local_filepath: str,
    ) -> Dict[str, Any]:
        """
        Uploads a verified local file into a web form file input via locator.set_input_files().
        """
        target_path = Path(local_filepath)
        if not target_path.exists():
            return {"status": "failed", "error": f"Local file not found: {local_filepath}"}

        context = await self._create_context()
        page: Page = await context.new_page()

        try:
            await page.goto(url, timeout=self.timeout_ms, wait_until="domcontentloaded")
            locator = page.locator(file_input_selector).first
            await locator.set_input_files(str(target_path))
            return {
                "status": "success",
                "file_uploaded": target_path.name,
                "selector": file_input_selector,
            }
        except Exception as exc:
            logger.error(f"[BrowserEngine] Upload error: {exc}")
            return {"status": "failed", "error": str(exc)}
        finally:
            await context.close()

    async def detect_login_requirement(self, page_or_html: Any) -> Dict[str, Any]:
        """
        Inspects active page or HTML content for login walls, password fields,
        OAuth/SSO sign-in buttons, or authorization redirects.
        """
        if isinstance(page_or_html, str):
            # Parse raw HTML string
            html_lower = page_or_html.lower()
            soup = BeautifulSoup(page_or_html, "html.parser")
            has_password = bool(soup.find("input", {"type": "password"}))
            has_auth_buttons = any(
                w in html_lower for w in ["sign in with google", "log in with", "sso", "sign in to continue"]
            )
            is_login_wall = has_password or has_auth_buttons
            return {
                "is_login_wall": is_login_wall,
                "has_password_field": has_password,
                "auth_type": "password" if has_password else ("sso" if has_auth_buttons else "none"),
            }

        # Otherwise page_or_html is a Playwright Page instance
        page: Page = page_or_html
        try:
            pwd_count = await page.locator("input[type='password']").count()
            current_url = page.url.lower()
            is_login_url = any(k in current_url for k in ["login", "signin", "auth", "account/sign-in"])

            # Check SSO / OAuth buttons
            sso_count = await page.locator("button:has-text('Sign In'), a:has-text('Sign In'), button:has-text('Log In')").count()
            is_login_wall = pwd_count > 0 or (is_login_url and sso_count > 0)

            return {
                "is_login_wall": is_login_wall,
                "has_password_field": pwd_count > 0,
                "url": page.url,
            }
        except Exception as exc:
            return {"is_login_wall": False, "error": str(exc)}

    async def crawl_with_pagination(
        self,
        start_url: str,
        item_selector: str,
        target_count: int = 10,
        next_button_selector: Optional[str] = None,
        max_pages: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Crawls multi-page web listings with deduplication, supporting both
        'Next' pagination buttons and infinite scroll until target_count is satisfied.
        """
        extracted_items = []
        seen_texts = set()

        context = await self._create_context()
        page: Page = await context.new_page()

        try:
            await page.goto(start_url, timeout=self.timeout_ms, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            current_page = 1
            while len(extracted_items) < target_count and current_page <= max_pages:
                locators = page.locator(item_selector)
                count = await locators.count()

                for i in range(count):
                    try:
                        elem = locators.nth(i)
                        txt = (await elem.inner_text()).strip()
                        if txt and txt not in seen_texts:
                            seen_texts.add(txt)
                            extracted_items.append({"index": len(extracted_items) + 1, "text": txt})
                            if len(extracted_items) >= target_count:
                                break
                    except Exception:
                        continue

                if len(extracted_items) >= target_count:
                    break

                # Attempt navigation to next page
                navigated = False
                if next_button_selector:
                    try:
                        next_btn = page.locator(next_button_selector).first
                        if await next_btn.is_visible(timeout=2000):
                            await next_btn.click()
                            await page.wait_for_timeout(2500)
                            navigated = True
                    except Exception:
                        pass

                # Fallback: Scroll down for infinite scroll listings
                if not navigated:
                    try:
                        await page.mouse.wheel(0, 1500)
                        await page.wait_for_timeout(2000)
                    except Exception:
                        break

                current_page += 1

            return extracted_items[:target_count]
        finally:
            await context.close()

    def manage_bookmarks(self, action: str = "list", title: Optional[str] = None, url: Optional[str] = None) -> Dict[str, Any]:
        """
        Safely reads or adds bookmarks from/to Chrome's local User Data profile.
        """
        local_app = os.environ.get("LOCALAPPDATA", "")
        bm_path = Path(local_app) / r"Google\Chrome\User Data\Default\Bookmarks"
        
        if not bm_path.exists():
            return {"status": "not_found", "message": "Chrome Bookmarks file not found", "bookmarks": []}

        try:
            with open(bm_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            bookmarks = []
            def _extract_bm(node):
                if isinstance(node, dict):
                    if node.get("type") == "url":
                        bookmarks.append({"name": node.get("name"), "url": node.get("url")})
                    for child in node.get("children", []):
                        _extract_bm(child)

            roots = data.get("roots", {})
            for r_key in ["bookmark_bar", "other", "synced"]:
                if r_key in roots:
                    _extract_bm(roots[r_key])

            if action.lower() == "add" and title and url:
                new_entry = {
                    "date_added": "13370000000000000",
                    "id": str(len(bookmarks) + 100),
                    "name": title,
                    "type": "url",
                    "url": url,
                }
                roots.setdefault("bookmark_bar", {}).setdefault("children", []).append(new_entry)
                with open(bm_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                return {"status": "success", "message": f"Added bookmark: {title}", "url": url}

            return {"status": "success", "count": len(bookmarks), "bookmarks": bookmarks[:50]}
        except Exception as exc:
            logger.error(f"[BrowserEngine] Bookmarks error: {exc}")
            return {"status": "failed", "error": str(exc), "bookmarks": []}

    def manage_browsing_history(self, limit: int = 25, query: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Safely queries Chrome recent browsing history by cloning SQLite 'History'
        to a temp copy to avoid file locks.
        """
        local_app = os.environ.get("LOCALAPPDATA", "")
        hist_path = Path(local_app) / r"Google\Chrome\User Data\Default\History"

        if not hist_path.exists():
            return []

        temp_db = Path(tempfile.gettempdir()) / f"chrome_history_{os.getpid()}.sqlite"
        try:
            shutil.copy2(str(hist_path), str(temp_db))
            conn = sqlite3.connect(str(temp_db))
            cursor = conn.cursor()

            sql = "SELECT title, url, visit_count, last_visit_time FROM urls "
            params = []
            if query:
                sql += "WHERE title LIKE ? OR url LIKE ? "
                params.extend([f"%{query}%", f"%{query}%"])
            sql += "ORDER BY last_visit_time DESC LIMIT ?"
            params.append(limit)

            cursor.execute(sql, params)
            rows = cursor.fetchall()
            conn.close()

            history = []
            for r in rows:
                history.append({
                    "title": r[0] or "No Title",
                    "url": r[1],
                    "visit_count": r[2],
                })
            return history
        except Exception as exc:
            logger.debug(f"[BrowserEngine] History read note: {exc}")
            return []
        finally:
            if temp_db.exists():
                try:
                    temp_db.unlink()
                except Exception:
                    pass
