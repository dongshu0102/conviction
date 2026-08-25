from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.nasdaq100_classification import Nasdaq100Classification


class Nasdaq100ClassificationRepository(ABC):
    @abstractmethod
    def save_batch(self, results: list[Nasdaq100Classification]) -> None:
        """Replaces the entire cached table with this batch -- a full
        refresh, not an incremental merge, same rationale as
        ConvictionScreenerRepository.save_batch: a ticker dropped from
        the Nasdaq-100 since the last refresh should not linger with a
        stale row forever."""

    @abstractmethod
    def get_all(
        self,
        industry: str | None = None,
        market_structure_category: str | None = None,
        value_chain_position: str | None = None,
        business_model: str | None = None,
        market_cap_tier: str | None = None,
        maturity_stage: str | None = None,
    ) -> list[Nasdaq100Classification]:
        """The real screener query -- every argument is an optional,
        exact-match filter on that dimension; None means "no filter on
        this dimension," never "filter for a genuinely null value.\""""
