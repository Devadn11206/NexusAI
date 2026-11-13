"""
NEXUS AI - External Inbound Webhook Gateway Endpoint
Listens for external JSON events (GitHub, Stripe, custom webhooks)
and queues execution through the LangGraph Supervisor DAG.
"""

import uuid
import logging
from typing import Dict, Any
from fastapi import APIRouter, status, BackgroundTasks
from pydantic import BaseModel

from app.core.planner import planner
from app.agents.graph import nexus_graph

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["External Webhooks"])


class GenericWebhookPayload(BaseModel):
    event_type: str = "generic_event"
    payload: Dict[str, Any] = {}


async def _run_webhook_plan(prompt: str, user_id: str):
    try:
        plan = await planner.generate_plan(prompt=prompt)
        initial_state = {
            "user_id": user_id,
            "chat_id": user_id,
            "channel": "webhook",
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
        await nexus_graph.ainvoke(initial_state)
        logger.info(f"[ExternalWebhook] Completed webhook execution for prompt: '{prompt}'")
    except Exception as exc:
        logger.error(f"[ExternalWebhook] Failed running webhook task: {exc}", exc_info=True)


@router.post("/{source}", status_code=status.HTTP_200_OK)
async def handle_inbound_webhook(
    source: str,
    data: GenericWebhookPayload,
    background_tasks: BackgroundTasks,
):
    """
    Receives external inbound webhooks, translates payload into prompt,
    and runs multi-agent execution asynchronously.
    """
    logger.info(f"[ExternalWebhook] Received webhook from source='{source}', event='{data.event_type}'")

    prompt = f"Process inbound webhook from {source}: event '{data.event_type}' with payload {data.payload}"
    user_id = f"webhook_{source}_{uuid.uuid4().hex[:6]}"

    background_tasks.add_task(_run_webhook_plan, prompt, user_id)

    return {
        "status": "accepted",
        "source": source,
        "event_type": data.event_type,
        "message": "Webhook queued for LangGraph multi-agent execution.",
    }

