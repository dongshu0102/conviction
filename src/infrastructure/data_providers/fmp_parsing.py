"""Pure parsing functions for FMP Phase C payloads (news + EOD history).

Kept free of httpx imports so these are unit-testable in environments
without network libraries — same pattern as marketdata_parsing.py.
Malformed rows are skipped with a warning, never crash the whole parse.
"""
from __future__ import annotations

import logging
from datetime import date, datetime

from src.domain.entities.market_quote import PriceBar
from src.domain.entities.news import NewsArticle

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
