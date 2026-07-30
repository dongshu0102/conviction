"""Domain entities for computed financial analysis.

Deliberately NOT persisted to a table. These are a pure function of
already-stored financial statements — recomputed on every request rather
than cached, so a re-ingested (restated) statement is never silently
stale. Computing ~9 ratios from a handful of statements is cheap; the
staleness risk of caching derived data is not worth avoiding that cost.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class YearlyRatios:
    """Ratios for a single fiscal year. Any ratio is None when the
    underlying inputs are missing or would require division by zero —
    never silently computed as 0 or fabricated, since a missing ratio is
    a meaningfully different fact from a ratio that happens to be zero.
    """

    fiscal_year: int

    # Growth — None for the earliest year in the series (no prior year
    # to compare against).
    revenue_growth_yoy: float | None

    # Profitability
    gross_margin: float | None
    operating_margin: float | None
    net_margin: float | None
    free_cash_flow_margin: float | None

    # Returns
    return_on_equity: float | None
    return_on_assets: float | None

    # Leverage / liquidity
    debt_to_equity: float | None
    current_ratio: float | None


@dataclass(frozen=True, slots=True)
class CompanyFinancialAnalysis:
    ticker: str
    yearly_ratios: list[YearlyRatios]  # ascending by fiscal_year — oldest first, for trend reading
