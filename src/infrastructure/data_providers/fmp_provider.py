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
from src.domain.services.cusip_ticker_resolution import CusipSearchResult
from src.domain.services.beneficial_ownership_form_type import derive_form_type_from_url
from src.domain.entities.capital_flow import InsiderTrade, PoliticianTrade
from src.domain.entities.financial_statement import (
    BalanceSheet,
    CashFlowStatement,
    FiscalPeriodKey,
    IncomeStatement,
    Period,
)
from src.domain.entities.earnings import EarningsEvent
from src.domain.entities.economic_indicator import EconomicIndicatorReading
from src.domain.entities.etf import EtfProfile
from src.domain.entities.general_news import GeneralNewsHeadline
from src.domain.entities.institutional_holding import InstitutionalHolding
from src.domain.entities.beneficial_ownership_disclosure import BeneficialOwnershipDisclosure
from src.domain.entities.insider_transaction import InsiderTransaction
from src.domain.entities.market_quote import MarketQuote, PriceBar
from src.domain.entities.market_risk_premium import MarketRiskPremium
from src.domain.entities.news import NewsArticle
from src.domain.entities.treasury_rates import TreasuryRates
from src.infrastructure.data_providers.fmp_parsing import (
    parse_earnings_calendar,
    parse_economic_indicator,
    parse_eod_full,
    parse_eod_light,
    parse_etf_info,
    parse_general_news,
    parse_latest_house_trades,
    parse_latest_insider_trades,
    parse_latest_senate_trades,
    parse_market_risk_premium,
    parse_stock_news,
    parse_treasury_rates,
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


def _safe_int(value) -> int:
    """Confirmed necessary against real, live data, not hypothetical:
    some numeric-looking fields in this real data source can genuinely
    arrive as None. Defaults to 0 -- "no value disclosed for this
    specific power type" is the honest, most likely real-world meaning
    of a missing numeric field here, not a genuinely different,
    non-zero value being silently lost."""
    if value is None:
        return 0
    return int(value)


def _safe_float(value) -> float:
    if value is None:
        return 0.0
    return float(value)


def _extract_accession_number(filing_url: str) -> str:
    """FMP's response never includes a standalone accession_number
    field the way this app's own SEC-sourced pipeline does -- only a
    filing URL (link/finalLink). Confirmed directly against a real
    response: the URL's own filename carries the properly-dashed
    accession number, e.g.
    ".../0001193125-26-352200-index.htm" -> "0001193125-26-352200".
    Returns "" (never raises) for a missing or unrecognized URL shape
    -- an honest empty value, not a fabricated one, since this field
    is not the primary key for FMP-sourced rows the way it is for
    this app's own SEC-sourced ones."""
    if not filing_url:
        return ""
    filename = filing_url.rstrip("/").rsplit("/", 1)[-1]
    return filename.removesuffix("-index.htm") if filename.endswith("-index.htm") else ""


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

    def get_treasury_rates(self) -> TreasuryRates:
        payload = self._get("/treasury-rates")
        try:
            return parse_treasury_rates(payload)
        except (ValueError, KeyError) as exc:
            raise DataProviderError(f"Malformed treasury-rates payload: {exc}") from exc

    def get_economic_indicator(self, name: str) -> list[EconomicIndicatorReading]:
        payload = self._get("/economic-indicators", name=name)
        return parse_economic_indicator(payload)

    def get_market_risk_premium(self, country: str = "United States") -> MarketRiskPremium | None:
        payload = self._get("/market-risk-premium")
        return parse_market_risk_premium(payload, country=country)

    def get_stock_news(self, ticker: str, limit: int = 10) -> list[NewsArticle]:
        payload = self._get("/news/stock", symbols=ticker, limit=limit)
        return parse_stock_news(payload, ticker)

    def search_cusip(self, cusip: str) -> list[CusipSearchResult]:
        """Confirmed newly accessible on the Ultimate plan tonight
        (previously blocked/legacy on lower tiers). Can legitimately
        return several rows for one CUSIP — one per exchange listing
        of the same underlying company (confirmed directly against
        real data: Apple's CUSIP returns "AAPL" plus three foreign
        listings). Disambiguation happens in the domain layer
        (pick_primary_us_ticker), not here — this method's only job is
        translating FMP's raw JSON shape faithfully."""
        payload = self._get("/search-cusip", cusip=cusip)
        return [
            CusipSearchResult(
                symbol=row["symbol"],
                company_name=row.get("companyName", ""),
                market_cap=row.get("marketCap"),
            )
            for row in payload
        ]

    def get_institutional_holdings_by_filer(
        self, cik: str, year: int, quarter: int, filer_name: str,
    ) -> list[InstitutionalHolding]:
        """One filer's 13F portfolio for one quarter, sourced live
        from FMP rather than this app's own free, bulk-ingested SEC
        pipeline — confirmed genuinely fresher for a quarter still
        actively filling in (SEC's own bulk file is published once,
        "closely after" the deadline, not continuously; FMP had a
        real filer's same-day filing available within hours,
        confirmed directly).

        filer_name is a required parameter, not something this method
        derives itself: FMP's raw response includes the filer's CIK
        but never its name, so the caller (which already resolved
        this filer by name against the local database before falling
        back here) must supply it.

        Several fields InstitutionalHolding otherwise carries simply
        aren't in FMP's response at all (investment_discretion, the
        three voting_authority_* breakdowns) -- these get an honest
        "UNKNOWN" / 0 placeholder rather than a fabricated, specific
        value. investment_discretion is the one of these actually
        shown to users (voting_authority_* never is, confirmed
        directly against the real API response schema), which is
        exactly why it gets an honest sentinel instead of guessing at
        a real 13F discretion code like "SOLE" or "DFND" that FMP
        never actually told us.

        Confirmed directly, not assumed: FMP's raw value field is
        already in real dollars, not thousands -- a real filing's
        implied price-per-share worked out to exactly $150.00,
        genuinely plausible, not the ~1000x-inflated number tonight's
        earlier SEC-parsing bug would have produced.

        Also confirmed directly, and deliberately NOT replicated here:
        unlike this app's own raw SEC-sourced data (where a single
        CUSIP can genuinely span several line items -- e.g. different
        voting-authority categories -- that must be summed before
        comparing), FMP's response already has exactly one row per
        distinct CUSIP. Checked directly against Berkshire's real Q2
        2026 response: 29 rows, 29 distinct CUSIPs, zero duplicates.
        This method intentionally does no aggregation of its own;
        adding one would silently double-count real FMP data that is
        already clean.
        """
        payload = self._get(
            "/institutional-ownership/extract", cik=cik, year=year, quarter=quarter,
        )
        holdings = []
        for row in payload:
            accession_number = _extract_accession_number(row.get("link") or row.get("finalLink") or "")
            holdings.append(InstitutionalHolding(
                accession_number=accession_number,
                filer_cik=cik,
                filer_name=filer_name,
                period_of_report=date.fromisoformat(row["date"]),
                issuer_name=row["nameOfIssuer"],
                title_of_class=row["titleOfClass"],
                cusip=row["securityCusip"],
                value_usd=int(row["value"]),
                shares_or_principal_amount=int(row["shares"]),
                share_type=row["sharesType"],
                put_call=row.get("putCallShare") or None,
                investment_discretion="UNKNOWN",
                voting_authority_sole=0,
                voting_authority_shared=0,
                voting_authority_none=0,
            ))
        return holdings

    def get_institutional_holders_by_symbol(
        self, symbol: str, year: int, quarter: int, limit: int = 20,
    ) -> list[InstitutionalHolding]:
        """Every institutional filer's reported position in one
        security for one quarter, sourced live from FMP -- the
        symbol-based sibling of get_institutional_holdings_by_filer,
        for "who holds X" rather than "what does Y hold." Confirmed
        directly against real data (Roblox, Q2 2026): matches the
        known real CUSIP (771049103) exactly, and marketValue is
        already in real dollars, not thousands -- confirmed directly,
        market_value / shares == the response's own quarterEndPrice
        exactly (54.37999990040604 vs 54.38).

        Genuinely richer than get_institutional_holdings_by_filer's
        response shape: investorName (filer name) and
        investmentDiscretion are both given directly here, so neither
        needs an "UNKNOWN" placeholder or a caller-supplied name the
        way the filer-side method does.

        putCallShare is "Share" for an ordinary equity position (FMP's
        own convention, confirmed directly) -- mapped to None here,
        not passed through literally, since that's the same real-world
        meaning ("not an option") this app's own SEC-sourced put_call
        field already uses an empty-string-to-None mapping for.
        """
        payload = self._get(
            "/institutional-ownership/extract-analytics/holder",
            symbol=symbol, year=year, quarter=quarter, page=0, limit=limit,
        )
        holdings = []
        for row in payload:
            put_call = row.get("putCallShare")
            if put_call not in ("Put", "Call"):
                put_call = None
            holdings.append(InstitutionalHolding(
                accession_number="",  # genuinely not provided by this endpoint
                filer_cik=row["cik"],
                filer_name=row["investorName"],
                period_of_report=date.fromisoformat(row["date"]),
                issuer_name=row["securityName"],
                title_of_class=row["typeOfSecurity"],
                cusip=row["securityCusip"],
                value_usd=int(row["marketValue"]),
                shares_or_principal_amount=int(row["sharesNumber"]),
                share_type=row["sharesType"],
                put_call=put_call,
                investment_discretion=row["investmentDiscretion"],
                voting_authority_sole=0,
                voting_authority_shared=0,
                voting_authority_none=0,
            ))
        return holdings

    def get_beneficial_ownership_disclosures(self, symbol: str) -> list[BeneficialOwnershipDisclosure]:
        """Every reporting person's Schedule 13D/13G disclosure for one
        security -- confirmed directly against real data, not assumed:
        Vanguard Capital Management's real, passive Apple stake (7.48%,
        13G) and Temasek Capital's real stake in e2open (a real,
        reported Elliott Management activist situation, 13D).

        percentOfClass arrives as a percent string ("7.48"), converted
        here to a fraction (0.0748) to match this codebase's existing
        convention for percentage fields elsewhere. The four power
        fields and amountBeneficiallyOwned all arrive as plain
        strings, not numbers, despite being numeric -- confirmed
        directly against the real response shape.
        """
        payload = self._get("/acquisition-of-beneficial-ownership", symbol=symbol)
        disclosures = []
        for i, row in enumerate(payload):
            try:
                disclosures.append(BeneficialOwnershipDisclosure(
                    cik=row.get("cik", ""),
                    symbol=row.get("symbol", symbol),
                    filing_date=date.fromisoformat(row["filingDate"]),
                    accepted_date=date.fromisoformat(row["acceptedDate"]),
                    cusip=row.get("cusip", ""),
                    name_of_reporting_person=row.get("nameOfReportingPerson") or "UNKNOWN",
                    citizenship_or_place_of_organization=row.get("citizenshipOrPlaceOfOrganization"),
                    sole_voting_power=_safe_int(row.get("soleVotingPower")),
                    shared_voting_power=_safe_int(row.get("sharedVotingPower")),
                    sole_dispositive_power=_safe_int(row.get("soleDispositivePower")),
                    shared_dispositive_power=_safe_int(row.get("sharedDispositivePower")),
                    amount_beneficially_owned=_safe_int(row.get("amountBeneficiallyOwned")),
                    percent_of_class=_safe_float(row.get("percentOfClass")) / 100,
                    type_of_reporting_person=row.get("typeOfReportingPerson"),
                    form_type=derive_form_type_from_url(row.get("url", "")),
                    source_url=row.get("url", ""),
                ))
            except (KeyError, ValueError, TypeError) as exc:
                logger.warning(
                    "Skipping malformed beneficial-ownership row %d for %s: %s", i, symbol, exc,
                )
        return disclosures

    def get_insider_transactions(self, symbol: str) -> list[InsiderTransaction]:
        """Every reported Form 3/4/5 transaction for one company's
        insiders -- officers, directors, and 10%+ owners. Confirmed
        directly against real data: a real Apple SVP/GC's real, recent
        open-market sale at a genuine, non-zero price (307.75), and a
        real, paired M-Exempt option-exercise event (one "D" row for
        the option/RSU, one "A" row for the resulting common stock,
        both at price=0, a real, honest reflection of a routine
        compensation event, not missing data).
        """
        payload = self._get("/insider-trading/search", symbol=symbol)
        transactions = []
        for i, row in enumerate(payload):
            try:
                transactions.append(InsiderTransaction(
                    symbol=row.get("symbol", symbol),
                    filing_date=date.fromisoformat(row["filingDate"]),
                    transaction_date=date.fromisoformat(row["transactionDate"]),
                    reporting_cik=row.get("reportingCik", ""),
                    company_cik=row.get("companyCik", ""),
                    reporting_name=row.get("reportingName") or "UNKNOWN",
                    type_of_owner=row.get("typeOfOwner") or "",
                    transaction_type=row.get("transactionType") or "",
                    acquisition_or_disposition=row.get("acquisitionOrDisposition") or "",
                    direct_or_indirect=row.get("directOrIndirect") or "",
                    security_name=row.get("securityName") or "",
                    securities_transacted=_safe_float(row.get("securitiesTransacted")),
                    securities_owned=_safe_float(row.get("securitiesOwned")),
                    price=_safe_float(row.get("price")),
                    source_url=row.get("url", ""),
                ))
            except (KeyError, ValueError, TypeError) as exc:
                logger.warning(
                    "Skipping malformed insider-transaction row %d for %s: %s", i, symbol, exc,
                )
        return transactions

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

    def get_general_news(self, limit: int = 20) -> list[GeneralNewsHeadline]:
        # Confirmed live: /stable/general-news (the docs-suggested path)
        # 404s — the real path is /stable/news/general-latest.
        payload = self._get("/news/general-latest", page=0, limit=limit)
        return parse_general_news(payload)

    def get_latest_insider_trades(self, limit: int = 100) -> list[InsiderTrade]:
        # Confirmed live tonight: /stable/insider-trading/latest,
        # page-based pagination (not a plain limit-only cutoff).
        payload = self._get("/insider-trading/latest", page=0, limit=limit)
        return parse_latest_insider_trades(payload)

    def get_latest_senate_trades(self, limit: int = 100) -> list[PoliticianTrade]:
        # Confirmed live tonight: /stable/senate-latest.
        payload = self._get("/senate-latest", page=0, limit=limit)
        return parse_latest_senate_trades(payload)

    def get_latest_house_trades(self, limit: int = 100) -> list[PoliticianTrade]:
        # Confirmed live tonight: /stable/house-latest.
        payload = self._get("/house-latest", page=0, limit=limit)
        return parse_latest_house_trades(payload)

    def get_daily_bars_full(self, ticker: str, limit: int = 30) -> list[PriceBar]:
        # Confirmed live tonight: /stable/historical-price-eod/full
        # (genuinely different from /light — includes volume, which
        # get_daily_closes' underlying endpoint does not).
        payload = self._get("/historical-price-eod/full", symbol=ticker)
        return parse_eod_full(payload, ticker)[:limit]
