"""Domain entities for risk-parity portfolio construction — proposing
an allocation across a list of tickers FROM SCRATCH, not just flagging
concentration in an existing portfolio (that's suggest_rebalancing's
job, and remains a separate, narrower tool).

Methodology: naive (inverse-volatility) risk parity — see
portfolio_risk_math.inverse_volatility_weights for the full rationale.
Not full mean-variance optimization: that requires an expected-return
estimate per ticker, and there is no reliable source for one here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

METHODOLOGY_NOTE = (
    "Naive (inverse-volatility) risk parity: each ticker's target weight "
    "is proportional to 1/volatility, so lower-volatility names get more "
    "capital and higher-volatility names get less. This does NOT account "
    "for correlation between tickers the way full Equal Risk Contribution "
    "would, and it is NOT mean-variance optimization — there is no "
    "expected-return forecast involved, deliberately, since there is no "
    "reliable source for one. This is a risk-based allocation, not a "
    "return-maximizing one."
)


@dataclass(frozen=True, slots=True)
class RiskParityAllocation:
    ticker: str
    daily_volatility: float
    target_weight: float  # fraction of total_investment, sums to 1 across allocations
    target_dollar_amount: float
    current_price: float
    suggested_shares: float  # fractional — same convention as RebalancingSuggestion.shares_to_trim


@dataclass(frozen=True, slots=True)
class RiskParityConstructionResult:
    as_of: datetime
    total_investment: float
    allocations: list[RiskParityAllocation] = field(default_factory=list)
    # Tickers dropped for insufficient price history, a fetch failure,
    # or undefined/zero volatility — never force-fit into the weighting.
    excluded: list[str] = field(default_factory=list)
    methodology_note: str = METHODOLOGY_NOTE
