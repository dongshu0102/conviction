"""Use case: fetch real, human Wall Street analyst ratings and price
targets for one ticker.

A simple, direct pass-through -- same pattern already established for
GetStockCandlesUseCase and ScreenMarketUseCase.
"""
from __future__ import annotations

from src.application.interfaces.data_provider import FinancialDataProvider
from src.domain.entities.analyst_ratings import AnalystRatings


class GetAnalystRatingsUseCase:
    def __init__(self, provider: FinancialDataProvider) -> None:
        self._provider = provider

    def execute(self, ticker: str) -> AnalystRatings | None:
        return self._provider.get_analyst_ratings(ticker.strip().upper())
