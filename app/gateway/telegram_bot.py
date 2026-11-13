"""
NEXUS AI - Telegram Gateway & Callback Router
Processes incoming updates, handles command routing (/menu, /apps, /start),
and routes callback queries (app launching, pagination, screenshots, re-scanning)
directly to host OS automation engines.
"""

import asyncio
import logging
from typing import Dict, Any, Optional

from app.core.security import is_telegram_user_whitelisted
from app.core.repo_scanner import RepoAppScanner
from app.gateway.telegram_menu import (
    build_dynamic_control_center,
    get_control_center_message_text,
    get_music_control_keyboard,
    get_music_control_message_text,
)
from app.services.messaging import telegram_service
from app.tools.computer import launch_application, close_application, capture_desktop_screenshot, control_music_playback

logger = logging.getLogger(__name__)


class TelegramGatewayBot:
    """Central handler for Telegram commands and interactive callback queries."""

    @classmethod
    async def handle_command(cls, chat_id: str, command: str) -> None:
        """Handles slash commands like /menu, /apps, /start, /close."""
        cmd_clean = command.strip().lower()
        if cmd_clean in ("/menu", "/apps", "/start", "/control"):
            msg_text = get_control_center_message_text()
            markup = build_dynamic_control_center(page=1)
            await telegram_service.send_menu(chat_id=chat_id, text=msg_text, reply_markup=markup)
        elif cmd_clean in ("/music", "/player", "/spotify"):
            kb = get_music_control_keyboard()
            msg = get_music_control_message_text()
            await telegram_service.send_menu(chat_id=chat_id, text=msg, reply_markup=kb)
        elif cmd_clean == "/screenshot":
            await cls.handle_screenshot_action(chat_id=chat_id)
        elif cmd_clean.startswith("/close") or cmd_clean.startswith("/quit") or cmd_clean.startswith("/kill"):
            # Syntax: /close <app_name> or /close notepad
            parts = command.strip().split(maxsplit=1)
            target = parts[1].strip() if len(parts) > 1 else ""
            if not target:
                await telegram_service.send_text(
                    chat_id=chat_id,
                    text="ℹ️ *Close Command Usage*:\n`/close <app_name>`\nExample: `/close notepad` or `/close chrome` or `/close spotify`"
                )
                return

            res = await close_application(target)
            if res.get("status") == "success":
                await telegram_service.send_text(
                    chat_id=chat_id,
                    text=f"🛑 *Closed Application*: Successfully closed `{target}` ({res.get('terminated_count', 1)} process instance(s) terminated)."
                )
                # Send proof screenshot
                try:
                    await cls.handle_screenshot_action(chat_id=chat_id)
                except Exception:
                    pass
            else:
                await telegram_service.send_text(
                    chat_id=chat_id,
                    text=f"⚠️ *Not Found*: No active running window or process matching `{target}` on your laptop."
                )
        else:
            await telegram_service.send_text(
                chat_id=chat_id,
                text="ℹ️ Send /menu or /apps to open the Laptop Control Center, or `/close <app>` to quit an app."
            )

    @classmethod
    async def handle_callback_query(cls, callback_query: Dict[str, Any]) -> Dict[str, Any]:
        """
        Routes callback query actions:
        - launch:<app_alias>
        - menu:page:<n>
        - action:screenshot
        - action:rescan
        """
        cb_id = str(callback_query.get("id"))
        from_user = callback_query.get("from", {})
        sender_id = str(from_user.get("id"))
        message = callback_query.get("message", {})
        chat = message.get("chat", {})
        chat_id = str(chat.get("id", sender_id))
        message_id = message.get("message_id")
        data = str(callback_query.get("data", ""))

        # 1. Gatekeeper Authorization Check
        if not is_telegram_user_whitelisted(sender_id):
            logger.warning(f"[TelegramGateway] Unauthorized callback query from: {sender_id}")
            try:
                await telegram_service.answer_callback_query(
                    callback_query_id=cb_id,
                    text="⛔ Unauthorized user access denied.",
                    show_alert=True
                )
            except Exception:
                pass
            return {"status": "unauthorized"}

        logger.info(f"[TelegramGateway] Handling callback '{data}' from {sender_id} in chat {chat_id}")

        # 2. Application Launch Dispatch
        if data.startswith("launch:"):
            app_alias = data.split(":", 1)[1]
            try:
                await telegram_service.answer_callback_query(
                    callback_query_id=cb_id,
                    text=f"🚀 Launching '{app_alias}' on laptop screen..."
                )
            except Exception as exc:
                logger.debug(f"Acknowledge note: {exc}")

            # Invoke launch_application to pop window directly to foreground
            launch_res = await launch_application(app_alias)

            # Auto-capture proof screenshot
            proof_path: Optional[str] = None
            try:
                proof_path = await capture_desktop_screenshot(filename=f"launch_{app_alias}.png")
            except Exception as e:
                logger.warning(f"Screenshot capture note: {e}")

            # Send visual confirmation with quick Close button
            status_text = (
                f"✅ **Application Launched**: `{app_alias}`\n"
                f"• **Status**: Active in visual foreground\n"
                f"• **Result**: {launch_res.get('message', 'Window rendered')}\n\n"
                f"Tap below or send `/close {app_alias}` to quit when done:"
            )
            close_markup = {
                "inline_keyboard": [
                    [
                        {"text": f"🛑 Close {app_alias.capitalize()}", "callback_data": f"close:{app_alias}"},
                        {"text": "📸 Refresh Screenshot", "callback_data": "action:screenshot"},
                    ]
                ]
            }
            await telegram_service.send_text(chat_id=chat_id, text=status_text)
            await telegram_service.send_menu(chat_id=chat_id, text=f"⚡ Control `{app_alias}`:", reply_markup=close_markup)

            if proof_path:
                try:
                    await telegram_service.send_image(
                        chat_id=chat_id,
                        image_bytes_or_path=proof_path,
                        caption=f"📸 Proof: '{app_alias}' open on laptop screen"
                    )
                except Exception as img_err:
                    logger.warning(f"Failed sending proof photo: {img_err}")

            return {"status": "launched", "app": app_alias, "result": launch_res}

        # 3. Application Close Callback
        elif data.startswith("close:"):
            app_target = data.split(":", 1)[1]
            try:
                await telegram_service.answer_callback_query(
                    callback_query_id=cb_id,
                    text=f"🛑 Closing '{app_target}' on laptop screen..."
                )
            except Exception:
                pass

            close_res = await close_application(app_target)
            if close_res.get("status") == "success":
                await telegram_service.send_text(
                    chat_id=chat_id,
                    text=f"🛑 *Closed Application*: Successfully closed `{app_target}` on your laptop."
                )
                try:
                    await cls.handle_screenshot_action(chat_id=chat_id)
                except Exception:
                    pass
            else:
                await telegram_service.send_text(
                    chat_id=chat_id,
                    text=f"⚠️ *Not Running*: `{app_target}` is not currently open on your screen."
                )
            return {"status": "closed", "app": app_target, "result": close_res}

        # 3. Menu Pagination
        elif data.startswith("menu:page:"):
            try:
                target_page = int(data.split(":")[2])
            except (IndexError, ValueError):
                target_page = 1

            new_markup = build_dynamic_control_center(page=target_page)
            msg_text = get_control_center_message_text()

            if message_id:
                try:
                    await telegram_service.edit_message_reply_markup(
                        chat_id=chat_id,
                        message_id=message_id,
                        reply_markup=new_markup,
                        text=msg_text,
                    )
                except Exception as exc:
                    logger.warning(f"Edit message note: {exc}")

            try:
                await telegram_service.answer_callback_query(callback_query_id=cb_id)
            except Exception:
                pass
            return {"status": "page_changed", "page": target_page}

        # 4. Action: Screenshot
        elif data == "action:screenshot":
            try:
                await telegram_service.answer_callback_query(
                    callback_query_id=cb_id, text="📸 Capturing live laptop screen..."
                )
            except Exception:
                pass
            await cls.handle_screenshot_action(chat_id=chat_id)
            return {"status": "screenshot_sent"}

        # 5. Action: Re-Scan Workspace Apps
        elif data == "action:rescan":
            try:
                await telegram_service.answer_callback_query(
                    callback_query_id=cb_id, text="🔄 Scanning workspace for app configs..."
                )
            except Exception:
                pass

            # Refresh list
            apps = RepoAppScanner.get_all_registered_apps()
            new_markup = build_dynamic_control_center(page=1)
            msg_text = (
                f"🔄 *Repository Scanned Successfully!*\n"
                f"Discovered **{len(apps)}** application definitions across workspace.\n\n"
                f"{get_control_center_message_text(len(apps))}"
            )

            if message_id:
                try:
                    await telegram_service.edit_message_reply_markup(
                        chat_id=chat_id,
                        message_id=message_id,
                        reply_markup=new_markup,
                        text=msg_text,
                    )
                except Exception as exc:
                    logger.warning(f"Edit message note on rescan: {exc}")

            return {"status": "rescanned", "total_apps": len(apps)}

        # 6. Specialized Music Controller Callbacks
        elif data.startswith("music:"):
            sub_action = data.split(":", 1)[1]
            if sub_action == "play_pause":
                res = await control_music_playback("play_pause")
            elif sub_action == "next":
                res = await control_music_playback("next")
            elif sub_action == "vol_up":
                res = await control_music_playback("volume_up")
            elif sub_action == "vol_down":
                res = await control_music_playback("volume_down")
            elif sub_action == "now_playing":
                res = await control_music_playback("status")
            elif sub_action.startswith("launch:"):
                target_app = sub_action.split(":", 1)[1]
                res = await launch_application(target_app)
            else:
                res = await control_music_playback(sub_action)

            now_p = res.get("now_playing") or res.get("app") or "Active Media"
            try:
                await telegram_service.answer_callback_query(
                    callback_query_id=cb_id, text=f"🎵 {sub_action.replace('_', ' ').title()}"
                )
            except Exception:
                pass

            if message_id:
                try:
                    kb = get_music_control_keyboard()
                    msg = get_music_control_message_text(now_playing=now_p)
                    await telegram_service.edit_message_reply_markup(
                        chat_id=chat_id,
                        message_id=message_id,
                        reply_markup=kb,
                        text=msg,
                    )
                except Exception as edit_err:
                    logger.debug(f"Edit music menu note: {edit_err}")

            return {"status": "music_action_success", "action": sub_action, "details": res}

        # Default no-op
        try:
            await telegram_service.answer_callback_query(callback_query_id=cb_id)
        except Exception:
            pass
        return {"status": "noop"}

    @classmethod
    async def handle_screenshot_action(cls, chat_id: str) -> None:
        """Captures a screenshot of the laptop monitor and transmits it to the chat."""
        try:
            shot_path = await capture_desktop_screenshot(filename="control_center_screen.png")
            await telegram_service.send_image(
                chat_id=chat_id,
                image_bytes_or_path=shot_path,
                caption="📸 Current Laptop Desktop View"
            )
        except Exception as exc:
            logger.error(f"Failed capturing desktop screenshot: {exc}")
            await telegram_service.send_text(
                chat_id=chat_id,
                text=f"❌ Failed capturing screenshot: {exc}"
            )

