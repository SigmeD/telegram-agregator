"""Message handler: build RawMessage row + Celery enqueue for downstream filter.

Called by listener.main's @client.on(events.NewMessage) hook. Idempotent on
per-event basis: any exception logs and returns — listener stays alive.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from shared.db.tables.raw_message import RawMessage
from worker.tasks.filter_keywords import filter_message

if TYPE_CHECKING:
    from collections.abc import Mapping

logger = structlog.get_logger(__name__)


def _full_name(sender: Any) -> str | None:
    """Compose ``first_name last_name`` from a Telethon sender, ``None`` if empty."""
    if sender is None:
        return None
    first = getattr(sender, "first_name", None) or ""
    last = getattr(sender, "last_name", None) or ""
    name = f"{first} {last}".strip()
    return name or None


def _extract_thread_id(event: Any) -> int | None:
    """Pull forum-topic or reply-thread id from a Telethon NewMessage event."""
    msg = getattr(event, "message", None)
    reply_to = getattr(msg, "reply_to", None) if msg is not None else None
    if reply_to is None:
        return None
    forum_topic_id = getattr(reply_to, "forum_topic_id", None)
    if forum_topic_id is not None:
        return int(forum_topic_id)
    reply_top_id = getattr(reply_to, "reply_to_top_id", None)
    return int(reply_top_id) if reply_top_id is not None else None


async def handle_message(
    event: Any,
    db_pool: Any,
    source_by_chat_id: Mapping[int, Any],
) -> None:
    """Persist ``event`` as a ``raw_messages`` row and enqueue the keyword filter.

    Any unexpected exception is swallowed with ``logger.exception`` so a single
    bad event cannot crash the listener loop. Celery enqueue failures are
    isolated separately — the row is already committed.
    """
    try:
        source = source_by_chat_id.get(event.chat_id)
        if source is None:
            logger.warning("message_for_unknown_source", chat_id=event.chat_id)
            return

        sender = getattr(event, "sender", None)
        msg = RawMessage(
            source_id=source.id,
            telegram_message_id=event.id,
            sender_id=event.sender_id,
            sender_username=getattr(sender, "username", None) if sender is not None else None,
            sender_name=_full_name(sender),
            message_text=event.raw_text or "",
            has_media=bool(event.media),
            media_type=type(event.media).__name__ if event.media else None,
            reply_to_message_id=event.reply_to_msg_id,
            thread_id=_extract_thread_id(event),
            sent_at=event.date,
            processing_status="pending",
        )
        async with db_pool.session() as s:
            s.add(msg)
            await s.commit()
        try:
            filter_message.delay(raw_message_id=str(msg.id))
        except Exception:
            logger.error("celery_enqueue_failed", raw_message_id=str(msg.id), exc_info=True)
    except Exception:
        logger.exception("message_processing_failed", chat_id=getattr(event, "chat_id", None))
