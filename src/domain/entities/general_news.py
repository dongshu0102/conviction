"""Domain entity for a general (non-ticker-specific) market news
headline — the macro signal a theme suggestion grounds itself in.

Kept separate from NewsArticle (which is always ticker-scoped) rather
than making NewsArticle.ticker optional — a genuinely different shape
of data (FMP's own payload has symbol=null for these), not a variant
of the same thing.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class GeneralNewsHeadline:
    title: str
    published_at: datetime | None
    publisher: str | None
    url: str | None
    snippet: str | None
