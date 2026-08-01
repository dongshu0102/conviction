"""Financial Modeling Prep adapter.

This is the ONLY module in the codebase that knows what FMP's JSON
response shape looks like. Every field-name quirk, unit convention, or
null-handling decision for this vendor is quarantined here. If we ever
add a second vendor or switch entirely, no other layer changes.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

import httpx

from src.application.interfaces.data_provider import (
    DataProviderError,
    FinancialDataProvider,
)
from src.domain.entities.company import Company, Sector
from src.domain.entities.financial_statement import (
    BalanceSheet,
    CashFlowStatement,
    FiscalPeriodKey,
    IncomeStatement,
    Period,
)
from src.domain.entities.earnings import EarningsEvent
from src.domain.entities.etf import EtfProfile
from src.domain.entities.market_quote import MarketQuote, PriceBar
from src.domain.entities.news import NewsArticle
from src.infrastructure.data_providers.fmp_parsing import (
    parse_earnings_calendar,
    parse_eod_light,
    parse_etf_info,
    parse_stock_news,
)
from src.infrastructure.config import Settings

logger = logging.getLogger(__name__)

_FMP_SECTOR_MAP: dict[str, Sector] = {
    "Technology": Sector.TECHNOLOGY,
    "Healthcare": Sector.HEALTHCARE,
    "Financial Services": Sector.FINANCIALS,
    "Consumer Cyclical": Sector.CONSUMER_DISCRETIONARY,
    "Consumer Defensive": Sector.CONSUMER_STAPLES,
    "Industrials": Sector.INDUSTRIALS,
    "Energy": Sector.ENERGY,
    "Utilities": Sector.UTILITIES,
    "Basic Materials": Sector.MATERIALS,
    "Real Estate": Sector.REAL_ESTATE,
    "Communication Services": Sector.COMMUNICATION_SERVICES,
}


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def _parse_fiscal_quarter(period_str: str) -> int | None:
    """FMP reports quarterly periods as 'Q1'..'Q4'. Returns None for
    annual rows (period_str like 'FY') so FiscalPeriodKey's own
    validation (quarter is None iff period == QUARTERLY) stays correct.
    """
    digits = period_str.lstrip("Q")
    return int(digits) if digits.isdigit() else None


class FinancialModelingPrepProvider(FinancialDataProvider):
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.Client(
            base_url=settings.fmp_base_url,
            timeout=settings.fmp_request_timeout_seconds,
        )

    def _get(self, path: str, **params: str | int) -> list | dict:
        params = {**params, "apikey": self._settings.fmp_api_key}
        try:
            response = self._client.get(path, params=params)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise DataProviderError(f"FMP request failed for {path}: {exc}") from exc

        data = response.json()
        if isinstance(data, dict) and "Error Message" in data:
            raise DataProviderError(f"FMP error for {path}: {data['Error Message']}")
        return data

    def get_company_profile(self, ticker: str) -> Company:
        payload = self._get("/profile", symbol=ticker)
        if not payload:
            raise DataProviderError(f"No profile data returned for '{ticker}'")
        p = payload[0]

        return Company(
            ticker=p["symbol"],
            name=p.get("companyName", ticker),
            sector=_FMP_SECTOR_MAP.get(p.get("sector", ""), Sector.UNKNOWN),
            industry=p.get("industry") or "Unknown",
            exchange=p.get("exchangeShortName") or p.get("exchange") or "Unknown",
            country=p.get("country") or "Unknown",
            ipo_date=_parse_date(p.get("ipoDate")),
            description=p.get("description"),
            website=p.get("website"),
            is_active=not p.get("isDelisted", False),
        )

    def get_income_statements(
        self, ticker: str, period: Period, limit: int
    ) -> list[IncomeStatement]:
        fmp_period = "quarter" if period == Period.QUARTERLY else "annual"
        payload = self._get("/income-statement", symbol=ticker, period=fmp_period, limit=limit)

        results: list[IncomeStatement] = []
        for row in payload:
            fiscal_date = _parse_date(row["date"])
            results.append(
                IncomeStatement(
                    key=FiscalPeriodKey(
                        ticker=ticker,
                        fiscal_year=int(row["fiscalYear"]),
                        period=period,
                        fiscal_quarter=_parse_fiscal_quarter(row.get("period", ""))
                        if period == Period.QUARTERLY
                        else None,
                    ),
                    fiscal_date_ending=fiscal_date,
                    reported_currency=row.get("reportedCurrency", "USD"),
                    revenue=row.get("revenue"),
                    cost_of_revenue=row.get("costOfRevenue"),
                    gross_profit=row.get("grossProfit"),
                    operating_expenses=row.get("operatingExpenses"),
                    operating_income=row.get("operatingIncome"),
                    net_income=row.get("netIncome"),
                    eps_basic=row.get("eps"),
                    eps_diluted=row.get("epsDiluted"),
                    ebitda=row.get("ebitda"),
                    raw=row,
                )
            )
        return results

    def get_balance_sheets(
        self, ticker: str, period: Period, limit: int
    ) -> list[BalanceSheet]:
        fmp_period = "quarter" if period == Period.QUARTERLY else "annual"
        payload = self._get("/balance-sheet-statement", symbol=ticker, period=fmp_period, limit=limit)

        results: list[BalanceSheet] = []
        for row in payload:
            results.append(
                BalanceSheet(
                    key=FiscalPeriodKey(
                        ticker=ticker,
                        fiscal_year=int(row["fiscalYear"]),
                        period=period,
                        fiscal_quarter=_parse_fiscal_quarter(row.get("period", ""))
                        if period == Period.QUARTERLY
                        else None,
                    ),
                    fiscal_date_ending=_parse_date(row["date"]),
                    reported_currency=row.get("reportedCurrency", "USD"),
                    total_assets=row.get("totalAssets"),
                    total_current_assets=row.get("totalCurrentAssets"),
                    cash_and_equivalents=row.get("cashAndCashEquivalents"),
                    total_liabilities=row.get("totalLiabilities"),
                    total_current_liabilities=row.get("totalCurrentLiabilities"),
                    total_debt=row.get("totalDebt"),
                    total_equity=row.get("totalStockholdersEquity"),
                    shares_outstanding=row.get("commonStock"),
                    raw=row,
                )
            )
        return results

    def get_cash_flow_statements(
        self, ticker: str, period: Period, limit: int
    ) -> list[CashFlowStatement]:
        fmp_period = "quarter" if period == Period.QUARTERLY else "annual"
        payload = self._get("/cash-flow-statement", symbol=ticker, period=fmp_period, limit=limit)

        results: list[CashFlowStatement] = []
        for row in payload:
            results.append(
                CashFlowStatement(
                    key=FiscalPeriodKey(
                        ticker=ticker,
                        fiscal_year=int(row["fiscalYear"]),
                        period=period,
                        fiscal_quarter=_parse_fiscal_quarter(row.get("period", ""))
                        if period == Period.QUARTERLY
                        else None,
                    ),
                    fiscal_date_ending=_parse_date(row["date"]),
                    reported_currency=row.get("reportedCurrency", "USD"),
                    operating_cash_flow=row.get("operatingCashFlow"),
                    capital_expenditures=row.get("capitalExpenditure"),
                    free_cash_flow=row.get("freeCashFlow"),
                    dividends_paid=row.get("dividendsPaid"),
                    net_change_in_cash=row.get("netChangeInCash"),
                    raw=row,
                )
            )
        return results

    def get_sp500_constituent_tickers(self) -> list[str]:
        payload = self._get("/sp500-constituent")
        return sorted({row["symbol"] for row in payload if row.get("symbol")})

    def get_quote(self, ticker: str) -> MarketQuote:
        payload = self._get("/quote", symbol=ticker)
        if not payload:
            raise DataProviderError(f"No quote data returned for '{ticker}'")
        q = payload[0]

        if q.get("price") is None or q.get("marketCap") is None:
            raise DataProviderError(f"Quote for '{ticker}' missing price or marketCap")

        return MarketQuote(
            ticker=ticker,
            price=q["price"],
            market_cap=q["marketCap"],
            as_of=datetime.now(timezone.utc),
        )

    def get_stock_news(self, ticker: str, limit: int = 10) -> list[NewsArticle]:
        payload = self._get("/news/stock", symbols=ticker, limit=limit)
        return parse_stock_news(payload, ticker)

    def get_daily_closes(self, ticker: str, limit: int = 30) -> list[PriceBar]:
        payload = self._get("/historical-price-eod/light", symbol=ticker)
        return parse_eod_light(payload, ticker)[:limit]

    def get_earnings_calendar(self, from_date: date, to_date: date) -> list[EarningsEvent]:
        payload = self._get(
            "/earnings-calendar", **{"from": from_date.isoformat(), "to": to_date.isoformat()}
        )
        return parse_earnings_calendar(payload)

    def get_etf_profile(self, ticker: str) -> EtfProfile | None:
        payload = self._get("/etf/info", symbol=ticker)
        return parse_etf_info(payload, ticker)
