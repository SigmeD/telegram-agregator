"""Centralised application settings loaded from environment / .env.

All four services (listener, worker, api, bot) import the same :class:`Settings`
singleton via :func:`get_settings` so configuration stays consistent.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Backend-wide configuration.

    Fields map 1:1 to environment variables with the same name (case-insensitive).
    Secrets are wrapped in :class:`SecretStr` so they are never logged by default.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- Telegram user-session (Telethon) ---------------------------------
    TELEGRAM_API_ID: int = Field(..., description="api_id from my.telegram.org")
    TELEGRAM_API_HASH: SecretStr = Field(..., description="api_hash from my.telegram.org")
    TELEGRAM_PHONE: str = Field(..., description="Phone number in E.164 format")
    TELETHON_SESSION_KEY: SecretStr = Field(
        ...,
        description="Fernet key used to encrypt the Telethon .session file on disk.",
    )

    # ---- Persistence ------------------------------------------------------
    DATABASE_URL: str = Field(
        ...,
        description="Async Postgres DSN, e.g. postgresql+asyncpg://user:pass@host/db",
    )
    REDIS_URL: str = Field(..., description="Redis DSN used as Celery broker and cache")

    # ---- LLM providers ----------------------------------------------------
    ANTHROPIC_API_KEY: SecretStr = Field(..., description="Primary LLM provider key")
    OPENAI_API_KEY: SecretStr = Field(..., description="Fallback LLM provider key")
    PROMPT_VERSION: str = Field("v1", description="Active prompt version directory")
    LLM_DAILY_COST_LIMIT_USD: float = Field(
        10.0,
        ge=0.0,
        description="Hard daily spend cap across both providers.",
    )

    # ---- Notification bot -------------------------------------------------
    NOTIFY_BOT_TOKEN: SecretStr = Field(..., description="Aiogram bot token")
    NOTIFY_BOT_ADMIN_CHAT_ID: int = Field(
        ...,
        description="Telegram chat ID that receives hot-lead notifications.",
    )

    # ---- Security ---------------------------------------------------------
    JWT_SECRET: SecretStr = Field(..., description="HS256 secret for admin-API JWTs")

    # ---- Observability ----------------------------------------------------
    SENTRY_DSN: SecretStr | None = Field(None, description="Optional Sentry DSN")
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        "INFO", description="Root log level"
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a process-wide cached :class:`Settings` instance."""

    return Settings()
