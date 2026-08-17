from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from src.domain.entities.conviction_summary import ConvictionScreenerResult


class ConvictionScreenerRepository(ABC):
    @abstractmethod
    def save_batch(self, results: list[ConvictionScreenerResult]) -> None:
        """Replaces the entire cached universe snapshot with this batch
        -- a full refresh, not an incremental merge, same rationale as
        FactorScoreRepository.save_batch: a ticker dropped from the
        S&P 500 since the last scan should not linger with a stale
        result forever."""

    @abstractmethod
    def save_one(self, result: ConvictionScreenerResult) -> None:
        """Upserts a single ticker's result WITHOUT touching any other
        row -- deliberately, genuinely different from save_batch's own
        full-refresh semantics. Exists for retrying just the handful
        of tickers a full scan's own transient failures (a network
        timeout, a dropped DB connection) left missing, without
        re-running -- or worse, accidentally wiping -- the rest of an
        already-completed, many-hour scan."""

    @abstractmethod
    def get_latest_as_of(self) -> datetime | None:
        """None if no scan has ever completed."""

    @abstractmethod
    def get_all(self, min_signal_count: int = 0) -> list[ConvictionScreenerResult]:
        """Sorted by signal_count descending, then ticker ascending for
        a stable, deterministic order among ties. min_signal_count
        filters out the (usually large) majority of tickers with no
        real signal at all -- callers browsing for convergence want
        the tickers that actually show something, not every S&P 500
        constituent."""
