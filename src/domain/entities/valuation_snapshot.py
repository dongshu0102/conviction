"""Domain entity for a valuation snapshot.

Every multiple is computed against total market_cap rather than
per-share price/EPS — mathematically equivalent, but avoids depending
on share-count data (our shares_outstanding field is a known imperfect
proxy, mapped from the vendor's "commonStock" balance sheet line, not a
verified share count).

Deliberately labeled with which fiscal year's fundamentals were used,
since price is live but fundamentals are as-of the last filed annual
statement — mixing a live numerator with a stale-by-months denominator
is inherent to any point-in-time valuation multiple, and should be
visible to the consumer, not hidden.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ValuationSnapshot:
    ticker: str
    as_of: datetime
    price: float
    market_cap: float
    enterprise_value: float | None
    fundamentals_fiscal_year: int  # which annual statement backs the ratios below

    price_to_earnings: float | None
    price_to_sales: float | None
    price_to_book: float | None
    price_to_free_cash_flow: float | None
    ev_to_ebitda: float | None
