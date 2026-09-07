"""Pure parsing logic for MarketData.app's stock candles and bulk
quotes responses.

Deliberately separated from the HTTP client code -- same principle as
marketdata_parsing.py for options: zero I/O dependencies, testable in
complete isolation, since wire format bugs (not HTTP mechanics) are
where the real risk lives.

Candles response shape confirmed directly against MarketData.app's own
published documentation: {"s": "ok", "o": [...], "h": [...], "l": [...],
"c": [...], "t": [...], "v": [...]}, "t" as Unix timestamps.

Bulk quotes response shape is an HONEST, WELL-GROUNDED INFERENCE, not a
directly-confirmed bulkquotes-specific example: the exact endpoint path
(/v1/stocks/bulkquotes/) was confirmed directly from MarketData.app's
own, real, live /status/ endpoint, and the single-symbol quotes
endpoint's own real, confirmed response shape ({"s": "ok", "symbol":
[...], "mid": [...], "updated": [...], ...}) uses the same "symbol
array + parallel data arrays" pattern as the directly-confirmed
bulkcandles response. Bulk quotes is inferred to follow that same,
established pattern -- flagged honestly here, not presented as
directly verified, matching this app's own confidence-note discipline
already used for less-certain brokerage integrations.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.domain.entities.stock_candle import BulkQuote, StockCandle

logger = logging.getLogger(__name__)


def parse_candles_response(ticker: str, data: dict) -> list[StockCandle]:
    """Converts MarketData.app's columnar candles response into a
    normal list of StockCandle records."""
    if data.get("s") != "ok":
        return []  # "no_data" status — a real, valid "nothing found" response

    count = len(data.get("t", []))
    candles: list[StockCandle] = []
    for i in range(count):
        try:
            candles.append(StockCandle(
                ticker=ticker,
                timestamp=datetime.fromtimestamp(data["t"][i], tz=timezone.utc),
                open=data["o"][i],
                high=data["h"][i],
                low=data["l"][i],
                close=data["c"][i],
                volume=data["v"][i],
            ))
        except (KeyError, IndexError, TypeError) as exc:
            # One malformed candle in a long history shouldn't take
            # down the whole response — skip it, log it, move on.
            logger.warning("Skipping malformed candle at index %d for %s: %s", i, ticker, exc)
            continue

    return candles


def parse_bulk_quotes_response(data: dict) -> list[BulkQuote]:
    """Converts MarketData.app's columnar bulk quotes response into a
    normal list of BulkQuote records. See module docstring for the
    honest confidence note on this response shape."""
    if data.get("s") != "ok":
        return []

    symbols = data.get("symbol", [])
    count = len(symbols)
    quotes: list[BulkQuote] = []
    for i in range(count):
        try:
            mid = data.get("mid", [None] * count)[i]
            if mid is None:
                # A genuinely missing quote for this ticker -- omitted
                # from the result, never represented with a fabricated price.
                continue
            quotes.append(BulkQuote(
                ticker=symbols[i],
                price=mid,
                as_of=(
                    datetime.fromtimestamp(data["updated"][i], tz=timezone.utc)
                    if data.get("updated")
                    else datetime.now(timezone.utc)
                ),
            ))
        except (KeyError, IndexError, TypeError) as exc:
            logger.warning("Skipping malformed bulk quote at index %d: %s", i, exc)
            continue

    return quotes
