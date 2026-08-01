"""Domain entity for a point-in-time market quote.

Deliberately not persisted like financial statements — price and market
cap are live, continuously-changing facts, not periodic filed data.
Fetched fresh whenever a valuation calculation needs it, same treatment
as computed ratios: cheap to fetch, staleness risk not worth caching.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class MarketQuote:
    ticker: str
    price: float
    market_cap: float
    as_of: datetime


@dataclass(frozen=True, slots=True)
class PriceBar:
    """One end-of-day close. Used for momentum computation — fetched
    live from FMP's historical EOD endpoint (Starter-plan accessible),
    NOT stored locally; there is deliberately no price-history table."""

    bar_date: date
    close: float
