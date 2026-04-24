"""Telethon listener entry-point.

Reads all active ``telegram_sources``, subscribes to ``events.NewMessage`` and
pushes each message into Redis + ``raw_messages`` table (see FEATURE-03).
"""

from __future__ import annotations

import asyncio

from shared.observability.logging import configure_logging, get_logger
from shared.telegram.session_manager import SessionManager

logger = get_logger(__name__)


async def run() -> None:
    """Main async loop: connect Telethon client and start listening."""

    configure_logging()
    session = SessionManager()
    client = await session.connect()

    # TODO(FEATURE-03): register `@client.on(events.NewMessage(chats=...))`
    # handler that writes to `raw_messages` and enqueues filter_keywords task.
    logger.info("listener.started", client=repr(client))

    try:
        # TODO: replace with `await client.run_until_disconnected()` once the
        # handler is wired up.
        while True:  # noqa: ASYNC110
            await asyncio.sleep(60)
    finally:
        await session.disconnect()


def main() -> None:
    """Synchronous wrapper used by the console script / ``python -m listener``."""

    asyncio.run(run())


if __name__ == "__main__":
    main()
