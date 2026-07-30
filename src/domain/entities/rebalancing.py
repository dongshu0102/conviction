"""Domain entities for rebalancing suggestions.

Deliberately scoped to POSITION concentration only (a single holding
too large a share of the portfolio) — not sector-level suggestions.
Sector concentration is real and already surfaced by
ComputePortfolioRiskUseCase, but "reduce Tech exposure" isn't
actionable the way "trim N shares of AAPL" is: it doesn't say which
specific holding to sell. Position-level trims are concrete and
correct; sector-level rebalancing would need a genuinely different
(and more opinionated) allocation model to do responsibly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class RebalancingSuggestion:
    ticker: str
    current_weight: float
    target_weight: float
    shares_to_trim: float
    estimated_proceeds: float


@dataclass(frozen=True, slots=True)
class RebalancingPlan:
    portfolio_id: str
    as_of: datetime
    target_max_weight: float
    suggestions: list[RebalancingSuggestion] = field(default_factory=list)
