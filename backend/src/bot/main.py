"""Aiogram 3 notification bot entry-point (FEATURE-08)."""

from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher

from shared.config import get_settings
from shared.observability.logging import configure_logging, get_logger

logger = get_logger(__name__)


def build_dispatcher() -> Dispatcher:
    """Build the root :class:`aiogram.Dispatcher` with routers attached."""

    dispatcher = Dispatcher()
    # TODO(FEATURE-08): register routers for /start, inline-button callbacks
    # ("mark as handled" / "not a lead"), daily digest scheduler, quiet hours.
    return dispatcher


async def run() -> None:
    """Launch long-polling loop."""

    configure_logging()
    settings = get_settings()
    bot = Bot(token=settings.NOTIFY_BOT_TOKEN.get_secret_value())
    dispatcher = build_dispatcher()
    logger.info("bot.started", chat_id=settings.NOTIFY_BOT_ADMIN_CHAT_ID)

    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


def main() -> None:
    """Synchronous wrapper used by ``python -m bot``."""

    asyncio.run(run())


if __name__ == "__main__":
    main()
