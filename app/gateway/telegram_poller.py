"""
NEXUS AI - Local Long-Polling Telegram Gateway Runner
Allows instant testing and continuous interactive button control in Telegram
without needing an external public webhook or ngrok tunnel.
"""

import asyncio
import logging
import httpx

from app.config import settings
from app.gateway.telegram_bot import TelegramGatewayBot
from app.gateway.telegram_hub import publish_or_update_master_hub
from app.services.messaging import telegram_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("telegram_poller")


async def run_poller():
    bot_token = settings.TELEGRAM_BOT_TOKEN
    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN is not configured in .env.")
        return

    logger.info("Starting NEXUS AI Telegram Long-Polling Engine...")

    # Drop any pending webhook to allow clean getUpdates
    base_url = f"https://api.telegram.org/bot{bot_token}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            await client.get(f"{base_url}/deleteWebhook?drop_pending_updates=False")
            logger.info("Webhook deleted to switch cleanly to getUpdates long-polling.")
        except Exception as e:
            logger.warning(f"deleteWebhook note: {e}")

    # Publish or update the Master Hub for the whitelisted chat
    chat_id = settings.ALLOWED_TELEGRAM_CHAT_IDS[0] if settings.ALLOWED_TELEGRAM_CHAT_IDS else None
    if chat_id:
        try:
            await publish_or_update_master_hub(chat_id=chat_id, target_deck="hub:main", edit_in_place=True)
            logger.info(f"Master Command Center published & pinned in Telegram chat {chat_id}.")
        except Exception as e:
            logger.warning(f"Initial Hub push note: {e}")

    offset = 0
    poll_client = httpx.AsyncClient(timeout=40.0)

    try:
        while True:
            try:
                resp = await poll_client.get(
                    f"{base_url}/getUpdates",
                    params={"offset": offset, "timeout": 25, "allowed_updates": ["message", "callback_query"]},
                )
                if not resp.is_success:
                    await asyncio.sleep(2)
                    continue

                data = resp.json()
                updates = data.get("result", [])
                for update in updates:
                    offset = update["update_id"] + 1

                    # Handle Callback Queries (Buttons)
                    if "callback_query" in update:
                        cb = update["callback_query"]
                        logger.info(f"Received CallbackQuery: '{cb.get('data')}' from {cb.get('from', {}).get('id')}")
                        asyncio.create_task(TelegramGatewayBot.handle_callback_query(cb))

                    # Handle Messages / Commands / Quick Buttons
                    elif "message" in update:
                        msg = update["message"]
                        text = (msg.get("text") or "").strip()
                        c_id = str(msg.get("chat", {}).get("id"))
                        from_id = str(msg.get("from", {}).get("id"))

                        if not text:
                            continue

                        logger.info(f"Received Message: '{text}' from {from_id}")

                        # Check quick remote button taps
                        if text == "🏠 Master Hub":
                            await publish_or_update_master_hub(chat_id=c_id, target_deck="hub:main", edit_in_place=False)
                        elif text == "⏯️ Play/Pause":
                            from app.tools.computer import control_media_playback
                            await control_media_playback("play_pause")
                            await telegram_service.send_text(chat_id=c_id, text="⏯️ Play/Pause toggled.")
                        elif text == "📸 Screenshot":
                            await TelegramGatewayBot.handle_screenshot_action(chat_id=c_id)
                        elif text == "📋 Run Clipboard":
                            fake_cb = {
                                "id": "btn_clip",
                                "from": {"id": int(from_id) if from_id.isdigit() else 0},
                                "message": {"message_id": msg.get("message_id"), "chat": {"id": c_id}},
                                "data": "hub:run_clipboard",
                            }
                            await TelegramGatewayBot.handle_callback_query(fake_cb)
                        elif text == "🎙️ Spoken Summary":
                            fake_cb = {
                                "id": "btn_voice",
                                "from": {"id": int(from_id) if from_id.isdigit() else 0},
                                "message": {"message_id": msg.get("message_id"), "chat": {"id": c_id}},
                                "data": "hub:voice_summary",
                            }
                            await TelegramGatewayBot.handle_callback_query(fake_cb)
                        elif text == "🛑 Emergency Halt":
                            from app.tools.computer import control_media_playback
                            await control_media_playback("pause")
                            await telegram_service.send_text(chat_id=c_id, text="🛑 *Emergency Halt Triggered*: Active background tasks and playback halted.")
                        elif text.startswith("/"):
                            await TelegramGatewayBot.handle_command(chat_id=c_id, command=text)
                        else:
                            # Natural language query -> route to brain/graph
                            from app.api.v1.webhooks import execute_task_graph_background, format_plan_summary
                            from app.core.planner import planner
                            import uuid
                            plan = await planner.generate_plan(prompt=text)
                            plan_text = format_plan_summary(plan)
                            await telegram_service.send_text(chat_id=c_id, text=plan_text)
                            asyncio.create_task(
                                execute_task_graph_background(
                                    task_id=str(uuid.uuid4())[:8],
                                    user_id=from_id,
                                    chat_id=c_id,
                                    channel="telegram",
                                    raw_prompt=text,
                                    plan_dict=plan.model_dump(),
                                )
                            )

            except asyncio.CancelledError:
                break
            except Exception as loop_err:
                logger.error(f"Polling loop exception: {loop_err}")
                await asyncio.sleep(2)
    finally:
        await poll_client.aclose()
        logger.info("NEXUS AI Telegram Long-Polling Engine stopped.")


if __name__ == "__main__":
    asyncio.run(run_poller())
