"""
NEXUS AI - Local Telegram Poller / Direct Runner
Lets you talk to @ddnandu3_bot directly without needing ngrok or a public domain!
"""
import asyncio
import logging
import httpx
from app.config import settings
from app.services.messaging import telegram_service
from app.core.planner import planner
from app.agents.graph import nexus_graph
from app.core.voice import transcribe_audio
from app.core.security import is_telegram_user_whitelisted
from app.gateway.telegram_bot import TelegramGatewayBot

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("nexus-poller")


async def process_incoming_telegram_message(message: dict):
    from_user = message.get("from", {})
    chat = message.get("chat", {})
    sender_id = str(from_user.get("id"))
    chat_id = str(chat.get("id"))

    # 1. Gatekeeper Check
    if not is_telegram_user_whitelisted(sender_id):
        logger.warning(f"Rejected message from non-whitelisted sender: {sender_id}")
        return

    # 2. Check for commands (/menu, /apps, /start)
    if message.get("text"):
        text_str = message.get("text").strip()
        if text_str.startswith("/"):
            await TelegramGatewayBot.handle_command(chat_id=chat_id, command=text_str)
            return

    # 3. Extract Text or Transcribe Voice
    prompt = None
    if message.get("text"):
        prompt = message.get("text").strip()
    elif message.get("voice"):
        file_id = message["voice"]["file_id"]
        logger.info(f"Downloading Telegram voice note: {file_id}...")
        try:
            audio_bytes = await telegram_service.download_file_bytes(file_id)
            prompt = await transcribe_audio(audio_bytes, filename=f"voice_{file_id}.ogg")
            logger.info(f"Voice note transcribed: '{prompt}'")
        except Exception as exc:
            logger.error(f"Voice transcription failed: {exc}")
            await telegram_service.send_text(chat_id=chat_id, text=f"❌ Voice note error: {exc}")
            return

    if not prompt:
        return

    logger.info(f"Received prompt from {sender_id}: {prompt}")

    # 3. Intent & DAG Planning
    plan = await planner.generate_plan(prompt=prompt)

    if plan.requires_clarification:
        clarify_msg = f"❓ *Clarification Needed*:\n\n{plan.clarification_prompt}"
        await telegram_service.send_text(chat_id=chat_id, text=clarify_msg)
        return

    # 4. Send Plan Acknowledgment
    lines = [f"⚡ *Plan Generated* ({plan.intent_category.value})"]
    lines.append(f"📋 *Summary*: _{plan.summary}_\n")
    lines.append("🔹 *Execution Steps (DAG)*:")
    for idx, step in enumerate(plan.steps, 1):
        lines.append(f"  {idx}. `{step.target_agent.value}` ➔ {step.description}")
    await telegram_service.send_text(chat_id=chat_id, text="\n".join(lines))

    # 5. Execute LangGraph Multi-Agent System
    initial_state = {
        "user_id": sender_id,
        "chat_id": chat_id,
        "channel": "telegram",
        "raw_prompt": prompt,
        "task_graph": plan.model_dump(),
        "current_step_id": None,
        "completed_steps": [],
        "failed_steps": [],
        "step_results": {},
        "retry_counts": {},
        "is_graph_complete": False,
        "agent_outputs": {},
        "artifacts": [],
        "token_usage": {},
        "hitl_approval_required": False,
        "hitl_payload": None,
        "error_logs": [],
    }

    config = {"configurable": {"thread_id": f"chat_{chat_id}"}}
    try:
        final_state = await nexus_graph.ainvoke(initial_state, config=config)

        # Notify completion with synthesized answer
        answer = final_state.get("agent_outputs", {}).get("verification", {}).get("summary", "Task executed successfully.")
        
        reply_message = (
            f"✅ *NEXUS AI Answer*:\n\n"
            f"{answer}"
        )
        await telegram_service.send_text(chat_id=chat_id, text=reply_message)

        # Send any screenshots / files generated
        for art in final_state.get("artifacts", []):
            try:
                await telegram_service.send_document(
                    chat_id=chat_id,
                    file_path=art["path"],
                    caption=f"Generated: {art['filename']}",
                )
            except Exception as e:
                logger.warning(f"Could not send artifact: {e}")

    except Exception as exc:
        logger.error(f"Execution error: {exc}", exc_info=True)
        await telegram_service.send_text(chat_id=chat_id, text=f"❌ Execution failed: {exc}")


async def poll_telegram():
    token = settings.TELEGRAM_BOT_TOKEN
    base_url = f"https://api.telegram.org/bot{token}"
    offset = 0

    print("\n=======================================================")
    print("🤖 NEXUS AI Telegram Poller is LIVE!")
    print(f"👉 Open Telegram and message your bot: @ddnandu3_bot")
    print("   Send text or send a voice note!")
    print("=======================================================\n")

    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            try:
                resp = await client.get(f"{base_url}/getUpdates", params={"offset": offset, "timeout": 20})
                if resp.status_code == 200:
                    data = resp.json()
                    for update in data.get("result", []):
                        offset = update["update_id"] + 1
                        if "message" in update:
                            asyncio.create_task(process_incoming_telegram_message(update["message"]))
                        elif "callback_query" in update:
                            asyncio.create_task(TelegramGatewayBot.handle_callback_query(update["callback_query"]))
            except Exception as exc:
                logger.warning(f"Polling error (will retry): {exc}")
                await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(poll_telegram())

