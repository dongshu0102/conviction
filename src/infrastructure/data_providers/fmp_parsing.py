"""Pure parsing functions for FMP Phase C payloads (news + EOD history).

Kept free of httpx imports so these are unit-testable in environments
without network libraries — same pattern as marketdata_parsing.py.
Malformed rows are skipped with a warning, never crash the whole parse.
"""
from __future__ import annotations

import logging
from datetime import date, datetime

from src.domain.entities.earnings import EarningsEvent
from src.domain.entities.etf import EtfProfile
from src.domain.entities.general_news import GeneralNewsHeadline
from src.domain.entities.market_quote import PriceBar
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
