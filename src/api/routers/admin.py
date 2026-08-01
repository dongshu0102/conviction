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
import threading

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])

# Confirmed in production: nothing stopped repeated POSTs from stacking
# multiple concurrent refreshes against the same 506 tickers — three in
# a row within a few minutes, each firing its own full pass of API
# calls. Wasteful (3x calls for one outcome) and actively counter-
# productive (more concurrent load = more 429s, the exact problem the
# retry logic exists to survive, not multiply). This lock refuses a
# second trigger while one is already running instead of silently
# stacking work.
#
# SCOPE: in-memory, so it only coordinates within a single running
# container. If this service ever scales to multiple instances, this
# stops being sufficient and a distributed lock (e.g. a DB-backed flag)
# would be needed instead — acceptable for now given this is a
# single-instance admin tool, not something to leave unexamined if that
# ever changes.
_refresh_lock = threading.Lock()

from src.infrastructure.persistence.database import session_scope
from src.infrastructure.persistence.models import CompanyModel, IncomeStatementModel

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
    try:
        factor_repo = SqlAlchemyFactorScoreRepository()
        use_case = ComputeUniverseFactorSnapshotUseCase(
            provider, valuation_use_case, analysis_use_case, factor_repo
        )
        # Same default as scripts/refresh_factor_snapshot.py: use
        # already-ingested tickers rather than the data provider's live
        # S&P 500 constituents endpoint, which sits behind its own plan
        # entitlement separate from ordinary fundamentals access.
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
    finally:
        # Always release, even on failure — a permanently-stuck lock
        # from one crashed run would be worse than the stacking problem
        # this exists to prevent.
        _refresh_lock.release()


@router.post("/refresh-factor-snapshot")
def refresh_factor_snapshot(
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_authenticated_user_id),
    provider: FinancialModelingPrepProvider = Depends(get_data_provider),
    valuation_use_case: ComputeValuationUseCase = Depends(get_valuation_use_case),
    analysis_use_case: ComputeFinancialAnalysisUseCase = Depends(get_analysis_use_case),
    company_repo: SqlAlchemyCompanyRepository = Depends(get_company_repository),
) -> dict[str, str]:
    # Non-blocking acquire: if a refresh is already running, refuse
    # rather than stack a second one — confirmed in production that
    # nothing previously stopped three concurrent refreshes from firing
    # within a few minutes of each other, tripling API load against
    # the same 506 tickers for no benefit.
    if not _refresh_lock.acquire(blocking=False):
        return {
            "status": "already_running",
            "message": (
                "A factor snapshot refresh is already in progress. Wait for "
                "it to finish rather than starting another — check server "
                "logs for 'refresh complete', or query "
                "GET /companies/{ticker}/factor-score once it's done."
            ),
        }
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


@router.get("/non-usd-reporters")
def list_non_usd_reporters(
    user_id: str = Depends(get_authenticated_user_id),
) -> dict[str, list[dict[str, str]]]:
    """Diagnostic endpoint: every ingested ticker whose MOST RECENT
    annual income statement reports in a currency other than USD.

    Confirmed in production that this silently corrupts every valuation
    ratio (P/E, P/S, P/B, EV/EBITDA) for that ticker — see
    ComputeValuationUseCase's currency guard, added after TSM's
    TWD-denominated EPS produced a P/E of ~1.2 when divided against its
    USD ADR price. This endpoint exists to find every OTHER ticker with
    the same latent exposure, not just the one that happened to get
    noticed.

    A direct query against the model, not the repository interface —
    this is a one-off audit tool, not a domain operation, so it doesn't
    warrant new repository surface area for a single caller.
    """
    with session_scope() as session:
        # Most recent annual statement per ticker — a company could
        # theoretically have switched reporting currency across years
        # (extremely rare), so "most recent" is the one that actually
        # matters for current valuation calculations.
        latest_per_ticker: dict[str, IncomeStatementModel] = {}
        rows = session.execute(
            select(IncomeStatementModel).where(IncomeStatementModel.period == "ANNUAL")
        ).scalars().all()
        for row in rows:
            existing = latest_per_ticker.get(row.ticker)
            if existing is None or row.fiscal_year > existing.fiscal_year:
                latest_per_ticker[row.ticker] = row

        non_usd = [
            row for row in latest_per_ticker.values()
            if (row.reported_currency or "").strip().upper() != "USD"
        ]

        tickers = [row.ticker for row in non_usd]
        names_by_ticker = {}
        if tickers:
            companies = session.execute(
                select(CompanyModel).where(CompanyModel.ticker.in_(tickers))
            ).scalars().all()
            names_by_ticker = {c.ticker: c.name for c in companies}

        return {
            "non_usd_reporters": [
                {
                    "ticker": row.ticker,
                    "name": names_by_ticker.get(row.ticker, ""),
                    "reported_currency": row.reported_currency,
                    "fiscal_year": str(row.fiscal_year),
                }
                for row in sorted(non_usd, key=lambda r: r.ticker)
            ]
        }
