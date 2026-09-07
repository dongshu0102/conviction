"""Contract for a stock candle / bulk quote data provider.

Deliberately separate from OptionsDataProvider -- genuinely different
data (plain equity OHLCV history and midpoint prices, not option
contracts and their greeks). Same Dependency Inversion pattern: the
application layer depends on this interface, never on a specific
provider's wire format directly.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from src.domain.entities.stock_candle import BulkQuote, StockCandle


class StockDataProvider(ABC):
    @abstractmethod
    def get_candles(
        self, ticker: str, resolution: str, from_date: date, to_date: date,
    ) -> list[StockCandle]:
        """Historical OHLCV candles for one real ticker. resolution
        follows the provider's own real, documented values (e.g. "D"
        for daily, "1" for 1-minute) -- passed through directly, not
        reinterpreted, since a "resolution" concept genuinely varies
        by provider."""

    @abstractmethod
    def get_bulk_quotes(self, tickers: list[str]) -> list[BulkQuote]:
        """Real, current midpoint prices for multiple real tickers in
        one request -- for cheaply refreshing a whole shortlist's
        prices at once, rather than one request per ticker. Tickers
        with no real, available quote are simply omitted from the
        result, not represented with a fabricated price."""


class StockDataProviderError(Exception):
    pass
