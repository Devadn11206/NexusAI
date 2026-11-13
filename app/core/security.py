import logging
from pathlib import Path
from typing import Union
from fastapi import HTTPException, status
from app.config import settings

logger = logging.getLogger(__name__)


def is_telegram_user_whitelisted(chat_id: Union[int, str]) -> bool:
    """Verify if the incoming Telegram chat/sender ID is in the whitelist."""
    cid_str = str(chat_id).strip()
    allowed = settings.ALLOWED_TELEGRAM_CHAT_IDS
    # If no whitelist is configured, reject all to maintain secure-by-default posture
    if not allowed:
        logger.warning("Telegram whitelist is empty. Rejecting incoming message.")
        return False
    return cid_str in allowed


def is_whatsapp_user_whitelisted(phone: str) -> bool:
    """Verify if the incoming WhatsApp phone number is in the whitelist."""
    phone_clean = phone.strip().replace(" ", "").replace("-", "")
    allowed = settings.ALLOWED_WHATSAPP_PHONES
    if not allowed:
        logger.warning("WhatsApp whitelist is empty. Rejecting incoming message.")
        return False
    return any(phone_clean == a.strip().replace(" ", "").replace("-", "") for a in allowed)


def enforce_telegram_whitelist(chat_id: Union[int, str]) -> None:
    """Fast-fail check for Telegram. Raises 403 HTTP exception if unauthorized."""
    if not is_telegram_user_whitelisted(chat_id):
        logger.warning(f"Security Gatekeeper: Unauthorized Telegram sender blocked: {chat_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access Denied: Sender is not whitelisted in NEXUS AI Security Gatekeeper."
        )


def enforce_whatsapp_whitelist(phone: str) -> None:
    """Fast-fail check for WhatsApp. Raises 403 HTTP exception if unauthorized."""
    if not is_whatsapp_user_whitelisted(phone):
        logger.warning(f"Security Gatekeeper: Unauthorized WhatsApp sender blocked: {phone}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access Denied: Sender is not whitelisted in NEXUS AI Security Gatekeeper."
        )


def verify_sender_authorized(sender_id: Union[int, str], channel: str) -> None:
    """Unified authorization gatekeeper check for incoming messaging channels."""
    channel_lower = channel.lower()
    if channel_lower == "telegram":
        enforce_telegram_whitelist(sender_id)
    elif channel_lower == "whatsapp":
        enforce_whatsapp_whitelist(str(sender_id))
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported messaging channel: '{channel}'"
        )


def resolve_safe_workspace_path(sub_path: str) -> Path:
    """
    Enforce directory boundary isolation.
    Ensures sub_path resolves strictly within WORKSPACE_DIR.
    """
    base_dir = Path(settings.WORKSPACE_DIR).resolve()
    target_path = (base_dir / sub_path).resolve()
    if not target_path.is_relative_to(base_dir):
        raise PermissionError(f"Security Alert: Attempted path escape outside sandbox: {sub_path}")
    return target_path

