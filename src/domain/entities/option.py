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
    # Added after the fact — MarketData.app's midpoint between bid/ask,
    # the standard field for valuation (avoids bid-ask spread bias that
    # `last` carries for illiquid contracts with a stale last trade).
    # Default keeps this additive; existing construction sites that
    # don't pass it still work.
    mid: float | None = None


@dataclass(frozen=True, slots=True)
class OptionHolding:
    contract: OptionContract
    contracts_held: int  # positive = long, negative = short; 1 contract = 100 shares, standard
    cost_basis_per_contract: float
    acquired_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class OptionPositionValue:
    """Current market value and P&L for one option position.

    cost_basis_per_contract and current_price are BOTH per-share
    premiums, consistent with how bid/ask/last/mid are quoted in
    OptionQuote and how the market universally quotes option prices
    (e.g. "the option costs $3.20" means $3.20/share). Total dollar
    value always needs the *100 contract multiplier applied — this is
    NOT already baked into either per-share field.
    """

    contract: OptionContract
    contracts_held: int
    cost_basis_per_contract: float
    current_price: float
    market_value: float
    cost_basis_total: float
    unrealized_gain: float
    unrealized_gain_pct: float | None


@dataclass(frozen=True, slots=True)
class OptionPortfolioValuation:
    portfolio_id: str
    as_of: datetime
    positions: list[OptionPositionValue] = field(default_factory=list)
    total_market_value: float = 0.0
    total_cost_basis: float = 0.0
    total_unrealized_gain: float = 0.0
    total_unrealized_gain_pct: float | None = None
    positions_excluded: list[str] = field(default_factory=list)  # contracts with no live quote


@dataclass(frozen=True, slots=True)
class HedgeSuggestion:
    """A mechanical delta hedge for one underlying — buy/sell shares of
    the underlying itself to neutralize combined stock + option delta
    exposure on that ticker. Deliberately hedges with the underlying's
    own shares, not a new option position — that would require choosing
    a strike/expiration for the hedge itself, a second layer of
    ambiguity this keeps out of scope."""

    underlying_ticker: str
    net_delta: float  # combined stock + option delta exposure BEFORE hedging
    shares_to_trade: float  # positive = buy, negative = sell/short
    resulting_delta: float  # net_delta + shares_to_trade, should be ~0


@dataclass(frozen=True, slots=True)
class HedgingPlan:
    portfolio_id: str
    as_of: datetime
    suggestions: list[HedgeSuggestion] = field(default_factory=list)
    positions_excluded: list[str] = field(default_factory=list)  # option contracts with no live quote


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
