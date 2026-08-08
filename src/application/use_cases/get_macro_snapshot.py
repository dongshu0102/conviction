"""Use case: a combined macro snapshot — GDP, CPI, unemployment,
the real US equity risk premium, and recent macro news headlines, all
in one call. Every piece fetched independently and allowed to fail on
its own: a missing indicator or a down news feed shouldn't block the
rest of the snapshot from returning what it does have. This is
explicitly the *structured, quantifiable* half of "macro" — real
numbers and real headlines, not an attempt to model geopolitical risk,
regulatory change, or foreign central bank policy, none of which have
a clean numeric API to ingest.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from src.application.interfaces.data_provider import DataProviderError, FinancialDataProvider
from src.domain.entities.economic_indicator import EconomicIndicatorReading
from src.domain.entities.general_news import GeneralNewsHeadline
from src.domain.entities.market_risk_premium import MarketRiskPremium

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MacroSnapshot:
    as_of: datetime
    gdp: EconomicIndicatorReading | None
    cpi: EconomicIndicatorReading | None
    unemployment_rate: EconomicIndicatorReading | None
    risk_premium: MarketRiskPremium | None
    recent_news: list[GeneralNewsHeadline]


class GetMacroSnapshotUseCase:
    def __init__(self, data_provider: FinancialDataProvider) -> None:
        self._data_provider = data_provider

    def execute(self, news_limit: int = 5) -> MacroSnapshot:
        return MacroSnapshot(
            as_of=datetime.now(timezone.utc),
            gdp=self._most_recent("GDP"),
            cpi=self._most_recent("CPI"),
            unemployment_rate=self._most_recent("unemploymentRate"),
            risk_premium=self._risk_premium(),
            recent_news=self._news(news_limit),
        )

    def _most_recent(self, name: str) -> EconomicIndicatorReading | None:
        try:
            readings = self._data_provider.get_economic_indicator(name)
        except (DataProviderError, NotImplementedError) as exc:
            logger.warning("Macro snapshot: %s unavailable: %s", name, exc)
            return None
        return readings[0] if readings else None

    def _risk_premium(self) -> MarketRiskPremium | None:
        try:
            return self._data_provider.get_market_risk_premium()
        except (DataProviderError, NotImplementedError) as exc:
            logger.warning("Macro snapshot: risk premium unavailable: %s", exc)
            return None

    def _news(self, limit: int) -> list[GeneralNewsHeadline]:
        try:
            return self._data_provider.get_general_news(limit)
        except (DataProviderError, NotImplementedError) as exc:
            logger.warning("Macro snapshot: general news unavailable: %s", exc)
            return []
