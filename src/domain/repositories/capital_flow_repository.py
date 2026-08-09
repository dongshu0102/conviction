from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.capital_flow import CapitalFlowEvent, CapitalFlowSource


class CapitalFlowRepository(ABC):
    @abstractmethod
    def save_new_events(self, events: list[CapitalFlowEvent]) -> list[CapitalFlowEvent]:
        """Saves every event whose dedup_key hasn't been seen before,
        silently skipping any that have — returns only the genuinely
        NEW events (the ones a caller should actually alert on), not
        the full input list. This is the single operation a scan run
        needs: "persist and tell me what's actually new," not two
        separate round-trips for a check-then-save that could race
        against a concurrent run."""

    @abstractmethod
    def list_recent(
        self, source: CapitalFlowSource | None = None, limit: int = 50,
    ) -> list[CapitalFlowEvent]:
        """Most recently detected events first, across every source or
        filtered to one. This is the read side for REST/frontend
        queries — a scan run never calls this itself."""
