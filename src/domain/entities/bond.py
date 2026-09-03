"""Domain entities for bond/fixed-income holdings.

Deliberately a genuinely separate model from PortfolioHolding
(equities), matching the same additive-extension pattern already
established for OptionHolding: bonds have no real equivalent to a
stock ticker (identified by CUSIP/ISIN instead), no "shares" (a face
value and a quantity of bonds instead), and several genuinely distinct
concepts equities don't have at all -- coupon rate, maturity date,
credit rating. Extending PortfolioHolding with a pile of nullable,
bond-specific fields would leave most fields always-null for one asset
type or the other; a real, separate entity is honestly cleaner.

Prices and cost basis are quoted as a percentage of face value (e.g.
98.5 means $985 per $1,000 of face value) -- the real, standard bond
market convention, not a dollar amount directly.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class BondIdentity:
    """Identifies a specific bond issuance. Two bonds are the same
    bond if these fields match, regardless of when you're asking --
    same role as OptionContract for options."""

    cusip: str | None  # the real, standard 9-character bond identifier, when known
    issuer_name: str
    coupon_rate: float  # decimal, e.g. 0.045 for 4.5% annual coupon
    maturity_date: date
    face_value: float = 1000.0  # standard U.S. bond convention; not universal, but the common default


@dataclass(frozen=True, slots=True)
class BondHolding:
    bond: BondIdentity
    quantity: int  # number of bonds held, each worth bond.face_value at maturity
    cost_basis_price: float  # % of face value paid, e.g. 98.5 (not 0.985) -- standard bond quoting convention
    acquired_at: date | None = None

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("BondHolding.quantity must be positive")
        if self.cost_basis_price <= 0:
            raise ValueError("BondHolding.cost_basis_price must be positive")


@dataclass(frozen=True, slots=True)
class BondValuation:
    """Real, computed analytics for one bond holding -- current yield
    and yield to maturity, both derived deterministically from the
    holding's own real inputs, never fetched from a live market price
    this app doesn't have access to."""

    bond: BondIdentity
    quantity: int
    cost_basis_price: float
    current_price: float | None  # None when no live price is available; cost basis is used as the estimate instead
    current_yield: float | None  # annual coupon / current price, as a decimal
    yield_to_maturity: float | None  # None if a real YTM couldn't be solved (e.g. already matured)
    years_to_maturity: float
    total_face_value: float
    total_cost_basis: float


@dataclass(frozen=True, slots=True)
class BondPortfolioValuation:
    portfolio_id: str
    as_of: datetime
    positions: list[BondValuation]
    total_face_value: float = 0.0
    total_cost_basis: float = 0.0
