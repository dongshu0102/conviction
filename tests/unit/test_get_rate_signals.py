"""Tests for GetRateSignalsUseCase."""
from __future__ import annotations

from datetime import date

from src.application.use_cases.get_rate_signals import GetRateSignalsUseCase
from src.domain.entities.economic_indicator import EconomicIndicatorReading
from src.domain.entities.treasury_rates import TreasuryRates


class _FakeProvider:
    def __init__(
        self,
        rates: TreasuryRates | None = None,
        rates_raise: bool = False,
        indicators: dict[str, list[EconomicIndicatorReading]] | None = None,
    ):
        self._rates = rates
        self._rates_raise = rates_raise
        self._indicators = indicators or {}

    def get_treasury_rates(self) -> TreasuryRates:
        if self._rates_raise:
            raise NotImplementedError("not supported")
        return self._rates

    def get_economic_indicator(self, name: str) -> list[EconomicIndicatorReading]:
        return self._indicators.get(name, [])


def _rates(year2=0.0425, year10=0.0469, month3=0.039) -> TreasuryRates:
    return TreasuryRates(
        as_of=date(2026, 8, 6), month1=None, month2=None, month3=month3, month6=None,
        year1=None, year2=year2, year3=None, year5=None, year7=None,
        year10=year10, year20=None, year30=None,
    )


def _reading(name: str, value: float) -> EconomicIndicatorReading:
    return EconomicIndicatorReading(name=name, as_of=date(2025, 11, 1), value=value)


def test_execute_returns_a_real_yield_curve_reading() -> None:
    provider = _FakeProvider(rates=_rates())
    use_case = GetRateSignalsUseCase(provider)
    result = use_case.execute()
    assert result.yield_curve.is_inverted is False
    assert abs(result.yield_curve.spread_10y_2y - 0.44) < 1e-6


def test_execute_computes_the_full_taylor_rule_when_all_data_is_available() -> None:
    provider = _FakeProvider(
        rates=_rates(),
        indicators={
            "inflationRate": [_reading("inflationRate", 2.3)],
            "GDP": [_reading("GDP", 31422.526)],
            "nominalPotentialGDP": [_reading("nominalPotentialGDP", 31029.6201689)],
            "federalFunds": [_reading("federalFunds", 3.88)],
        },
    )
    use_case = GetRateSignalsUseCase(provider)
    result = use_case.execute()

    assert result.taylor_rule is not None
    assert abs(result.taylor_rule.target_rate - 3.5831141486124243) < 1e-6
    assert result.taylor_rule_unavailable_reason is None


def test_execute_reports_taylor_rule_unavailable_when_inflation_is_missing() -> None:
    """inflation_rate is the one genuinely required input — GDP/potential
    GDP/fed funds are all optional refinements, but a Taylor Rule reading
    with no inflation figure at all isn't a Taylor Rule reading."""
    provider = _FakeProvider(rates=_rates(), indicators={})
    use_case = GetRateSignalsUseCase(provider)
    result = use_case.execute()

    assert result.taylor_rule is None
    assert result.taylor_rule_unavailable_reason is not None
    assert "inflation" in result.taylor_rule_unavailable_reason.lower()


def test_execute_degrades_gracefully_when_treasury_rates_are_unavailable() -> None:
    provider = _FakeProvider(rates_raise=True)
    use_case = GetRateSignalsUseCase(provider)
    result = use_case.execute()

    assert result.yield_curve.spread_10y_2y is None
    assert result.yield_curve.is_inverted is False
    # The rest of the snapshot is still a real, usable object.
    assert result.as_of is not None


def test_execute_computes_a_partial_taylor_rule_without_the_optional_output_gap() -> None:
    provider = _FakeProvider(
        rates=_rates(),
        indicators={"inflationRate": [_reading("inflationRate", 2.3)]},  # no GDP data at all
    )
    use_case = GetRateSignalsUseCase(provider)
    result = use_case.execute()

    assert result.taylor_rule is not None
    assert result.taylor_rule.output_gap_pct is None
    assert abs(result.taylor_rule.target_rate - 2.95) < 1e-6  # matches the no-output-gap hand calc


def test_execute_passes_through_custom_neutral_rate_and_target_inflation() -> None:
    provider = _FakeProvider(
        rates=_rates(), indicators={"inflationRate": [_reading("inflationRate", 2.5)]},
    )
    use_case = GetRateSignalsUseCase(provider)
    result = use_case.execute(neutral_real_rate=1.0, target_inflation=2.5)

    assert result.taylor_rule is not None
    assert abs(result.taylor_rule.target_rate - 3.5) < 1e-6
