"""Domain entity for an earnings announcement.

Fetched live from the data provider's earnings calendar (Phase C-style
optional capability — see FinancialDataProvider.get_earnings_calendar),
never persisted. Same "cheap to fetch fresh, no reason to cache"
treatment as MarketQuote and NewsArticle.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class EarningsEvent:
    ticker: str
    report_date: date
    eps_estimated: float | None
    eps_actual: float | None  # None until the report is actually out
    revenue_estimated: float | None
    revenue_actual: float | None
