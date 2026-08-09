"""Contract every external market-data vendor adapter must satisfy.

This is the seam that lets us swap Financial Modeling Prep for
Polygon.io, Tiingo, or an enterprise vendor later by writing one new
adapter class — without touching use cases, API routes, or the database.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from src.domain.entities.company import Company
from src.domain.entities.capital_flow import InsiderTrade, PoliticianTrade
from src.domain.entities.earnings import EarningsEvent
from src.domain.entities.economic_indicator import EconomicIndicatorReading
from src.domain.entities.etf import EtfProfile
from src.domain.entities.general_news import GeneralNewsHeadline
from src.domain.entities.financial_statement import (
    BalanceSheet,
    CashFlowStatement,
    IncomeStatement,
    Period,
)
from src.domain.entities.market_quote import MarketQuote, PriceBar
from src.domain.entities.market_risk_premium import MarketRiskPremium
from src.domain.entities.news import NewsArticle
from src.domain.entities.treasury_rates import TreasuryRates


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

    def get_etf_profile(self, ticker: str) -> EtfProfile | None:
        """None means the ticker isn't a recognized ETF (or the lookup
        failed) — distinct from NotImplementedError, which means this
        provider doesn't support ETF lookups at all."""
        raise NotImplementedError("This data provider does not support get_etf_profile")

    def get_general_news(self, limit: int = 20) -> list[GeneralNewsHeadline]:
        """Non-ticker-specific market/macro news — the grounding signal
        for theme suggestion, distinct from get_stock_news which is
        always scoped to one symbol."""
        raise NotImplementedError("This data provider does not support get_general_news")

    @abstractmethod
    def get_quote(self, ticker: str) -> MarketQuote:
        """Current market price and market cap — the one piece of live
        market data (as opposed to periodic filed statements) this
        platform needs, specifically for valuation multiples.
        """

    def get_treasury_rates(self) -> TreasuryRates:
        """The most recent daily Treasury yield curve — the market's
        real-time proxy for the risk-free rate. Optional, like
        get_general_news: not every provider offers macro/economic
        data, so this raises by default rather than being abstract."""
        raise NotImplementedError("This data provider does not support get_treasury_rates")

    def get_economic_indicator(self, name: str) -> list[EconomicIndicatorReading]:
        """Historical readings for one named economic indicator (GDP,
        CPI, unemploymentRate, etc) — most recent first. Optional,
        same rationale as get_treasury_rates."""
        raise NotImplementedError("This data provider does not support get_economic_indicator")

    def get_market_risk_premium(self, country: str = "United States") -> MarketRiskPremium | None:
        """One country's current equity risk premium. Returns None if
        the country isn't found in the dataset, rather than raising —
        a missing country is a normal, expected outcome, not a
        provider failure. Optional, same rationale as
        get_treasury_rates."""
        raise NotImplementedError("This data provider does not support get_market_risk_premium")

    def get_latest_insider_trades(self, limit: int = 100) -> list[InsiderTrade]:
        """The most recent insider-trading disclosures across the
        entire market, most recent first — not scoped to a single
        ticker. Optional, same rationale as get_treasury_rates."""
        raise NotImplementedError("This data provider does not support get_latest_insider_trades")

    def get_latest_senate_trades(self, limit: int = 100) -> list[PoliticianTrade]:
        """The most recent U.S. Senate financial disclosures across
        the entire market, most recent first. Optional, same rationale
        as get_treasury_rates."""
        raise NotImplementedError("This data provider does not support get_latest_senate_trades")

    def get_latest_house_trades(self, limit: int = 100) -> list[PoliticianTrade]:
        """The most recent U.S. House financial disclosures across the
        entire market, most recent first. Optional, same rationale as
        get_treasury_rates."""
        raise NotImplementedError("This data provider does not support get_latest_house_trades")

    def get_daily_bars_full(self, ticker: str, limit: int = 30) -> list[PriceBar]:
        """Real OHLCV bars INCLUDING volume, most recent first — unlike
        get_daily_closes (close price only, used for momentum). Optional,
        same rationale as get_treasury_rates."""
        raise NotImplementedError("This data provider does not support get_daily_bars_full")


class DataProviderError(Exception):
    """Raised on any vendor failure (HTTP error, rate limit, bad payload).

    Use cases catch this — never a vendor-specific exception — so that
    swapping providers never requires touching error-handling logic
    upstream.
    """
