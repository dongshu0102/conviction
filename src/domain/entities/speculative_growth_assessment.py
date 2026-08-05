"""Domain entity for a speculative-growth assessment.

Deliberately NOT a single score. Standard factor scoring z-scores a
ticker against an established-company peer universe and penalizes
negative ROE, a meaningless P/E, thin history — exactly the profile of
a genuine early-stage company before a real growth story plays out.
Using that same scoring here would systematically screen out the
companies this assessment exists to surface.

Instead: a structured, honest breakdown. Every field that can't be
computed from real data is None, not guessed — same discipline as
factor scores' null z-scores, applied to a genuinely different kind of
company.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class SpeculativeGrowthAssessment:
    ticker: str
    as_of: datetime
    market_cap: float | None

    revenue_growth_latest_yoy: float | None
    revenue_growth_prior_yoy: float | None
    growth_trend: str  # "accelerating" | "decelerating" | "insufficient_data"

    is_profitable: bool | None  # None only if net_income itself is unknown
    net_income_latest: float | None

    # None whenever operating cash flow isn't negative (burning cash is
    # the only situation "runway" is a meaningful concept for at all) —
    # a positive/unknown operating cash flow means this field simply
    # doesn't apply, not that it's zero.
    cash_runway_months: float | None

    years_of_data_available: int
    risk_flags: list[str] = field(default_factory=list)
