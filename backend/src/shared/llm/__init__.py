"""LLM client abstraction with Claude primary + GPT-4 fallback (FEATURE-05)."""

from shared.llm.client import LLMClient, LLMResponse

__all__ = ["LLMClient", "LLMResponse"]
