"""Structlog configuration shared by all services."""

from __future__ import annotations

from typing import Any

import structlog


def configure_logging(*, log_level: str = "INFO", json_output: bool = True) -> None:
    """Configure :mod:`structlog` processors and stdlib bridging.

    Must be called once at process startup (before the first log call).
    Concrete processor pipeline will be finalised together with the Sentry
    integration (FEATURE-10 / observability epic).

    Args:
        log_level: Root log level (``"DEBUG"`` / ``"INFO"`` / ...).
        json_output: If ``True``, emit JSON logs (prod); otherwise use the
            console renderer (dev).
    """

    # NOTE: actual processors chain is filled in a follow-up.
    _ = log_level, json_output


def get_logger(name: str | None = None, **initial_values: Any) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger with optional initial context."""

    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name).bind(**initial_values)
    return logger
