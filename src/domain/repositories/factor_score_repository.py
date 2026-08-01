from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from src.domain.entities.factor_scores import FactorScore


class FactorScoreRepository(ABC):
    @abstractmethod
    def save_batch(self, scores: list[FactorScore]) -> None:
        """Replaces the entire cached universe snapshot with this batch
        — a full refresh, not an incremental merge. A ticker dropped
        from the S&P 500 since the last refresh should not linger with
        stale scores forever."""

    @abstractmethod
    def get_latest_as_of(self) -> datetime | None:
        """None if no snapshot has ever been computed. Used to decide
        whether the cache is stale enough to warrant a refresh."""

    @abstractmethod
    def get(self, ticker: str) -> FactorScore | None:
        ...

    @abstractmethod
    def get_all(self) -> list[FactorScore]:
        ...
