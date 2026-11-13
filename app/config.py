from typing import List, Union, Any
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """NEXUS AI Environment Settings & Configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Core Application
    APP_NAME: str = "NEXUS AI"
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # PostgreSQL + pgvector Database
    DATABASE_URL: str = "postgresql+asyncpg://nexus:nexuspassword@localhost:5432/nexus_db"
    DB_ECHO: bool = False

    # Redis Connection
    REDIS_URL: str = "redis://localhost:6379/0"

    # Security Whitelists (Stored as strings or lists; parsed safely)
    ALLOWED_TELEGRAM_CHAT_IDS: Any = Field(default_factory=list)
    ALLOWED_WHATSAPP_PHONES: Any = Field(default_factory=list)

    # Ingress Credentials
    TELEGRAM_BOT_TOKEN: str = ""
    WHATSAPP_API_TOKEN: str = ""
    WHATSAPP_VERIFY_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""

    # AI & Speech-to-Text API Keys
    GROQ_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    WHISPER_MODEL: str = "whisper-large-v3"

    # Workspace Sandbox Boundary
    WORKSPACE_DIR: str = "./workspace"

    @field_validator("ALLOWED_TELEGRAM_CHAT_IDS", mode="before")
    @classmethod
    def parse_telegram_whitelist(cls, v: Any) -> List[str]:
        if isinstance(v, (int, float)):
            return [str(v)]
        if isinstance(v, str):
            if not v.strip():
                return []
            return [item.strip() for item in v.split(",") if item.strip()]
        if isinstance(v, list):
            return [str(item).strip() for item in v]
        return []

    @field_validator("ALLOWED_WHATSAPP_PHONES", mode="before")
    @classmethod
    def parse_whatsapp_whitelist(cls, v: Any) -> List[str]:
        if isinstance(v, (int, float)):
            return [str(v)]
        if isinstance(v, str):
            if not v.strip():
                return []
            return [item.strip() for item in v.split(",") if item.strip()]
        if isinstance(v, list):
            return [str(item).strip() for item in v]
        return []


settings = Settings()
