import asyncio
import logging
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas import (
    TelegramWebhookPayload,
    WhatsAppWebhookPayload,
    WebhookIngressResponse,
)
from app.config import settings
from app.core.database import get_db_session
from app.core.security import verify_sender_authorized
from app.core.voice import transcribe_audio
from app.core.planner import planner
from app.db.models import User, Task, TaskStatus
from app.services.messaging import telegram_service, whatsapp_service
from app.agents.graph import nexus_graph

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


async def execute_task_graph_background(
    task_id: str,
    user_id: str,
    chat_id: str,
    channel: str,
    raw_prompt: str,
    plan_dict: dict,
):
    """
    Executes the synthesized DAG through LangGraph asynchronously in background.
    Updates task state and notifies user on completion.
    """
    logger.info(f"Background LangGraph runner launched for task {task_id}.")
    initial_state = {
        "user_id": user_id,
        "chat_id": chat_id,
        "channel": channel,
        "raw_prompt": raw_prompt,
        "task_graph": plan_dict,
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

    config = {"configurable": {"thread_id": str(task_id)}}

    try:
        final_state = await nexus_graph.ainvoke(initial_state, config=config)
        logger.info(f"Task {task_id} completed successfully via LangGraph.")

        # Outbound notification on completion
        completed_count = len(final_state.get("completed_steps", []))
        verification_summary = final_state.get("agent_outputs", {}).get("verification", {}).get("summary", "Finished.")
        summary = (
            f"✅ *NEXUS AI Answer* ({completed_count} steps executed):\n\n"
            f"{verification_summary}"
        )

        if channel == "telegram":
            await telegram_service.send_text(chat_id=chat_id, text=summary)
            # Dispatch artifacts if any
            for art in final_state.get("artifacts", []):
                try:
                    await telegram_service.send_document(
                        chat_id=chat_id,
                        file_path=art["path"],
                        caption=f"Generated artifact: {art['filename']}",
                    )
                except Exception as file_err:
                    logger.warning(f"Could not dispatch artifact: {file_err}")
        else:
            await whatsapp_service.send_text(phone=chat_id, text=summary)

    except Exception as exc:
        logger.error(f"Error during background LangGraph execution for task {task_id}: {exc}", exc_info=True)
        fail_msg = f"❌ *NEXUS AI Task Failed*: Execution halted with error: {str(exc)}"
        if channel == "telegram":
            await telegram_service.send_text(chat_id=chat_id, text=fail_msg)
        else:
            await whatsapp_service.send_text(phone=chat_id, text=fail_msg)


async def get_or_create_user(
    session: AsyncSession,
    channel: str,
    sender_id: str,
) -> User:
    """Find an existing user or create a new whitelisted record."""
    if channel == "telegram":
        stmt = select(User).where(User.telegram_chat_id == sender_id)
    else:
        stmt = select(User).where(User.whatsapp_phone == sender_id)

    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            telegram_chat_id=sender_id if channel == "telegram" else None,
            whatsapp_phone=sender_id if channel == "whatsapp" else None,
            is_whitelisted=True,
            user_metadata={"registered_via": channel},
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    return user


def format_plan_summary(plan) -> str:
    """Formats TaskGraph into human-readable messaging summary."""
    lines = [f"⚡ *NEXUS AI Plan Generated* ({plan.intent_category.value})"]
    lines.append(f"📋 *Summary*: _{plan.summary}_\n")
    lines.append("🔹 *Execution Steps (DAG)*:")
    for idx, step in enumerate(plan.steps, 1):
        dep_str = f" [depends on: {', '.join(step.depends_on)}]" if step.depends_on else ""
        lines.append(f"  {idx}. `{step.target_agent.value}` ➔ {step.description}{dep_str}")
    return "\n".join(lines)


@router.get("/whatsapp")
async def verify_whatsapp_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
):
    """Handles WhatsApp Meta Cloud API webhook verification challenge handshake."""
    if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN:
        logger.info("WhatsApp webhook handshake challenge verified successfully.")
        return Response(content=hub_challenge or "", media_type="text/plain")
    logger.warning("WhatsApp webhook verification failed token handshake.")
    return Response(content="Verification failed", status_code=status.HTTP_403_FORBIDDEN)


