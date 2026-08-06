"""Speculative-growth candidate tracking API routes. Requires a valid
API key (X-Api-Key header).

The manual-trigger check endpoint exists for testing/demo convenience,
same rationale as alerts.py's /check — real scheduled checking runs
via a periodic job, not through this endpoint.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.api.auth import get_authenticated_user_id
from src.api.routers.companies import get_speculative_growth_use_case
from src.api.schemas import AlertSchema, SpeculativeGrowthCandidateSchema
from src.application.use_cases.assess_speculative_growth import AssessSpeculativeGrowthUseCase
from src.application.use_cases.check_speculative_growth_candidates import (
    CheckSpeculativeGrowthCandidatesUseCase,
)
from src.application.use_cases.get_company_financials import CompanyNotFoundError
from src.application.use_cases.manage_speculative_growth_candidates import (
    AddSpeculativeGrowthCandidateUseCase,
    ListSpeculativeGrowthCandidatesUseCase,
    RemoveSpeculativeGrowthCandidateUseCase,
)
from src.infrastructure.persistence.monitoring_repository_impl import SqlAlchemyAlertRepository
from src.infrastructure.persistence.speculative_growth_candidate_repository_impl import (
    SqlAlchemySpeculativeGrowthCandidateRepository,
)

router = APIRouter(prefix="/growth-candidates", tags=["growth-candidates"])


def get_candidate_repository() -> SqlAlchemySpeculativeGrowthCandidateRepository:
    return SqlAlchemySpeculativeGrowthCandidateRepository()


def get_add_use_case(
    candidate_repo: SqlAlchemySpeculativeGrowthCandidateRepository = Depends(get_candidate_repository),
    assess: AssessSpeculativeGrowthUseCase = Depends(get_speculative_growth_use_case),
) -> AddSpeculativeGrowthCandidateUseCase:
    return AddSpeculativeGrowthCandidateUseCase(candidate_repo, assess)


def get_remove_use_case(
    candidate_repo: SqlAlchemySpeculativeGrowthCandidateRepository = Depends(get_candidate_repository),
) -> RemoveSpeculativeGrowthCandidateUseCase:
    return RemoveSpeculativeGrowthCandidateUseCase(candidate_repo)


def get_list_use_case(
    candidate_repo: SqlAlchemySpeculativeGrowthCandidateRepository = Depends(get_candidate_repository),
) -> ListSpeculativeGrowthCandidatesUseCase:
    return ListSpeculativeGrowthCandidatesUseCase(candidate_repo)


def get_check_use_case(
    candidate_repo: SqlAlchemySpeculativeGrowthCandidateRepository = Depends(get_candidate_repository),
    assess: AssessSpeculativeGrowthUseCase = Depends(get_speculative_growth_use_case),
) -> CheckSpeculativeGrowthCandidatesUseCase:
    return CheckSpeculativeGrowthCandidatesUseCase(
        candidate_repo, SqlAlchemyAlertRepository(), assess
    )


def _to_schema(candidate) -> SpeculativeGrowthCandidateSchema:
    return SpeculativeGrowthCandidateSchema(
        ticker=candidate.ticker,
        added_at=candidate.added_at,
        last_growth_trend=candidate.last_growth_trend,
        last_cash_runway_months=candidate.last_cash_runway_months,
        last_market_cap=candidate.last_market_cap,
        last_checked_at=candidate.last_checked_at,
    )


def _alert_to_schema(alert) -> AlertSchema:
    return AlertSchema(
        id=alert.id, user_id=alert.user_id, ticker=alert.ticker,
        alert_type=alert.alert_type.value, message=alert.message,
        change_pct=alert.change_pct, is_read=alert.is_read, created_at=alert.created_at,
    )


@router.get("", response_model=list[SpeculativeGrowthCandidateSchema])
def list_candidates(
    user_id: str = Depends(get_authenticated_user_id),
    use_case: ListSpeculativeGrowthCandidatesUseCase = Depends(get_list_use_case),
) -> list[SpeculativeGrowthCandidateSchema]:
    return [_to_schema(c) for c in use_case.execute(user_id)]


@router.post("/check", response_model=list[AlertSchema])
def trigger_check(
    user_id: str = Depends(get_authenticated_user_id),
    use_case: CheckSpeculativeGrowthCandidatesUseCase = Depends(get_check_use_case),
) -> list[AlertSchema]:
    """Manual trigger for testing — see module docstring. Registered
    BEFORE /{ticker} deliberately: as a dynamic path segment, /{ticker}
    would otherwise match "check" as a literal ticker value and this
    route would never be reached."""
    return [_alert_to_schema(a) for a in use_case.execute(user_id)]


@router.post("/{ticker}", response_model=SpeculativeGrowthCandidateSchema)
def add_candidate(
    ticker: str,
    user_id: str = Depends(get_authenticated_user_id),
    use_case: AddSpeculativeGrowthCandidateUseCase = Depends(get_add_use_case),
) -> SpeculativeGrowthCandidateSchema:
    try:
        candidate = use_case.execute(user_id, ticker)
    except CompanyNotFoundError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"'{ticker.upper()}' has not been ingested yet — ingest it first.",
        ) from exc
    return _to_schema(candidate)


@router.delete("/{ticker}")
def remove_candidate(
    ticker: str,
    user_id: str = Depends(get_authenticated_user_id),
    use_case: RemoveSpeculativeGrowthCandidateUseCase = Depends(get_remove_use_case),
) -> dict[str, bool]:
    removed = use_case.execute(user_id, ticker)
    if not removed:
        raise HTTPException(
            status_code=404, detail=f"'{ticker.upper()}' is not on your candidate list."
        )
    return {"removed": True}
