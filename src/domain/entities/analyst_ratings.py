"""Domain entity for real, human Wall Street analyst ratings and
price targets -- Step 2's "analyst ratings" from the original
screen/rank/validate/monitor workflow.

REVISED after a real, direct production finding: this app's real FMP
account has access to /grades (raw, per-analyst grade actions) and
/price-target-summary, but NOT /grades-summary (FMP's own pre-computed
buy/sell/hold consensus count) -- confirmed directly by hitting FMP's
real, live API with the real, production key, not assumed from the
account's plan name alone. AnalystRatings is therefore built from the
real, raw grade actions this account genuinely has, rather than a
consensus count it doesn't -- no invented buy/sell/hold tally standing
in for data this account can't actually see.

Also deliberately NOT built from /ratings-snapshot: that's FMP's own
internal, algorithmically-computed score derived from fundamentals
(DCF/ROE/ROA/debt-to-equity/etc), not real analyst opinions at all --
confirmed directly by testing all three real candidates live before
choosing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True, slots=True)
class AnalystGrade:
    """One real, individual analyst firm's grade action on one real
    date -- the raw material this account actually has access to,
    not a pre-aggregated summary."""

    grading_company: str
    date: date
    previous_grade: str
    new_grade: str
    action: str  # e.g. "upgrade", "downgrade", "maintain", "initiate" -- FMP's own real, raw value


@dataclass(frozen=True, slots=True)
class AnalystRatings:
    ticker: str
    recent_grades: list[AnalystGrade] = field(default_factory=list)
    last_month_avg_price_target: float | None = None
    last_month_count: int = 0
    last_quarter_avg_price_target: float | None = None
    last_quarter_count: int = 0
    last_year_avg_price_target: float | None = None
    last_year_count: int = 0
