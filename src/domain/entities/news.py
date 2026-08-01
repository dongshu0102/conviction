"""Domain entity for a stock news article.

Phase C scope note: news comes from FMP's stock-news endpoint, which is
included in the Starter plan (verified against FMP's published plan
comparison, July 2026). The earnings calendar is Premium-only and is
deliberately NOT modeled here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class NewsArticle:
    ticker: str
    title: str
    published_at: datetime | None  # None when the source date is unparseable
    source: str | None
    url: str | None
    snippet: str | None
