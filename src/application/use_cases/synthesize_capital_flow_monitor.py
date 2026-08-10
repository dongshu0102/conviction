"""Use case: synthesize a loaded Capital Flow Monitor board into one
overall verdict, and save the regime label into today's snapshot.
"""
from __future__ import annotations

from datetime import date

from src.application.interfaces.capital_flow_monitor_agent import (
    CapitalFlowMonitorAgent,
    CapitalFlowMonitorAgentError,
)
from src.domain.entities.capital_flow_monitor import (
    CapitalFlowMonitorModuleResult,
    CapitalFlowMonitorSnapshot,
    CapitalFlowMonitorSynthesis,
)
from src.domain.repositories.capital_flow_monitor_repository import (
    CapitalFlowMonitorSnapshotRepository,
)

MIN_MODULES_FOR_SYNTHESIS = 3  # matches the frontend's "Synthesize board" button being disabled below this


class SynthesizeCapitalFlowMonitorError(Exception):
    pass


class SynthesizeCapitalFlowMonitorUseCase:
    def __init__(
        self,
        agent: CapitalFlowMonitorAgent,
        snapshot_repo: CapitalFlowMonitorSnapshotRepository,
    ) -> None:
        self._agent = agent
        self._snapshot_repo = snapshot_repo

    def execute(
        self, user_id: str, loaded: list[tuple[str, str, CapitalFlowMonitorModuleResult]],
    ) -> CapitalFlowMonitorSynthesis:
        """loaded: [(title, group, result), ...] for every module the
        caller has already loaded this session."""
        if len(loaded) < MIN_MODULES_FOR_SYNTHESIS:
            raise SynthesizeCapitalFlowMonitorError(
                f"Need at least {MIN_MODULES_FOR_SYNTHESIS} loaded modules to synthesize, got {len(loaded)}"
            )

        try:
            synthesis = self._agent.synthesize(loaded)
        except CapitalFlowMonitorAgentError as exc:
            raise SynthesizeCapitalFlowMonitorError(str(exc)) from exc

        snapshot = CapitalFlowMonitorSnapshot(
            snapshot_date=date.today(),
            signals={},  # module signals are already saved individually as each module loads
            regime_label=synthesis.regime,
            regime_stance=synthesis.stance,
        )
        self._snapshot_repo.save_snapshot(user_id, snapshot)

        return synthesis
