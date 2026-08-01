"""Domain entity for portfolio risk analysis.

Every metric here is a standard, well-known risk measure — not a novel
invention — computed deterministically from data this platform already
holds. No new external data source, no LLM.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class SectorExposure:
    sector: str
    weight: float  # fraction of total portfolio market value in this sector


@dataclass(frozen=True, slots=True)
class PairwiseCorrelation:
    ticker_a: str
    ticker_b: str
    correlation: float


@dataclass(frozen=True, slots=True)
class PortfolioRiskAnalysis:
    portfolio_id: str
    as_of: datetime

    # Concentration risk
    largest_position_weight: float | None
    # Herfindahl-Hirschman Index: sum of each position's weight squared.
    # Ranges 0 (perfectly diversified) to 1 (single position). A common
    # rule of thumb: >0.25 is considered highly concentrated.
    herfindahl_index: float | None

    sector_exposures: list[SectorExposure] = field(default_factory=list)

    # Weighted by position market value. None if no holding had both a
    # computable debt_to_equity ratio and a known weight.
    weighted_avg_debt_to_equity: float | None = None

    # Tickers with no financial analysis available (e.g. never ingested
    # statements) — flagged explicitly rather than silently excluded,
    # since a risk report with silent gaps is worse than no report.
    excluded_from_leverage_calc: list[str] = field(default_factory=list)

    # -- Volatility/correlation (additive; all None/empty if the data
    # provider passed to the use case doesn't support price history —
    # concentration and leverage above are unaffected either way). --
    # Un-annualized, from daily simple returns over the lookback window.
    portfolio_daily_volatility: float | None = None
    portfolio_annualized_volatility: float | None = None
    # Parametric (variance-covariance) 1-day 95% VaR, in dollars — the
    # estimated loss not expected to be exceeded, for the COVERED
    # portion of the portfolio only (see volatility_covered_weight).
    parametric_var_95_1day_dollar: float | None = None
    # Fraction of total portfolio market value actually included in the
    # volatility/VaR calculation — a ticker missing sufficient price
    # history is excluded, not force-fit, so this can be < 1.0.
    volatility_covered_weight: float | None = None
    # The actual number of aligned trading-day observations used, after
    # trimming every included ticker to the shortest common length.
    volatility_lookback_days_used: int | None = None
    pairwise_correlations: list[PairwiseCorrelation] = field(default_factory=list)
    excluded_from_volatility_calc: list[str] = field(default_factory=list)
