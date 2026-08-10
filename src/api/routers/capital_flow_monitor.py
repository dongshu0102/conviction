"""Capital Flow Monitor API routes.

Per-user (unlike capital_flow.py's Capital Flow Agent, which is
platform-wide) — history is a personal, saved board, matching the
existing watchlist/alerts pattern, not a shared global one.
"""
from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException

from src.api.auth import get_authenticated_user_id
from src.api.schemas import (
    CapitalFlowMonitorDetailSchema,
    CapitalFlowMonitorModuleDefSchema,
    CapitalFlowMonitorModuleResultSchema,
    CapitalFlowMonitorSnapshotSchema,
    CapitalFlowMonitorSynthesisRequestSchema,
    CapitalFlowMonitorSynthesisSchema,
)
from src.application.use_cases.get_capital_flow_monitor_history import (
    GetCapitalFlowMonitorHistoryUseCase,
)
from src.application.use_cases.load_capital_flow_monitor_module import (
    LoadCapitalFlowMonitorModuleError,
    LoadCapitalFlowMonitorModuleUseCase,
)
from src.application.use_cases.synthesize_capital_flow_monitor import (
    SynthesizeCapitalFlowMonitorError,
    SynthesizeCapitalFlowMonitorUseCase,
)
from src.domain.entities.capital_flow_monitor import CAPITAL_FLOW_MONITOR_MODULES
from src.infrastructure.config import get_settings
from src.infrastructure.data_providers.fred_provider import FredProvider
from src.infrastructure.llm_providers.anthropic_capital_flow_monitor_agent import (
    AnthropicCapitalFlowMonitorAgent,
)
from src.infrastructure.persistence.capital_flow_monitor_agent_cache_repository_impl import (
    SqlAlchemyCapitalFlowMonitorAgentCacheRepository,
)
from src.infrastructure.persistence.capital_flow_monitor_repository_impl import (
    SqlAlchemyCapitalFlowMonitorSnapshotRepository,
)
from src.infrastructure.rate_limit.in_memory_rate_limiter import InMemoryRateLimiter

router = APIRouter(prefix="/capital-flow-monitor", tags=["capital-flow-monitor"])


def get_capital_flow_monitor_agent() -> AnthropicCapitalFlowMonitorAgent:
    return AnthropicCapitalFlowMonitorAgent(settings=get_settings())


def get_fred_provider_for_monitor() -> FredProvider:
    return FredProvider(settings=get_settings())


def get_capital_flow_monitor_snapshot_repository() -> SqlAlchemyCapitalFlowMonitorSnapshotRepository:
    return SqlAlchemyCapitalFlowMonitorSnapshotRepository()


def get_capital_flow_monitor_agent_cache_repository() -> SqlAlchemyCapitalFlowMonitorAgentCacheRepository:
    return SqlAlchemyCapitalFlowMonitorAgentCacheRepository()


@lru_cache
def get_load_module_rate_limiter() -> InMemoryRateLimiter:
    # 30 requests per 15 minutes per user — generous enough for a
    # couple of full "Load all" cycles (11 modules each) plus manual
    # refreshes, while still bounding a runaway loop. This limits how
    # often the USE CASE can be invoked at all; the agent cache above
    # separately bounds how often that invocation actually reaches a
    # real, costly Anthropic call — the two guard different things and
    # both matter (a cache hit is still a real request worth capping).
    return InMemoryRateLimiter(max_requests=30, window_seconds=15 * 60)


def get_load_module_use_case(
    agent: AnthropicCapitalFlowMonitorAgent = Depends(get_capital_flow_monitor_agent),
    fred: FredProvider = Depends(get_fred_provider_for_monitor),
    repo: SqlAlchemyCapitalFlowMonitorSnapshotRepository = Depends(get_capital_flow_monitor_snapshot_repository),
    cache_repo: SqlAlchemyCapitalFlowMonitorAgentCacheRepository = Depends(get_capital_flow_monitor_agent_cache_repository),
) -> LoadCapitalFlowMonitorModuleUseCase:
    return LoadCapitalFlowMonitorModuleUseCase(agent, fred, repo, cache_repo)


def get_synthesize_use_case(
    agent: AnthropicCapitalFlowMonitorAgent = Depends(get_capital_flow_monitor_agent),
    repo: SqlAlchemyCapitalFlowMonitorSnapshotRepository = Depends(get_capital_flow_monitor_snapshot_repository),
) -> SynthesizeCapitalFlowMonitorUseCase:
    return SynthesizeCapitalFlowMonitorUseCase(agent, repo)


