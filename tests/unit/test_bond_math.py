from datetime import date

from src.domain.services.bond_math import (
    compute_bond_price,
    compute_current_yield,
    compute_years_to_maturity,
    compute_yield_to_maturity,
)


def test_compute_years_to_maturity_hand_verified() -> None:
    result = compute_years_to_maturity(date(2030, 1, 1), date(2026, 1, 1))
    assert round(result, 1) == 4.0


def test_compute_years_to_maturity_for_a_bond_that_already_matured_is_negative() -> None:
    result = compute_years_to_maturity(date(2020, 1, 1), date(2026, 1, 1))
    assert result < 0


def test_compute_current_yield_hand_verified() -> None:
    """5% coupon at a price of 95 (a real, genuine discount) -> current
    yield = 5/95 = 0.05263... (5.263%, as a decimal, matching the
    established "every rate is a decimal" convention this codebase
    uses everywhere else)."""
    result = compute_current_yield(0.05, 95.0)
    assert round(result, 5) == round(5 / 95, 5)


def test_compute_current_yield_is_none_for_a_non_positive_price() -> None:
    assert compute_current_yield(0.05, 0.0) is None
    assert compute_current_yield(0.05, -10.0) is None


def test_compute_bond_price_at_par_when_ytm_equals_coupon_rate() -> None:
    """A well-known, real bond-math truth: when a bond's real yield to
    maturity exactly equals its own coupon rate, it genuinely, always
    prices at exactly 100 (par), regardless of maturity."""
    price = compute_bond_price(0.05, 0.05, 10.0)
    assert abs(price - 100.0) < 1e-6


def test_compute_bond_price_below_par_when_ytm_exceeds_coupon() -> None:
    price = compute_bond_price(0.06, 0.05, 10.0)
    assert price < 100.0


def test_compute_bond_price_above_par_when_ytm_below_coupon() -> None:
    price = compute_bond_price(0.04, 0.05, 10.0)
    assert price > 100.0


def test_compute_yield_to_maturity_recovers_the_coupon_rate_for_a_genuine_par_bond() -> None:
    ytm = compute_yield_to_maturity(0.05, 100.0, 10.0)
    assert ytm is not None
    assert round(ytm, 4) == 0.0500


def test_compute_yield_to_maturity_is_higher_than_coupon_for_a_real_discount_bond() -> None:
    ytm = compute_yield_to_maturity(0.04, 95.0, 5.0)
    assert ytm is not None
    assert ytm > 0.04


def test_compute_yield_to_maturity_is_lower_than_coupon_for_a_real_premium_bond() -> None:
    ytm = compute_yield_to_maturity(0.06, 105.0, 5.0)
    assert ytm is not None
    assert ytm < 0.06


def test_compute_yield_to_maturity_is_internally_consistent_with_compute_bond_price() -> None:
    """The real, defining relationship: feeding a solved YTM back into
    compute_bond_price must reproduce the original, real price."""
    ytm = compute_yield_to_maturity(0.045, 92.5, 7.0)
    assert ytm is not None
    recovered_price = compute_bond_price(ytm, 0.045, 7.0)
    assert abs(recovered_price - 92.5) < 1e-4


def test_compute_yield_to_maturity_is_honestly_none_for_an_already_matured_bond() -> None:
    assert compute_yield_to_maturity(0.05, 100.0, -1.0) is None
    assert compute_yield_to_maturity(0.05, 100.0, 0.0) is None


def test_compute_yield_to_maturity_is_honestly_none_for_a_non_positive_price() -> None:
    assert compute_yield_to_maturity(0.05, 0.0, 5.0) is None
