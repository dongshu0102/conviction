"""Tests for the pure FMP Phase C parsers (news + EOD history)."""
from __future__ import annotations

from datetime import date, datetime

from src.infrastructure.data_providers.fmp_parsing import parse_eod_light, parse_stock_news


def test_parse_stock_news_happy_path() -> None:
    payload = [
        {
            "symbol": "NVDA",
            "publishedDate": "2026-07-30 14:05:00",
            "publisher": "Reuters",
            "title": "Nvidia announces new chip",
            "url": "https://example.com/a",
            "text": "Some snippet.",
        },
    ]
    articles = parse_stock_news(payload, "NVDA")
    assert len(articles) == 1
    a = articles[0]
    assert a.ticker == "NVDA"
    assert a.title == "Nvidia announces new chip"
    assert a.published_at == datetime(2026, 7, 30, 14, 5, 0)
    assert a.source == "Reuters"


def test_parse_stock_news_skips_malformed_and_tolerates_bad_dates() -> None:
    payload = [
        {"symbol": "NVDA"},  # no title -> skipped
        {"title": "Undated headline", "publishedDate": "not-a-date", "site": "Blog"},
    ]
    articles = parse_stock_news(payload, "NVDA")
    assert len(articles) == 1
    assert articles[0].published_at is None  # unparseable date -> None, article kept
    assert articles[0].source == "Blog"  # site fallback when no publisher
    assert articles[0].ticker == "NVDA"  # ticker fallback when no symbol


def test_parse_stock_news_rejects_non_list_payload() -> None:
    assert parse_stock_news({"Error Message": "nope"}, "NVDA") == []


def test_parse_eod_light_flat_shape_sorted_most_recent_first() -> None:
    payload = [
        {"symbol": "NVDA", "date": "2026-07-28", "price": 195.0},
        {"symbol": "NVDA", "date": "2026-07-30", "price": 200.0},
        {"symbol": "NVDA", "date": "2026-07-29", "price": 197.0},
    ]
    bars = parse_eod_light(payload, "NVDA")
    assert [b.close for b in bars] == [200.0, 197.0, 195.0]
    assert bars[0].bar_date == date(2026, 7, 30)


def test_parse_eod_light_wrapped_legacy_shape_and_close_key() -> None:
    payload = {"symbol": "NVDA", "historical": [{"date": "2026-07-30", "close": 200.0}]}
    bars = parse_eod_light(payload, "NVDA")
    assert len(bars) == 1 and bars[0].close == 200.0


def test_parse_eod_light_skips_malformed_rows() -> None:
    payload = [
        {"date": "2026-07-30", "price": 200.0},
        {"date": "bad-date", "price": 1.0},
        {"price": 2.0},  # no date
        {"date": "2026-07-29"},  # no price
    ]
    bars = parse_eod_light(payload, "NVDA")
    assert len(bars) == 1
