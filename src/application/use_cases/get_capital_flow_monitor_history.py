from __future__ import annotations

from src.domain.entities.capital_flow_monitor import CapitalFlowMonitorSnapshot
from src.domain.repositories.capital_flow_monitor_repository import (
    CapitalFlowMonitorSnapshotRepository,
)

DEFAULT_HISTORY_LIMIT = 14  # matches the artifact's "last 14 saved days" history strip


class GetCapitalFlowMonitorHistoryUseCase:
    def __init__(self, snapshot_repo: CapitalFlowMonitorSnapshotRepository) -> None:
        self._snapshot_repo = snapshot_repo

    def execute(self, user_id: str, limit: int = DEFAULT_HISTORY_LIMIT) -> list[CapitalFlowMonitorSnapshot]:
        return self._snapshot_repo.list_recent(user_id, limit=limit)
