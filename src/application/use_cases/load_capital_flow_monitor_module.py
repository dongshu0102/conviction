"""Use case: load a single Capital Flow Monitor module.

Dispatches to one of 3 real data-sourcing paths based on module_id:
- "credit" -> a real FRED call (capital_flow_monitor_math.py)
- "liquidity" -> 4 real FRED calls (capital_flow_monitor_math.py)
- anything else -> the Claude + web_search agent

Every successful load also saves a snapshot for that one module,
matching the original artifact's "every successful load persists
immediately" behavior — history accumulates module-by-module, not
only when synthesis runs.
"""
from __future__ import annotations

from datetime import date

from src.application.interfaces.capital_flow_monitor_agent import (
    CapitalFlowMonitorAgent,
    CapitalFlowMonitorAgentError,
)
from src.application.interfaces.macro_history_provider import (
    MacroHistoryProvider,
    MacroHistoryProviderError,
)
from src.domain.entities.capital_flow_monitor import (
    CAPITAL_FLOW_MONITOR_MODULES,
    CapitalFlowMonitorModuleResult,
    CapitalFlowMonitorSnapshot,
)
from src.domain.repositories.capital_flow_monitor_repository import (
    CapitalFlowMonitorSnapshotRepository,
)
from src.domain.services.capital_flow_monitor_math import (
    CREDIT_SPREAD_SERIES_ID,
    LIQUIDITY_SERIES,
    build_credit_spread_module,
    build_liquidity_module,
)

_MODULES_BY_ID = {m.id: m for m in CAPITAL_FLOW_MONITOR_MODULES}


class LoadCapitalFlowMonitorModuleError(Exception):
    """A real, visible failure to load one module — never silently
    swallowed, since the frontend needs to distinguish "still loading"
    from "genuinely failed, try again."""


class LoadCapitalFlowMonitorModuleUseCase:
    def __init__(
        self,
        agent: CapitalFlowMonitorAgent,
        macro_history_provider: MacroHistoryProvider,
        snapshot_repo: CapitalFlowMonitorSnapshotRepository,
    ) -> None:
        self._agent = agent
        self._macro_history_provider = macro_history_provider
        self._snapshot_repo = snapshot_repo

    def execute(self, user_id: str, module_id: str) -> CapitalFlowMonitorModuleResult:
        module_def = _MODULES_BY_ID.get(module_id)
        if module_def is None:
            raise LoadCapitalFlowMonitorModuleError(f"Unknown module_id: {module_id}")

        if module_id == "credit":
            result = self._load_credit()
        elif module_id == "liquidity":
            result = self._load_liquidity()
        else:
            try:
                result = self._agent.fetch_module(module_def)
            except CapitalFlowMonitorAgentError as exc:
                raise LoadCapitalFlowMonitorModuleError(str(exc)) from exc

        self._save_single_module_snapshot(user_id, result)
        return result

    def _load_credit(self) -> CapitalFlowMonitorModuleResult:
        try:
            readings = self._macro_history_provider.get_series_history(CREDIT_SPREAD_SERIES_ID, limit=800)
        except (MacroHistoryProviderError, NotImplementedError) as exc:
            raise LoadCapitalFlowMonitorModuleError(f"credit: FRED request failed: {exc}") from exc
        if not readings:
            raise LoadCapitalFlowMonitorModuleError("credit: FRED returned no data")
        return build_credit_spread_module(readings)

    def _load_liquidity(self) -> CapitalFlowMonitorModuleResult:
        readings_by_series = {}
        for series_id in LIQUIDITY_SERIES:
            try:
                readings = self._macro_history_provider.get_series_history(series_id, limit=20)
            except (MacroHistoryProviderError, NotImplementedError):
                # One series being down doesn't fail the whole module —
                # build_liquidity_module reports it as "unavailable" in
                # its own detail row instead, and WALCL specifically is
                # checked as required below.
                continue
            if readings:
                readings_by_series[series_id] = readings
        if "WALCL" not in readings_by_series:
            raise LoadCapitalFlowMonitorModuleError("liquidity: FRED request failed for WALCL (required series)")
        return build_liquidity_module(readings_by_series)

    def _save_single_module_snapshot(self, user_id: str, result: CapitalFlowMonitorModuleResult) -> None:
        snapshot = CapitalFlowMonitorSnapshot(
            snapshot_date=date.today(),
            signals={result.module_id: (result.headline_value, result.headline_direction, result.as_of)},
        )
        self._snapshot_repo.save_snapshot(user_id, snapshot)
