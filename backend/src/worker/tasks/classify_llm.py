"""FEATURE-05: LLM-based lead classification & data extraction."""

from __future__ import annotations

from uuid import UUID

from worker.celery_app import app


@app.task(name="worker.tasks.classify_llm.classify_message", bind=False)  # type: ignore[untyped-decorator]
def classify_message(raw_message_id: str) -> str:
    """Run Claude (fallback: GPT-4) classification and persist ``lead_analysis``.

    Args:
        raw_message_id: UUID of the ``raw_messages`` row to analyze.

    Returns:
        UUID of the created ``lead_analysis`` row.

    Raises:
        NotImplementedError: Stub implementation.
    """

    _ = UUID(raw_message_id)
    raise NotImplementedError("classify_message is not implemented yet")
