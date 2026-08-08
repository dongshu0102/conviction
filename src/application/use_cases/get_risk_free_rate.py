"""Use case: the current risk-free rate, from the real Treasury yield
curve — the market's own live proxy for the "first input" a rate
change actually flows through into every DCF's discount rate.
"""
from __future__ import annotations

from src.application.interfaces.data_provider import DataProviderError, FinancialDataProvider
from src.domain.entities.treasury_rates import TreasuryRates

# Fallback only — used when the real, live equity risk premium
# (FMP's market-risk-premium endpoint) is unavailable. A standard,
# widely-used long-run approximation, not this use case's first
# choice: get_default_discount_rate prefers the real current reading
# whenever the data source supports it.
FALLBACK_EQUITY_RISK_PREMIUM = 0.05


class GetRiskFreeRateUseCase:
    def __init__(self, data_provider: FinancialDataProvider) -> None:
        self._data_provider = data_provider

    def execute(self) -> TreasuryRates:
        try:
            return self._data_provider.get_treasury_rates()
        except DataProviderError:
            raise

    def get_default_discount_rate(self) -> float | None:
        """10-year Treasury yield + the real, current US equity risk
        premium (falling back to a standard constant if that specific
        reading is unavailable) — a market-derived default for DCF's
        discount_rate, instead of an arbitrary hardcoded constant.
        Returns None only if the yield curve itself is unavailable,
        so callers can fall back to their own constant rather than
        silently using a bad number."""
        try:
            rates = self._data_provider.get_treasury_rates()
        except (DataProviderError, NotImplementedError):
            return None
        if rates.year10 is None:
            return None

        equity_risk_premium = FALLBACK_EQUITY_RISK_PREMIUM
        try:
            premium = self._data_provider.get_market_risk_premium()
            if premium is not None:
                equity_risk_premium = premium.total_equity_risk_premium
        except (DataProviderError, NotImplementedError):
            pass  # real reading unavailable — the fallback constant above is used

        return rates.year10 + equity_risk_premium

