"""Computed, live portfolio valuation. Not persisted — recomputed from
current holdings + live quotes on every request, same principle as
ValuationSnapshot: price changes constantly, caching it risks staleness
for no real benefit.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class PositionValue:
    ticker: str
    shares: float
    cost_basis_per_share: float
    current_price: float
    market_value: float
    cost_basis_total: float
    unrealized_gain: float
    unrealized_gain_pct: float | None
    weight: float | None  # this position's share of total portfolio market value


@dataclass(frozen=True, slots=True)
class PortfolioValuation:
    portfolio_id: str
    name: str
    as_of: datetime
    positions: list[PositionValue]
    total_market_value: float
    total_cost_basis: float
    total_unrealized_gain: float
    total_unrealized_gain_pct: float | None
