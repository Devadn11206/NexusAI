"""
NEXUS AI - Persistent WhatsApp Web Remote Dispatcher
Automates WhatsApp Web using persistent Playwright Chromium user data profiles,
contacts search, automatic file locating, file attachment, and delivery verification screenshots.
"""

import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from playwright.async_api import async_playwright

from app.config import settings
from app.core.security import resolve_safe_workspace_path

logger = logging.getLogger(__name__)

WHATSAPP_URL = "https://web.whatsapp.com"
WHATSAPP_USER_DATA_DIR = "./workspace/sessions/whatsapp_profile"


def find_target_file(file_query: str) -> Optional[Path]:
    """
    Searches workspace and subdirectories for the target file matching file_query.
    Returns resolved absolute Path or None.
    """
    clean_query = file_query.strip()
    direct_path = resolve_safe_workspace_path(clean_query)
    if direct_path.exists() and direct_path.is_file():
        return direct_path

    # Search recursively within ./workspace/
    ws_root = Path(settings.WORKSPACE_DIR).resolve()
    for p in ws_root.rglob("*"):
        if p.is_file() and clean_query.lower() in p.name.lower():
            return p

    return None


async def send_whatsapp_file(
    contact_name: str,
    file_query: str,
    caption: str = "",
    headless: bool = False,
    timeout_ms: int = 40000,
) -> Dict[str, Any]:
    """
    Launches persistent WhatsApp Web session, finds contact, attaches requested file,
    sends it with optional caption, and captures visual delivery proof.
    """
    logger.info(f"[WhatsAppDispatcher] Preparing dispatch: file='{file_query}' to '{contact_name}'")

    # 1. Resolve target file
    resolved_file = find_target_file(file_query)
    if not resolved_file:
        error_msg = f"Target file '{file_query}' not found in workspace."
        logger.error(f"[WhatsAppDispatcher] {error_msg}")
        return {"status": "failed", "error": error_msg}

    profile_dir = Path(WHATSAPP_USER_DATA_DIR).resolve()
    profile_dir.mkdir(parents=True, exist_ok=True)

    artifacts_dir = resolve_safe_workspace_path("artifacts")
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    proof_path = artifacts_dir / "whatsapp_sent_proof.png"

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=headless,
            channel="chrome",
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
            viewport=None if not headless else {"width": 1920, "height": 1080},
        )
        page = context.pages[0] if context.pages else await context.new_page()

        try:
            logger.info(f"[WhatsAppDispatcher] Navigating to {WHATSAPP_URL}...")
            await page.goto(WHATSAPP_URL, timeout=timeout_ms, wait_until="domcontentloaded")

            # Check if login QR code is displayed
            qr_canvas = page.locator("canvas[aria-label='Scan this QR code to link a device!']")
            if await qr_canvas.is_visible(timeout=4000):
                qr_proof = artifacts_dir / "whatsapp_qr_code.png"
                await page.screenshot(path=str(qr_proof))
                logger.warning("[WhatsAppDispatcher] WhatsApp session unauthenticated. QR code required.")
                return {
                    "status": "requires_auth",
                    "message": "Please scan WhatsApp QR code in the browser.",
                    "qr_screenshot": str(qr_proof),
                }

            # 2. Search for target contact
            search_box_selectors = [
                "div[contenteditable='true'][data-tab='3']",
                "div[role='textbox'][title='Search input textbox']",
                "div[role='textbox'][aria-label='Search or start new chat']",
                "[data-testid='chat-list-search']",
            ]
            search_input = None
            for sel in search_box_selectors:
                try:
                    locator = page.locator(sel).first
                    if await locator.is_visible(timeout=3000):
                        search_input = locator
                        break
                except Exception:
                    continue

            if not search_input:
                search_input = page.locator("div[contenteditable='true']").first

            await search_input.click()
            await search_input.fill("")
            await search_input.press_sequentially(contact_name, delay=60)
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(2000)

            # 3. Attach file via file chooser or file input
            attach_btn_selectors = [
                "span[data-icon='plus']",
                "span[data-icon='attach-menu-plus']",
                "div[title='Attach']",
                "button[aria-label='Attach']",
            ]
            for sel in attach_btn_selectors:
                try:
                    btn = page.locator(sel).first
                    if await btn.is_visible(timeout=2000):
                        await btn.click()
                        break
                except Exception:
                    continue

            # Set file input
            file_input = page.locator("input[type='file']").first
            await file_input.set_input_files(str(resolved_file))
            await page.wait_for_timeout(2000)

            # 4. Optional caption
            if caption:
                caption_input = page.locator("div[contenteditable='true'][data-tab='10']").first
                if await caption_input.is_visible(timeout=2000):
                    await caption_input.fill(caption)

            # 5. Send file
            send_btn = page.locator("span[data-icon='send'], div[aria-label='Send']").first
            if await send_btn.is_visible(timeout=3000):
                await send_btn.click()
            else:
                await page.keyboard.press("Enter")

            # Wait for message upload and delivery
            await page.wait_for_timeout(3500)

            # 6. Capture proof screenshot
            await page.screenshot(path=str(proof_path))
            logger.info(f"[WhatsAppDispatcher] File sent successfully: proof={proof_path}")

            return {
                "status": "success",
                "contact": contact_name,
                "file": str(resolved_file),
                "caption": caption,
                "proof_screenshot": str(proof_path),
            }

        except Exception as exc:
            logger.error(f"[WhatsAppDispatcher] Error sending file: {exc}", exc_info=True)
            return {"status": "failed", "error": str(exc)}
        finally:
            await context.close()

