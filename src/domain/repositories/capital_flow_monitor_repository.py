from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.capital_flow_monitor import CapitalFlowMonitorSnapshot


class CapitalFlowMonitorSnapshotRepository(ABC):
    @abstractmethod
    def save_snapshot(self, user_id: str, snapshot: CapitalFlowMonitorSnapshot) -> None:
        """Upserts today's snapshot for this user — merges with
        whatever's already saved for the same (user_id, snapshot_date)
        rather than overwriting it, matching the artifact's original
        "partial loads accumulate over the day" behavior: loading 3
        modules this morning and 2 more this afternoon should leave
        all 5 in the same day's row, not just the last 2."""

    @abstractmethod
    def list_recent(self, user_id: str, limit: int = 14) -> list[CapitalFlowMonitorSnapshot]:
        """This user's last `limit` saved days, most recent first."""
