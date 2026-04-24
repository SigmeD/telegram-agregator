"""Naming convention + metadata regression guards for shared.db.Base."""

from __future__ import annotations

import pytest

from shared.db.session import Base

pytestmark = pytest.mark.unit


def test_base_metadata_has_project_naming_convention() -> None:
    """Alembic autogenerate relies on stable constraint/index names.

    Changing these without bumping a migration breaks diff detection.
    """

    nc = Base.metadata.naming_convention
    assert nc["ix"] == "ix_%(column_0_label)s"
    assert nc["uq"] == "uq_%(table_name)s_%(column_0_name)s"
    assert nc["ck"] == "ck_%(table_name)s_%(constraint_name)s"
    assert nc["fk"] == "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
    assert nc["pk"] == "pk_%(table_name)s"


EXPECTED_TABLES: frozenset[str] = frozenset(
    {
        "telegram_sources",
        "raw_messages",
        "keyword_triggers",
        "lead_analysis",
        "sender_profiles",
    }
)


def test_base_metadata_registers_all_domain_tables() -> None:
    """All 5 domain tables are importable and registered on Base.metadata.

    Regression guard: if someone moves a model out of the ``tables/``
    package, Alembic autogenerate silently stops seeing it.
    """

    import shared.db.models  # noqa: F401  — side-effect import registers mappers

    assert EXPECTED_TABLES.issubset(Base.metadata.tables.keys())
