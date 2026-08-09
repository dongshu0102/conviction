"""Pure parsing functions for FMP Phase C payloads (news + EOD history).

Kept free of httpx imports so these are unit-testable in environments
without network libraries — same pattern as marketdata_parsing.py.
Malformed rows are skipped with a warning, never crash the whole parse.
"""
from __future__ import annotations

import logging
from datetime import date, datetime

from src.domain.entities.capital_flow import CapitalFlowSource, InsiderTrade, PoliticianTrade
from src.domain.entities.earnings import EarningsEvent
from src.domain.entities.economic_indicator import EconomicIndicatorReading
from src.domain.entities.etf import EtfProfile
from src.domain.entities.general_news import GeneralNewsHeadline
from src.domain.entities.market_quote import PriceBar
from src.domain.entities.market_risk_premium import MarketRiskPremium
from src.domain.entities.news import NewsArticle
from src.domain.entities.treasury_rates import TreasuryRates

logger = logging.getLogger(__name__)


def _parse_news_datetime(value) -> datetime | None:
    """FMP publishes dates like '2026-07-30 14:05:00' (sometimes ISO with
    'T'). Unparseable dates become None rather than killing the article —
    a headline with no timestamp is still a headline."""
    if not value or not isinstance(value, str):
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    logger.warning("Unparseable news date: %r", value)
    return None


def parse_stock_news(payload, ticker: str) -> list[NewsArticle]:
    if not isinstance(payload, list):
        logger.warning("Unexpected news payload shape for %s: %s", ticker, type(payload))
        return []
    articles: list[NewsArticle] = []
    for i, row in enumerate(payload):
        try:
            title = row.get("title")
            if not title:
                raise ValueError("missing title")
            articles.append(
                NewsArticle(
                    ticker=(row.get("symbol") or ticker).upper(),
                    title=title,
                    published_at=_parse_news_datetime(row.get("publishedDate")),
                    source=row.get("publisher") or row.get("site"),
                    url=row.get("url"),
                    snippet=row.get("text"),
                )
            )
        except (AttributeError, ValueError, TypeError) as exc:
            logger.warning("Skipping malformed news row %d for %s: %s", i, ticker, exc)
    return articles


def parse_eod_light(payload, ticker: str) -> list[PriceBar]:
    """Accepts both the stable flat-list shape ([{date, price|close}...])
    and the legacy wrapped shape ({'historical': [...]}). Returns bars
    most-recent-first, which is how FMP orders them and how the momentum
    computation indexes them."""
    rows = payload
    if isinstance(payload, dict):
        rows = payload.get("historical", [])
    if not isinstance(rows, list):
        logger.warning("Unexpected EOD payload shape for %s: %s", ticker, type(payload))
        return []

    bars: list[PriceBar] = []
    for i, row in enumerate(rows):
        try:
            close = row.get("price", row.get("close"))
            bar_date = datetime.strptime(row["date"], "%Y-%m-%d").date()
            if close is None:
                raise ValueError("missing price/close")
            bars.append(PriceBar(bar_date=bar_date, close=float(close)))
        except (AttributeError, KeyError, ValueError, TypeError) as exc:
            logger.warning("Skipping malformed EOD row %d for %s: %s", i, ticker, exc)
    bars.sort(key=lambda b: b.bar_date, reverse=True)
    return bars


def parse_earnings_calendar(payload) -> list[EarningsEvent]:
    """Parses FMP's earnings-calendar payload into EarningsEvent
    objects. A malformed row (missing symbol/date) is skipped, not
    fatal to the whole batch — same discipline as parse_stock_news."""
    if not isinstance(payload, list):
        logger.warning("Unexpected earnings-calendar payload shape: %s", type(payload))
        return []

    events: list[EarningsEvent] = []
    for i, row in enumerate(payload):
        try:
            symbol = row["symbol"]
            report_date = datetime.strptime(row["date"], "%Y-%m-%d").date()
            events.append(
                EarningsEvent(
                    ticker=symbol.upper(),
                    report_date=report_date,
                    eps_estimated=row.get("epsEstimated"),
                    eps_actual=row.get("epsActual"),
                    revenue_estimated=row.get("revenueEstimated"),
                    revenue_actual=row.get("revenueActual"),
                )
            )
        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            logger.warning("Skipping malformed earnings-calendar row %d: %s", i, exc)
    return events