@router.post("/telegram", response_model=WebhookIngressResponse)
async def receive_telegram_webhook(
    payload: TelegramWebhookPayload,
    session: AsyncSession = Depends(get_db_session),
) -> WebhookIngressResponse:
    """
    Ingress endpoint for Telegram updates.
    Decomposes prompts into DAG TaskGraph and initiates LangGraph multi-agent execution.
    """
    # 1. Handle Callback Queries (Buttons from /menu or actions)
    if payload.callback_query:
        from app.gateway.telegram_bot import TelegramGatewayBot
        cb_dict = payload.callback_query.model_dump(by_alias=True)
        cb_res = await TelegramGatewayBot.handle_callback_query(cb_dict)
        return WebhookIngressResponse(
            success=True,
            task_id=uuid.uuid4(),
            status="CALLBACK_PROCESSED",
            message=f"Callback handled: {cb_res.get('status')}",
        )

    if not payload.message:
        return WebhookIngressResponse(
            success=True,
            task_id=uuid.uuid4(),
            status="IGNORED",
            message="No message found in update.",
        )

    sender_id = str(payload.message.from_.id)
    chat_id = str(payload.message.chat.id)

    # 2. Gatekeeper Verification: Fast-fail if not whitelisted
    verify_sender_authorized(sender_id=sender_id, channel="telegram")

    # 3. Check for Slash Commands (/menu, /apps, /start)
    if payload.message.text and payload.message.text.strip().startswith("/"):
        from app.gateway.telegram_bot import TelegramGatewayBot
        cmd = payload.message.text.strip()
        await TelegramGatewayBot.handle_command(chat_id=chat_id, command=cmd)
        return WebhookIngressResponse(
            success=True,
            task_id=uuid.uuid4(),
            status="COMMAND_PROCESSED",
            message=f"Command executed: {cmd}",
        )

    prompt: Optional[str] = None

    # 2. Extract Text or Download & Transcribe Voice Note
    if payload.message.text:
        prompt = payload.message.text.strip()
    elif payload.message.voice:
        file_id = payload.message.voice.file_id
        logger.info(f"Received Telegram voice note ({file_id}) from user {sender_id}. Downloading...")
        try:
            audio_bytes = await telegram_service.download_file_bytes(file_id)
            prompt = await transcribe_audio(audio_bytes, filename=f"voice_{file_id}.ogg")
            logger.info(f"Telegram voice note transcribed: '{prompt}'")
        except Exception as exc:
            logger.error(f"Failed to process Telegram voice note: {exc}", exc_info=True)
            await telegram_service.send_text(
                chat_id=chat_id,
                text="❌ *NEXUS AI Error*: Failed to transcribe your voice note. Please try again or send text.",
            )
            return WebhookIngressResponse(
                success=False,
                task_id=uuid.uuid4(),
                status="FAILED",
                message=f"Voice transcription failed: {str(exc)}",
            )
    elif payload.message.audio:
        file_id = payload.message.audio.file_id
        logger.info(f"Received Telegram audio file ({file_id}) from user {sender_id}. Downloading...")
        try:
            audio_bytes = await telegram_service.download_file_bytes(file_id)
            fname = payload.message.audio.file_name or f"audio_{file_id}.mp3"
            prompt = await transcribe_audio(audio_bytes, filename=fname)
            logger.info(f"Telegram audio transcribed: '{prompt}'")
        except Exception as exc:
            logger.error(f"Failed to process Telegram audio: {exc}", exc_info=True)
            await telegram_service.send_text(
                chat_id=chat_id,
                text="❌ *NEXUS AI Error*: Failed to process your audio file. Please try again.",
            )
            return WebhookIngressResponse(
                success=False,
                task_id=uuid.uuid4(),
                status="FAILED",
                message=f"Audio transcription failed: {str(exc)}",
            )

    if not prompt:
        return WebhookIngressResponse(
            success=True,
            task_id=uuid.uuid4(),
            status="IGNORED",
            message="No actionable text or audio content found.",
        )

    # 3. Intent Analysis, Ambiguity Check & DAG Generation
    plan = await planner.generate_plan(prompt=prompt)

    task_status = TaskStatus.REQUIRES_USER_INPUT if plan.requires_clarification else TaskStatus.EXECUTING

    try:
        user = await get_or_create_user(session, channel="telegram", sender_id=sender_id)
        task = Task(
            user_id=user.id,
            prompt=prompt,
            channel="telegram",
            status=task_status,
            task_graph=plan.model_dump(),
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)
        task_id = task.id
    except Exception as exc:
        logger.warning(f"Database unavailable for task persistence (proceeding with ephemeral UUID): {exc}")
        task_id = uuid.uuid4()

    # 4. Outbound Response & Asynchronous Execution Trigger
    try:
        if plan.requires_clarification:
            clarify_text = f"❓ *NEXUS AI Clarification Needed*:\n\n{plan.clarification_prompt}"
            await telegram_service.send_text(chat_id=chat_id, text=clarify_text)
        else:
            plan_text = format_plan_summary(plan)
            await telegram_service.send_text(chat_id=chat_id, text=plan_text)
            # Launch multi-agent execution asynchronously in background
            asyncio.create_task(
                execute_task_graph_background(
                    task_id=str(task_id),
                    user_id=str(sender_id),
                    chat_id=chat_id,
                    channel="telegram",
                    raw_prompt=prompt,
                    plan_dict=plan.model_dump(),
                )
            )
    except Exception as exc:
        logger.warning(f"Could not send Telegram reply (check credentials): {exc}")

    return WebhookIngressResponse(
        success=True,
        task_id=task_id,
        status=task_status.value,
        message="Ambiguity clarification requested." if plan.requires_clarification else "Plan enqueued and executing.",
    )


