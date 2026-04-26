"""Prometheus metrics registry + common instruments.

The concrete counters/histograms (``messages_received_total``,
``messages_per_minute``, LLM latency, etc.) are defined in TZ FEATURE-03 /
FEATURE-05 and will be registered here once the listener/worker are wired up.
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry

_registry: CollectorRegistry | None = None


def get_registry() -> CollectorRegistry:
    """Return the process-wide Prometheus registry."""

    global _registry
    if _registry is None:
        _registry = CollectorRegistry()
    return _registry
