from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.speculative_growth_candidate import SpeculativeGrowthCandidate


class SpeculativeGrowthCandidateRepository(ABC):
    @abstractmethod
    def add(self, candidate: SpeculativeGrowthCandidate) -> SpeculativeGrowthCandidate:
        """Idempotent — adding an already-tracked ticker for this user
        returns the existing candidate unchanged rather than resetting
        its last-known state and losing the ability to detect a real
        change on the next check."""

    @abstractmethod
    def remove(self, user_id: str, ticker: str) -> bool:
        """Returns True if a candidate existed and was removed."""

    @abstractmethod
    def list_for_user(self, user_id: str) -> list[SpeculativeGrowthCandidate]: ...

    @abstractmethod
    def update_last_state(
        self,
        user_id: str,
        ticker: str,
        growth_trend: str | None,
        cash_runway_months: float | None,
        market_cap: float | None,
        checked_at,
    ) -> None:
        """Overwrites the last-known state fields after a check —
        called regardless of whether an alert fired, same as
        PriceSnapshot.save being unconditional in run_monitoring_check."""
