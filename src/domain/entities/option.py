"""Domain entities for options trading.

Real, verified against MarketData.app's actual documented API response
(fetched directly from their docs, not guessed) — the wire format is
columnar (parallel arrays), which this domain model deliberately does
NOT mirror; the adapter's job is to convert that into these normal,
one-record-per-contract entities before anything else in the app ever
sees them.

Rho is deliberately absent from OptionQuote — MarketData.app's option
chain endpoint returns delta/gamma/theta/vega but not rho (confirmed
from their real response schema), and we're not computing Greeks
ourselves for v1, only parsing what the provider gives us.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class OptionContract:
    """Identifies a specific option — the OCC-symbology contract, not a
    live quote. Two contracts are the same contract if these four
    fields match, regardless of when you're asking."""

    underlying_ticker: str
    strike: float
    expiration: date
    option_type: str  # "call" or "put"

    @property
    def occ_symbol_fragment(self) -> str:
        """A human-readable identifier, not the real OCC symbol format
        (which needs zero-padding etc.) — just for logging/display."""
        return f"{self.underlying_ticker} {self.expiration.isoformat()} {self.option_type.upper()} {self.strike}"


@dataclass(frozen=True, slots=True)
class OptionQuote:
    contract: OptionContract
    bid: float | None
    ask: float | None
    last: float | None
    implied_volatility: float | None
    open_interest: int | None
    volume: int | None
    delta: float | None
    gamma: float | None
    theta: float | None
    vega: float | None
    underlying_price: float | None
    as_of: datetime


@dataclass(frozen=True, slots=True)
class OptionHolding:
    contract: OptionContract
    contracts_held: int  # positive = long, negative = short; 1 contract = 100 shares, standard
    cost_basis_per_contract: float
    acquired_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class PortfolioGreeks:
    """Portfolio-level aggregate — position-size-weighted sum of each
    Greek across all option holdings. This is the 'Measure Portfolio
    Greeks' step from the original workflow request."""

    portfolio_id: str
    as_of: datetime
    total_delta: float
    total_gamma: float
    total_theta: float
    total_vega: float
    positions_included: int
    positions_excluded: list[str] = field(default_factory=list)
