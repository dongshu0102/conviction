"""Domain entity for a real, market-wide stock screen -- genuinely
distinct from ScreenedStock/ScreenResult (stock_screen.py), which
screens a caller-supplied, bounded set of tickers via one FMP call
per ticker for value/quality scoring.

This screens the REAL, WHOLE market server-side (FMP's own screener
endpoint filters ~10,000+ tickers in a single call) by real, structural
criteria -- market cap, sector, industry, price, beta, dividend,
volume, exchange -- not fundamentals ratios. This is genuinely the
"which stocks?" entry point a value/quality screen like ScreenResult
is meant to run on afterward, not a replacement for it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class MarketScreenCandidate:
    ticker: str
    company_name: str
    market_cap: float
    price: float
    beta: float | None
    last_annual_dividend: float | None
    volume: int
    sector: str | None
    industry: str | None
    exchange: str
    country: str | None


@dataclass(frozen=True, slots=True)
class MarketScreenResult:
    as_of: datetime
    candidates: list[MarketScreenCandidate] = field(default_factory=list)
