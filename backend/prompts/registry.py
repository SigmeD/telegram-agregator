"""Prompt registry: loads versioned markdown prompts from ``prompts/v<N>/``.

Version is selected by ``Settings.PROMPT_VERSION`` (env var ``PROMPT_VERSION``).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from shared.config import get_settings

_PROMPTS_ROOT = Path(__file__).resolve().parent


class PromptNotFoundError(KeyError):
    """Raised when a prompt file is missing for the active version."""


@lru_cache(maxsize=32)
def load_prompt(name: str, *, version: str | None = None) -> str:
    """Load prompt template by logical ``name`` (e.g. ``"classify_lead"``).

    Args:
        name: File stem under ``prompts/v<version>/``.
        version: Optional explicit version override. Defaults to
            ``Settings.PROMPT_VERSION``.

    Returns:
        Raw template text (str.format-style placeholders).

    Raises:
        PromptNotFoundError: If the markdown file does not exist.
    """

    resolved_version = version or get_settings().PROMPT_VERSION
    path = _PROMPTS_ROOT / resolved_version / f"{name}.md"
    if not path.is_file():
        raise PromptNotFoundError(f"Prompt '{name}' not found for version '{resolved_version}'")
    return path.read_text(encoding="utf-8")
