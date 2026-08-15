"""Institutional 13F holdings query API routes.

Deliberately platform-wide, not per-user — same rationale as
capital_flow.py: this is public SEC data, identical for every user, so
no get_authenticated_user_id() dependency here.

Read-only by design: ingestion happens exclusively via the standalone
scripts/ingest_form_13f.py batch job (a single quarter's data set is
90+ MB and can span millions of rows — no HTTP request should ever
trigger that), never through this router.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.schemas import (
    InstitutionalHoldersResponseSchema,
    InstitutionalHoldingSchema,
    InstitutionalPortfolioResponseSchema,
    PositionChangeSchema,
    PositionChangesResponseSchema,
)
from src.application.use_cases.detect_position_changes import (
    DetectPositionChangesError,
    DetectPositionChangesUseCase,
)
from src.application.use_cases.get_institutional_holders import (
    GetInstitutionalHoldersError,
    GetInstitutionalHoldersUseCase,
)
from src.application.use_cases.get_institutional_portfolio import (
    GetInstitutionalPortfolioError,
    GetInstitutionalPortfolioUseCase,
)
from src.infrastructure.config import get_settings
from src.infrastructure.data_providers.fmp_provider import FinancialModelingPrepProvider
from src.infrastructure.persistence.institutional_holding_repository_impl import (
    SqlAlchemyInstitutionalHoldingRepository,
)

router = APIRouter(prefix="/institutional-holdings", tags=["institutional-holdings"])

_SOURCE_NOTES = {
    "sec_bulk": "SEC EDGAR Form 13F, free official bulk data set — not a paid vendor.",
    "fmp_live": (
        "Live from FMP — the free SEC bulk data set for this quarter isn't "
        "published yet (SEC publishes it once, closely after the filing "
        "deadline, not continuously), so this one filer's freshest quarter "
        "was fetched live instead of showing stale data."
    ),
}


def _repository() -> SqlAlchemyInstitutionalHoldingRepository:
    return SqlAlchemyInstitutionalHoldingRepository()


def get_data_provider() -> FinancialModelingPrepProvider:
    return FinancialModelingPrepProvider(settings=get_settings())


def _to_schema(h) -> InstitutionalHoldingSchema:
    return InstitutionalHoldingSchema(
        filer_name=h.filer_name, issuer_name=h.issuer_name, cusip=h.cusip,
        title_of_class=h.title_of_class, value_usd=h.value_usd,
        shares_or_principal_amount=h.shares_or_principal_amount, share_type=h.share_type,
        put_call=h.put_call, investment_discretion=h.investment_discretion,
    )


@router.get("/holders", response_model=InstitutionalHoldersResponseSchema)
def get_holders(
    issuer: str = Query(..., min_length=1, description="Issuer name to search for, e.g. \"Apple\"."),
    limit: int = Query(20, ge=1, le=100),
) -> InstitutionalHoldersResponseSchema:
    use_case = GetInstitutionalHoldersUseCase(_repository())
    try:
        result = use_case.execute(issuer, limit=limit)
    except GetInstitutionalHoldersError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return InstitutionalHoldersResponseSchema(
        issuer_query=result.issuer_query, issuer_name=result.issuer_name,
        period_of_report=result.period_of_report,
        holders=[_to_schema(h) for h in result.holders],
    )


@router.get("/portfolio", response_model=InstitutionalPortfolioResponseSchema)
def get_portfolio(
    filer: str = Query(..., min_length=1, description="Filer name to search for, e.g. \"Berkshire\"."),
    limit: int = Query(50, ge=1, le=200),
    provider: FinancialModelingPrepProvider = Depends(get_data_provider),
) -> InstitutionalPortfolioResponseSchema:
    use_case = GetInstitutionalPortfolioUseCase(_repository(), provider)
    try:
        result = use_case.execute(filer, limit=limit)
    except GetInstitutionalPortfolioError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return InstitutionalPortfolioResponseSchema(
        filer_query=result.filer_query, filer_name=result.filer_name,
        period_of_report=result.period_of_report,
        holdings=[_to_schema(h) for h in result.holdings],
        source=result.source, source_note=_SOURCE_NOTES[result.source],
    )


@router.get("/position-changes", response_model=PositionChangesResponseSchema)
def get_position_changes(
    filer: str = Query(..., min_length=1, description="Filer name to search for, e.g. \"Berkshire\"."),
    min_pct_change: float = Query(
        0.0, ge=0.0, le=1.0,
        description="Filters out increased/decreased changes below this fraction (e.g. 0.05 for 5%). New/closed positions are always included.",
    ),
) -> PositionChangesResponseSchema:
    use_case = DetectPositionChangesUseCase(_repository())
    try:
        result = use_case.execute(filer, min_pct_change=min_pct_change)
    except DetectPositionChangesError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return PositionChangesResponseSchema(
        filer_query=result.filer_query, filer_name=result.filer_name,
        prior_period=result.prior_period, current_period=result.current_period,
        filer_had_no_prior_period_data=result.filer_had_no_prior_period_data,
        changes=[
            PositionChangeSchema(
                cusip=c.cusip, issuer_name=c.issuer_name, change_type=c.change_type,
                prior_shares=c.prior_shares, current_shares=c.current_shares,
                prior_value_usd=c.prior_value_usd, current_value_usd=c.current_value_usd,
                pct_change=c.pct_change,
            )
            for c in result.changes
        ],
    )
