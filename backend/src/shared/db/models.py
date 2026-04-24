"""Aggregated re-exports of all ORM models.

Alembic's ``env.py`` imports this module so autogenerate can see every
mapper registered on :class:`shared.db.session.Base`. Individual models
live under :mod:`shared.db.tables`; add new ones there and extend
``tables.__all__`` to expose them.
"""

from __future__ import annotations

from shared.db.session import Base
from shared.db.tables import *  # noqa: F401,F403  — side-effect import for mappers

__all__ = ["Base"]
