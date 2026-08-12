from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ChangeType = Literal["new", "closed", "increased", "decreased"]


@dataclass(frozen=True, slots=True)
class PositionChange:
    """A detected, real change in shares held between two quarters for
    one filer's position in one security. Deliberately based on SHARE
    COUNT changes, not value_usd changes — confirmed as a necessary
    distinction against real ingested data: Berkshire Hathaway's Apple
    stake showed an IDENTICAL share count across two real quarters
    while value_usd changed by billions, purely from the stock's price
    moving, not any actual buying or selling. A value-based signal
    would have falsely flagged that as trading activity."""

    cusip: str
    issuer_name: str
    change_type: ChangeType
    prior_shares: int
    current_shares: int
    prior_value_usd: int
    current_value_usd: int
    pct_change: float | None  # None for "new"/"closed" — undefined when one side is zero
