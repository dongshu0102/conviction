"""Tests for DCF, reverse DCF, and IRR — every case here was first
verified against a hand-calculated expected value directly, not just
asserted against whatever the code happened to produce."""
from __future__ import annotations

from src.domain.services.valuation_math import (
    DcfAssumptionError,
    compute_comps_valuation,
    compute_dcf,
    compute_irr,
    solve_reverse_dcf,
)


def test_dcf_matches_hand_calculation_when_growth_equals_discount_rate() -> None:
    # When growth_rate == discount_rate, each explicit year's PV
    # equals exactly base_fcf — a clean, hand-verifiable property.
    result = compute_dcf(
        base_fcf=100, growth_rate=0.10, discount_rate=0.10,
        terminal_growth_rate=0.03, years=5, net_debt=0, shares_outstanding=100,
    )
    assert abs(sum(p.present_value for p in result.projections) - 500.0) < 1e-6
    assert abs(result.projections[-1].projected_fcf - 161.051) < 1e-6
    assert abs(result.terminal_value - (161.051 * 1.03 / 0.07)) < 1e-6
    assert abs(result.per_share_value - 19.714) < 0.01


def test_dcf_subtracts_net_debt_before_per_share_value() -> None:
    result = compute_dcf(
        base_fcf=100, growth_rate=0.05, discount_rate=0.10,
        terminal_growth_rate=0.02, years=5, net_debt=500, shares_outstanding=100,
    )
    assert abs(result.equity_value - (result.enterprise_value - 500)) < 1e-9
    assert abs(result.per_share_value - (result.equity_value / 100)) < 1e-9


def test_dcf_per_share_value_is_none_without_shares_outstanding() -> None:
    result = compute_dcf(
        base_fcf=100, growth_rate=0.05, discount_rate=0.10,
        terminal_growth_rate=0.02, years=5, net_debt=0, shares_outstanding=None,
    )
    assert result.per_share_value is None
    assert result.enterprise_value > 0  # the rest of the model still computes


def test_dcf_raises_when_terminal_growth_meets_or_exceeds_discount_rate() -> None:
    try:
        compute_dcf(
            base_fcf=100, growth_rate=0.05, discount_rate=0.05,
            terminal_growth_rate=0.05, years=5,
        )
        raise AssertionError("expected DcfAssumptionError")
    except DcfAssumptionError:
        pass

    try:
        compute_dcf(
            base_fcf=100, growth_rate=0.05, discount_rate=0.03,
            terminal_growth_rate=0.05, years=5,
        )
        raise AssertionError("expected DcfAssumptionError")
    except DcfAssumptionError:
        pass


def test_dcf_raises_for_zero_or_negative_years() -> None:
    try:
        compute_dcf(base_fcf=100, growth_rate=0.05, discount_rate=0.10, terminal_growth_rate=0.02, years=0)
        raise AssertionError("expected DcfAssumptionError")
    except DcfAssumptionError:
        pass


def test_reverse_dcf_recovers_the_growth_rate_that_produced_the_price() -> None:
    forward = compute_dcf(
        base_fcf=100, growth_rate=0.10, discount_rate=0.10,
        terminal_growth_rate=0.03, years=5, net_debt=0, shares_outstanding=100,
    )
    implied = solve_reverse_dcf(
        target_price=forward.per_share_value, base_fcf=100, discount_rate=0.10,
        terminal_growth_rate=0.03, years=5, net_debt=0, shares_outstanding=100,
    )
    assert implied is not None
    assert abs(implied - 0.10) < 1e-4


def test_reverse_dcf_returns_none_for_a_price_outside_any_reasonable_growth_range() -> None:
    # A target price far beyond what even 200% annual growth could
    # justify — should honestly report "no solution," not force a
    # nonsensical extrapolated number.
    implied = solve_reverse_dcf(
        target_price=10_000_000, base_fcf=100, discount_rate=0.10,
        terminal_growth_rate=0.03, years=5, net_debt=0, shares_outstanding=100,
    )
    assert implied is None


def test_irr_simple_single_period_case() -> None:
    # -100 today, +110 in one year: IRR is exactly 10% by construction.
    irr = compute_irr([-100, 110])
    assert irr is not None
    assert abs(irr - 0.10) < 1e-6


def test_irr_multi_year_case_has_near_zero_npv_at_the_solved_rate() -> None:
    cash_flows = [-1000, 200, 200, 200, 200, 1200]
    irr = compute_irr(cash_flows)
    assert irr is not None
    npv_at_irr = sum(cf / (1 + irr) ** i for i, cf in enumerate(cash_flows))
    assert abs(npv_at_irr) < 1e-4


def test_irr_returns_none_when_all_cash_flows_are_positive() -> None:
    # No sign change anywhere in the search range — no real solution.
    assert compute_irr([100, 100, 100]) is None


def test_comps_matches_hand_calculation_for_enterprise_level_multiple() -> None:
    result = compute_comps_valuation(
        peer_multiples=[5.0, 6.0, 7.0, 8.0, 9.0],
        target_metric=500, metric_is_enterprise_level=True,
        net_debt=200, shares_outstanding=100,
    )
    assert result.median_multiple == 7.0
    assert result.implied_enterprise_value == 3500.0
    assert result.implied_equity_value == 3300.0
    assert result.implied_per_share_value == 33.0


def test_comps_equity_level_multiple_does_not_subtract_net_debt() -> None:
    # P/E-style: the multiple already implies equity value directly.
    result = compute_comps_valuation(
        peer_multiples=[15.0, 20.0, 25.0],
        target_metric=100,  # target's own net income
        metric_is_enterprise_level=False,
        net_debt=999,  # deliberately large — must be ignored entirely
        shares_outstanding=50,
    )
    assert result.implied_enterprise_value is None
    assert result.implied_equity_value == 2000.0  # 20.0 median x 100
    assert result.implied_per_share_value == 40.0


def test_comps_uses_median_not_mean_so_one_outlier_does_not_dominate() -> None:
    result = compute_comps_valuation(
        peer_multiples=[5.0, 6.0, 7.0, 8.0, 100.0],  # one wild outlier
        target_metric=500, metric_is_enterprise_level=True,
    )
    assert result.median_multiple == 7.0
    assert result.mean_multiple > 20  # confirms the outlier genuinely skews the mean
    assert result.implied_enterprise_value == 3500.0  # median-based, unaffected by it


def test_comps_raises_with_no_peers() -> None:
    try:
        compute_comps_valuation(peer_multiples=[], target_metric=500, metric_is_enterprise_level=True)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
