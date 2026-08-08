"""Pure function for computing the Sahm Rule — a real, established
recession indicator created by economist Claudia Sahm.

Kept free of any repository/provider imports — same principle as
valuation_math.py, factor_math.py, rate_signal_math.py, and
portfolio_risk_math.py: this is arithmetic with an exact right answer
given its inputs, hand-verifiable and unit-testable in isolation,
independent of how those inputs get fetched.

The rule: take the 3-month moving average of the national unemployment
rate, and compare it against the minimum that 3-month average has been
over the trailing 12 months. If the current average is at least 0.50
percentage points above that trailing minimum, the rule triggers —
historically, a real, fairly reliable early signal that a recession is
already underway. Genuinely different in kind from the yield curve
(a market-pricing signal) and the Taylor Rule (a policy-formula
signal): this one is a real-economy, backward-looking labor-market
signal, not a market expectation or a policy prescription. Like the
other two, it does not predict anything on its own — it is one more
real, standard tool, not a forecast.

Needs a real 3-month-average-vs-12-month-minimum window, which needs
at least 15 months of monthly unemployment readings to compute at all
(3 months to seed the very first 3-month average, plus a further 12
months to have a real trailing window to compare it against). This is
deliberately never approximated with less data than that — an
under-provisioned calculation would produce a number that looks real
but isn't backed by what the rule actually requires.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

# The threshold Claudia Sahm's own original research established —
# not this module's opinion, the rule's actual, published definition.
SAHM_RULE_TRIGGER_THRESHOLD = 0.50

# The rule needs 3 months to seed its first moving average, plus a
# further 12 months of that average's own history to compare against.
MIN_MONTHS_OF_DATA_REQUIRED = 15


@dataclass(frozen=True, slots=True)
class SahmRuleResult:
    current_3mo_avg: float
    trailing_12mo_min_3mo_avg: float
    gap: float
    is_triggered: bool
    interpretation: str


def compute_sahm_rule(
    readings_most_recent_first: list[tuple[date, float]],
) -> SahmRuleResult | None:
    """readings_most_recent_first: (date, unemployment_rate) tuples,
    most recent reading first, matching this codebase's established
    convention for economic-indicator history. Returns None if there
    genuinely isn't enough data to compute a real result — never a
    fabricated or partially-computed one."""
    if len(readings_most_recent_first) < MIN_MONTHS_OF_DATA_REQUIRED:
        return None

    # Oldest-to-newest is the natural order for a rolling-window
    # calculation like this one.
    values_oldest_first = [value for _, value in reversed(readings_most_recent_first)]

    three_month_avgs: list[float] = []
    for i in range(2, len(values_oldest_first)):
        window = values_oldest_first[i - 2 : i + 1]
        three_month_avgs.append(sum(window) / 3)

    current_avg = three_month_avgs[-1]
    trailing_12mo_window = three_month_avgs[-12:]
    min_avg = min(trailing_12mo_window)
    gap = current_avg - min_avg
    is_triggered = gap >= SAHM_RULE_TRIGGER_THRESHOLD

    if is_triggered:
        interpretation = (
            f"The Sahm Rule is triggered — the 3-month average unemployment rate "
            f"({current_avg:.2f}%) is {gap:.2f} points above its own trailing "
            f"12-month low ({min_avg:.2f}%), at or above the rule's real, "
            f"published 0.50-point threshold. Historically, a real, fairly "
            f"reliable signal that a recession is already underway, though not "
            f"a certainty and not a prediction of what happens next."
        )
    else:
        interpretation = (
            f"The Sahm Rule is not triggered — the 3-month average unemployment "
            f"rate ({current_avg:.2f}%) is {gap:.2f} points above its own trailing "
            f"12-month low ({min_avg:.2f}%), below the rule's 0.50-point threshold."
        )

    return SahmRuleResult(
        current_3mo_avg=current_avg,
        trailing_12mo_min_3mo_avg=min_avg,
        gap=gap,
        is_triggered=is_triggered,
        interpretation=interpretation,
    )
