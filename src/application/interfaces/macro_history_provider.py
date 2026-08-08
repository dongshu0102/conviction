"""Contract for a deep-macro-history data provider.

Same Dependency Inversion pattern as FinancialDataProvider and
OptionsDataProvider — the application layer depends on this
interface, never on FRED's specific wire format directly. Exists as
its own, separate interface (rather than an addition to
FinancialDataProvider) because it is a genuinely different vendor
solving a genuinely different problem: FMP's own economic-indicators
endpoint hard-caps at 2 historical readings regardless of plan tier
(confirmed directly against the real API, including after a plan
upgrade specifically to test this), which makes it unusable for any
calculation needing real historical depth — like the Sahm Rule, which
needs at least 15 months of monthly unemployment data. FRED (the St.
Louis Fed's own, free, authoritative source) has no such limitation.
If we ever swap providers, only the infrastructure adapter changes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.economic_indicator import EconomicIndicatorReading


class MacroHistoryProvider(ABC):
    @abstractmethod
    def get_series_history(self, series_id: str, limit: int = 24) -> list[EconomicIndicatorReading]:
        """Historical readings for one named FRED series (e.g.
        'UNRATE' for unemployment), most recent first, up to `limit`
        readings. Real historical depth, not a fixed 1-2 row cap."""


class MacroHistoryProviderError(Exception):
    pass
