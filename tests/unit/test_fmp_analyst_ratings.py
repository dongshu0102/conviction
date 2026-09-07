"""Tests for FinancialModelingPrepProvider.get_analyst_ratings --
mocks self._get directly, matching the established pattern from
test_fmp_screen_market.py.
"""
from __future__ import annotations

from unittest.mock import patch

from src.infrastructure.config import Settings
from src.infrastructure.data_providers.fmp_provider import FinancialModelingPrepProvider

_FAKE_SETTINGS = Settings(fmp_api_key="fake", fmp_base_url="https://fake.test")

# Real, exact shapes confirmed directly against FMP's own live API for AAPL.
_REAL_GRADES_SUMMARY = {
    "symbol": "AAPL", "strongBuy": 1, "buy": 70, "hold": 32, "sell": 9,
    "strongSell": 0, "consensus": "Buy",
}
_REAL_PRICE_TARGET_SUMMARY = {
    "symbol": "AAPL", "lastMonthCount": 2, "lastMonthAvgPriceTarget": 331.83,
    "lastQuarterCount": 17, "lastQuarterAvgPriceTarget": 331.69,
    "lastYearCount": 69, "lastYearAvgPriceTarget": 309.56,
    "allTimeCount": 259, "allTimeAvgPriceTarget": 232.31,
}


def test_combines_real_grades_and_price_target_data_correctly() -> None:
    provider = FinancialModelingPrepProvider(settings=_FAKE_SETTINGS)
    with patch.object(
        provider, "_get", side_effect=[[_REAL_GRADES_SUMMARY], [_REAL_PRICE_TARGET_SUMMARY]],
    ):
        result = provider.get_analyst_ratings("AAPL")

    assert result is not None
    assert result.ticker == "AAPL"
    assert result.strong_buy == 1
    assert result.buy == 70
    assert result.consensus == "Buy"
    assert result.last_quarter_avg_price_target == 331.69
    assert result.total_analysts == 112


def test_returns_honestly_none_when_grades_summary_is_genuinely_empty() -> None:
    """A ticker with no real analyst coverage at all -- honestly None,
    never a fabricated, zeroed-out result."""
    provider = FinancialModelingPrepProvider(settings=_FAKE_SETTINGS)
    with patch.object(provider, "_get", return_value=[]):
        result = provider.get_analyst_ratings("OBSCURETICKER")

    assert result is None


def test_still_returns_grades_data_when_price_targets_are_genuinely_missing() -> None:
    """Grades and price targets are two, real, separate FMP calls --
    a genuine gap in one shouldn't discard real, available data from
    the other."""
    provider = FinancialModelingPrepProvider(settings=_FAKE_SETTINGS)
    with patch.object(provider, "_get", side_effect=[[_REAL_GRADES_SUMMARY], []]):
        result = provider.get_analyst_ratings("AAPL")

    assert result is not None
    assert result.consensus == "Buy"
    assert result.last_month_avg_price_target is None
    assert result.last_month_count == 0
