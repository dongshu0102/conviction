"""Tests for FinancialModelingPrepProvider.get_analyst_ratings --
mocks self._get directly, matching the established pattern from
test_fmp_screen_market.py.

Uses /grades, not /grades-summary: confirmed directly in production
that this app's real FMP account key doesn't have access to
/grades-summary (a genuinely empty result), despite /grades and
/price-target-summary both genuinely working for the exact same
ticker with the exact same key.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import patch

from src.infrastructure.config import Settings
from src.infrastructure.data_providers.fmp_provider import FinancialModelingPrepProvider

_FAKE_SETTINGS = Settings(fmp_api_key="fake", fmp_base_url="https://fake.test")

# Real, exact rows confirmed directly against this app's own, real,
# working production FMP key for AAPL.
_REAL_GRADES = [
    {"symbol": "AAPL", "date": "2026-09-02", "gradingCompany": "DA Davidson",
     "previousGrade": "Neutral", "newGrade": "Neutral", "action": "maintain"},
    {"symbol": "AAPL", "date": "2026-09-02", "gradingCompany": "Morgan Stanley",
     "previousGrade": "Overweight", "newGrade": "Overweight", "action": "maintain"},
]
_REAL_PRICE_TARGET_SUMMARY = [{
    "symbol": "AAPL", "lastMonthCount": 2, "lastMonthAvgPriceTarget": 331.83,
    "lastQuarterCount": 17, "lastQuarterAvgPriceTarget": 331.69,
    "lastYearCount": 69, "lastYearAvgPriceTarget": 309.56,
    "allTimeCount": 259, "allTimeAvgPriceTarget": 232.31,
}]


def test_combines_real_grades_and_price_target_data_correctly() -> None:
    provider = FinancialModelingPrepProvider(settings=_FAKE_SETTINGS)
    with patch.object(provider, "_get", side_effect=[_REAL_GRADES, _REAL_PRICE_TARGET_SUMMARY]):
        result = provider.get_analyst_ratings("AAPL")

    assert result is not None
    assert result.ticker == "AAPL"
    assert len(result.recent_grades) == 2
    assert result.recent_grades[0].grading_company == "DA Davidson"
    assert result.recent_grades[0].date == date(2026, 9, 2)
    assert result.recent_grades[0].action == "maintain"
    assert result.last_quarter_avg_price_target == 331.69


def test_returns_honestly_none_when_both_real_endpoints_are_genuinely_empty() -> None:
    """A ticker with no real analyst coverage at all -- honestly None,
    never a fabricated, empty-but-present result."""
    provider = FinancialModelingPrepProvider(settings=_FAKE_SETTINGS)
    with patch.object(provider, "_get", side_effect=[[], []]):
        result = provider.get_analyst_ratings("OBSCURETICKER")

    assert result is None


def test_still_returns_price_targets_when_grades_are_genuinely_empty() -> None:
    """Grades and price targets are two, real, separate FMP calls --
    a genuine gap in one shouldn't discard real, available data from
    the other."""
    provider = FinancialModelingPrepProvider(settings=_FAKE_SETTINGS)
    with patch.object(provider, "_get", side_effect=[[], _REAL_PRICE_TARGET_SUMMARY]):
        result = provider.get_analyst_ratings("AAPL")

    assert result is not None
    assert result.recent_grades == []
    assert result.last_month_avg_price_target == 331.83


def test_caps_recent_grades_at_a_reasonable_number() -> None:
    """/grades can genuinely return a long, real history -- capped at
    a reasonable, recent window rather than returning everything."""
    many_grades = [
        {"symbol": "AAPL", "date": "2026-01-01", "gradingCompany": f"Firm {i}",
         "previousGrade": "Hold", "newGrade": "Buy", "action": "upgrade"}
        for i in range(50)
    ]
    provider = FinancialModelingPrepProvider(settings=_FAKE_SETTINGS)
    with patch.object(provider, "_get", side_effect=[many_grades, []]):
        result = provider.get_analyst_ratings("AAPL")

    assert result is not None
    assert len(result.recent_grades) == 20
