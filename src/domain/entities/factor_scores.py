"""Domain entities for cross-sectional factor scoring.

The core distinction from screen_stocks: that use case scores each
ticker against FIXED absolute bands (P/E under 20 = cheap). Factor
scores are STANDARDIZED against the rest of the universe at the same
point in time — a z-score, so "cheap" means "cheaper than the other
S&P 500 names right now," which is what makes factors comparable across
time and combinable into a portfolio-construction signal.

Design split, driven directly by the two constraints in play: the raw
z-scores are expensive to compute (require pulling financials for the
whole universe) so they are CACHED; the composite weighting is cheap
(a weighted sum of already-computed z-scores) so it is recomputed FRESH
on every request. Changing weights never touches the cache; only a
stale snapshot does.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class FactorRawMetrics:
    """The un-standardized inputs behind the z-scores, kept alongside
    them so a score is explainable ("NVDA's momentum z-score of 1.8 is
    driven by a 34% 1-month move") rather than an opaque number."""

    price_to_earnings: float | None  # Value (lower = better; z-score sign flipped)
    return_on_equity: float | None  # Quality
    revenue_growth_yoy: float | None  # Growth
    momentum_1m_pct: float | None  # Momentum
    market_cap: float | None  # Size (lower = smaller-cap tilt; z-score sign flipped)


@dataclass(frozen=True, slots=True)
class FactorZScores:
    """Each z-score is None when the underlying raw metric was missing
    for this ticker — never fabricated as 0, which would silently claim
    "exactly average" for a fact we don't actually have. Signs are
    oriented so that HIGHER always means "more attractive on this
    factor": Value and Size z-scores are the negative of the raw
    metric's z-score, since a lower P/E or smaller market cap is the
    conventionally favorable direction for those two factors."""

    value: float | None
    quality: float | None
    growth: float | None
    momentum: float | None
    size: float | None


@dataclass(frozen=True, slots=True)
class FactorScore:
    ticker: str
    as_of: datetime
    raw: FactorRawMetrics
    z_scores: FactorZScores


@dataclass(frozen=True)
class FactorWeights:
    """Composite = weighted sum of z-scores. Weights need not sum to 1;
    the composite is a relative ranking signal, not a probability, so
    normalization is cosmetic rather than required. Missing factors
    (ticker had no data for that metric) are excluded from BOTH the
    weighted sum and the weight total actually used — an equal-weight
    request for a ticker missing Growth data still produces a fair
    composite over the 4 factors it does have, rather than penalizing
    it for a hole in the data."""

    value: float = 0.2
    quality: float = 0.2
    growth: float = 0.2
    momentum: float = 0.2
    size: float = 0.2


@dataclass(frozen=True, slots=True)
class RankedFactorScore:
    ticker: str
    composite_score: float | None  # None only if EVERY factor was missing
    factors_used: int  # out of 5 — how many factors actually contributed
    score: FactorScore