def get_history_use_case(
    repo: SqlAlchemyCapitalFlowMonitorSnapshotRepository = Depends(get_capital_flow_monitor_snapshot_repository),
) -> GetCapitalFlowMonitorHistoryUseCase:
    return GetCapitalFlowMonitorHistoryUseCase(repo)


def _result_to_schema(result) -> CapitalFlowMonitorModuleResultSchema:
    return CapitalFlowMonitorModuleResultSchema(
        module_id=result.module_id, headline_value=result.headline_value,
        headline_direction=result.headline_direction, headline_label=result.headline_label,
        details=[CapitalFlowMonitorDetailSchema(label=d.label, value=d.value) for d in result.details],
        read=result.read, source_note=result.source_note, as_of=result.as_of,
        fetched_at=result.fetched_at, is_agent_estimate=result.is_agent_estimate,
    )


@router.get("/modules", response_model=list[CapitalFlowMonitorModuleDefSchema])
def list_modules() -> list[CapitalFlowMonitorModuleDefSchema]:
    """Static metadata for all 11 modules — lets the frontend render
    the board without hardcoding the module list itself."""
    return [
        CapitalFlowMonitorModuleDefSchema(
            id=m.id, group=m.group, title=m.title, cadence=m.cadence, source=m.source,
            is_agent_estimate=m.prompt is not None,
        )
        for m in CAPITAL_FLOW_MONITOR_MODULES
    ]


@router.post("/modules/{module_id}/load", response_model=CapitalFlowMonitorModuleResultSchema)
def load_module(
    module_id: str,
    user_id: str = Depends(get_authenticated_user_id),
    use_case: LoadCapitalFlowMonitorModuleUseCase = Depends(get_load_module_use_case),
    rate_limiter: InMemoryRateLimiter = Depends(get_load_module_rate_limiter),
) -> CapitalFlowMonitorModuleResultSchema:
    if not rate_limiter.allow(user_id):
        raise HTTPException(
            status_code=429,
            detail="Too many module loads — please wait a few minutes and try again.",
        )
    try:
        result = use_case.execute(user_id, module_id)
    except LoadCapitalFlowMonitorModuleError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _result_to_schema(result)


@router.post("/synthesize", response_model=CapitalFlowMonitorSynthesisSchema)
def synthesize(
    request: CapitalFlowMonitorSynthesisRequestSchema,
    user_id: str = Depends(get_authenticated_user_id),
    use_case: SynthesizeCapitalFlowMonitorUseCase = Depends(get_synthesize_use_case),
) -> CapitalFlowMonitorSynthesisSchema:
    from src.domain.entities.capital_flow_monitor import (
        CapitalFlowMonitorDetail,
        CapitalFlowMonitorModuleResult,
    )

    loaded = [
        (
            item.title,
            item.group,
            CapitalFlowMonitorModuleResult(
                module_id=item.result.module_id, headline_value=item.result.headline_value,
                headline_direction=item.result.headline_direction, headline_label=item.result.headline_label,
                details=tuple(CapitalFlowMonitorDetail(label=d.label, value=d.value) for d in item.result.details),
                read=item.result.read, source_note=item.result.source_note, as_of=item.result.as_of,
                fetched_at=item.result.fetched_at, is_agent_estimate=item.result.is_agent_estimate,
            ),
        )
        for item in request.loaded
    ]

    try:
        synthesis = use_case.execute(user_id, loaded)
    except SynthesizeCapitalFlowMonitorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return CapitalFlowMonitorSynthesisSchema(
        regime=synthesis.regime, stance=synthesis.stance,
        supportive=list(synthesis.supportive), headwinds=list(synthesis.headwinds),
        conflict=synthesis.conflict, watch=synthesis.watch,
    )


@router.get("/history", response_model=list[CapitalFlowMonitorSnapshotSchema])
def get_history(
    user_id: str = Depends(get_authenticated_user_id),
    use_case: GetCapitalFlowMonitorHistoryUseCase = Depends(get_history_use_case),
) -> list[CapitalFlowMonitorSnapshotSchema]:
    snapshots = use_case.execute(user_id)
    return [
        CapitalFlowMonitorSnapshotSchema(
            snapshot_date=s.snapshot_date,
            signals={k: list(v) for k, v in s.signals.items()},
            regime_label=s.regime_label, regime_stance=s.regime_stance,
        )
        for s in snapshots
    ]
