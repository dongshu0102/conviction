from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.cusip_ticker_mapping import CusipTickerMapping


class CusipTickerMapRepository(ABC):
    @abstractmethod
    def get(self, cusip: str) -> CusipTickerMapping | None:
        """A single, already-resolved mapping, or None if this CUSIP
        has never been looked up at all — distinct from a resolved
        mapping whose ticker itself is None."""

    @abstractmethod
    def get_many(self, cusips: list[str]) -> dict[str, CusipTickerMapping]:
        """Every already-resolved mapping among the given CUSIPs,
        keyed by cusip. CUSIPs never looked up simply don't appear in
        the result — callers should not assume every requested CUSIP
        comes back."""

    @abstractmethod
    def save(self, mapping: CusipTickerMapping) -> None:
        """Upserts one mapping — overwrites any prior resolution for
        the same CUSIP."""

    @abstractmethod
    def get_unresolved(self, cusips: list[str]) -> list[str]:
        """Which of the given CUSIPs have never been looked up at
        all — the real, actionable work list for a backfill run, so
        it never re-queries FMP for a CUSIP already resolved (even
        one that genuinely resolved to no US ticker)."""
