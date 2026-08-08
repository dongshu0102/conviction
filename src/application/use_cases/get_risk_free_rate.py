"""Use case: the current risk-free rate, from the real Treasury yield
curve — the market's own live proxy for the "first input" a rate
change actually flows through into every DCF's discount rate.
"""
from __future__ import annotations

from src.application.interfaces.data_provider import DataProviderError, FinancialDataProvider
from src.domain.entities.treasury_rates import TreasuryRates

# Standard, widely-used long-run US equity risk premium — the extra
# return investors have historically demanded for holding stocks over
# risk-free Treasuries. A single, explicit constant, not something
# this use case tries to estimate dynamically.
DEFAULT_EQUITY_RISK_PREMIUM = 0.05


class GetRiskFreeRateUseCase:
    def __init__(self, data_provider: FinancialDataProvider) -> None:
        self._data_provider = data_provider

    def execute(self) -> TreasuryRates:
        try:
            return self._data_provider.get_treasury_rates()
        except DataProviderError:
            raise

    def get_default_discount_rate(self) -> float | None:
        """10-year Treasury yield + a standard equity risk premium —
        a real, market-derived default for DCF's discount_rate,
        instead of an arbitrary hardcoded constant. Returns None if
        the yield curve is unavailable, so callers can fall back to
        their own constant rather than silently using a bad number."""
        try:
            rates = self._data_provider.get_treasury_rates()
        except (DataProviderError, NotImplementedError):
            return None
        if rates.year10 is None:
            return None
        return rates.year10 + DEFAULT_EQUITY_RISK_PREMIUM
