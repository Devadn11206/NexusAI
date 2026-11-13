import io
import logging
from pathlib import Path
from typing import Optional, Union, Dict, Any, List
import httpx
from app.config import settings

logger = logging.getLogger(__name__)


class TelegramMessagingService:
    """Outbound communication adapter for Telegram Bot API."""

    def __init__(self, bot_token: Optional[str] = None):
        self.bot_token = bot_token or settings.TELEGRAM_BOT_TOKEN
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

    async def send_text(self, chat_id: Union[int, str], text: str, parse_mode: Optional[str] = None) -> Dict[str, Any]:
        """
        Send a text message to an authorized Telegram chat with automatic chunking (<= 4000 chars)
        and fallback for unescaped Markdown syntax errors.
        """
        url = f"{self.base_url}/sendMessage"
        if not text or not str(text).strip():
            return {"ok": True, "result": {}}

        # Telegram hard limits message length to 4096 chars. Chunk at 3900 to stay safely below limit.
        max_chunk = 3900
        full_text = str(text).strip()
        chunks: List[str] = []

        while len(full_text) > max_chunk:
            split_idx = full_text.rfind("\n", 0, max_chunk)
            if split_idx == -1 or split_idx < max_chunk // 2:
                split_idx = max_chunk
            chunks.append(full_text[:split_idx].strip())
            full_text = full_text[split_idx:].strip()
        if full_text:
            chunks.append(full_text)

        last_resp_data = {"ok": True}
        async with httpx.AsyncClient(timeout=20.0) as client:
            for chunk in chunks:
                if not chunk:
                    continue
                payload = {
                    "chat_id": str(chat_id),
                    "text": chunk,
                }
                if parse_mode:
                    payload["parse_mode"] = parse_mode

                resp = await client.post(url, json=payload)
                if resp.status_code == 400:
                    # Fallback 1: Retry as plain text if markdown formatting characters failed
                    if "parse_mode" in payload:
                        payload.pop("parse_mode", None)
                        resp = await client.post(url, json=payload)
                
                if not resp.is_success:
                    logger.error(f"[TelegramMessaging] Error sending message: {resp.status_code} - {resp.text}")
                resp.raise_for_status()
                last_resp_data = resp.json()

        return last_resp_data

    async def send_document(
        self, chat_id: Union[int, str], file_path: Union[str, Path], caption: str = ""
    ) -> Dict[str, Any]:
        """Send a document or generated file from disk to Telegram."""
        url = f"{self.base_url}/sendDocument"
        path_obj = Path(file_path).resolve()
        if not path_obj.exists():
            raise FileNotFoundError(f"Attachment file not found: {file_path}")

        data = {"chat_id": str(chat_id), "caption": caption}
        async with httpx.AsyncClient(timeout=30.0) as client:
            with open(path_obj, "rb") as f:
                files = {"document": (path_obj.name, f)}
                resp = await client.post(url, data=data, files=files)
                resp.raise_for_status()
                return resp.json()

    async def send_image(
        self,
        chat_id: Union[int, str],
        image_bytes_or_path: Union[bytes, str, Path],
        caption: str = "",
    ) -> Dict[str, Any]:
        """Send a photo or screenshot to Telegram."""
        url = f"{self.base_url}/sendPhoto"
        data = {"chat_id": str(chat_id), "caption": caption}

        async with httpx.AsyncClient(timeout=30.0) as client:
            if isinstance(image_bytes_or_path, (str, Path)):
                img_path = Path(image_bytes_or_path).resolve()
                if not img_path.exists():
                    raise FileNotFoundError(f"Image not found: {image_bytes_or_path}")
                with open(img_path, "rb") as f:
                    files = {"photo": (img_path.name, f, "image/png")}
                    resp = await client.post(url, data=data, files=files)
            else:
                files = {"photo": ("screenshot.png", image_bytes_or_path, "image/png")}
                resp = await client.post(url, data=data, files=files)

            resp.raise_for_status()
            return resp.json()

    async def send_approval_buttons(
        self, chat_id: Union[int, str], text: str, approval_id: str
    ) -> Dict[str, Any]:
        """Send interactive inline keyboard buttons for Human-in-the-Loop (HITL) approval."""
        url = f"{self.base_url}/sendMessage"
        inline_keyboard = {
            "inline_keyboard": [
                [
                    {"text": "Approve", "callback_data": f"approve:{approval_id}"},
                    {"text": "Reject", "callback_data": f"reject:{approval_id}"},
                ]
            ]
        }
        payload = {
            "chat_id": str(chat_id),
            "text": text,
            "reply_markup": inline_keyboard,
            "parse_mode": "Markdown",
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()

    async def send_menu(
        self,
        chat_id: Union[int, str],
        text: str,
        reply_markup: Dict[str, Any],
        parse_mode: Optional[str] = "Markdown",
    ) -> Dict[str, Any]:
        """Send or display a dynamic interactive inline keyboard menu."""
        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": str(chat_id),
            "text": text,
            "reply_markup": reply_markup,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 400 and "parse_mode" in payload:
                payload.pop("parse_mode", None)
                resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()

    async def edit_message_reply_markup(
        self,
        chat_id: Union[int, str],
        message_id: int,
        reply_markup: Dict[str, Any],
        text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Edit an existing message text and/or its inline keyboard (for pagination/menu refresh)."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            if text:
                url = f"{self.base_url}/editMessageText"
                payload = {
                    "chat_id": str(chat_id),
                    "message_id": message_id,
                    "text": text,
                    "reply_markup": reply_markup,
                    "parse_mode": "Markdown",
                }
            else:
                url = f"{self.base_url}/editMessageReplyMarkup"
                payload = {
                    "chat_id": str(chat_id),
                    "message_id": message_id,
                    "reply_markup": reply_markup,
                }
            resp = await client.post(url, json=payload)
            if resp.status_code == 400 and text and "parse_mode" in payload:
                payload.pop("parse_mode", None)
                resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: Optional[str] = None,
        show_alert: bool = False,
    ) -> Dict[str, Any]:
        """Acknowledge Telegram callback query and optionally display inline toast message."""
        url = f"{self.base_url}/answerCallbackQuery"
        payload: Dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        if show_alert:
            payload["show_alert"] = show_alert
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()

    async def download_file_bytes(self, file_id: str) -> bytes:
        """Download a file (e.g. voice note audio) via Telegram Bot API."""
        get_file_url = f"{self.base_url}/getFile"
        async with httpx.AsyncClient(timeout=30.0) as client:
            file_info_resp = await client.get(get_file_url, params={"file_id": file_id})
            file_info_resp.raise_for_status()
            file_path = file_info_resp.json().get("result", {}).get("file_path")
            if not file_path:
                raise ValueError(f"Could not retrieve file_path for Telegram file_id: {file_id}")

            download_url = f"https://api.telegram.org/file/bot{self.bot_token}/{file_path}"
            download_resp = await client.get(download_url)
            download_resp.raise_for_status()
            return download_resp.content


class WhatsAppMessagingService:
    """Outbound communication adapter for WhatsApp Business Cloud API."""

    def __init__(
        self,
        api_token: Optional[str] = None,
        phone_number_id: Optional[str] = None,
    ):
        self.api_token = api_token or settings.WHATSAPP_API_TOKEN
        self.phone_number_id = phone_number_id or settings.WHATSAPP_PHONE_NUMBER_ID
        self.base_url = f"https://graph.facebook.com/v21.0/{self.phone_number_id}/messages"

    @property
    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    async def send_text(self, phone: str, text: str) -> Dict[str, Any]:
        """Send a text message via WhatsApp Cloud API."""
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": phone.replace("+", "").replace(" ", "").replace("-", ""),
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(self.base_url, headers=self._headers, json=payload)
            resp.raise_for_status()
            return resp.json()

    async def send_document(self, phone: str, file_path: Union[str, Path], caption: str = "") -> Dict[str, Any]:
        """Send a document or file link via WhatsApp Cloud API."""
        path_obj = Path(file_path).resolve()
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": phone.replace("+", "").replace(" ", "").replace("-", ""),
            "type": "document",
            "document": {
                "filename": path_obj.name,
                "caption": caption,
            },
        }
        # Note: If host has media ID or public URL, link is added here
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(self.base_url, headers=self._headers, json=payload)
            resp.raise_for_status()
            return resp.json()

    async def send_image(self, phone: str, image_path: Union[str, Path], caption: str = "") -> Dict[str, Any]:
        """Send an image via WhatsApp Cloud API."""
        path_obj = Path(image_path).resolve()
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": phone.replace("+", "").replace(" ", "").replace("-", ""),
            "type": "image",
            "image": {
                "caption": caption,
            },
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(self.base_url, headers=self._headers, json=payload)
            resp.raise_for_status()
            return resp.json()

    async def download_media_bytes(self, media_id: str) -> bytes:
        """Download audio or media bytes using WhatsApp Cloud API media ID."""
        info_url = f"https://graph.facebook.com/v21.0/{media_id}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            info_resp = await client.get(info_url, headers={"Authorization": f"Bearer {self.api_token}"})
            info_resp.raise_for_status()
            download_url = info_resp.json().get("url")
            if not download_url:
                raise ValueError(f"Could not retrieve media URL for WhatsApp media_id: {media_id}")

            media_resp = await client.get(download_url, headers={"Authorization": f"Bearer {self.api_token}"})
            media_resp.raise_for_status()
            return media_resp.content


# Service singletons
telegram_service = TelegramMessagingService()
whatsapp_service = WhatsAppMessagingService()

