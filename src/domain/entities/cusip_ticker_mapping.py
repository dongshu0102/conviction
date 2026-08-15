from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class CusipTickerMapping:
    """One resolved (or genuinely attempted-and-failed) CUSIP-to-ticker
    mapping. ticker is None when resolution was attempted and no
    US-listed ticker was found — a real, different state from no
    mapping existing at all (see cusip_ticker_resolution's own
    docstring)."""

    cusip: str
    ticker: str | None
    company_name: str | None
    resolved_at: datetime
