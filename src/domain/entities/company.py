"""Domain entity representing a publicly traded company.

Pure domain object — no framework or infrastructure dependencies.
Per Clean Architecture's dependency rule, the domain layer may not import
from application, infrastructure, or api. Everything else in the system
depends on this layer; this layer depends on nothing.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class Sector(str, Enum):
    TECHNOLOGY = "Technology"
    HEALTHCARE = "Healthcare"
    FINANCIALS = "Financials"
    CONSUMER_DISCRETIONARY = "Consumer Discretionary"
    CONSUMER_STAPLES = "Consumer Staples"
    INDUSTRIALS = "Industrials"
    ENERGY = "Energy"
    UTILITIES = "Utilities"
    MATERIALS = "Materials"
    REAL_ESTATE = "Real Estate"
    COMMUNICATION_SERVICES = "Communication Services"
    ETF = "ETF"  # distinct from UNKNOWN — a fund has no GICS sector by
    # nature, which is a different situation from a data gap on a real
    # operating company. Keeping them distinct means a portfolio's
    # sector-exposure breakdown can say "12% ETF" honestly instead of
    # lumping funds in with genuine missing-data cases.
    UNKNOWN = "Unknown"


class AssetType(str, Enum):
    EQUITY = "EQUITY"
    ETF = "ETF"


@dataclass(frozen=True, slots=True)
class Company:
    """Immutable snapshot of a company's identifying profile.

    `ticker` is the natural business key used across the entire platform:
    financial statements, valuations, and every future agent's output
    reference a company by ticker rather than a synthetic surrogate id
    the domain layer doesn't own.

    ETFs are modeled as a variant of this SAME entity (asset_type=ETF)
    rather than a parallel type — deliberate choice: every existing
    "is this ticker known" check across watchlists, themes, and
    screening already queries this repository, and reusing it means
    ETFs participate in all of that for free. An ETF ticker simply has
    zero ingested financial statements (by construction — funds don't
    file income statements), which the valuation/analysis pipeline
    already treats as honestly-partial data, not a hard failure — the
    exact machinery proven by the TSM currency-guard case. expense_ratio
    and aum are meaningless (None) for an EQUITY; sector/industry are
    meaningless (Sector.ETF / "ETF") for a fund.
    """

    ticker: str
    name: str
    sector: Sector
    industry: str
    exchange: str
    country: str
    ipo_date: date | None = None
    description: str | None = None
    website: str | None = None
    is_active: bool = True
    asset_type: AssetType = AssetType.EQUITY
    expense_ratio: float | None = None  # ETF only
    aum: float | None = None  # ETF only — analog to market_cap for factor Size

    def __post_init__(self) -> None:
        if not self.ticker or not self.ticker.strip():
            raise ValueError("Company.ticker must be a non-empty string")
        # Normalize so "aapl" and "AAPL" are never treated as different companies.
        object.__setattr__(self, "ticker", self.ticker.strip().upper())
