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
    UNKNOWN = "Unknown"


@dataclass(frozen=True, slots=True)
class Company:
    """Immutable snapshot of a company's identifying profile.

    `ticker` is the natural business key used across the entire platform:
    financial statements, valuations, and every future agent's output
    reference a company by ticker rather than a synthetic surrogate id
    the domain layer doesn't own.
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

    def __post_init__(self) -> None:
        if not self.ticker or not self.ticker.strip():
            raise ValueError("Company.ticker must be a non-empty string")
        # Normalize so "aapl" and "AAPL" are never treated as different companies.
        object.__setattr__(self, "ticker", self.ticker.strip().upper())
