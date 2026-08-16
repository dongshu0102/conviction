"""Conviction Summary -- combines three genuinely independent SEC
disclosure regimes (13F institutional accumulation, 13D activist
intent, and Form 4 insider buying) into one, honest summary for a
single ticker.

Deliberately platform-wide, not per-user, same rationale as
institutional_holdings.py, beneficial_ownership.py, and
insider_transactions.py: this is public SEC/market data, identical for
every user.

Also hosts the market-wide screener: POST /screen triggers a full,
background scan of every ingested (S&P 500) ticker, storing one
lightweight result row per ticker; GET /screen-results reads those
stored rows back, fast and free of further live calls. Same
background-task + non-blocking lock pattern as admin.py's own
refresh-factor-snapshot endpoint, including the same, real, confirmed
reason for the lock: nothing would otherwise stop repeated triggers
from stacking multiple concurrent, genuinely expensive (~4,000 live
API calls) scans against the same ~500 tickers.
"""
from __future__ import annotations

import logging
import threading

from fastapi import APIRouter, BackgroundTasks, Depends, Query

from src.api.auth import get_admin_user_id
from src.api.schemas import (
    BeneficialOwnershipDisclosureSchema,
    ConvictionScreenerResultSchema,
    ConvictionScreenerResultsResponseSchema,
    ConvictionSummaryResponseSchema,
    InsiderTransactionSchema,
    InstitutionalHolderSignalSchema,
    ScreenForConvictionResponseSchema,
)
from src.application.use_cases.detect_position_changes import DetectPositionChangesUseCase
from src.application.use_cases.get_beneficial_ownership_disclosures import (
    GetBeneficialOwnershipDisclosuresUseCase,
)
from src.application.use_cases.get_conviction_summary import GetConvictionSummaryUseCase
from src.application.use_cases.get_insider_transactions import GetInsiderTransactionsUseCase
from src.application.use_cases.get_institutional_holders import GetInstitutionalHoldersUseCase
from src.application.use_cases.screen_for_conviction import ScreenForConvictionUseCase
from src.infrastructure.config import get_settings
from src.infrastructure.data_providers.fmp_provider import FinancialModelingPrepProvider
from src.infrastructure.persistence.company_repository_impl import SqlAlchemyCompanyRepository
from src.infrastructure.persistence.conviction_screener_repository_impl import (
    SqlAlchemyConvictionScreenerRepository,
)
from src.infrastructure.persistence.institutional_holding_repository_impl import (
    SqlAlchemyInstitutionalHoldingRepository,
)

logger = logging.getLogger(__name__)

# Same rationale as admin.py's own _refresh_lock: in-memory, so it
# only coordinates within a single running container -- acceptable for
# now given this is a single-instance service, same caveat as that
# lock's own docstring.
_screen_lock = threading.Lock()

router = APIRouter(prefix="/conviction-summary", tags=["conviction-summary"])


def get_data_provider() -> FinancialModelingPrepProvider:
    return FinancialModelingPrepProvider(settings=get_settings())


def get_conviction_summary_use_case(
    provider: FinancialModelingPrepProvider = Depends(get_data_provider),
) -> GetConvictionSummaryUseCase:
    repository = SqlAlchemyInstitutionalHoldingRepository()
    return GetConvictionSummaryUseCase(
        get_institutional_holders=GetInstitutionalHoldersUseCase(repository, provider),
        detect_position_changes=DetectPositionChangesUseCase(repository, provider),
        get_beneficial_ownership_disclosures=GetBeneficialOwnershipDisclosuresUseCase(provider),
        get_insider_transactions=GetInsiderTransactionsUseCase(provider),
        company_repository=SqlAlchemyCompanyRepository(),
    )


@router.get("", response_model=ConvictionSummaryResponseSchema)
def get_conviction_summary(
    ticker: str = Query(..., min_length=1, description="Ticker symbol, e.g. \"AAPL\"."),
    use_case: GetConvictionSummaryUseCase = Depends(get_conviction_summary_use_case),
) -> ConvictionSummaryResponseSchema:
    result = use_case.execute(ticker)

    return ConvictionSummaryResponseSchema(
        ticker=result.ticker,
        institutional_holders=[
            InstitutionalHolderSignalSchema(
                filer_name=h.filer_name, current_shares=h.current_shares,
                current_value_usd=h.current_value_usd, is_increasing=h.is_increasing,
            )
            for h in result.institutional_holders
        ],
        institutional_signal=result.institutional_signal,
        activist_disclosures_13d=[
            BeneficialOwnershipDisclosureSchema(
                cik=d.cik, filing_date=d.filing_date, accepted_date=d.accepted_date,
                cusip=d.cusip, name_of_reporting_person=d.name_of_reporting_person,
                citizenship_or_place_of_organization=d.citizenship_or_place_of_organization,
                sole_voting_power=d.sole_voting_power, shared_voting_power=d.shared_voting_power,
                sole_dispositive_power=d.sole_dispositive_power, shared_dispositive_power=d.shared_dispositive_power,
                amount_beneficially_owned=d.amount_beneficially_owned, percent_of_class=d.percent_of_class,
                type_of_reporting_person=d.type_of_reporting_person, form_type=d.form_type,
                source_url=d.source_url,
            )
            for d in result.activist_disclosures_13d
        ],
        activist_signal=result.activist_signal,
        insider_purchases=[
            InsiderTransactionSchema(
                filing_date=t.filing_date, transaction_date=t.transaction_date,
                reporting_cik=t.reporting_cik, company_cik=t.company_cik,
                reporting_name=t.reporting_name, type_of_owner=t.type_of_owner,
                transaction_type=t.transaction_type, acquisition_or_disposition=t.acquisition_or_disposition,
                direct_or_indirect=t.direct_or_indirect, security_name=t.security_name,
                securities_transacted=t.securities_transacted, securities_owned=t.securities_owned,
                price=t.price, source_url=t.source_url,
            )
            for t in result.insider_purchases
        ],
        insider_signal=result.insider_signal,
        signal_count=result.signal_count,
    )


