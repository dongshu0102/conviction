"""Domain entities for periodic financial statements.

Each statement type is modeled explicitly with typed fields rather than as
a generic key-value bag, so downstream analysis (ratios, valuation models,
the future Financial Analysis Agent) gets compile-time safety on the
fields it actually needs.

A `raw` payload is retained alongside the typed fields for line items we
haven't modeled yet. This avoids the two failure modes of a naive design:
  (a) blocking ingestion until every possible vendor line item is mapped, or
  (b) silently discarding source data that a future feature will need.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class Period(str, Enum):
    ANNUAL = "ANNUAL"
    QUARTERLY = "QUARTERLY"
    TTM = "TTM"  # trailing twelve months — derived, never stored from a vendor


@dataclass(frozen=True, slots=True)
class FiscalPeriodKey:
    """Uniquely identifies one reporting period for one company.

    This is the natural key for every statement table: (ticker, fiscal_year,
    fiscal_quarter, period). Re-ingesting the same period overwrites rather
    than duplicates — important, because vendors restate historical figures.
    """

    ticker: str
    fiscal_year: int
    period: Period
    fiscal_quarter: int | None = None  # None for ANNUAL/TTM, 1-4 for QUARTERLY

    def __post_init__(self) -> None:
        if self.period == Period.QUARTERLY and self.fiscal_quarter is None:
            raise ValueError("QUARTERLY statements require fiscal_quarter (1-4)")
        if self.period != Period.QUARTERLY and self.fiscal_quarter is not None:
            raise ValueError(f"{self.period.value} statements must not set fiscal_quarter")


@dataclass(frozen=True, slots=True)
class IncomeStatement:
    key: FiscalPeriodKey
    fiscal_date_ending: date
    reported_currency: str
    revenue: float | None = None
    cost_of_revenue: float | None = None
    gross_profit: float | None = None
    operating_expenses: float | None = None
    operating_income: float | None = None
    net_income: float | None = None
    eps_basic: float | None = None
    eps_diluted: float | None = None
    ebitda: float | None = None
    raw: dict = field(default_factory=dict, repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class BalanceSheet:
    key: FiscalPeriodKey
    fiscal_date_ending: date
    reported_currency: str
    total_assets: float | None = None
    total_current_assets: float | None = None
    cash_and_equivalents: float | None = None
    total_liabilities: float | None = None
    total_current_liabilities: float | None = None
    total_debt: float | None = None
    total_equity: float | None = None
    shares_outstanding: float | None = None
    raw: dict = field(default_factory=dict, repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class CashFlowStatement:
    key: FiscalPeriodKey
    fiscal_date_ending: date
    reported_currency: str
    operating_cash_flow: float | None = None
    capital_expenditures: float | None = None
    free_cash_flow: float | None = None
    dividends_paid: float | None = None
    net_change_in_cash: float | None = None
    raw: dict = field(default_factory=dict, repr=False, compare=False)