@router.post("/whatsapp", response_model=WebhookIngressResponse)
async def receive_whatsapp_webhook(
    payload: WhatsAppWebhookPayload,
    session: AsyncSession = Depends(get_db_session),
) -> WebhookIngressResponse:
    """
    Ingress endpoint for WhatsApp updates.
    Decomposes prompts into DAG TaskGraph and initiates LangGraph multi-agent execution.
    """
    msg_item = None
    for entry in payload.entry:
        for change in entry.changes:
            if change.value.messages:
                msg_item = change.value.messages[0]
                break
        if msg_item:
            break

    if not msg_item:
        return WebhookIngressResponse(
            success=True,
            task_id=uuid.uuid4(),
            status="IGNORED",
            message="No message content found in WhatsApp payload.",
        )

    sender_phone = msg_item.from_

    # 1. Gatekeeper Verification: Fast-fail if not whitelisted
    verify_sender_authorized(sender_id=sender_phone, channel="whatsapp")

    prompt: Optional[str] = None

    # 2. Extract Text or Download & Transcribe Voice Note
    if msg_item.text:
        prompt = msg_item.text.body.strip()
    elif msg_item.audio or msg_item.voice:
        audio_obj = msg_item.audio or msg_item.voice
        media_id = audio_obj.id
        logger.info(f"Received WhatsApp voice/audio ({media_id}) from {sender_phone}. Downloading...")
        try:
            audio_bytes = await whatsapp_service.download_media_bytes(media_id)
            prompt = await transcribe_audio(audio_bytes, filename=f"wa_voice_{media_id}.ogg")
            logger.info(f"WhatsApp audio transcribed: '{prompt}'")
        except Exception as exc:
            logger.error(f"Failed to process WhatsApp audio: {exc}", exc_info=True)
            await whatsapp_service.send_text(
                phone=sender_phone,
                text="❌ *NEXUS AI Error*: Failed to transcribe your voice note. Please try again or send text.",
            )
            return WebhookIngressResponse(
                success=False,
                task_id=uuid.uuid4(),
                status="FAILED",
                message=f"WhatsApp voice transcription failed: {str(exc)}",
            )

    if not prompt:
        return WebhookIngressResponse(
            success=True,
            task_id=uuid.uuid4(),
            status="IGNORED",
            message="No actionable text or audio in WhatsApp payload.",
        )

    # 3. Intent Analysis, Ambiguity Check & DAG Generation
    plan = await planner.generate_plan(prompt=prompt)
    task_status = TaskStatus.REQUIRES_USER_INPUT if plan.requires_clarification else TaskStatus.EXECUTING

    try:
        user = await get_or_create_user(session, channel="whatsapp", sender_id=sender_phone)
        task = Task(
            user_id=user.id,
            prompt=prompt,
            channel="whatsapp",
            status=task_status,
            task_graph=plan.model_dump(),
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)
        task_id = task.id
    except Exception as exc:
        logger.warning(f"Database unavailable for task persistence (proceeding with ephemeral UUID): {exc}")
        task_id = uuid.uuid4()

    # 4. Outbound Response & Asynchronous Execution Trigger
    try:
        if plan.requires_clarification:
            clarify_text = f"❓ *NEXUS AI Clarification Needed*:\n\n{plan.clarification_prompt}"
            await whatsapp_service.send_text(phone=sender_phone, text=clarify_text)
        else:
            plan_text = format_plan_summary(plan)
            await whatsapp_service.send_text(phone=sender_phone, text=plan_text)
            asyncio.create_task(
                execute_task_graph_background(
                    task_id=str(task_id),
                    user_id=str(sender_phone),
                    chat_id=sender_phone,
                    channel="whatsapp",
                    raw_prompt=prompt,
                    plan_dict=plan.model_dump(),
                )
            )
    except Exception as exc:
        logger.warning(f"Could not send WhatsApp reply (check credentials): {exc}")

    return WebhookIngressResponse(
        success=True,
        task_id=task_id,
        status=task_status.value,
        message="Ambiguity clarification requested." if plan.requires_clarification else "Plan enqueued and executing.",
    )
