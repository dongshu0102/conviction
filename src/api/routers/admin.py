"""Admin/maintenance endpoints.

These are NOT distinguished from ordinary users by role — this app has
no admin/user distinction in its auth model, so "protected" here means
"requires a valid API key," same as everything else. Good enough given
this is a single-operator instance; would need real role-based auth
before this app ever had multiple untrusted users.

The factor-snapshot refresh specifically exists here because RDS is
correctly configured with PubliclyAccessible=False — no route from
outside AWS at all — so it can only ever be triggered from inside the
running service, which already has working VPC access to it every day.
Run as a BackgroundTask, not inline: 500+ tickers even gently paced
will exceed any reasonable HTTP request timeout, the same class of
problem already fixed once for the live chat/REST path (see
get_factor_scores.py's auto_refresh default). This endpoint returns
immediately; check server logs or GET /universe/factor-snapshot-status
to see whether it actually finished.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends

from src.api.auth import get_authenticated_user_id
from src.api.routers.companies import get_analysis_use_case, get_company_repository, get_data_provider
from src.api.routers.companies import get_valuation_use_case
from src.application.use_cases.compute_financial_analysis import ComputeFinancialAnalysisUseCase
from src.application.use_cases.compute_universe_factor_snapshot import (
    ComputeUniverseFactorSnapshotUseCase,
)
from src.application.use_cases.compute_valuation import ComputeValuationUseCase
from src.infrastructure.data_providers.fmp_provider import FinancialModelingPrepProvider
from src.infrastructure.persistence.company_repository_impl import SqlAlchemyCompanyRepository
from src.infrastructure.persistence.factor_score_repository_impl import (
    SqlAlchemyFactorScoreRepository,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


def _run_factor_snapshot_refresh(
    provider: FinancialModelingPrepProvider,
    valuation_use_case: ComputeValuationUseCase,
    analysis_use_case: ComputeFinancialAnalysisUseCase,
    company_repo: SqlAlchemyCompanyRepository,
) -> None:
    """The actual background work. Runs after the HTTP response has
    already been sent — any exception here is only visible in logs,
    never to the caller, which is the correct tradeoff for a job this
    long-running; a caller waiting on the HTTP response for the
    real-time result would just time out instead."""
    factor_repo = SqlAlchemyFactorScoreRepository()
    use_case = ComputeUniverseFactorSnapshotUseCase(
        provider, valuation_use_case, analysis_use_case, factor_repo
    )
    # Same default as scripts/refresh_factor_snapshot.py: use already-
    # ingested tickers rather than the data provider's live S&P 500
    # constituents endpoint, which sits behind its own plan entitlement
    # separate from ordinary fundamentals access.
    tickers = [c.ticker for c in company_repo.list_all()]
    logger.info("Admin-triggered factor snapshot refresh starting: %d tickers", len(tickers))
    try:
        result = use_case.execute(tickers=tickers)
        logger.info(
            "Admin-triggered factor snapshot refresh complete: %d/%d scored, %d failed",
            result.succeeded, result.total_tickers, len(result.failed),
        )
    except Exception:
        logger.exception("Admin-triggered factor snapshot refresh failed")


@router.post("/refresh-factor-snapshot")
def refresh_factor_snapshot(
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_authenticated_user_id),
    provider: FinancialModelingPrepProvider = Depends(get_data_provider),
    valuation_use_case: ComputeValuationUseCase = Depends(get_valuation_use_case),
    analysis_use_case: ComputeFinancialAnalysisUseCase = Depends(get_analysis_use_case),
    company_repo: SqlAlchemyCompanyRepository = Depends(get_company_repository),
) -> dict[str, str]:
    background_tasks.add_task(
        _run_factor_snapshot_refresh, provider, valuation_use_case, analysis_use_case, company_repo
    )
    return {
        "status": "started",
        "message": (
            "Factor snapshot refresh started in the background. This takes "
            "a few minutes for the full universe. Check server logs, or "
            "query GET /companies/{ticker}/factor-score for any ticker "
            "once it's done — the as_of timestamp will confirm completion."
        ),
    }
