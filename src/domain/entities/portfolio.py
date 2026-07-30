"""Domain entities for portfolio construction.

Portfolio.portfolio_id is a UUID generated at creation time in the use
case, not a DB-assigned autoincrement id — this keeps portfolio creation
fully testable without a database, same principle used throughout this
codebase (see CompanyResearchReport's natural-key approach).

Holdings represent CURRENT POSITION STATE (shares + average cost basis),
not a transaction log. Adding the same ticker again updates the existing
position rather than appending a trade. A transaction-history feature
(individual buy/sell lots) is a reasonable future addition but is a
different, larger feature — this is deliberately just "what do I hold
right now."

Same unauthenticated user_id caveat as WatchlistItem: no login/session
system exists yet.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class PortfolioHolding:
    ticker: str
    shares: float
    cost_basis_per_share: float
    acquired_at: date | None = None

    def __post_init__(self) -> None:
        if self.shares <= 0:
            raise ValueError("PortfolioHolding.shares must be positive")
        if self.cost_basis_per_share < 0:
            raise ValueError("PortfolioHolding.cost_basis_per_share cannot be negative")
        object.__setattr__(self, "ticker", self.ticker.strip().upper())


@dataclass(frozen=True, slots=True)
class Portfolio:
    portfolio_id: str
    user_id: str
    name: str
    created_at: datetime
    holdings: list[PortfolioHolding] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("Portfolio.name must be a non-empty string")
