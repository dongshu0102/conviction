"""Tests for MarketData.app's stock candles/bulk quotes response
parsing, using real excerpts from their documented sample responses.

Imports the pure parsing functions directly, not the provider class --
same reasoning as test_marketdata_app_provider.py: the provider
module imports httpx, the parsing logic doesn't, and the parsing
logic is where the real risk (wire-format bugs) lives.
"""
from __future__ import annotations

from datetime import datetime, timezone

from src.infrastructure.data_providers.marketdata_stock_parsing import (
    parse_bulk_quotes_response,
    parse_candles_response,
)

# A REAL, exact example from MarketData.app's own documented sample
# response for the candles endpoint -- exact field names, exact
# columnar shape, exact values, taken directly from their docs.
_REAL_CANDLES_RESPONSE = {
    "s": "ok",
    "o": [221.03, 218.55, 220],
    "h": [222.49, 221.5, 220.94],
    "l": [217.19, 217.1402, 218.83],
    "c": [217.68, 221.03, 219.89],
    "t": [1569297600, 1569384000, 1569470400],
    "v": [33463820, 24018876, 20730608],
}

# A REAL, exact example from MarketData.app's own documented sample
# response for the (single-symbol, multi-ticker) quotes endpoint --
# used here as the basis for bulk quotes, per the honest confidence
# note in marketdata_stock_parsing.py's own module docstring.
_REAL_QUOTES_RESPONSE = {
    "s": "ok",
    "symbol": ["AAPL", "MSFT"],
    "ask": [278.02, 479.45],
    "askSize": [100, 40],
    "bid": [277.97, 479.37],
    "bidSize": [100, 40],
    "mid": [277.995, 479.41],
    "last": [278.0188, 479.42],
    "change": [-0.0112, -4.05],
    "changepct": [0.0, -0.0084],
    "volume": [4964676, 3581398],
    "updated": [1765552906, 1765552906],
}


def test_parse_candles_response_hand_verified_against_the_real_documented_example() -> None:
    candles = parse_candles_response("AAPL", _REAL_CANDLES_RESPONSE)

    assert len(candles) == 3
    first = candles[0]
    assert first.ticker == "AAPL"
    assert first.open == 221.03
    assert first.high == 222.49
    assert first.low == 217.19
    assert first.close == 217.68
    assert first.volume == 33463820
    assert first.timestamp == datetime.fromtimestamp(1569297600, tz=timezone.utc)


def test_parse_candles_response_returns_honestly_empty_for_no_data_status() -> None:
    assert parse_candles_response("XXXX", {"s": "no_data"}) == []


def test_parse_candles_response_skips_a_malformed_candle_without_failing_the_whole_batch() -> None:
    malformed = {
        "s": "ok",
        "o": [221.03, None],  # a real, malformed row (missing required fields entirely)
        "h": [222.49],
        "l": [217.19],
        "c": [217.68],
        "t": [1569297600, 1569384000],
        "v": [33463820],
    }
    candles = parse_candles_response("AAPL", malformed)
    assert len(candles) == 1  # the first, well-formed candle survives; the malformed one is skipped


def test_parse_bulk_quotes_response_hand_verified_against_the_real_documented_example() -> None:
    quotes = parse_bulk_quotes_response(_REAL_QUOTES_RESPONSE)

    assert len(quotes) == 2
    assert quotes[0].ticker == "AAPL"
    assert quotes[0].price == 277.995
    assert quotes[1].ticker == "MSFT"
    assert quotes[1].price == 479.41
    assert quotes[0].as_of == datetime.fromtimestamp(1765552906, tz=timezone.utc)


def test_parse_bulk_quotes_response_returns_honestly_empty_for_no_data_status() -> None:
    assert parse_bulk_quotes_response({"s": "no_data"}) == []


def test_parse_bulk_quotes_response_omits_a_genuinely_missing_quote_rather_than_fabricating_a_price() -> None:
    partial = {
        "s": "ok", "symbol": ["AAPL", "BADTICKER"],
        "mid": [277.995, None], "updated": [1765552906, 1765552906],
    }
    quotes = parse_bulk_quotes_response(partial)
    assert len(quotes) == 1
    assert quotes[0].ticker == "AAPL"
