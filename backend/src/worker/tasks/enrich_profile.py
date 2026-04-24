"""FEATURE-07: sender profile enrichment (bio, external links, history)."""

from __future__ import annotations

from worker.celery_app import app


@app.task(name="worker.tasks.enrich_profile.enrich_sender", bind=False)
def enrich_sender(telegram_user_id: int) -> str:
    """Fetch profile, parse bio, extract external links and persist result.

    Args:
        telegram_user_id: Telegram numeric user id.

    Returns:
        UUID of the upserted ``sender_profiles`` row.

    Raises:
        NotImplementedError: Stub implementation.
    """

    _ = telegram_user_id
    raise NotImplementedError("enrich_sender is not implemented yet")
