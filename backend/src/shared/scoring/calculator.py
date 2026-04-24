"""Lead scoring calculator.

The concrete formula, factor weights and bucket thresholds (Hot/Warm/Cold/
Irrelevant) are defined in ``docs/BUSINESS_RULES.md`` and must not be
hardcoded here — they will be loaded from a config file in a follow-up.

See TZ FEATURE-06 for the initial reference implementation.
"""

from __future__ import annotations

from typing import Any


def calculate_lead_score(
    lead_analysis: Any,
    source: Any,
    sender_history: Any,
) -> int:
    """Return an integer lead score in the closed interval ``[0, 100]``.

    Args:
        lead_analysis: ``lead_analysis`` row (LLM output).
        source: ``telegram_sources`` row the message came from.
        sender_history: Aggregated stats for the sender profile.

    Returns:
        Final score clamped to ``[0, 100]``.

    Raises:
        NotImplementedError: Stub implementation — see BUSINESS_RULES.md.
    """

    raise NotImplementedError("calculate_lead_score is not implemented yet")
