from __future__ import annotations

from datetime import datetime, timezone

from src.application.use_cases.classify_economic_cycle import ClassifyEconomicCycleUseCase
from src.application.use_cases.get_rate_signals import RateSignals
from src.domain.services.rate_signal_math import YieldCurveReading
from src.domain.services.sahm_rule_math import SahmRuleResult


class _FakeRateSignalsUseCase:
    def __init__(self, signals: RateSignals) -> None:
        self._signals = signals

    def execute(self) -> RateSignals:
        return self._signals


def _signals(is_inverted: bool, sahm: SahmRuleResult | None) -> RateSignals:
    return RateSignals(
        as_of=datetime.now(timezone.utc),
        yield_curve=YieldCurveReading(
            spread_10y_2y=-0.01 if is_inverted else 0.01, spread_10y_3m=0.0,
            is_inverted=is_inverted, interpretation="test",
        ),
        taylor_rule=None, taylor_rule_unavailable_reason="test",
        sahm_rule=sahm, sahm_rule_unavailable_reason=None if sahm else "test",
    )


def _sahm(triggered: bool) -> SahmRuleResult:
    return SahmRuleResult(
        current_3mo_avg=4.0, trailing_12mo_min_3mo_avg=3.5,
        gap=0.5 if triggered else 0.1, is_triggered=triggered, interpretation="test",
    )


def test_classifies_contraction_when_the_real_sahm_rule_has_triggered() -> None:
    signals = _signals(is_inverted=True, sahm=_sahm(triggered=True))
    use_case = ClassifyEconomicCycleUseCase(_FakeRateSignalsUseCase(signals))

    result = use_case.execute()

    assert result.state == "Contraction"


def test_classifies_late_cycle_warning_when_curve_inverted_but_sahm_has_not_triggered() -> None:
    signals = _signals(is_inverted=True, sahm=_sahm(triggered=False))
    use_case = ClassifyEconomicCycleUseCase(_FakeRateSignalsUseCase(signals))

    result = use_case.execute()

    assert result.state == "Late-cycle warning"


def test_classifies_expansion_when_neither_real_signal_is_present() -> None:
    signals = _signals(is_inverted=False, sahm=_sahm(triggered=False))
    use_case = ClassifyEconomicCycleUseCase(_FakeRateSignalsUseCase(signals))

    result = use_case.execute()

    assert result.state == "Expansion"


def test_handles_a_genuinely_unavailable_sahm_rule_honestly() -> None:
    """When the Sahm Rule is genuinely unavailable (e.g. no
    macro_history_provider configured), the classification should
    still work correctly off the real, available curve signal alone."""
    signals = _signals(is_inverted=True, sahm=None)
    use_case = ClassifyEconomicCycleUseCase(_FakeRateSignalsUseCase(signals))

    result = use_case.execute()

    assert result.state == "Late-cycle warning"
    assert result.sahm_rule_triggered is None
