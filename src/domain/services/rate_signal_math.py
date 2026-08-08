"""Pure functions for reading rate-direction signals out of real macro
data: yield curve inversion and the Taylor Rule.

Kept free of any repository/provider imports — same principle as
valuation_math.py, factor_math.py, and portfolio_risk_math.py: this is
arithmetic with an exact right answer given its inputs, hand-verifiable
and unit-testable in isolation, independent of how those inputs get
fetched.

Neither function predicts anything. A yield curve inversion is a real,
widely-cited historical recession signal, not a certainty. The Taylor
Rule is a real, standard economic formula, but it is one input
professional economists weigh alongside others — not a forecast, and
not what the Fed is bound to do. Every constant either function relies
on (r*, the 2% inflation target) is an explicit, named parameter with
a sane default drawn from real, cited conventions — never a silently
buried assumption.
"""
from __future__ import annotations

from dataclasses import dataclass

# The Fed's own stated long-run inflation target — not this module's
# opinion, an explicit, publicly stated policy number.
FED_INFLATION_TARGET = 2.0

# A standard, widely-cited long-run estimate of the neutral real
# interest rate ("r-star") — the rate that neither stimulates nor
# restricts growth. Real-world estimates commonly range roughly
# 0.5%-1.0%; this uses the low end of that range as an explicit,
# named default, never a hidden guess. Always overridable.
DEFAULT_NEUTRAL_REAL_RATE = 0.5


@dataclass(frozen=True, slots=True)
class YieldCurveReading:
    spread_10y_2y: float | None
    spread_10y_3m: float | None
    is_inverted: bool
    interpretation: str


def read_yield_curve(
    year2: float | None, year10: float | None, month3: float | None,
) -> YieldCurveReading:
    """Reads the two most commonly cited yield-curve spreads (10yr-2yr,
    the more media-cited one, and 10yr-3mo, the NY Fed's own preferred
    recession-probability input) and reports whether either is
    inverted. Inputs are decimal rates (0.0469), matching the
    TreasuryRates convention used everywhere else in this codebase —
    the spread itself is returned in percentage points (e.g. -0.25 for
    a quarter-point inversion), matching how spreads are conventionally
    quoted, not as a raw decimal.
    """
    spread_10y_2y = None
    spread_10y_3m = None
    if year10 is not None and year2 is not None:
        spread_10y_2y = (year10 - year2) * 100
    if year10 is not None and month3 is not None:
        spread_10y_3m = (year10 - month3) * 100

    is_inverted = (spread_10y_2y is not None and spread_10y_2y < 0) or (
        spread_10y_3m is not None and spread_10y_3m < 0
    )

    if spread_10y_2y is None and spread_10y_3m is None:
        interpretation = "Insufficient yield data to read the curve."
    elif is_inverted:
        interpretation = (
            "The yield curve is inverted — short-term yields exceed "
            "long-term yields. This has historically preceded most US "
            "recessions, though with a lag that has varied widely (roughly "
            "6 to 24 months) and it is not a guarantee."
        )
    else:
        interpretation = (
            "The yield curve is not inverted (normal, upward-sloping) — "
            "the market is not currently pricing in near-term recession risk "
            "through this specific signal."
        )

    return YieldCurveReading(
        spread_10y_2y=spread_10y_2y, spread_10y_3m=spread_10y_3m,
        is_inverted=is_inverted, interpretation=interpretation,
    )


@dataclass(frozen=True, slots=True)
class TaylorRuleResult:
    target_rate: float
    current_rate: float | None
    gap: float | None
    inflation_rate: float
    output_gap_pct: float | None
    interpretation: str


def compute_taylor_rule(
    inflation_rate: float,
    gdp: float | None = None,
    potential_gdp: float | None = None,
    current_fed_funds_rate: float | None = None,
    neutral_real_rate: float = DEFAULT_NEUTRAL_REAL_RATE,
    target_inflation: float = FED_INFLATION_TARGET,
) -> TaylorRuleResult:
    """target_rate = neutral_real_rate + inflation
                    + 0.5*(inflation - target_inflation)
                    + 0.5*(output_gap_pct)

    All rate inputs are percentage points (2.3 for 2.3%), matching how
    FMP's own inflationRate/federalFunds indicators are reported — NOT
    the decimal convention (0.023) used for discount_rate/growth_rate
    elsewhere in this codebase, since those are genuinely different
    kinds of inputs (macro indicator readings vs computed financial
    rates). output_gap is only computed when both gdp and
    potential_gdp are supplied; when either is missing, that term is
    treated as zero (a neutral assumption, not a hidden guess) and
    output_gap_pct is reported as None so the caller knows it was
    excluded, not that it was computed and found to be zero.
    """
    output_gap_pct = None
    output_gap_term = 0.0
    if gdp is not None and potential_gdp is not None and potential_gdp != 0:
        output_gap_pct = (gdp - potential_gdp) / potential_gdp * 100
        output_gap_term = 0.5 * output_gap_pct

    target_rate = (
        neutral_real_rate + inflation_rate
        + 0.5 * (inflation_rate - target_inflation)
        + output_gap_term
    )

    gap = None
    if current_fed_funds_rate is not None:
        gap = current_fed_funds_rate - target_rate

    if gap is None:
        interpretation = (
            f"Taylor Rule implies a target rate of {target_rate:.2f}%. "
            "Current fed funds rate not supplied, so no comparison is available."
        )
    elif abs(gap) < 0.25:
        interpretation = (
            f"Taylor Rule implies a target rate of {target_rate:.2f}%, "
            f"close to the current {current_fed_funds_rate:.2f}% — the formula "
            "does not suggest a strong case for a near-term move either way."
        )
    elif gap > 0:
        interpretation = (
            f"Taylor Rule implies a target rate of {target_rate:.2f}%, "
            f"below the current {current_fed_funds_rate:.2f}% — the formula "
            "suggests room to cut, all else being the standard assumptions "
            "this rule makes, not a prediction of what the Fed will do."
        )
    else:
        interpretation = (
            f"Taylor Rule implies a target rate of {target_rate:.2f}%, "
            f"above the current {current_fed_funds_rate:.2f}% — the formula "
            "suggests room to hike, all else being the standard assumptions "
            "this rule makes, not a prediction of what the Fed will do."
        )

    return TaylorRuleResult(
        target_rate=target_rate, current_rate=current_fed_funds_rate, gap=gap,
        inflation_rate=inflation_rate, output_gap_pct=output_gap_pct,
        interpretation=interpretation,
    )
