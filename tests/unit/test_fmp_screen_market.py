"""Tests for FinancialModelingPrepProvider.screen_market -- focused on
the real, critical logic: which filter params get included/excluded,
and the currency-mismatch-avoidance default. Mocks self._get directly
(a simple internal method on the same class) rather than the full
httpx.Client, since the real risk here is the parameter-building logic
itself, not the HTTP mechanics.
"""
from __future__ import annotations

from unittest.mock import patch

from src.infrastructure.config import Settings
from src.infrastructure.data_providers.fmp_provider import FinancialModelingPrepProvider

_FAKE_SETTINGS = Settings(fmp_api_key="fake", fmp_base_url="https://fake.test")

# A REAL, exact shape of what FMP's own /company-screener endpoint
# genuinely returns -- confirmed directly against their live API.
_REAL_SCREENER_ROW = {
    "symbol": "AAPL", "companyName": "Apple Inc.", "marketCap": 4699513299320,
    "sector": "Technology", "industry": "Consumer Electronics", "beta": 1.085,
    "price": 319.97, "lastAnnualDividend": 1.06, "volume": 39606884,
    "exchange": "NASDAQ Global Select", "exchangeShortName": "NASDAQ", "country": "US",
}


def test_parses_a_real_screener_row_correctly() -> None:
    provider = FinancialModelingPrepProvider(settings=_FAKE_SETTINGS)
    with patch.object(provider, "_get", return_value=[_REAL_SCREENER_ROW]) as mock_get:
        results = provider.screen_market(sector="Technology")

    assert len(results) == 1
    r = results[0]
    assert r.ticker == "AAPL"
    assert r.market_cap == 4699513299320
    assert r.beta == 1.085
    assert r.exchange == "NASDAQ"  # exchangeShortName, not the long-form exchange name


def test_only_includes_explicitly_given_filter_params() -> None:
    provider = FinancialModelingPrepProvider(settings=_FAKE_SETTINGS)
    with patch.object(provider, "_get", return_value=[]) as mock_get:
        provider.screen_market(sector="Technology", market_cap_more_than=10_000_000_000)

    call_kwargs = mock_get.call_args.kwargs
    assert call_kwargs.get("sector") == "Technology"
    assert call_kwargs.get("marketCapMoreThan") == 10_000_000_000
    # Never-given filters must be genuinely absent, not sent as None or 0.
    assert "industry" not in call_kwargs
    assert "priceMoreThan" not in call_kwargs
    assert "betaMoreThan" not in call_kwargs


def test_country_us_without_an_explicit_exchange_defaults_to_the_real_major_us_exchanges() -> None:
    """The real, confirmed currency-mismatch gotcha: country="US" alone
    genuinely includes foreign-exchange CEDEAR/ADR listings priced in a
    different local currency (confirmed directly against real, live
    FMP data for AMD's own Buenos Aires listing)."""
    provider = FinancialModelingPrepProvider(settings=_FAKE_SETTINGS)
    with patch.object(provider, "_get", return_value=[]) as mock_get:
        provider.screen_market(country="US")

    assert mock_get.call_args.kwargs.get("exchange") == "NASDAQ,NYSE,AMEX"


def test_an_explicit_exchange_is_never_overridden_even_with_country_us() -> None:
    """The caller's own, explicit exchange choice is always honored --
    the currency-mismatch default only fills in when nothing was given."""
    provider = FinancialModelingPrepProvider(settings=_FAKE_SETTINGS)
    with patch.object(provider, "_get", return_value=[]) as mock_get:
        provider.screen_market(country="US", exchange="NYSE")

    assert mock_get.call_args.kwargs.get("exchange") == "NYSE"


def test_no_exchange_default_is_applied_without_country_us() -> None:
    """The currency-mismatch default is specifically scoped to
    country="US" -- it must not fire for a query with no country filter
    at all, or a different country."""
    provider = FinancialModelingPrepProvider(settings=_FAKE_SETTINGS)
    with patch.object(provider, "_get", return_value=[]) as mock_get:
        provider.screen_market(sector="Technology")

    assert "exchange" not in mock_get.call_args.kwargs
