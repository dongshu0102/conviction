"""Use case: IRR for a buy-hold-sell investment scenario.

Genuinely different in character from DCF/reverse DCF — this isn't
about assessing a company's fundamentals, it's a return calculator for
a specific hypothetical trade: buy at some price, optionally collect
dividends along the way, sell at some assumed exit price after N years.
entry_price defaults to the ticker's live quote if not supplied, but
every other assumption (exit price, years, dividend) is the caller's
to set — there's no way to derive a "default" exit price without
assuming the conclusion.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.application.interfaces.data_provider import DataProviderError, FinancialDataProvider
from src.domain.services.valuation_math import compute_irr


class InvalidIrrScenarioError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class IrrScenario:
    entry_price: float
    exit_price: float
    years: int
    annual_dividend_per_share: float
    cash_flows: list[float]


@dataclass(frozen=True, slots=True)
class IrrResult:
    ticker: str | None
    as_of: datetime
    irr: float | None
    scenario: IrrScenario


class ComputeInvestmentIrrUseCase:
    def __init__(self, data_provider: FinancialDataProvider) -> None:
        self._data_provider = data_provider

    def execute(
        self,
        exit_price: float,
        years: int,
        ticker: str | None = None,
        entry_price: float | None = None,
        annual_dividend_per_share: float = 0.0,
    ) -> IrrResult:
        if years < 1:
            raise InvalidIrrScenarioError("years must be at least 1.")
        if entry_price is None:
            if ticker is None:
                raise InvalidIrrScenarioError(
                    "Either entry_price or ticker (to fetch a live price) is required."
                )
            ticker = ticker.strip().upper()
            try:
                quote = self._data_provider.get_quote(ticker)
            except DataProviderError:
                raise
            entry_price = quote.price
        if entry_price <= 0:
            raise InvalidIrrScenarioError("entry_price must be positive.")

        cash_flows = [-entry_price]
        for year in range(1, years + 1):
            flow = annual_dividend_per_share
            if year == years:
                flow += exit_price
            cash_flows.append(flow)

        irr = compute_irr(cash_flows)

        scenario = IrrScenario(
            entry_price=entry_price, exit_price=exit_price, years=years,
            annual_dividend_per_share=annual_dividend_per_share, cash_flows=cash_flows,
        )
        return IrrResult(
            ticker=ticker, as_of=datetime.now(timezone.utc), irr=irr, scenario=scenario,
        )
