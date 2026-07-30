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

    def __post_init__(self) -> None:
        if not self.user_id or not self.user_id.strip():
            raise ValueError("WatchlistItem.user_id must be a non-empty string")
        if not self.ticker or not self.ticker.strip():
            raise ValueError("WatchlistItem.ticker must be a non-empty string")
        object.__setattr__(self, "ticker", self.ticker.strip().upper())
