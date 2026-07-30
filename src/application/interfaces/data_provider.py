"""Contract every external market-data vendor adapter must satisfy.

This is the seam that lets us swap Financial Modeling Prep for
Polygon.io, Tiingo, or an enterprise vendor later by writing one new
adapter class — without touching use cases, API routes, or the database.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.company import Company
from src.domain.entities.financial_statement import (
    BalanceSheet,
    CashFlowStatement,
    IncomeStatement,
    Period,
)
from src.domain.entities.market_quote import MarketQuote


class FinancialDataProvider(ABC):
    @abstractmethod
    def get_company_profile(self, ticker: str) -> Company: ...

    @abstractmethod
    def get_income_statements(
        self, ticker: str, period: Period, limit: int
    ) -> list[IncomeStatement]: ...

    @abstractmethod
    def get_balance_sheets(
        self, ticker: str, period: Period, limit: int
    ) -> list[BalanceSheet]: ...

    @abstractmethod
    def get_cash_flow_statements(
        self, ticker: str, period: Period, limit: int
    ) -> list[CashFlowStatement]: ...

    @abstractmethod
    def get_sp500_constituent_tickers(self) -> list[str]:
        """Current S&P 500 membership, as tickers only.

        Deliberately returns just tickers, not full constituent metadata
        (sector, date added, etc.) — that data already lives in Company
        via get_company_profile, and duplicating it here would create two
        sources of truth for the same fact.
        """

    @abstractmethod
    def get_quote(self, ticker: str) -> MarketQuote:
        """Current market price and market cap — the one piece of live
        market data (as opposed to periodic filed statements) this
        platform needs, specifically for valuation multiples.
        """


class DataProviderError(Exception):
    """Raised on any vendor failure (HTTP error, rate limit, bad payload).

    Use cases catch this — never a vendor-specific exception — so that
    swapping providers never requires touching error-handling logic
    upstream.
    """