def parse_treasury_rates(payload):
    """Parses FMP's treasury-rates payload into a TreasuryRates for
    the most recent date — the response is a list ordered most-recent
    first. Every maturity is converted from FMP's raw percentage
    (4.69) to the decimal convention (0.0469) every rate elsewhere in
    this codebase already uses (discount_rate, growth_rate, etc)."""
    if not isinstance(payload, list) or not payload:
        raise ValueError("Empty or malformed treasury-rates payload")

    row = payload[0]

    def _pct(key: str) -> float | None:
        value = row.get(key)
        return value / 100 if value is not None else None

    return TreasuryRates(
        as_of=datetime.strptime(row["date"], "%Y-%m-%d").date(),
        month1=_pct("month1"), month2=_pct("month2"), month3=_pct("month3"),
        month6=_pct("month6"), year1=_pct("year1"), year2=_pct("year2"),
        year3=_pct("year3"), year5=_pct("year5"), year7=_pct("year7"),
        year10=_pct("year10"), year20=_pct("year20"), year30=_pct("year30"),
    )


def parse_economic_indicator(payload) -> list[EconomicIndicatorReading]:
    """Parses FMP's economic-indicators payload — a list of
    {name, date, value} readings, most recent first. Deliberately does
    NOT divide value by 100 the way parse_treasury_rates does: GDP,
    CPI, and unemploymentRate have genuinely different units (dollars,
    an index number, and percentage points respectively), not a
    single shared "rate" convention — the raw value is passed through
    as-is, in whatever unit that specific indicator actually uses.
    A malformed row is skipped, not fatal to the whole batch."""
    if not isinstance(payload, list):
        logger.warning("Unexpected economic-indicators payload shape: %s", type(payload))
        return []

    readings: list[EconomicIndicatorReading] = []
    for i, row in enumerate(payload):
        try:
            readings.append(EconomicIndicatorReading(
                name=row["name"],
                as_of=datetime.strptime(row["date"], "%Y-%m-%d").date(),
                value=float(row["value"]),
            ))
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("Skipping malformed economic-indicator row %d: %s", i, exc)
    return readings


def parse_market_risk_premium(payload, country: str = "United States") -> MarketRiskPremium | None:
    """Parses FMP's market-risk-premium payload — a flat list across
    every country, not keyed by date the way Treasury rates is.
    Returns None if the requested country isn't present, rather than
    raising: a missing country is a normal, expected outcome (the
    dataset's coverage can change), not a parse failure."""
    if not isinstance(payload, list):
        logger.warning("Unexpected market-risk-premium payload shape: %s", type(payload))
        return None

    for row in payload:
        if row.get("country") == country:
            try:
                return MarketRiskPremium(
                    country=row["country"],
                    # Converted to decimal (0.0446), matching the
                    # discount_rate/growth_rate convention used
                    # everywhere else in this codebase — the raw FMP
                    # value is a percentage (4.46), not already decimal.
                    country_risk_premium=float(row["countryRiskPremium"]) / 100,
                    total_equity_risk_premium=float(row["totalEquityRiskPremium"]) / 100,
                )
            except (KeyError, ValueError, TypeError) as exc:
                logger.warning("Malformed market-risk-premium row for %s: %s", country, exc)
                return None
    return None


def parse_etf_info(payload, ticker: str) -> EtfProfile | None:
    """FMP's /etf/info returns a LIST wrapping a single object (same
    list-wrapping convention as other stable endpoints), even for a
    single-symbol request. Missing/malformed data degrades to None
    fields rather than raising — same discipline as every other parser
    here."""
    if not isinstance(payload, list) or not payload:
        logger.warning("Unexpected etf/info payload shape for %s: %s", ticker, type(payload))
        return None

    row = payload[0]
    try:
        name = row["name"]
    except (KeyError, TypeError) as exc:
        logger.warning("Malformed etf/info row for %s: %s", ticker, exc)
        return None

    return EtfProfile(
        ticker=ticker.upper(),
        name=name,
        description=row.get("description"),
        asset_class=row.get("assetClass"),
        domicile=row.get("domicile"),
        expense_ratio=row.get("expenseRatio"),
        aum=row.get("assetsUnderManagement"),
    )


