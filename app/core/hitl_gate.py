"""
NEXUS AI - Advanced Security & Human-in-the-Loop (HITL) Gates
Intercepts high-risk operations, pauses execution, and requests user approval via Telegram.
"""

import asyncio
import logging
import uuid
from typing import Dict, Any, Optional

from app.services.messaging import telegram_service
from app.config import settings

logger = logging.getLogger(__name__)


class HITLApprovalManager:
    """
    Manages pending human approval gates, tracking approval IDs and waking waiting coroutines.
    """

    def __init__(self):
        self._pending_approvals: Dict[str, asyncio.Event] = {}
        self._approval_verdicts: Dict[str, bool] = {}
        self._approval_metadata: Dict[str, Dict[str, Any]] = {}

    def create_gate(
        self,
        action_name: str,
        reason: str,
        chat_id: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Creates an approval gate with a unique ID."""
        approval_id = str(uuid.uuid4())[:8]
        event = asyncio.Event()
        self._pending_approvals[approval_id] = event
        self._approval_metadata[approval_id] = {
            "action_name": action_name,
            "reason": reason,
            "chat_id": chat_id,
            "details": details or {},
        }
        return approval_id

    async def request_and_wait_for_approval(
        self,
        approval_id: str,
        timeout_seconds: int = 120,
    ) -> bool:
        """
        Dispatches approval buttons to Telegram and halts until user clicks Approve/Reject
        or timeout expires.
        """
        meta = self._approval_metadata.get(approval_id)
        if not meta:
            return False

        chat_id = meta["chat_id"]
        action_name = meta["action_name"]
        reason = meta["reason"]

        msg = (
            f"⚠️ *Human-in-the-Loop Approval Required*\n\n"
            f"• **Action**: `{action_name}`\n"
            f"• **Reason**: {reason}\n\n"
            f"Please approve or reject this system execution on your phone:"
        )

        try:
            await telegram_service.send_approval_buttons(
                chat_id=chat_id,
                text=msg,
                approval_id=approval_id,
            )
        except Exception as exc:
            logger.error(f"[HITLManager] Failed to send approval buttons: {exc}")

        event = self._pending_approvals.get(approval_id)
        if not event:
            return False

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout_seconds)
            return self._approval_verdicts.get(approval_id, False)
        except asyncio.TimeoutError:
            logger.warning(f"[HITLManager] Approval gate {approval_id} timed out.")
            return False
        finally:
            self._pending_approvals.pop(approval_id, None)

    def resolve_gate(self, approval_id: str, approved: bool) -> bool:
        """Resolves a pending approval gate from a Telegram callback query."""
        if approval_id in self._pending_approvals:
            self._approval_verdicts[approval_id] = approved
            event = self._pending_approvals[approval_id]
            event.set()
            logger.info(f"[HITLManager] Resolved gate {approval_id}: {'APPROVED' if approved else 'REJECTED'}")
            return True
        return False

    async def request_voice_or_telegram_approval(
        self,
        action_summary: str,
        thread_id: str = "default",
        timeout: int = 45,
        spoken_callback=None,
    ) -> bool:
        """
        Dual Voice + Telegram Approval:
        1. Emits voice prompt over live call WebSocket (or local TTS).
        2. Dispatches Telegram approval buttons simultaneously.
        3. Allows instant resolution if the user says 'yes', 'confirm', or 'approve',
           or clicks [Approve] on Telegram.
        """
        gate_id = self.create_gate(
            action_name=action_summary,
            reason="Sensitive system command requires explicit human authorization.",
            chat_id="6663290532",
        )

        spoken_prompt = f"Confirmation required for: {action_summary}. Say 'Yes, confirm' or 'Cancel'."
        if spoken_callback:
            try:
                res = spoken_callback(spoken_prompt, gate_id)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as e:
                logger.debug(f"[HITLManager] Spoken callback note: {e}")

        # Wait for either Telegram button click or spoken voice recognition verdict
        verdict = await self.request_and_wait_for_approval(approval_id=gate_id, timeout_seconds=timeout)
        return verdict

    def handle_voice_utterance_for_gate(self, utterance: str) -> Optional[bool]:
        """Checks if a spoken phrase matches a confirmation or cancellation for any active gate."""
        clean = utterance.strip().lower()
        if not self._pending_approvals:
            return None

        # Resolve all currently pending gates
        resolved = None
        for gate_id in list(self._pending_approvals.keys()):
            if any(w in clean for w in ["yes", "confirm", "approve", "go ahead", "do it", "sure"]):
                self.resolve_gate(gate_id, True)
                resolved = True
            elif any(w in clean for w in ["no", "cancel", "stop", "abort", "reject", "don't"]):
                self.resolve_gate(gate_id, False)
                resolved = False

        return resolved


hitl_manager = HITLApprovalManager()

