"""Use case: fetch real historical price candles for one ticker.

A simple, direct pass-through to the provider -- same pattern already
established for other simple "get" use cases in this app (e.g.
GetCompanyFinancialsUseCase). The value here is the Dependency
Inversion boundary itself (callers depend on StockDataProvider, never
on MarketData.app directly), not any additional business logic.
"""
from __future__ import annotations

from datetime import date

from src.application.interfaces.stock_data_provider import StockDataProvider
from src.domain.entities.stock_candle import StockCandle


class GetStockCandlesUseCase:
    def __init__(self, provider: StockDataProvider) -> None:
        self._provider = provider

    def execute(
        self, ticker: str, resolution: str, from_date: date, to_date: date,
    ) -> list[StockCandle]:
        return self._provider.get_candles(ticker.strip().upper(), resolution, from_date, to_date)
