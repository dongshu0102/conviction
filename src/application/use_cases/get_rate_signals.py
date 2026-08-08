"""Use case: a combined rate-direction picture — yield curve inversion,
the Taylor Rule, and the Sahm Rule, all real, hand-verified formulas
(see rate_signal_math.py and sahm_rule_math.py) applied to real, live
data. Reuses get_economic_indicator for inflationRate, federalFunds,
and nominalPotentialGDP — no new FMP provider capability needed for
those, since they're just different named series through the same
endpoint already built for GDP/CPI/unemployment.

The Sahm Rule is different: it genuinely needs deep historical
unemployment data (at least 15 months), and FMP's own
economic-indicators endpoint hard-caps at 2 rows regardless of plan
tier (confirmed directly, including after a plan upgrade specifically
to test this). macro_history_provider (FRED) is a separate, optional
dependency for exactly this reason — if it isn't configured, the Sahm
Rule is reported as unavailable with a real, honest reason, never
silently omitted or faked.

None of the three signals here predicts anything. All are real,
standard tools professional economists and the Fed itself use as one
input among several — genuinely different from a confident forecast.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from src.application.interfaces.data_provider import DataProviderError, FinancialDataProvider
from src.application.interfaces.macro_history_provider import (
    MacroHistoryProvider,
    MacroHistoryProviderError,
)
from src.domain.services.rate_signal_math import (
    TaylorRuleResult,
    YieldCurveReading,
    compute_taylor_rule,
    read_yield_curve,
)
from src.domain.services.sahm_rule_math import (
    MIN_MONTHS_OF_DATA_REQUIRED,
    SahmRuleResult,
    compute_sahm_rule,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RateSignals:
    as_of: datetime
    yield_curve: YieldCurveReading
    taylor_rule: TaylorRuleResult | None
    taylor_rule_unavailable_reason: str | None
    sahm_rule: SahmRuleResult | None
    sahm_rule_unavailable_reason: str | None


class GetRateSignalsUseCase:
    def __init__(
        self,
        data_provider: FinancialDataProvider,
        macro_history_provider: MacroHistoryProvider | None = None,
    ) -> None:
        self._data_provider = data_provider
        self._macro_history_provider = macro_history_provider

    def execute(
        self, neutral_real_rate: float | None = None, target_inflation: float | None = None,
    ) -> RateSignals:
        yield_curve = self._yield_curve()
        taylor_rule, taylor_unavailable_reason = self._taylor_rule(neutral_real_rate, target_inflation)
        sahm_rule, sahm_unavailable_reason = self._sahm_rule()
        return RateSignals(
            as_of=datetime.now(timezone.utc), yield_curve=yield_curve,
            taylor_rule=taylor_rule, taylor_rule_unavailable_reason=taylor_unavailable_reason,
            sahm_rule=sahm_rule, sahm_rule_unavailable_reason=sahm_unavailable_reason,
        )

    def _yield_curve(self) -> YieldCurveReading:
        try:
            rates = self._data_provider.get_treasury_rates()
        except (DataProviderError, NotImplementedError) as exc:
            logger.warning("Rate signals: Treasury rates unavailable: %s", exc)
            return read_yield_curve(year2=None, year10=None, month3=None)
        return read_yield_curve(year2=rates.year2, year10=rates.year10, month3=rates.month3)

    def _most_recent_value(self, name: str) -> float | None:
        try:
            readings = self._data_provider.get_economic_indicator(name)
        except (DataProviderError, NotImplementedError):
            return None
        return readings[0].value if readings else None

    def _taylor_rule(
        self, neutral_real_rate: float | None, target_inflation: float | None,
    ) -> tuple[TaylorRuleResult | None, str | None]:
        inflation_rate = self._most_recent_value("inflationRate")
        if inflation_rate is None:
            return None, "The real, current inflation rate reading is unavailable."

        gdp = self._most_recent_value("GDP")
        potential_gdp = self._most_recent_value("nominalPotentialGDP")
        current_fed_funds_rate = self._most_recent_value("federalFunds")

        kwargs = {}
        if neutral_real_rate is not None:
            kwargs["neutral_real_rate"] = neutral_real_rate
        if target_inflation is not None:
            kwargs["target_inflation"] = target_inflation

        result = compute_taylor_rule(
            inflation_rate=inflation_rate, gdp=gdp, potential_gdp=potential_gdp,
            current_fed_funds_rate=current_fed_funds_rate, **kwargs,
        )
        return result, None

    def _sahm_rule(self) -> tuple[SahmRuleResult | None, str | None]:
        if self._macro_history_provider is None:
            return None, "No FRED (deep macro history) provider is configured."

        try:
            readings = self._macro_history_provider.get_series_history(
                "UNRATE", limit=MIN_MONTHS_OF_DATA_REQUIRED
            )
        except (MacroHistoryProviderError, NotImplementedError) as exc:
            logger.warning("Rate signals: FRED unemployment history unavailable: %s", exc)
            return None, "Real, historical unemployment data from FRED is currently unavailable."

        result = compute_sahm_rule([(r.as_of, r.value) for r in readings])
        if result is None:
            return None, (
                f"Fewer than {MIN_MONTHS_OF_DATA_REQUIRED} months of real unemployment "
                "history were available to compute the Sahm Rule."
            )
        return result, None
