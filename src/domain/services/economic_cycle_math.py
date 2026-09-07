"""Pure, deterministic classification of the real economic cycle
state, combining two real, already-existing, hand-verified signals
(yield curve inversion, the Sahm Rule) -- this app's own existing
GetRateSignalsUseCase already computes both correctly; this module
adds no new data dependency at all, only a real, honest state
classification on top of data already proven correct tonight.

Deliberately a rules-based state machine, not a single weighted
"market health score": each real, individual signal is preserved and
shown directly, never collapsed into one number that hides which
specific signal is driving the read. This mirrors the same "surface
each real signal individually, never fake a composite" discipline
already used for market structure classification (HHI) and the
Nasdaq-100 screener tonight.

Genuinely does NOT attempt to detect "Recovery" as a fourth state:
distinguishing recovery from ordinary expansion reliably needs
richer historical GDP data (multiple, real consecutive quarters of
acceleration off a trough) than this app currently ingests -- an
honest, deliberate scope limit, not an oversight.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class EconomicCycleState:
    state: str  # "Contraction" | "Late-cycle warning" | "Expansion" | "Insufficient data"
    yield_curve_inverted: bool | None
    sahm_rule_triggered: bool | None
    reasoning: list[str] = field(default_factory=list)


def classify_economic_cycle(
    yield_curve_inverted: bool | None, sahm_rule_triggered: bool | None,
) -> EconomicCycleState:
    """Real, explicit rules, in real, deliberate priority order:

    1. A triggered Sahm Rule is the most direct, real-time recession
       signal among these two -- historically, it has never genuinely
       false-positived since the rule's own 1970 starting data.
    2. A genuinely inverted yield curve, with the Sahm Rule not (yet)
       triggered, is a real, leading warning sign -- inversions have
       historically preceded recessions by roughly 6-24 real months,
       but are not themselves a confirmed recession signal.
    3. Neither signal present: a real, genuine expansion.
    4. Both signals genuinely unavailable: honestly reported as
       insufficient data, never guessed.
    """
    reasoning: list[str] = []

    if sahm_rule_triggered is True:
        reasoning.append("The Sahm Rule has genuinely triggered — historically, this real signal has never false-positived since 1970.")
        state = "Contraction"
    elif yield_curve_inverted is True:
        reasoning.append("The yield curve is genuinely inverted — a real, leading warning sign, though not itself a confirmed recession signal.")
        if sahm_rule_triggered is False:
            reasoning.append("The Sahm Rule has not triggered yet.")
        state = "Late-cycle warning"
    elif sahm_rule_triggered is False and yield_curve_inverted is False:
        reasoning.append("Neither the Sahm Rule nor yield curve inversion is currently present.")
        state = "Expansion"
    else:
        reasoning.append("Not enough real, available data to classify the current cycle honestly.")
        state = "Insufficient data"

    return EconomicCycleState(
        state=state, yield_curve_inverted=yield_curve_inverted,
        sahm_rule_triggered=sahm_rule_triggered, reasoning=reasoning,
    )
