from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.watchlist import WatchlistItem


class WatchlistRepository(ABC):
    @abstractmethod
    def add(self, item: WatchlistItem) -> None:
        """Idempotent: adding a ticker already on the same named list
        updates that item's fields rather than creating a duplicate.
        The identity key is (user_id, list_name, ticker) — the same
        ticker on a DIFFERENT list is a separate item."""

    @abstractmethod
    def remove(self, user_id: str, ticker: str, list_name: str | None = None) -> bool:
        """list_name=None removes the ticker from ALL of the user's
        lists (backward-compatible with the pre-named-lists behavior);
        a specific list_name removes it from that list only. Returns
        True if anything was actually removed."""

    @abstractmethod
    def get(self, user_id: str, ticker: str, list_name: str) -> WatchlistItem | None:
        """Fetch one specific item so callers can update individual
        fields without clobbering the rest (see UpdateWatchlistItem)."""

    @abstractmethod
    def list_for_user(self, user_id: str, list_name: str | None = None) -> list[WatchlistItem]:
        """list_name=None returns items across ALL lists."""

    @abstractmethod
    def contains(self, user_id: str, ticker: str) -> bool:
        """True if the ticker is on ANY of the user's lists."""
