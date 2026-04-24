"""Domain ORM tables."""

from __future__ import annotations

from shared.db.tables.keyword_trigger import KeywordTrigger
from shared.db.tables.lead_analysis import LeadAnalysis
from shared.db.tables.raw_message import RawMessage
from shared.db.tables.sender_profile import SenderProfile
from shared.db.tables.telegram_source import TelegramSource

__all__ = [
    "KeywordTrigger",
    "LeadAnalysis",
    "RawMessage",
    "SenderProfile",
    "TelegramSource",
]
