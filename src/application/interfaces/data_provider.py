"""Contract every external market-data vendor adapter must satisfy.

This is the seam that lets us swap Financial Modeling Prep for
Polygon.io, Tiingo, or an enterprise vendor later by writing one new
adapter class — without touching use cases, API routes, or the database.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from src.domain.entities.company import Company
from src.domain.entities.earnings import EarningsEvent
from src.domain.entities.financial_statement import (
    BalanceSheet,
    CashFlowStatement,
    IncomeStatement,
    Period,
)
from src.domain.entities.market_quote import MarketQuote, PriceBar
from src.domain.entities.news import NewsArticle


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

    # -- Phase C capabilities: deliberately NON-abstract, unlike the
    # rest of this interface. Making them abstract would break every
    # existing fake/test provider for capabilities those tests don't
    # exercise. Consumers must treat NotImplementedError as "capability
    # absent" and degrade honestly (signal=None / feature unavailable),
    # never crash.
    def get_stock_news(self, ticker: str, limit: int = 10) -> list[NewsArticle]:
        raise NotImplementedError("This data provider does not support get_stock_news")

    def get_daily_closes(self, ticker: str, limit: int = 30) -> list[PriceBar]:
        """Most-recent-first end-of-day closes."""
        raise NotImplementedError("This data provider does not support get_daily_closes")

    def get_earnings_calendar(self, from_date: date, to_date: date) -> list[EarningsEvent]:
        """Every earnings announcement (any ticker) within the date
        range — callers filter to whichever tickers they care about."""
        raise NotImplementedError("This data provider does not support get_earnings_calendar")

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
