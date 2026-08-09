"""Capital Flow Agent API routes.

Deliberately platform-wide, not per-user — unlike growth_candidates.py
or alerts.py, there's no watchlist to scope this to, so no
get_authenticated_user_id() dependency here; the global X-Api-Key
middleware (applied at the app level, same as companies.py) is the
only auth this needs.

The manual-trigger scan endpoint exists for testing/demo convenience,
same rationale as growth_candidates.py's /check — real scheduled
scanning runs via scripts/run_capital_flow_scan.py on a cron schedule,
not through this endpoint. include_volume_scan defaults to False
here specifically because volume scanning costs real, per-ticker API
calls (500 for the S&P 500) — a manual test-trigger endpoint
shouldn't accidentally burn that budget by default.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from src.api.schemas import CapitalFlowEventSchema, CapitalFlowScanResultSchema
from src.application.use_cases.run_capital_flow_scan import RunCapitalFlowScanUseCase
from src.domain.entities.capital_flow import CapitalFlowEvent, CapitalFlowSource
from src.infrastructure.config import get_settings
from src.infrastructure.data_providers.fmp_provider import FinancialModelingPrepProvider
from src.infrastructure.data_providers.fred_provider import FredProvider
from src.infrastructure.persistence.capital_flow_repository_impl import (
    SqlAlchemyCapitalFlowRepository,
)

router = APIRouter(prefix="/capital-flow", tags=["capital-flow"])

# Real, confirmed-live FRED series (see FredProvider) — a deliberately
# curated, explicit list of international capital-flow series, not
# "every BOP-tagged series FRED has" (734 of them), most of which are
# too narrow or too slow-moving to be a real signal here.
DEFAULT_MACRO_SERIES: dict[str, str] = {
    "IEABC": "Balance on current account",
    "ROWFDIQ027S": "Foreign Direct Investment in U.S. (transactions)",
    "USLTTOTALPOS99996": "U.S. portfolio holdings of foreign long-term securities",
    "FORLTTOTALPOS69995": "Foreign portfolio holdings of U.S. long-term securities",
}


def get_capital_flow_repository() -> SqlAlchemyCapitalFlowRepository:
    return SqlAlchemyCapitalFlowRepository()


def get_fred_provider_for_capital_flow() -> FredProvider:
    return FredProvider(settings=get_settings())


def get_capital_flow_scan_use_case(
    repo: SqlAlchemyCapitalFlowRepository = Depends(get_capital_flow_repository),
    fred: FredProvider = Depends(get_fred_provider_for_capital_flow),
    include_volume_scan: bool = Query(default=False),
) -> RunCapitalFlowScanUseCase:
    fmp = FinancialModelingPrepProvider(settings=get_settings())
    # Only pay the real cost of fetching the S&P 500 constituent list
    # when volume scanning was actually requested — not on every call
    # to this dependency regardless of the flag's value.
    ticker_universe = fmp.get_sp500_constituent_tickers() if include_volume_scan else None
    return RunCapitalFlowScanUseCase(
        fmp, repo, macro_history_provider=fred, macro_series=DEFAULT_MACRO_SERIES,
        ticker_universe=ticker_universe,
    )


def _to_schema(event: CapitalFlowEvent) -> CapitalFlowEventSchema:
    return CapitalFlowEventSchema(
        source=event.source.value, symbol=event.symbol, event_date=event.event_date,
        direction=event.direction.value, headline=event.headline,
        detail_url=event.detail_url, detected_at=event.detected_at,
    )


@router.get("", response_model=list[CapitalFlowEventSchema])
def list_recent_events(
    source: str | None = Query(default=None, description="Filter to one source: INSIDER, SENATE, or HOUSE."),
    limit: int = Query(default=50, ge=1, le=200),
    repo: SqlAlchemyCapitalFlowRepository = Depends(get_capital_flow_repository),
) -> list[CapitalFlowEventSchema]:
    source_enum = CapitalFlowSource(source.upper()) if source else None
    events = repo.list_recent(source=source_enum, limit=limit)
    return [_to_schema(e) for e in events]


@router.post("/scan", response_model=CapitalFlowScanResultSchema)
def trigger_scan(
    use_case: RunCapitalFlowScanUseCase = Depends(get_capital_flow_scan_use_case),
) -> CapitalFlowScanResultSchema:
    """Manual trigger for testing — see module docstring. Registered
    with an explicit /scan path segment (not just POST to the bare
    router path) so it can never collide with a future GET /{id}-style
    route the way growth_candidates.py's /check has to reason about
    against /{ticker}."""
    new_events = use_case.execute()
    return CapitalFlowScanResultSchema(
        new_event_count=len(new_events), events=[_to_schema(e) for e in new_events],
    )
