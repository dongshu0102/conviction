"""Domain entity for a watchlist item.

user_id is a plain string, unauthenticated at this layer — there is no
login/session system yet. Every API caller is trusted to supply their
own correct user_id; nothing here verifies identity. This is a known,
deliberate MVP gap (real auth is Phase 5+ scope), not an oversight —
the ownership *model* exists now so the schema doesn't need to change
when real auth arrives, but access control does not exist yet.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class WatchlistItem:
    user_id: str
    ticker: str
    added_at: datetime
    notes: str | None = None
    # -- Smart watchlist fields (all additive; every existing
    # construction site keeps working unchanged) --
    # Named lists are a label on the item, not a separate table — an
    # accepted MVP tradeoff (no empty lists, rename touches all rows)
    # in exchange for a much smaller schema change.
    list_name: str = "Default"
    # Entry-alert semantics: alert when price crosses AT OR BELOW this.
    target_price: float | None = None
    # Per-ticker override of the monitoring move threshold (e.g. 0.03
    # = 3%). None means use the global default.
    alert_threshold_pct: float | None = None
    # Captured at add time, best effort — the baseline that makes
    # "how has this changed since I started watching it" answerable.
    added_price: float | None = None
    added_pe: float | None = None

    def __post_init__(self) -> None:
        if not self.user_id or not self.user_id.strip():
            raise ValueError("WatchlistItem.user_id must be a non-empty string")
        if not self.ticker or not self.ticker.strip():
            raise ValueError("WatchlistItem.ticker must be a non-empty string")
        if not self.list_name or not self.list_name.strip():
            raise ValueError("WatchlistItem.list_name must be a non-empty string")
        object.__setattr__(self, "ticker", self.ticker.strip().upper())
        object.__setattr__(self, "list_name", self.list_name.strip())
