"""MarketData.app adapter for stock candles and bulk quotes.

Endpoint paths confirmed directly from MarketData.app's own, real,
live /status/ endpoint (/v1/stocks/candles/, /v1/stocks/bulkquotes/),
not guessed. See marketdata_stock_parsing.py's own docstring for the
honest confidence note on the bulk quotes response shape specifically.
"""
from __future__ import annotations

import logging
from datetime import date

import httpx

from src.application.interfaces.stock_data_provider import (
    StockDataProvider,
    StockDataProviderError,
)
from src.domain.entities.stock_candle import BulkQuote, StockCandle
from src.infrastructure.config import Settings
from src.infrastructure.data_providers.marketdata_stock_parsing import (
    parse_bulk_quotes_response,
    parse_candles_response,
)

logger = logging.getLogger(__name__)

# MarketData.app returns 203 for cache-tier responses — identical body
# shape to 200, just a different status. Both must be treated as
# success; same real, confirmed behavior already relied on for the
# options chain endpoint.
_SUCCESS_STATUS_CODES = (200, 203)


class MarketDataStockProvider(StockDataProvider):
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.Client(
            base_url="https://api.marketdata.app/v1",
            headers={"Authorization": f"Bearer {settings.marketdata_api_key}"},
            timeout=30.0,
        )

    def get_candles(
        self, ticker: str, resolution: str, from_date: date, to_date: date,
    ) -> list[StockCandle]:
        params = {"from": from_date.isoformat(), "to": to_date.isoformat()}
        try:
            response = self._client.get(f"/stocks/candles/{resolution}/{ticker}/", params=params)
        except httpx.HTTPError as exc:
            raise StockDataProviderError(f"MarketData.app candles request failed for {ticker}: {exc}") from exc

        if response.status_code not in _SUCCESS_STATUS_CODES:
            raise StockDataProviderError(
                f"MarketData.app candles returned {response.status_code} for {ticker}: {response.text}"
            )
        return parse_candles_response(ticker, response.json())

    def get_bulk_quotes(self, tickers: list[str]) -> list[BulkQuote]:
        if not tickers:
            return []
        params = {"symbols": ",".join(tickers)}
        try:
            response = self._client.get("/stocks/bulkquotes/", params=params)
        except httpx.HTTPError as exc:
            raise StockDataProviderError(f"MarketData.app bulk quotes request failed: {exc}") from exc

        if response.status_code not in _SUCCESS_STATUS_CODES:
            raise StockDataProviderError(
                f"MarketData.app bulk quotes returned {response.status_code}: {response.text}"
            )
        return parse_bulk_quotes_response(response.json())
