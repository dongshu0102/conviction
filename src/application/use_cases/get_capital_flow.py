"""Use case: read recently-detected capital flow events.

A thin wrapper around CapitalFlowRepository.list_recent — this is the
READ side; scanning/detection happens in RunCapitalFlowScanUseCase,
via the cron script, never here. Matches the established convention
of even a simple repository read getting its own use case (same
pattern as ListSpeculativeGrowthCandidatesUseCase) rather than the
chat/REST layers touching a repository directly.
"""
from __future__ import annotations

from src.domain.entities.capital_flow import CapitalFlowEvent, CapitalFlowSource
from src.domain.repositories.capital_flow_repository import CapitalFlowRepository


class GetCapitalFlowUseCase:
    def __init__(self, capital_flow_repo: CapitalFlowRepository) -> None:
        self._capital_flow_repo = capital_flow_repo

    def execute(
        self, source: CapitalFlowSource | None = None, limit: int = 20,
    ) -> list[CapitalFlowEvent]:
        return self._capital_flow_repo.list_recent(source=source, limit=limit)
