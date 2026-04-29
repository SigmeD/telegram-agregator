"""FEATURE-04: cheap keyword-based pre-filter.

Consumes a ``raw_messages.id`` from the ``filter`` queue, looks up active
``keyword_triggers`` and either marks the row ``filtered_out`` or enqueues
:func:`worker.tasks.classify_llm.classify_message` with the same id.
"""

from __future__ import annotations

from uuid import UUID

from worker.celery_app import app


@app.task(name="worker.tasks.filter_keywords.filter_message", bind=False)  # type: ignore[untyped-decorator]
def filter_message(raw_message_id: str) -> str:
    """Apply keyword triggers to ``raw_messages[id=raw_message_id]``.

    Args:
        raw_message_id: UUID of the row to classify.

    Returns:
        New ``processing_status`` value (``"filtered_out"`` or ``"analyzing"``).

    Raises:
        NotImplementedError: Stub implementation.
    """

    _ = UUID(raw_message_id)
    raise NotImplementedError("filter_message is not implemented yet")
