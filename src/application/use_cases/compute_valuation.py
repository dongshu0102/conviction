"""Use case: compute valuation multiples from a live quote and the most
recent annual fundamentals.

Deterministic arithmetic, same principle as ComputeFinancialAnalysisUseCase
— valuation multiples have exact right answers given price and financial
data, so there's no reason to let an LLM compute them and risk an
arithmetic error.
"""
from __future__ import annotations

from datetime import datetime, timezone

from src.application.interfaces.data_provider import (
    DataProviderError,
    FinancialDataProvider,
)
from src.application.use_cases.get_company_financials import (
    CompanyNotFoundError,
    GetCompanyFinancialsUseCase,
)
from src.domain.entities.valuation_snapshot import ValuationSnapshot


def _safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


class NoFinancialDataError(Exception):
    def __init__(self, ticker: str) -> None:
        self.ticker = ticker
        super().__init__(
            f"'{ticker}' has a company profile but no ingested financial "
            f"statements — run ingestion before computing valuation."
        )


class ComputeValuationUseCase:
    def __init__(
        self,
        get_financials: GetCompanyFinancialsUseCase,
        data_provider: FinancialDataProvider,
    ) -> None:
        self._get_financials = get_financials
        self._data_provider = data_provider

    def execute(self, ticker: str) -> ValuationSnapshot:
        ticker = ticker.strip().upper()

        try:
            financials = self._get_financials.execute(ticker, years=1)
        except CompanyNotFoundError:
            raise

        if not financials.income_statements:
            raise NoFinancialDataError(ticker)

        try:
            quote = self._data_provider.get_quote(ticker)
        except DataProviderError:
            raise

        income = financials.income_statements[0]
        balance = financials.balance_sheets[0] if financials.balance_sheets else None
        cashflow = financials.cash_flow_statements[0] if financials.cash_flow_statements else None

        enterprise_value: float | None = None
        if balance is not None and balance.total_debt is not None and balance.cash_and_equivalents is not None:
            enterprise_value = quote.market_cap + balance.total_debt - balance.cash_and_equivalents

        return ValuationSnapshot(
            ticker=ticker,
            as_of=datetime.now(timezone.utc),
            price=quote.price,
            market_cap=quote.market_cap,
            enterprise_value=enterprise_value,
            fundamentals_fiscal_year=income.key.fiscal_year,
            price_to_earnings=_safe_div(quote.market_cap, income.net_income),
            price_to_sales=_safe_div(quote.market_cap, income.revenue),
            price_to_book=(
                _safe_div(quote.market_cap, balance.total_equity) if balance else None
            ),
            price_to_free_cash_flow=(
                _safe_div(quote.market_cap, cashflow.free_cash_flow) if cashflow else None
            ),
            ev_to_ebitda=_safe_div(enterprise_value, income.ebitda),
        )
