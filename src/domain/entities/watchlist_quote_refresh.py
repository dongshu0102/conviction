"""Domain entity for a bulk, cheap watchlist quote refresh.

Genuinely distinct from WatchlistTriageResult: triage computes a rich,
weighted urgency score from multiple signals (momentum, P/E drift,
day move), one FMP call per ticker. This is a simpler, narrower need
-- cheaply refresh every real, current price across a whole watchlist
in a single bulk call, for the "monitor a shortlist" workflow.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class WatchlistQuoteRefreshItem:
    ticker: str
    list_name: str
    current_price: float
    added_price: float | None
    change_since_added_pct: float | None
    target_price: float | None
    target_reached: bool


@dataclass(frozen=True, slots=True)
class WatchlistQuoteRefreshResult:
    user_id: str
    as_of: datetime
    items: list[WatchlistQuoteRefreshItem]
    # Tickers on the watchlist with no real, current quote available
    # from this refresh -- never fabricated, just honestly absent.
    tickers_excluded: list[str]
