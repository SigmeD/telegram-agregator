"""Smoke test: verify that all package roots import cleanly."""

from __future__ import annotations

import importlib

import pytest

MODULES = [
    "shared",
    "shared.config",
    "shared.db",
    "shared.db.session",
    "shared.db.models",
    "shared.llm.client",
    "shared.telegram.session_manager",
    "shared.scoring.calculator",
    "shared.observability.logging",
    "shared.observability.metrics",
    "listener.main",
    "worker.celery_app",
    "worker.tasks.filter_keywords",
    "worker.tasks.classify_llm",
    "worker.tasks.enrich_profile",
    "api.main",
    "api.routers.leads",
    "api.routers.sources",
    "api.routers.triggers",
    "bot.main",
]


@pytest.mark.unit
@pytest.mark.parametrize("module_name", MODULES)
def test_module_imports(module_name: str) -> None:
    """Every top-level module must be importable without side effects."""

    assert importlib.import_module(module_name) is not None
