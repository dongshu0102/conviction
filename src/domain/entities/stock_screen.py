"""Domain entities for stock screening.

Scoped deliberately: screens a caller-supplied, bounded set of tickers
(not the full ingested universe) — computing live valuation needs one
FMP call per ticker, so screening all 500+ names on every chat message
would be slow and rate-limit-risky. A full-universe screen needs a
periodic batch job (snapshotting valuation for everything on a
schedule, like monitoring does for watchlists) — real, separate
infrastructure, not built here. This covers "value stocks in
healthcare" (a handful of names); it does not cover "value stocks in
the whole S&P 500."

Also deliberately NOT covering price momentum ("hot stocks") — that
needs historical price data we don't store anywhere in this system yet
(PriceSnapshot only holds ONE snapshot per ticker, for monitoring
diffs, not a time series). Faking a "hot list" without real momentum
data would be worse than not having one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ScreenedStock:
    ticker: str
    price: float
    price_to_earnings: float | None
    price_to_sales: float | None
    ev_to_ebitda: float | None
    return_on_equity: float | None
    net_margin: float | None
    debt_to_equity: float | None
    # Percentile-rank composite scores among the screened set — lower is
    # always better (cheaper for value, higher-quality for quality).
    # Not comparable across different screen runs, only within one.
    value_score: float
    quality_score: float
    composite_score: float


@dataclass(frozen=True, slots=True)
class ScreenResult:
    as_of: datetime
    candidates_requested: int
    excluded: list[str] = field(default_factory=list)  # missing/negative data — shown for transparency, not hidden
    results: list[ScreenedStock] = field(default_factory=list)  # sorted by composite_score ascending
