"""Pure functions for DCF, reverse DCF, and IRR.

Kept free of any repository/provider imports — same principle as
factor_math.py and portfolio_risk_math.py: this is arithmetic with an
exact right answer given its inputs, so it has to be hand-verifiable
and unit-testable in isolation, independent of how those inputs get
fetched or estimated.

Deliberately does NOT attempt to compute a "true" WACC from beta/CAPM —
discount rate is always an explicit input, not a hidden, silently
estimated one. Every assumption a DCF depends on (growth rate, discount
rate, terminal growth rate) is a parameter here, never a default buried
inside the math itself. Reverse DCF exists specifically so a person
isn't forced to just trust an assumption — it turns "what's this worth
given growth rate X" into "what growth rate is the current price
already assuming," which is a much easier assumption to sanity-check.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DcfYearProjection:
    year: int
    projected_fcf: float
    present_value: float


@dataclass(frozen=True, slots=True)
class DcfResult:
    enterprise_value: float
    equity_value: float
    per_share_value: float | None
    terminal_value: float
    present_value_of_terminal_value: float
    projections: list[DcfYearProjection]


class DcfAssumptionError(ValueError):
    """Raised when the supplied assumptions make the model
    mathematically undefined — e.g. terminal growth at or above the
    discount rate blows up the Gordon Growth formula. This is a real
    constraint of the model, not an implementation limitation: a
    perpetuity literally has no finite value once growth catches up to
    the discount rate."""


def compute_dcf(
    base_fcf: float,
    growth_rate: float,
    discount_rate: float,
    terminal_growth_rate: float,
    years: int,
    net_debt: float = 0.0,
    shares_outstanding: float | None = None,
) -> DcfResult:
    """Standard multi-year DCF with a Gordon Growth terminal value.

    base_fcf: most recent actual free cash flow — the starting point
    every projected year compounds from.
    growth_rate: constant annual FCF growth assumed for the explicit
    forecast window (years). A single rate, not a declining schedule —
    keeps the model's sensitivity to this one number visible rather
    than hidden inside a more elaborate curve.
    discount_rate: the rate future cash flows get discounted back at.
    Supplied directly — this function never estimates WACC itself.
    terminal_growth_rate: the perpetual growth rate assumed forever
    after the explicit forecast window. Must be strictly less than
    discount_rate, or the terminal value is mathematically undefined.
    """
    if discount_rate <= terminal_growth_rate:
        raise DcfAssumptionError(
            f"discount_rate ({discount_rate}) must exceed terminal_growth_rate "
            f"({terminal_growth_rate}) — otherwise the terminal value is infinite."
        )
    if years < 1:
        raise DcfAssumptionError("years must be at least 1.")

    projections: list[DcfYearProjection] = []
    pv_sum = 0.0
    fcf = base_fcf
    for year in range(1, years + 1):
        fcf = fcf * (1 + growth_rate)
        pv = fcf / ((1 + discount_rate) ** year)
        projections.append(DcfYearProjection(year=year, projected_fcf=fcf, present_value=pv))
        pv_sum += pv

    final_year_fcf = projections[-1].projected_fcf
    terminal_value = (
        final_year_fcf * (1 + terminal_growth_rate) / (discount_rate - terminal_growth_rate)
    )
    pv_terminal_value = terminal_value / ((1 + discount_rate) ** years)

    enterprise_value = pv_sum + pv_terminal_value
    equity_value = enterprise_value - net_debt
    per_share_value = (
        equity_value / shares_outstanding
        if shares_outstanding is not None and shares_outstanding > 0
        else None
    )

    return DcfResult(
        enterprise_value=enterprise_value,
        equity_value=equity_value,
        per_share_value=per_share_value,
        terminal_value=terminal_value,
        present_value_of_terminal_value=pv_terminal_value,
        projections=projections,
    )


def solve_reverse_dcf(
    target_price: float,
    base_fcf: float,
    discount_rate: float,
    terminal_growth_rate: float,
    years: int,
    net_debt: float,
    shares_outstanding: float,
    low: float = -0.5,
    high: float = 2.0,
    tolerance: float = 1e-6,
    max_iterations: int = 200,
) -> float | None:
    """Binary search for the constant growth_rate that makes
    compute_dcf's per_share_value equal target_price — "what growth
    rate is the current price already assuming?"

    Returns None, honestly, if no growth rate in [low, high] (default
    -50% to +200% annual) produces that price — rather than returning
    a number outside any economically meaningful range. per_share_value
    is monotonically increasing in growth_rate ONLY when base_fcf is
    positive (holding every other assumption fixed) — with a positive
    base, a higher growth rate compounds every projected year's cash
    flow upward. With a NEGATIVE base_fcf this inverts: a higher growth
    rate makes an already-negative number more negative, so
    per_share_value actually DECREASES as growth_rate increases —
    confirmed directly, not assumed: base_fcf=-100 with growth_rate
    0.1/0.3/0.5/1.0 produced per_share_value -13.75/-16.25/-18.75/-25.00,
    monotonically decreasing. Binary search over an inverted function
    would either wrongly return None for valid inputs or silently
    converge to the wrong rate, so this is refused outright rather than
    risking either.
    """
    if base_fcf <= 0:
        raise DcfAssumptionError(
            f"solve_reverse_dcf requires a positive base_fcf ({base_fcf} given) — "
            "the growth-rate search relies on per_share_value increasing as "
            "growth_rate increases, which only holds for a positive base; a "
            "negative base_fcf inverts this and the search would silently "
            "converge to a meaningless answer, not a real, valid growth rate."
        )

    def per_share_at(rate: float) -> float | None:
        result = compute_dcf(
            base_fcf, rate, discount_rate, terminal_growth_rate, years,
            net_debt, shares_outstanding,
        )
        return result.per_share_value

    lo_val = per_share_at(low)
    hi_val = per_share_at(high)
    if lo_val is None or hi_val is None:
        return None
    if not (lo_val <= target_price <= hi_val):
        return None

    for _ in range(max_iterations):
        mid = (low + high) / 2
        mid_val = per_share_at(mid)
        if mid_val is None:
            return None
        if abs(mid_val - target_price) < tolerance * max(1.0, abs(target_price)):
            return mid
        if mid_val < target_price:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def compute_irr(
    cash_flows: list[float],
    low: float = -0.99,
    high: float = 10.0,
    tolerance: float = 1e-7,
    max_iterations: int = 200,
) -> float | None:
    """Solves for the discount rate that makes the NPV of cash_flows
    exactly zero — cash_flows[0] is the initial (negative) outlay,
    everything after is the return sequence. Bisection over the given
    rate range, not Newton-Raphson: bisection is guaranteed to converge
    once the NPV function changes sign across the range, which
    Newton-Raphson isn't for an arbitrary starting guess. Returns None,
    honestly, if NPV doesn't change sign anywhere in [low, high] — no
    real solution exists in a sane range, rather than forcing a number.
    """
    def npv(rate: float) -> float:
        return sum(cf / ((1 + rate) ** i) for i, cf in enumerate(cash_flows))

    npv_low = npv(low)
    npv_high = npv(high)
    if npv_low == 0:
        return low
    if npv_high == 0:
        return high
    if (npv_low > 0) == (npv_high > 0):
        return None

    for _ in range(max_iterations):
        mid = (low + high) / 2
        npv_mid = npv(mid)
        if abs(npv_mid) < tolerance:
            return mid
        if (npv_mid > 0) == (npv_low > 0):
            low = mid
        else:
            high = mid
    return (low + high) / 2


@dataclass(frozen=True, slots=True)
class CompsResult:
    peer_count: int
    median_multiple: float
    mean_multiple: float
    implied_enterprise_value: float | None
    implied_equity_value: float | None
    implied_per_share_value: float | None


def compute_comps_valuation(
    peer_multiples: list[float],
    target_metric: float,
    metric_is_enterprise_level: bool,
    net_debt: float = 0.0,
    shares_outstanding: float | None = None,
) -> CompsResult:
    """Applies a peer group's multiple to the target company's own
    metric — e.g. peer group's median EV/Revenue x target's revenue =
    implied enterprise value.

    peer_multiples: each peer's own multiple (already computed
    per-company, e.g. by the existing ComputeValuationUseCase) — this
    function only aggregates and applies them, it doesn't compute a
    single company's multiple itself.
    target_metric: the target company's own value for whatever metric
    the multiple is expressed against (revenue for EV/Revenue, EBITDA
    for EV/EBITDA, net income for P/E, etc).
    metric_is_enterprise_level: True for EV-based multiples (EV/Revenue,
    EV/EBITDA) — the result is an enterprise value needing net debt
    subtracted to reach equity value. False for equity-level multiples
    (P/E) — the multiple already implies equity value directly, and
    net_debt is not applied.

    Uses the median as the primary implied value — a small peer set is
    much more sensitive to one clear outlier under a mean than a
    median, and comps sets in practice are rarely large.
    """
    if not peer_multiples:
        raise ValueError("compute_comps_valuation requires at least one peer multiple.")

    sorted_multiples = sorted(peer_multiples)
    n = len(sorted_multiples)
    median = (
        sorted_multiples[n // 2]
        if n % 2 == 1
        else (sorted_multiples[n // 2 - 1] + sorted_multiples[n // 2]) / 2
    )
    mean = sum(sorted_multiples) / n

    implied_value = median * target_metric

    if metric_is_enterprise_level:
        implied_enterprise_value = implied_value
        implied_equity_value = implied_enterprise_value - net_debt
    else:
        implied_enterprise_value = None
        implied_equity_value = implied_value

    implied_per_share_value = (
        implied_equity_value / shares_outstanding
        if shares_outstanding is not None and shares_outstanding > 0
        else None
    )

    return CompsResult(
        peer_count=n,
        median_multiple=median,
        mean_multiple=mean,
        implied_enterprise_value=implied_enterprise_value,
        implied_equity_value=implied_equity_value,
        implied_per_share_value=implied_per_share_value,
    )
