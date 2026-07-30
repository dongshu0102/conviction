from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.watchlist import WatchlistItem


class WatchlistRepository(ABC):
    @abstractmethod
    def add(self, item: WatchlistItem) -> None:
        """Idempotent: adding a ticker already on the watchlist updates
        notes/timestamp rather than creating a duplicate entry."""

    @abstractmethod
    def remove(self, user_id: str, ticker: str) -> bool:
        """Returns True if an item was actually removed, False if it
        wasn't on the watchlist to begin with — lets the use case give
        an accurate response rather than a silent no-op."""

    @abstractmethod
    def list_for_user(self, user_id: str) -> list[WatchlistItem]: ...

    @abstractmethod
    def contains(self, user_id: str, ticker: str) -> bool: ...
