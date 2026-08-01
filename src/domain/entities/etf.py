"""Domain entity for ETF profile data, fetched at ingestion time.

Not a separate ticker-tracking entity — this is transient data used
ONCE, at ingestion, to populate Company's ETF-specific fields
(expense_ratio, aum). After ingestion, an ETF is just a Company with
asset_type=ETF; nothing downstream needs to re-fetch this profile.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EtfProfile:
    ticker: str
    name: str
    description: str | None
    asset_class: str | None  # FMP's "assetClass", e.g. "Equity", "Fixed Income"
    domicile: str | None  # FMP's "domicile", e.g. "US"
    # expenseRatio as FMP reports it — ALREADY a percentage figure
    # (0.09 means 0.09%, i.e. 9 basis points), NOT a fraction. Never
    # multiply this by 100 for display; it would silently be 100x wrong.
    expense_ratio: float | None
    aum: float | None
