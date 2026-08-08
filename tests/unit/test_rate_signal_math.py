"""Tests for read_yield_curve and compute_taylor_rule — every case
verified against a hand-calculated expected value first (see the
verification script run before this file was written)."""
from __future__ import annotations

from src.domain.services.rate_signal_math import (
    DEFAULT_NEUTRAL_REAL_RATE,
    FED_INFLATION_TARGET,
    compute_taylor_rule,
    read_yield_curve,
)


def test_yield_curve_not_inverted_with_real_data() -> None:
    # Real Treasury data confirmed directly against the live FMP
    # endpoint earlier this session.
    curve = read_yield_curve(year2=0.0425, year10=0.0469, month3=0.039)
    assert abs(curve.spread_10y_2y - 0.44) < 1e-6
    assert abs(curve.spread_10y_3m - 0.79) < 1e-6
    assert curve.is_inverted is False
    assert "not inverted" in curve.interpretation


def test_yield_curve_inverted_when_2yr_exceeds_10yr() -> None:
    curve = read_yield_curve(year2=0.05, year10=0.04, month3=0.045)
    assert abs(curve.spread_10y_2y - (-1.0)) < 1e-6
    assert curve.is_inverted is True
    assert "inverted" in curve.interpretation
    assert "not inverted" not in curve.interpretation


def test_yield_curve_inverted_via_3month_spread_alone() -> None:
    """A real, distinct case: 2yr spread positive but 3mo spread
    negative — either one being inverted should flag is_inverted."""
    curve = read_yield_curve(year2=0.04, year10=0.045, month3=0.05)
    assert curve.spread_10y_2y is not None and curve.spread_10y_2y > 0
    assert curve.spread_10y_3m is not None and curve.spread_10y_3m < 0
    assert curve.is_inverted is True


def test_yield_curve_handles_missing_data_gracefully() -> None:
    curve = read_yield_curve(year2=None, year10=None, month3=None)
    assert curve.spread_10y_2y is None
    assert curve.spread_10y_3m is None
    assert curve.is_inverted is False
    assert "Insufficient" in curve.interpretation


def test_taylor_rule_without_output_gap_matches_hand_calculation() -> None:
    # 0.5 (neutral) + 2.3 (inflation) + 0.5*(2.3-2.0) + 0 (no gap) = 2.95
    result = compute_taylor_rule(inflation_rate=2.3)
    assert abs(result.target_rate - 2.95) < 1e-6
    assert result.output_gap_pct is None
    assert result.gap is None


def test_taylor_rule_with_real_output_gap_matches_hand_calculation() -> None:
    # Real GDP/potential-GDP/inflation/fed-funds data confirmed
    # directly against the live FMP endpoint earlier this session.
    result = compute_taylor_rule(
        inflation_rate=2.3, gdp=31422.526, potential_gdp=31029.6201689,
        current_fed_funds_rate=3.88,
    )
    assert abs(result.output_gap_pct - 1.266228297224849) < 1e-6
    assert abs(result.target_rate - 3.5831141486124243) < 1e-6
    assert abs(result.gap - 0.2968858513875756) < 1e-6
    assert "room to cut" in result.interpretation


def test_taylor_rule_reports_room_to_hike_when_current_rate_is_below_target() -> None:
    result = compute_taylor_rule(inflation_rate=4.0, current_fed_funds_rate=2.0)
    assert result.gap is not None and result.gap < 0
    assert "room to hike" in result.interpretation


def test_taylor_rule_reports_no_strong_case_when_gap_is_small() -> None:
    result = compute_taylor_rule(inflation_rate=2.0, current_fed_funds_rate=2.5)
    # target = 0.5 + 2.0 + 0.5*(2.0-2.0) + 0 = 2.5, gap = 2.5-2.5 = 0.0
    assert abs(result.gap) < 0.25
    assert "does not suggest a strong case" in result.interpretation


def test_taylor_rule_respects_custom_neutral_rate_and_target_inflation() -> None:
    default_result = compute_taylor_rule(inflation_rate=2.5)
    custom_result = compute_taylor_rule(inflation_rate=2.5, neutral_real_rate=1.0, target_inflation=2.5)
    assert default_result.target_rate != custom_result.target_rate
    # 1.0 + 2.5 + 0.5*(2.5-2.5) + 0 = 3.5
    assert abs(custom_result.target_rate - 3.5) < 1e-6


def test_module_constants_match_documented_values() -> None:
    assert FED_INFLATION_TARGET == 2.0
    assert DEFAULT_NEUTRAL_REAL_RATE == 0.5
