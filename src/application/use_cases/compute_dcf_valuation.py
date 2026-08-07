"""Use cases: DCF and reverse DCF for a real, ingested ticker.

Wires real financial data (most recent free cash flow, net debt, share
count, historical revenue growth) to the pure math in valuation_math.py.
Every assumption used — including ones the caller didn't explicitly
supply — is returned alongside the result, never silently baked in.
Matches AssessSpeculativeGrowthUseCase's own principle: an honest
breakdown of what was actually assumed, not a bare number.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.application.interfaces.data_provider import DataProviderError, FinancialDataProvider
from src.application.use_cases.get_company_financials import (
    CompanyNotFoundError,
    GetCompanyFinancialsUseCase,
)
from src.domain.services.valuation_math import DcfAssumptionError, DcfResult, compute_dcf, solve_reverse_dcf

DEFAULT_DISCOUNT_RATE = 0.10
DEFAULT_TERMINAL_GROWTH_RATE = 0.025
DEFAULT_YEARS = 5


class InsufficientDataError(Exception):
    """Raised when a ticker exists but lacks the specific financial
    data (free cash flow, balance sheet figures) a DCF needs — a
    different, more specific failure than "ticker not found"."""


def _most_recent_free_cash_flow(cash_flow_statements) -> float | None:
    if not cash_flow_statements:
        return None
    latest = sorted(cash_flow_statements, key=lambda s: s.key.fiscal_year, reverse=True)[0]
    if latest.free_cash_flow is not None:
        return latest.free_cash_flow
    if latest.operating_cash_flow is not None and latest.capital_expenditures is not None:
        # capital_expenditures is conventionally reported as a negative
        # outflow — FCF = OCF + capex when capex is already negative.
        return latest.operating_cash_flow + latest.capital_expenditures
    return None


def _most_recent_balance_sheet(balance_sheets):
    if not balance_sheets:
        return None
    return sorted(balance_sheets, key=lambda s: s.key.fiscal_year, reverse=True)[0]


def _historical_revenue_cagr(income_statements) -> float | None:
    """Default growth-rate assumption when the caller doesn't supply
    one — the company's own historical revenue CAGR, not an arbitrary
    constant. Still just a starting point, not a claim about the
    future; the caller can always override it."""
    if len(income_statements) < 2:
        return None
    sorted_statements = sorted(income_statements, key=lambda s: s.key.fiscal_year)
    oldest, newest = sorted_statements[0], sorted_statements[-1]
    if oldest.revenue is None or newest.revenue is None or oldest.revenue <= 0:
        return None
    years = newest.key.fiscal_year - oldest.key.fiscal_year
    if years <= 0:
        return None
    return (newest.revenue / oldest.revenue) ** (1 / years) - 1


@dataclass(frozen=True, slots=True)
class DcfAssumptions:
    base_fcf: float
    growth_rate: float
    growth_rate_was_default: bool
    discount_rate: float
    terminal_growth_rate: float
    years: int
    net_debt: float
    shares_outstanding: float | None


@dataclass(frozen=True, slots=True)
class DcfAssessment:
    ticker: str
    as_of: datetime
    assumptions: DcfAssumptions
    result: DcfResult


class ComputeDcfUseCase:
    def __init__(self, get_financials: GetCompanyFinancialsUseCase) -> None:
        self._get_financials = get_financials

    def execute(
        self,
        ticker: str,
        growth_rate: float | None = None,
        discount_rate: float = DEFAULT_DISCOUNT_RATE,
        terminal_growth_rate: float = DEFAULT_TERMINAL_GROWTH_RATE,
        years: int = DEFAULT_YEARS,
    ) -> DcfAssessment:
        ticker = ticker.strip().upper()
        try:
            financials = self._get_financials.execute(ticker, years=5)
        except CompanyNotFoundError:
            raise

        base_fcf = _most_recent_free_cash_flow(financials.cash_flow_statements)
        if base_fcf is None:
            raise InsufficientDataError(
                f"No usable free cash flow data available for {ticker}."
            )

        balance_sheet = _most_recent_balance_sheet(financials.balance_sheets)
        total_debt = balance_sheet.total_debt if balance_sheet else None
        cash = balance_sheet.cash_and_equivalents if balance_sheet else None
        net_debt = (total_debt or 0.0) - (cash or 0.0)
        shares_outstanding = balance_sheet.shares_outstanding if balance_sheet else None

        growth_rate_was_default = growth_rate is None
        if growth_rate is None:
            growth_rate = _historical_revenue_cagr(financials.income_statements)
            if growth_rate is None:
                raise InsufficientDataError(
                    f"No growth_rate supplied and not enough history to derive a "
                    f"default for {ticker} — provide one explicitly."
                )

        assumptions = DcfAssumptions(
            base_fcf=base_fcf, growth_rate=growth_rate,
            growth_rate_was_default=growth_rate_was_default,
            discount_rate=discount_rate, terminal_growth_rate=terminal_growth_rate,
            years=years, net_debt=net_debt, shares_outstanding=shares_outstanding,
        )
        try:
            result = compute_dcf(
                base_fcf=base_fcf, growth_rate=growth_rate, discount_rate=discount_rate,
                terminal_growth_rate=terminal_growth_rate, years=years,
                net_debt=net_debt, shares_outstanding=shares_outstanding,
            )
        except DcfAssumptionError:
            raise

        return DcfAssessment(
            ticker=ticker, as_of=datetime.now(timezone.utc),
            assumptions=assumptions, result=result,
        )


@dataclass(frozen=True, slots=True)
class ReverseDcfAssumptions:
    base_fcf: float
    discount_rate: float
    terminal_growth_rate: float
    years: int
    net_debt: float
    shares_outstanding: float


@dataclass(frozen=True, slots=True)
class ReverseDcfResult:
    ticker: str
    as_of: datetime
    current_price: float
    implied_growth_rate: float | None
    assumptions: ReverseDcfAssumptions


class ComputeReverseDcfUseCase:
    def __init__(
        self,
        get_financials: GetCompanyFinancialsUseCase,
        data_provider: FinancialDataProvider,
    ) -> None:
        self._get_financials = get_financials
        self._data_provider = data_provider

    def execute(
        self,
        ticker: str,
        discount_rate: float = DEFAULT_DISCOUNT_RATE,
        terminal_growth_rate: float = DEFAULT_TERMINAL_GROWTH_RATE,
        years: int = DEFAULT_YEARS,
    ) -> ReverseDcfResult:
        ticker = ticker.strip().upper()
        try:
            financials = self._get_financials.execute(ticker, years=5)
        except CompanyNotFoundError:
            raise

        base_fcf = _most_recent_free_cash_flow(financials.cash_flow_statements)
        if base_fcf is None:
            raise InsufficientDataError(
                f"No usable free cash flow data available for {ticker}."
            )

        balance_sheet = _most_recent_balance_sheet(financials.balance_sheets)
        total_debt = balance_sheet.total_debt if balance_sheet else None
        cash = balance_sheet.cash_and_equivalents if balance_sheet else None
        net_debt = (total_debt or 0.0) - (cash or 0.0)
        shares_outstanding = balance_sheet.shares_outstanding if balance_sheet else None
        if shares_outstanding is None or shares_outstanding <= 0:
            raise InsufficientDataError(
                f"No usable shares-outstanding figure for {ticker} — "
                f"reverse DCF needs a real per-share target price to solve against."
            )

        try:
            quote = self._data_provider.get_quote(ticker)
        except DataProviderError:
            raise

        implied_growth_rate = solve_reverse_dcf(
            target_price=quote.price, base_fcf=base_fcf, discount_rate=discount_rate,
            terminal_growth_rate=terminal_growth_rate, years=years,
            net_debt=net_debt, shares_outstanding=shares_outstanding,
        )

        assumptions = ReverseDcfAssumptions(
            base_fcf=base_fcf, discount_rate=discount_rate,
            terminal_growth_rate=terminal_growth_rate, years=years,
            net_debt=net_debt, shares_outstanding=shares_outstanding,
        )

        return ReverseDcfResult(
            ticker=ticker, as_of=datetime.now(timezone.utc), current_price=quote.price,
            implied_growth_rate=implied_growth_rate, assumptions=assumptions,
        )
