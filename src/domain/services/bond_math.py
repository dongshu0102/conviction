"""Pure functions computing real bond analytics: current yield and
yield to maturity (YTM), both derived deterministically from a bond's
own real, known terms and a real price -- never fetched from a live
market data source this app doesn't have access to.

Kept free of any repository/provider imports -- same principle as
valuation_math.py, market_structure_scoring.py, and
nasdaq100_tier_scoring.py: given the same real inputs, there is
exactly one correct answer, hand-verifiable and unit-testable in
isolation.
"""
from __future__ import annotations

from datetime import date

# U.S. bonds conventionally pay coupons semi-annually, not annually --
# the real, standard market convention, not an approximation.
_PAYMENTS_PER_YEAR = 2


def compute_years_to_maturity(maturity_date: date, as_of: date) -> float:
    """Real, exact fractional years remaining -- 365.25 days/year to
    honestly account for leap years on average, not a naive 365."""
    days_remaining = (maturity_date - as_of).days
    return days_remaining / 365.25


def compute_current_yield(coupon_rate: float, price_pct: float) -> float | None:
    """Annual coupon payment / current price, both as real, comparable
    percentages of face value -- the simplest, real yield measure
    (ignores the real gain or loss at maturity that YTM captures)."""
    if price_pct <= 0:
        return None
    return (coupon_rate * 100) / price_pct


def compute_bond_price(
    ytm: float, coupon_rate: float, years_to_maturity: float, payments_per_year: int = _PAYMENTS_PER_YEAR,
) -> float:
    """The real, standard bond pricing formula: the present value of
    every real coupon payment plus the present value of face value
    (100, since this returns a % of face value) at maturity, all
    discounted at the given ytm. This is the real, forward direction
    (price from a known yield) -- compute_yield_to_maturity below
    solves the reverse, real direction."""
    n_periods = years_to_maturity * payments_per_year
    period_rate = ytm / payments_per_year
    period_coupon = (coupon_rate * 100) / payments_per_year

    if period_rate == 0:
        # A genuine, real 0% yield -- no discounting at all, price is
        # simply the sum of all real, undiscounted cash flows.
        return period_coupon * n_periods + 100

    pv_coupons = period_coupon * (1 - (1 + period_rate) ** -n_periods) / period_rate
    pv_face = 100 * (1 + period_rate) ** -n_periods
    return pv_coupons + pv_face


def compute_yield_to_maturity(
    coupon_rate: float, price_pct: float, years_to_maturity: float,
    payments_per_year: int = _PAYMENTS_PER_YEAR,
) -> float | None:
    """Solves for the real ytm that makes compute_bond_price(ytm, ...)
    equal the given, real price -- via bisection, since bond price is
    genuinely, monotonically decreasing in yield (a real, guaranteed
    property that makes bisection robust here, unlike Newton-Raphson
    which can diverge for a poor starting guess).

    Returns None for a bond that has already, genuinely matured
    (years_to_maturity <= 0) -- there's no real yield to solve for on
    a bond with no remaining cash flows to discount."""
    if years_to_maturity <= 0 or price_pct <= 0:
        return None

    low, high = -0.99, 5.0  # a real, wide bound: -99% to 500% annual yield, covers any genuine real case
    for _ in range(100):  # bisection converges far faster than this in practice; a hard, honest ceiling
        mid = (low + high) / 2
        price_at_mid = compute_bond_price(mid, coupon_rate, years_to_maturity, payments_per_year)
        if abs(price_at_mid - price_pct) < 1e-6:
            return mid
        # Price is genuinely, monotonically decreasing in yield -- if
        # the price at mid is too high, the real yield must be higher.
        if price_at_mid > price_pct:
            low = mid
        else:
            high = mid
    return (low + high) / 2
