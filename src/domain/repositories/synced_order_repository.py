from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime


class SyncedOrderRepository(ABC):
    @abstractmethod
    def is_already_synced(self, order_id: str) -> bool:
        """Whether this specific, real order_id has already been
        recorded as synced -- the real, authoritative check that
        prevents the same order's shares from being double-counted,
        regardless of how many times a sync is attempted (a stray
        double-click, a page refresh, a direct, repeated API call)."""

    @abstractmethod
    def record_sync(self, order_id: str, portfolio_id: str, ticker: str, synced_at: datetime) -> None:
        """Records this order_id as genuinely, permanently synced.
        Must be called only after a real, successful sync -- never
        speculatively, since this is the record that prevents any
        future re-sync of the same order."""