def parse_general_news(payload) -> list[GeneralNewsHeadline]:
    """Real confirmed shape from /stable/news/general-latest: symbol is
    always null (unlike parse_stock_news's payload), publishedDate,
    publisher, title, text, url. Malformed rows skipped, not fatal."""
    if not isinstance(payload, list):
        logger.warning("Unexpected general-news payload shape: %s", type(payload))
        return []

    headlines: list[GeneralNewsHeadline] = []
    for i, row in enumerate(payload):
        try:
            title = row["title"]
        except (KeyError, TypeError) as exc:
            logger.warning("Skipping malformed general-news row %d: %s", i, exc)
            continue
        headlines.append(
            GeneralNewsHeadline(
                title=title,
                published_at=_parse_news_datetime(row.get("publishedDate")),
                publisher=row.get("publisher"),
                url=row.get("url"),
                snippet=row.get("text"),
            )
        )
    return headlines


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def parse_eod_full(payload, ticker: str) -> list[PriceBar]:
    """Real, confirmed shape from /stable/historical-price-eod/full,
    verified directly against the live API tonight: {symbol, date,
    open, high, low, close, volume, change, changePercent, vwap}.
    Deliberately a separate function from parse_eod_light rather than
    a shared one with an "include volume" flag — the momentum
    computation that already depends on parse_eod_light has no reason
    to touch a new code path, and this function's only real job
    (volume) is the one thing that endpoint doesn't provide at all.
    Returns bars most-recent-first, same convention as parse_eod_light."""
    rows = payload
    if isinstance(payload, dict):
        rows = payload.get("historical", [])
    if not isinstance(rows, list):
        logger.warning("Unexpected EOD-full payload shape for %s: %s", ticker, type(payload))
        return []

    bars: list[PriceBar] = []
    for i, row in enumerate(rows):
        try:
            bar_date = datetime.strptime(row["date"], "%Y-%m-%d").date()
            close = float(row["close"])
            volume = float(row["volume"]) if row.get("volume") is not None else None
            bars.append(PriceBar(bar_date=bar_date, close=close, volume=volume))
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("Skipping malformed EOD-full row %d for %s: %s", i, ticker, exc)
            continue
    return bars


def parse_latest_insider_trades(payload) -> list[InsiderTrade]:
    """Real, confirmed shape from /stable/insider-trading/latest,
    verified directly against the live API tonight: symbol, filingDate,
    transactionDate, reportingCik, companyCik, transactionType,
    reportingName, typeOfOwner, acquisitionOrDisposition,
    directOrIndirect, formType, securitiesTransacted, price,
    securityName, url. Most real rows are noise (gifts, exercises,
    conversions) — that filtering happens in capital_flow_math.py, not
    here; this function's only job is a faithful, complete parse.
    A malformed row is skipped, not fatal to the whole batch."""
    if not isinstance(payload, list):
        logger.warning("Unexpected insider-trading/latest payload shape: %s", type(payload))
        return []

    trades: list[InsiderTrade] = []
    for i, row in enumerate(payload):
        try:
            trades.append(
                InsiderTrade(
                    symbol=row["symbol"],
                    filing_date=_parse_date(row["filingDate"]),
                    transaction_date=_parse_date(row["transactionDate"]),
                    reporting_name=row["reportingName"],
                    type_of_owner=row["typeOfOwner"],
                    transaction_type=row["transactionType"],
                    acquisition_or_disposition=row["acquisitionOrDisposition"],
                    securities_transacted=float(row["securitiesTransacted"]),
                    price=float(row["price"]),
                    security_name=row["securityName"],
                    url=row["url"],
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Skipping malformed insider-trading row %d: %s", i, exc)
            continue
    return trades


def _parse_politician_trades(payload, chamber: CapitalFlowSource, source_label: str) -> list[PoliticianTrade]:
    """Shared parser for /stable/senate-latest and /stable/house-latest
    — both confirmed, real shapes are close enough (same core columns)
    to share one function, given each row's chamber is passed in
    explicitly rather than inferred from the data itself."""
    if not isinstance(payload, list):
        logger.warning("Unexpected %s payload shape: %s", source_label, type(payload))
        return []

    trades: list[PoliticianTrade] = []
    for i, row in enumerate(payload):
        try:
            trades.append(
                PoliticianTrade(
                    chamber=chamber,
                    symbol=row["symbol"],
                    disclosure_date=_parse_date(row["disclosureDate"]),
                    transaction_date=_parse_date(row["transactionDate"]),
                    person_name=f"{row['firstName']} {row['lastName']}",
                    office=row["office"],
                    # Confirmed real quirk: House rows can report owner
                    # as an empty string rather than "Self" — passed
                    # through as-is, not silently defaulted to a value
                    # FMP itself didn't report.
                    owner=row.get("owner", ""),
                    asset_description=row["assetDescription"],
                    asset_type=row["assetType"],
                    transaction_type=row["type"],
                    amount_range=row["amount"],
                    link=row["link"],
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Skipping malformed %s row %d: %s", source_label, i, exc)
            continue
    return trades


def parse_latest_senate_trades(payload) -> list[PoliticianTrade]:
    """Real, confirmed shape from /stable/senate-latest, verified
    directly against the live API tonight."""
    return _parse_politician_trades(payload, CapitalFlowSource.SENATE, "senate-latest")


def parse_latest_house_trades(payload) -> list[PoliticianTrade]:
    """Real, confirmed shape from /stable/house-latest, verified
    directly against the live API tonight. Note the confirmed quirk:
    FMP reuses the field name "senateID" even in House rows — not a
    bug to "fix" here, just their real wire format, which this parser
    simply doesn't need (person_name is built from firstName/lastName
    instead)."""
    return _parse_politician_trades(payload, CapitalFlowSource.HOUSE, "house-latest")
