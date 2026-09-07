"""Domain entity for a single historical price candle (OHLCV).

Separate from anything option-related -- this represents real, plain
equity price history, genuinely different data than an option chain.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class StockCandle:
    ticker: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass(frozen=True, slots=True)
class BulkQuote:
    """One ticker's real, current midpoint price from a bulk quote
    request -- the MarketData.app "SmartMid" model, not a bid/ask
    spread. Genuinely different data shape than a single OptionQuote:
    this is a plain equity price, not an option contract's own,
    fuller quote (bid/ask/greeks/etc)."""

    ticker: str
    price: float
    as_of: datetime