def get_company_repository() -> SqlAlchemyCompanyRepository:
    return SqlAlchemyCompanyRepository()


def _run_conviction_screen(
    provider: FinancialModelingPrepProvider, company_repo: SqlAlchemyCompanyRepository,
) -> None:
    """The actual background work. Runs after the HTTP response has
    already been sent -- same tradeoff as admin.py's own
    _run_factor_snapshot_refresh: any exception here is only visible
    in logs, never to the caller, correct for a job this long-running."""
    try:
        holding_repo = SqlAlchemyInstitutionalHoldingRepository()
        get_conviction_summary = GetConvictionSummaryUseCase(
            get_institutional_holders=GetInstitutionalHoldersUseCase(holding_repo, provider),
            detect_position_changes=DetectPositionChangesUseCase(holding_repo, provider),
            get_beneficial_ownership_disclosures=GetBeneficialOwnershipDisclosuresUseCase(provider),
            get_insider_transactions=GetInsiderTransactionsUseCase(provider),
            company_repository=company_repo,
        )
        use_case = ScreenForConvictionUseCase(get_conviction_summary, SqlAlchemyConvictionScreenerRepository())
        # Same default as admin.py's own factor-snapshot refresh: use
        # already-ingested tickers (the S&P 500, ingested via
        # IngestSp500UniverseUseCase) rather than a live constituents
        # lookup that sits behind its own, separate plan entitlement.
        tickers = [c.ticker for c in company_repo.list_all()]
        logger.info("Conviction screen starting: %d tickers", len(tickers))
        result = use_case.execute(tickers)
        logger.info(
            "Conviction screen complete: %d/%d succeeded, %d failed",
            result.succeeded, result.total_tickers, len(result.failed),
        )
    except Exception:
        logger.exception("Conviction screen failed")
    finally:
        # Always release, even on failure -- a permanently-stuck lock
        # from one crashed run would be worse than the stacking
        # problem this exists to prevent.
        _screen_lock.release()


@router.post("/screen", response_model=ScreenForConvictionResponseSchema)
def trigger_conviction_screen(
    background_tasks: BackgroundTasks,
    admin_user_id: str = Depends(get_admin_user_id),
    provider: FinancialModelingPrepProvider = Depends(get_data_provider),
    company_repo: SqlAlchemyCompanyRepository = Depends(get_company_repository),
) -> ScreenForConvictionResponseSchema:
    # Non-blocking acquire: if a scan is already running, refuse rather
    # than stack a second one -- same real, confirmed rationale as
    # admin.py's own refresh lock, applied here before it becomes a
    # confirmed problem rather than after.
    if not _screen_lock.acquire(blocking=False):
        return ScreenForConvictionResponseSchema(
            status="already_running",
            message=(
                "A conviction screen is already in progress. Wait for it to "
                "finish rather than starting another -- check server logs for "
                "'screen complete', or query GET /conviction-summary/screen-results."
            ),
        )
    background_tasks.add_task(_run_conviction_screen, provider, company_repo)
    return ScreenForConvictionResponseSchema(
        status="started",
        message=(
            "Conviction screen started in the background. This takes minutes "
            "for the full S&P 500 (hundreds of tickers, thousands of live API "
            "calls). Check server logs, or query GET "
            "/conviction-summary/screen-results once it's done -- the as_of "
            "timestamp on any result will confirm completion."
        ),
    )


def get_conviction_screener_repository() -> SqlAlchemyConvictionScreenerRepository:
    return SqlAlchemyConvictionScreenerRepository()


@router.get("/screen-results", response_model=ConvictionScreenerResultsResponseSchema)
def get_conviction_screen_results(
    min_signal_count: int = Query(1, ge=0, le=3, description="Only tickers with at least this many signals."),
    repository: SqlAlchemyConvictionScreenerRepository = Depends(get_conviction_screener_repository),
) -> ConvictionScreenerResultsResponseSchema:
    results = repository.get_all(min_signal_count=min_signal_count)
    return ConvictionScreenerResultsResponseSchema(
        results=[
            ConvictionScreenerResultSchema(
                ticker=r.ticker, institutional_signal=r.institutional_signal,
                activist_signal=r.activist_signal, insider_signal=r.insider_signal,
                signal_count=r.signal_count, as_of=r.as_of,
            )
            for r in results
        ],
    )

