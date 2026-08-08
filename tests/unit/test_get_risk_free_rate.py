"""Tests for GetRiskFreeRateUseCase."""
from __future__ import annotations

from datetime import date

from src.application.interfaces.data_provider import DataProviderError
from src.application.use_cases.get_risk_free_rate import (
    FALLBACK_EQUITY_RISK_PREMIUM,
    GetRiskFreeRateUseCase,
)
from src.domain.entities.market_risk_premium import MarketRiskPremium
from src.domain.entities.treasury_rates import TreasuryRates


class _FakeProvider:
    def __init__(self, rates=None, raises=False, risk_premium=None, risk_premium_raises=False):
        self._rates = rates
        self._raises = raises
        self._risk_premium = risk_premium
        self._risk_premium_raises = risk_premium_raises

    def get_treasury_rates(self) -> TreasuryRates:
        if self._raises:
            raise DataProviderError("simulated failure")
        return self._rates

    def get_market_risk_premium(self, country: str = "United States") -> MarketRiskPremium | None:
        if self._risk_premium_raises:
            raise NotImplementedError("This data provider does not support get_market_risk_premium")
        return self._risk_premium


def _rates(year10=0.0469) -> TreasuryRates:
    return TreasuryRates(
        as_of=date(2026, 8, 6), month1=0.038, month2=None, month3=None,
        month6=None, year1=None, year2=None, year3=None, year5=None,
        year7=None, year10=year10, year20=None, year30=None,
    )


def test_execute_returns_the_real_yield_curve() -> None:
    use_case = GetRiskFreeRateUseCase(_FakeProvider(rates=_rates()))
    result = use_case.execute()
    assert result.year10 == 0.0469


def test_execute_propagates_data_provider_error() -> None:
    use_case = GetRiskFreeRateUseCase(_FakeProvider(raises=True))
    try:
        use_case.execute()
        raise AssertionError("expected DataProviderError")
    except DataProviderError:
        pass


def test_default_discount_rate_falls_back_to_the_constant_when_no_real_premium_is_configured() -> None:
    """_FakeProvider's default get_market_risk_premium returns None
    (no risk_premium configured) — the fallback constant should apply."""
    use_case = GetRiskFreeRateUseCase(_FakeProvider(rates=_rates(year10=0.0469)))
    result = use_case.get_default_discount_rate()
    assert abs(result - (0.0469 + FALLBACK_EQUITY_RISK_PREMIUM)) < 1e-9


def test_default_discount_rate_prefers_the_real_equity_risk_premium_when_available() -> None:
    """The actual, real-world case this refinement exists for: a
    genuine current reading (e.g. 4.46% for the US) should be used
    instead of the flat fallback constant."""
    real_premium = MarketRiskPremium(
        country="United States", country_risk_premium=0.0023, total_equity_risk_premium=0.0446,
    )
    use_case = GetRiskFreeRateUseCase(
        _FakeProvider(rates=_rates(year10=0.0469), risk_premium=real_premium)
    )
    result = use_case.get_default_discount_rate()
    assert abs(result - (0.0469 + 0.0446)) < 1e-9
    # Confirms the real premium was genuinely used, not the fallback.
    assert abs(result - (0.0469 + FALLBACK_EQUITY_RISK_PREMIUM)) > 1e-6


def test_default_discount_rate_falls_back_when_risk_premium_lookup_is_unsupported() -> None:
    """A provider that supports Treasury rates but not market risk
    premium (NotImplementedError) should still return a usable
    default — never crash mid-computation."""
    use_case = GetRiskFreeRateUseCase(
        _FakeProvider(rates=_rates(year10=0.0469), risk_premium_raises=True)
    )
    result = use_case.get_default_discount_rate()
    assert abs(result - (0.0469 + FALLBACK_EQUITY_RISK_PREMIUM)) < 1e-9


def test_default_discount_rate_is_none_when_year10_is_missing() -> None:
    use_case = GetRiskFreeRateUseCase(_FakeProvider(rates=_rates(year10=None)))
    assert use_case.get_default_discount_rate() is None


def test_default_discount_rate_is_none_on_provider_failure_not_an_exception() -> None:
    """A DCF caller should be able to fall back to its own constant
    rather than crash if the macro data source is unavailable."""
    use_case = GetRiskFreeRateUseCase(_FakeProvider(raises=True))
    assert use_case.get_default_discount_rate() is None


class _UnsupportedProvider:
    """A provider that genuinely doesn't implement get_treasury_rates
    at all — the real interface's own default behavior for an
    optional capability, distinct from a DataProviderError (a request
    that was attempted and failed)."""
    def get_treasury_rates(self):
        raise NotImplementedError("This data provider does not support get_treasury_rates")


def test_default_discount_rate_is_none_when_provider_does_not_implement_it() -> None:
    """Regression test: get_default_discount_rate's own docstring
    promises a graceful None on any unavailability, but the first
    implementation only caught DataProviderError — a provider that
    simply never implemented get_treasury_rates (NotImplementedError,
    the real interface's own default) would have crashed straight
    through instead."""
    use_case = GetRiskFreeRateUseCase(_UnsupportedProvider())
    assert use_case.get_default_discount_rate() is None
