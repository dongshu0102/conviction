"""Nasdaq-100 six-dimension screener -- GICS industry, market
concentration/HHI, value chain position, business model, factor
segmentation, and market cap tier/maturity stage.

POST /run triggers a full, background batch run across every real,
ingested Nasdaq-100 company, storing one row per ticker.
GET /results reads those stored rows back, with an optional,
exact-match filter on each of the six dimensions independently.

Same background-task + non-blocking lock pattern as the Conviction
Screener's own POST /screen, including the same, real, confirmed
reliability caveat: FastAPI's BackgroundTasks mechanism has been
directly observed to die silently mid-run on a container restart. For
a genuine, full, reliable run, use a standalone script (matching
scripts/screen_for_conviction.py's own proven pattern) instead of
this endpoint alone.
"""
from __future__ import annotations

import logging
import threading

from fastapi import APIRouter, BackgroundTasks, Depends, Query

from src.api.auth import get_admin_user_id
from src.api.routers.companies import get_company_repository, get_statement_repository
from src.api.routers.conviction_summary import get_index_membership_repository
from src.api.schemas import (
    Nasdaq100ClassificationRowSchema,
    Nasdaq100ScreenerResponseSchema,
    RunNasdaq100BatchResponseSchema,
)
from src.application.use_cases.compute_financial_analysis import ComputeFinancialAnalysisUseCase
from src.application.use_cases.compute_valuation import ComputeValuationUseCase
from src.application.use_cases.get_company_financials import GetCompanyFinancialsUseCase
from src.application.use_cases.run_nasdaq100_classification_batch import (
    RunNasdaq100ClassificationBatchUseCase,
)
from src.infrastructure.config import get_settings
from src.infrastructure.data_providers.fmp_provider import FinancialModelingPrepProvider
from src.infrastructure.llm_providers.anthropic_nasdaq100_classifier import (
    AnthropicNasdaq100Classifier,
)
from src.infrastructure.persistence.company_repository_impl import SqlAlchemyCompanyRepository
from src.infrastructure.persistence.financial_statement_repository_impl import (
    SqlAlchemyFinancialStatementRepository,
)
from src.infrastructure.persistence.index_membership_repository_impl import (
    SqlAlchemyIndexMembershipRepository,
)
from src.infrastructure.persistence.nasdaq100_classification_repository_impl import (
    SqlAlchemyNasdaq100ClassificationRepository,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/nasdaq100-screener", tags=["nasdaq100-screener"])

# In-memory, so it only coordinates within a single running container --
# same acknowledged limitation as the Conviction Screener's own lock.
_batch_lock = threading.Lock()


def get_nasdaq100_classification_repository() -> SqlAlchemyNasdaq100ClassificationRepository:
    return SqlAlchemyNasdaq100ClassificationRepository()


def _run_batch(
    company_repo: SqlAlchemyCompanyRepository,
    membership_repo: SqlAlchemyIndexMembershipRepository,
    classification_repo: SqlAlchemyNasdaq100ClassificationRepository,
    statement_repo: SqlAlchemyFinancialStatementRepository,
) -> None:
    """The actual background work. Runs after the HTTP response has
    already been sent -- same tradeoff as the Conviction Screener's
    own background task."""
    try:
        settings = get_settings()
        get_financials = GetCompanyFinancialsUseCase(company_repo, statement_repo)
        compute_analysis = ComputeFinancialAnalysisUseCase(get_financials)
        provider = FinancialModelingPrepProvider(settings=settings)
        compute_valuation = ComputeValuationUseCase(get_financials, provider)
        classifier = AnthropicNasdaq100Classifier(settings=settings)
        use_case = RunNasdaq100ClassificationBatchUseCase(
            company_repo, membership_repo, classification_repo,
            get_financials, compute_analysis, compute_valuation, classifier,
        )
        logger.info("Nasdaq-100 classification batch starting")
        succeeded, failed = use_case.execute()
        logger.info("Nasdaq-100 classification batch complete: %d succeeded, %d failed", succeeded, failed)
    except Exception:
        logger.exception("Nasdaq-100 classification batch failed")
    finally:
        _batch_lock.release()


@router.post("/run", response_model=RunNasdaq100BatchResponseSchema)
def trigger_nasdaq100_batch(
    background_tasks: BackgroundTasks,
    admin_user_id: str = Depends(get_admin_user_id),
    company_repo: SqlAlchemyCompanyRepository = Depends(get_company_repository),
    membership_repo: SqlAlchemyIndexMembershipRepository = Depends(get_index_membership_repository),
    classification_repo: SqlAlchemyNasdaq100ClassificationRepository = Depends(
        get_nasdaq100_classification_repository
    ),
    statement_repo: SqlAlchemyFinancialStatementRepository = Depends(get_statement_repository),
) -> RunNasdaq100BatchResponseSchema:
    if not _batch_lock.acquire(blocking=False):
        return RunNasdaq100BatchResponseSchema(
            status="already_running",
            message="A Nasdaq-100 classification batch is already in progress. Wait for it to finish.",
        )
    background_tasks.add_task(_run_batch, company_repo, membership_repo, classification_repo, statement_repo)
    return RunNasdaq100BatchResponseSchema(
        status="started",
        message=(
            "Nasdaq-100 classification batch started in the background. HONEST CAVEAT: "
            "FastAPI's BackgroundTasks mechanism has been confirmed to die silently on a "
            "container restart mid-run elsewhere in this app -- for a genuine, reliable "
            "full run, prefer a standalone script instead. Check GET "
            "/nasdaq100-screener/results afterward; the as_of timestamp on any row "
            "confirms completion."
        ),
    )


@router.get("/results", response_model=Nasdaq100ScreenerResponseSchema)
def get_nasdaq100_screener_results(
    industry: str | None = Query(None),
    market_structure_category: str | None = Query(None),
    value_chain_position: str | None = Query(None),
    business_model: str | None = Query(None),
    market_cap_tier: str | None = Query(None),
    maturity_stage: str | None = Query(None),
    repository: SqlAlchemyNasdaq100ClassificationRepository = Depends(
        get_nasdaq100_classification_repository
    ),
) -> Nasdaq100ScreenerResponseSchema:
    results = repository.get_all(
        industry=industry, market_structure_category=market_structure_category,
        value_chain_position=value_chain_position, business_model=business_model,
        market_cap_tier=market_cap_tier, maturity_stage=maturity_stage,
    )
    return Nasdaq100ScreenerResponseSchema(
        results=[
            Nasdaq100ClassificationRowSchema(
                ticker=r.ticker, as_of=r.as_of, industry=r.industry,
                market_structure_category=r.market_structure_category, hhi=r.hhi,
                value_chain_position=r.value_chain_position, business_model=r.business_model,
                market_cap_tier=r.market_cap_tier, maturity_stage=r.maturity_stage,
                market_cap=r.market_cap, revenue_growth=r.revenue_growth,
            )
            for r in results
        ],
    )
