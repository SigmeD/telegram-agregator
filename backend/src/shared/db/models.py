"""ORM models for the aggregator.

Models will be added in subsequent commits per FEATURE-02 / FEATURE-03 /
FEATURE-05 / FEATURE-07 specs (tables ``telegram_sources``, ``raw_messages``,
``keyword_triggers``, ``lead_analysis``, ``sender_profiles``). For now we only
re-export :class:`Base` so Alembic autogenerate can discover metadata.
"""

from __future__ import annotations

from shared.db.session import Base

__all__ = ["Base"]
