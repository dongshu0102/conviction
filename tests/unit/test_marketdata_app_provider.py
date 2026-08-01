"""Tests for MarketData.app's response parsing, using a real trimmed
excerpt from their documented sample response.

Imports the pure parsing function directly, not the provider class —
the provider class's module imports httpx, which isn't always
installed in every environment this test might run in; the parsing
logic itself has no such dependency, and it's the part with real risk
(wire-format bugs), not the HTTP mechanics.
"""
from __future__ import annotations

from datetime import date

from src.infrastructure.data_providers.marketdata_parsing import parse_option_chain_response

# This is a REAL, trimmed excerpt (2 contracts) from MarketData.app's
# own documented sample response — exact field names, exact columnar
# shape, taken directly from their API docs, not invented. Verifies
# our parser handles their real wire format correctly.
_REAL_SAMPLE_RESPONSE = {
    "s": "ok",
    "optionSymbol": ["AAPL230616C00150000", "AAPL230616P00150000"],
    "underlying": ["AAPL", "AAPL"],
    "expiration": [1686945600, 1686945600],  # unix timestamp, real value from their docs
    "side": ["call", "put"],
    "strike": [150, 150],
    "bid": [25.7, 0.11],
    "ask": [26.9, 0.12],
    "mid": [26.3, 0.115],
    "last": [25.95, 0.11],
    "volume": [207, 135],
    "openInterest": [33003, 40858],
    "underlyingPrice": [175.13, 175.13],
    "iv": [0.331, 0.469],
    "delta": [0.99, -0.151],
    "gamma": [0.002, 0.021],
    "theta": [-0.027, -0.019],
    "vega": [0.012, 0.068],
    "updated": [1684702875, 1684702875],
}


def test_parses_real_documented_response_shape_correctly() -> None:
    quotes = parse_option_chain_response(_REAL_SAMPLE_RESPONSE)

    assert len(quotes) == 2

    call = quotes[0]
    assert call.contract.underlying_ticker == "AAPL"
    assert call.contract.strike == 150
    assert call.contract.option_type == "call"
    assert call.contract.expiration == date(2023, 6, 16)
    assert call.delta == 0.99
    assert call.gamma == 0.002
    assert call.implied_volatility == 0.331
    assert call.open_interest == 33003

    put = quotes[1]
    assert put.contract.option_type == "put"
    assert put.delta == -0.151  # puts have negative delta — correctly preserved, not clamped


def test_no_data_status_returns_empty_list_not_error() -> None:
    quotes = parse_option_chain_response({"s": "no_data"})

    assert quotes == []


def test_malformed_contract_is_skipped_not_fatal() -> None:
    """One bad index in a chain of hundreds shouldn't crash the whole
    parse — the malformed contract is skipped, the rest still parse."""
    broken_response = dict(_REAL_SAMPLE_RESPONSE)
    broken_response["underlying"] = ["AAPL"]  # deliberately shorter than "strike" (length 2)

    quotes = parse_option_chain_response(broken_response)

    # First contract parses fine (underlying[0] exists); second index
    # raises IndexError on underlying[1] and gets skipped.
    assert len(quotes) == 1
