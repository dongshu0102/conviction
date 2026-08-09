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

from datetime import date

from fastapi import APIRouter, Depends, Query

from src.api.schemas import CapitalFlowEventSchema, CapitalFlowScanResultSchema, Next13FDeadlineSchema
from src.application.use_cases.run_capital_flow_scan import RunCapitalFlowScanUseCase
from src.domain.entities.capital_flow import CapitalFlowEvent, CapitalFlowSource
from src.domain.services.capital_flow_math import DEFAULT_MACRO_SERIES, next_13f_deadline
from src.infrastructure.config import get_settings
from src.infrastructure.data_providers.fmp_provider import FinancialModelingPrepProvider
from src.infrastructure.data_providers.fred_provider import FredProvider
from src.infrastructure.persistence.capital_flow_repository_impl import (
    SqlAlchemyCapitalFlowRepository,
)

router = APIRouter(prefix="/capital-flow", tags=["capital-flow"])


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
        is_late_filing=event.is_late_filing,
    )


@router.get("", response_model=list[CapitalFlowEventSchema])
def list_recent_events(
    source: str | None = Query(default=None, description="Filter to one source: INSIDER, SENATE, HOUSE, VOLUME, or MACRO."),
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


@router.get("/13f-deadline", response_model=Next13FDeadlineSchema)
def get_next_13f_deadline() -> Next13FDeadlineSchema:
    """The next real Form 13F filing deadline, from the SEC's own
    published table (see capital_flow_math.py's FORM_13F_DEADLINES for
    the exact source). Note: 13F data itself is not currently
    accessible via this platform's FMP plan tier (confirmed HTTP 402)
    — this endpoint tells you WHEN the next deadline is, honestly,
    even though the underlying holdings data can't be shown yet."""
    today = date.today()
    deadline = next_13f_deadline(today)
    return Next13FDeadlineSchema(
        next_deadline=deadline,
        days_until=(deadline - today).days if deadline else None,
        source_note=(
            "From the SEC's own published FAQ table (sec.gov, Form 13F FAQ, "
            "Question 25) — not computed. 13F holdings data itself is not "
            "currently accessible on this platform's FMP plan tier."
        ),
    )
