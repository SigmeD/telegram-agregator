"""Unified LLM client with Claude -> GPT-4 fallback.

Implements the provider chain described in TZ FEATURE-05:
1. Try Anthropic Claude (Haiku by default, Sonnet for low-confidence retries).
2. On provider error / rate limit / timeout -> retry with OpenAI GPT-4.
3. Record ``tokens_used`` and ``cost_usd`` so the ``LLM_DAILY_COST_LIMIT_USD``
   guard in :mod:`shared.config` can short-circuit further calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True, frozen=True)
class LLMResponse:
    """Provider-agnostic response wrapper."""

    content: str
    model: str
    tokens_used: int
    cost_usd: float
    raw: dict[str, Any]


class LLMClient:
    """High-level LLM facade used by worker tasks.

    The client is safe to share across coroutines; concrete HTTP clients are
    created lazily on first call.
    """

    def __init__(
        self,
        *,
        primary_model: str = "claude-3-haiku-20240307",
        fallback_model: str = "gpt-4o-mini",
    ) -> None:
        self._primary_model = primary_model
        self._fallback_model = fallback_model

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> LLMResponse:
        """Run a single completion with automatic provider fallback.

        Args:
            prompt: User-facing prompt text.
            system: Optional system prompt.
            max_tokens: Upper bound on generated tokens.
            temperature: Sampling temperature.

        Returns:
            :class:`LLMResponse` with normalized metadata.

        Raises:
            NotImplementedError: Stub implementation.
        """

        raise NotImplementedError("LLMClient.complete is not implemented yet")

    async def classify_lead(self, context: dict[str, Any]) -> LLMResponse:
        """Run the FEATURE-05 classification prompt against ``context``.

        Args:
            context: Render variables (chat_title, sender_name, message_text, ...).

        Raises:
            NotImplementedError: Stub implementation.
        """

        raise NotImplementedError("LLMClient.classify_lead is not implemented yet")
