from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field


# Health
class HealthStatusResponse(BaseModel):
    status: str = "healthy"
    postgres: str = "disconnected"
    redis: str = "disconnected"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# Telegram Webhook
class TelegramFrom(BaseModel):
    id: int
    is_bot: bool = False
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None


class TelegramChat(BaseModel):
    id: int
    type: str = "private"
    title: Optional[str] = None
    username: Optional[str] = None


class TelegramVoice(BaseModel):
    file_id: str
    file_unique_id: str
    duration: int
    mime_type: Optional[str] = None
    file_size: Optional[int] = None


class TelegramAudio(BaseModel):
    file_id: str
    file_unique_id: str
    duration: int
    file_name: Optional[str] = None
    mime_type: Optional[str] = None
    file_size: Optional[int] = None


class TelegramMessage(BaseModel):
    message_id: int
    from_: TelegramFrom = Field(alias="from")
    chat: TelegramChat
    date: int
    text: Optional[str] = None
    voice: Optional[TelegramVoice] = None
    audio: Optional[TelegramAudio] = None


class TelegramCallbackQuery(BaseModel):
    id: str
    from_: TelegramFrom = Field(alias="from")
    message: Optional[TelegramMessage] = None
    data: Optional[str] = None


class TelegramWebhookPayload(BaseModel):
    update_id: int
    message: Optional[TelegramMessage] = None
    callback_query: Optional[TelegramCallbackQuery] = None


# WhatsApp Cloud API Webhook
class WhatsAppTextMessage(BaseModel):
    body: str


class WhatsAppAudioMessage(BaseModel):
    id: str
    mime_type: Optional[str] = None


class WhatsAppMessageItem(BaseModel):
    id: str
    from_: str = Field(alias="from")
    timestamp: str
    type: str = "text"
    text: Optional[WhatsAppTextMessage] = None
    audio: Optional[WhatsAppAudioMessage] = None
    voice: Optional[WhatsAppAudioMessage] = None


class WhatsAppValue(BaseModel):
    messaging_product: str = "whatsapp"
    metadata: Optional[Dict[str, Any]] = None
    contacts: Optional[List[Dict[str, Any]]] = None
    messages: Optional[List[WhatsAppMessageItem]] = None


class WhatsAppChange(BaseModel):
    field: str
    value: WhatsAppValue


class WhatsAppEntry(BaseModel):
    id: str
    changes: List[WhatsAppChange]


class WhatsAppWebhookPayload(BaseModel):
    object: str
    entry: List[WhatsAppEntry]


# Webhook & Task Responses
class WebhookIngressResponse(BaseModel):
    success: bool
    task_id: UUID
    status: str
    message: str


class TaskStatusResponse(BaseModel):
    task_id: UUID
    user_id: UUID
    status: str
    channel: str
    prompt: str
    result_summary: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class HITLApprovalRequest(BaseModel):
    approved: bool
    reason: Optional[str] = None
    approver_id: str

