"""Use case: classify the real, current economic cycle state by
combining this app's own, already-existing, hand-verified rate
signals (yield curve inversion, the Sahm Rule).

Deliberately built on top of GetRateSignalsUseCase rather than
duplicating its own, real data-fetching logic -- both signals are
already correctly computed there; this adds a real, honest
classification layer on top, not a second, parallel implementation.
"""
from __future__ import annotations

from src.application.use_cases.get_rate_signals import GetRateSignalsUseCase
from src.domain.services.economic_cycle_math import EconomicCycleState, classify_economic_cycle


class ClassifyEconomicCycleUseCase:
    def __init__(self, rate_signals_use_case: GetRateSignalsUseCase) -> None:
        self._rate_signals_use_case = rate_signals_use_case

    def execute(self) -> EconomicCycleState:
        signals = self._rate_signals_use_case.execute()
        sahm_triggered = signals.sahm_rule.is_triggered if signals.sahm_rule else None
        return classify_economic_cycle(
            yield_curve_inverted=signals.yield_curve.is_inverted,
            sahm_rule_triggered=sahm_triggered,
        )
