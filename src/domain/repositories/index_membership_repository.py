from __future__ import annotations

from abc import ABC, abstractmethod


class IndexMembershipRepository(ABC):
    @abstractmethod
    def save_memberships(self, ticker: str, index_names: list[str]) -> None:
        """Replaces ALL of this ticker's own memberships with exactly
        this list -- a scoped delete-then-insert on this ticker alone
        (same reasoning as ConvictionScreenerRepository.save_one), not
        a full-table refresh. Passing [] clears this ticker's
        memberships entirely (e.g. it was dropped from every index
        this app tracks)."""

    @abstractmethod
    def get_memberships_for_tickers(self, tickers: list[str]) -> dict[str, list[str]]:
        """Bulk lookup -- one query for many tickers, not one query
        per ticker, since callers like the screener page need this for
        the entire, hundreds-strong universe at once. A ticker with no
        rows at all is simply absent from the returned dict (an empty
        list, not a KeyError, is the caller's responsibility to
        default to when looking a specific ticker up)."""
