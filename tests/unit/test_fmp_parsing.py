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


# ---- Earnings calendar ----

from src.infrastructure.data_providers.fmp_parsing import parse_earnings_calendar


def test_parse_earnings_calendar_happy_path() -> None:
    payload = [
        {
            "symbol": "aapl",
            "date": "2026-08-15",
            "epsEstimated": 1.5,
            "epsActual": None,
            "revenueEstimated": 90000000000,
            "revenueActual": None,
        },
    ]
    events = parse_earnings_calendar(payload)
    assert len(events) == 1
    e = events[0]
    assert e.ticker == "AAPL"  # uppercased
    assert e.report_date.isoformat() == "2026-08-15"
    assert e.eps_estimated == 1.5
    assert e.eps_actual is None
    assert e.revenue_estimated == 90000000000


def test_parse_earnings_calendar_skips_malformed_rows() -> None:
    payload = [
        {"symbol": "AAPL"},  # missing date -> skipped
        {"date": "2026-08-15"},  # missing symbol -> skipped
        {"symbol": "MSFT", "date": "not-a-date"},  # bad date format -> skipped
        {"symbol": "NVDA", "date": "2026-08-20"},  # valid, minimal
    ]
    events = parse_earnings_calendar(payload)
    assert len(events) == 1
    assert events[0].ticker == "NVDA"


def test_parse_earnings_calendar_rejects_non_list_payload() -> None:
    assert parse_earnings_calendar({"Error Message": "nope"}) == []


# ---- ETF info ----

from src.infrastructure.data_providers.fmp_parsing import parse_etf_info


def test_parse_etf_info_happy_path_real_spy_shape() -> None:
    # Real response shape confirmed live against FMP — list-wrapped
    # single object, expenseRatio already a percentage figure (0.09
    # means 0.09%, not a fraction).
    payload = [{
        "symbol": "SPY",
        "name": "State Street SPDR S&P 500 ETF",
        "description": "SPY is...",
        "assetClass": "Equity",
        "domicile": "US",
        "expenseRatio": 0.09,
        "assetsUnderManagement": 789063970000,
    }]
    profile = parse_etf_info(payload, "spy")
    assert profile is not None
    assert profile.ticker == "SPY"  # uppercased
    assert profile.name == "State Street SPDR S&P 500 ETF"
    assert profile.asset_class == "Equity"
    assert profile.domicile == "US"
    assert profile.expense_ratio == 0.09
    assert profile.aum == 789063970000


def test_parse_etf_info_missing_name_returns_none() -> None:
    payload = [{"symbol": "XYZ"}]
    assert parse_etf_info(payload, "XYZ") is None


def test_parse_etf_info_empty_list_returns_none() -> None:
    assert parse_etf_info([], "XYZ") is None


def test_parse_etf_info_non_list_payload_returns_none() -> None:
    assert parse_etf_info({"Error Message": "nope"}, "XYZ") is None


# ---- General (non-ticker-specific) news ----

from src.infrastructure.data_providers.fmp_parsing import parse_general_news


def test_parse_general_news_real_confirmed_shape() -> None:
    # Real payload confirmed live against FMP's /stable/news/general-latest.
    payload = [{
        "symbol": None,
        "publishedDate": "2026-08-01 21:00:00",
        "publisher": "WSJ",
        "title": "The Race to Build an American Alternative to Cheap AI From China",
        "site": "wsj.com",
        "text": "Silicon Valley startups are setting up open models...",
        "url": "https://www.wsj.com/tech/ai/example",
    }]
    headlines = parse_general_news(payload)
    assert len(headlines) == 1
    h = headlines[0]
    assert h.title == "The Race to Build an American Alternative to Cheap AI From China"
    assert h.publisher == "WSJ"
    assert h.published_at is not None


def test_parse_general_news_skips_malformed_rows() -> None:
    payload = [{"publisher": "WSJ"}, {"title": "Valid headline"}]  # first missing title
    headlines = parse_general_news(payload)
    assert len(headlines) == 1
    assert headlines[0].title == "Valid headline"


def test_parse_general_news_rejects_non_list_payload() -> None:
    assert parse_general_news({"Error Message": "nope"}) == []


from src.infrastructure.data_providers.fmp_parsing import parse_treasury_rates


def test_parse_treasury_rates_uses_the_most_recent_row_and_converts_to_decimal() -> None:
    # Real payload structure, confirmed directly against the live FMP
    # endpoint before writing this parser.
    payload = [
        {
            "date": "2026-08-06",
            "month1": 3.8, "month2": 3.84, "month3": 3.9, "month6": 3.99,
            "year1": 4.06, "year2": 4.25, "year3": 4.31, "year5": 4.4,
            "year7": 4.53, "year10": 4.69, "year20": 5.22, "year30": 5.22,
        },
        {
            "date": "2026-08-05",
            "month1": 3.77, "month2": 3.84, "month3": 3.89, "month6": 3.98,
            "year1": 4.03, "year2": 4.18, "year3": 4.24, "year5": 4.33,
            "year7": 4.47, "year10": 4.63, "year20": 5.18, "year30": 5.17,
        },
    ]
    result = parse_treasury_rates(payload)

    assert result.as_of.isoformat() == "2026-08-06"
    assert abs(result.year10 - 0.0469) < 1e-9
    assert abs(result.month1 - 0.038) < 1e-9
    # Confirms the older, second row was NOT used.
    assert abs(result.year10 - 0.0463) > 1e-6


def test_parse_treasury_rates_handles_a_null_maturity_gracefully() -> None:
    payload = [{"date": "2026-08-06", "month1": 3.8, "year10": None}]
    result = parse_treasury_rates(payload)
    assert result.year10 is None
    assert result.month1 == 0.038


def test_parse_treasury_rates_raises_on_empty_payload() -> None:
    try:
        parse_treasury_rates([])
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
