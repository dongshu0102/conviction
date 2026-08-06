"""Run a monitoring check for one or all users, as a standalone batch job.

Deliberately NOT run inside the FastAPI app process — see the code
comment in Dockerfile about why running workers=2 caused a race
condition with create_all(). An in-process scheduler (APScheduler) would
have the identical failure mode: every worker would independently fire
the same check. A cron-invoked script has no such issue, and follows
the same pattern as ingest_sp500.py.

Usage:
    python scripts/run_monitoring.py --user-id alice
    python scripts/run_monitoring.py --all-users   # every user with a watchlist

Suggested cron entry (every 15 minutes during market hours):
    */15 9-16 * * 1-5 cd /path/to/conviction && .venv/bin/python scripts/run_monitoring.py --all-users
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from src.application.use_cases.assess_speculative_growth import AssessSpeculativeGrowthUseCase
from src.application.use_cases.check_speculative_growth_candidates import (
    CheckSpeculativeGrowthCandidatesUseCase,
)
from src.application.use_cases.compute_valuation import ComputeValuationUseCase
from src.application.use_cases.get_company_financials import GetCompanyFinancialsUseCase
from src.application.use_cases.run_monitoring_check import RunMonitoringCheckUseCase
from src.infrastructure.config import get_settings
from src.infrastructure.data_providers.fmp_provider import FinancialModelingPrepProvider
from src.infrastructure.persistence.company_repository_impl import SqlAlchemyCompanyRepository
from src.infrastructure.persistence.database import session_scope
from src.infrastructure.persistence.financial_statement_repository_impl import (
    SqlAlchemyFinancialStatementRepository,
)
from src.infrastructure.persistence.models import SpeculativeGrowthCandidateModel, WatchlistItemModel
from src.infrastructure.persistence.monitoring_repository_impl import (
    SqlAlchemyAlertRepository,
    SqlAlchemyPriceSnapshotRepository,
)
from src.infrastructure.persistence.speculative_growth_candidate_repository_impl import (
    SqlAlchemySpeculativeGrowthCandidateRepository,
)
from src.infrastructure.persistence.watchlist_repository_impl import (
    SqlAlchemyWatchlistRepository,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _all_user_ids_with_watchlists() -> list[str]:
    with session_scope() as session:
        rows = session.execute(select(WatchlistItemModel.user_id).distinct()).scalars().all()
        return list(rows)


def _all_user_ids_with_growth_candidates() -> list[str]:
    with session_scope() as session:
        rows = session.execute(
            select(SpeculativeGrowthCandidateModel.user_id).distinct()
        ).scalars().all()
        return list(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--user-id", type=str, help="Run monitoring for one user")
    group.add_argument(
        "--all-users", action="store_true", help="Run monitoring for every user with a watchlist"
    )
    args = parser.parse_args()

    settings = get_settings()
    provider = FinancialModelingPrepProvider(settings=settings)
    watchlist_repo = SqlAlchemyWatchlistRepository()
    snapshot_repo = SqlAlchemyPriceSnapshotRepository()
    alert_repo = SqlAlchemyAlertRepository()
    use_case = RunMonitoringCheckUseCase(watchlist_repo, snapshot_repo, alert_repo, provider)

    company_repo = SqlAlchemyCompanyRepository()
    statement_repo = SqlAlchemyFinancialStatementRepository()
    get_financials = GetCompanyFinancialsUseCase(company_repo, statement_repo)
    compute_valuation = ComputeValuationUseCase(get_financials, provider)
    assess = AssessSpeculativeGrowthUseCase(get_financials, compute_valuation)
    candidate_repo = SqlAlchemySpeculativeGrowthCandidateRepository()
    growth_check_use_case = CheckSpeculativeGrowthCandidatesUseCase(
        candidate_repo, alert_repo, assess
    )

    if args.all_users:
        user_ids = sorted(
            set(_all_user_ids_with_watchlists()) | set(_all_user_ids_with_growth_candidates())
        )
    else:
        user_ids = [args.user_id]
    logger.info("Running monitoring check for %d user(s)", len(user_ids))

    total_alerts = 0
    for user_id in user_ids:
        alerts = use_case.execute(user_id)
        total_alerts += len(alerts)
        for alert in alerts:
            logger.info("ALERT [%s]: %s", user_id, alert.message)

        growth_alerts = growth_check_use_case.execute(user_id)
        total_alerts += len(growth_alerts)
        for alert in growth_alerts:
            logger.info("ALERT [%s]: %s", user_id, alert.message)

    print(f"\nMonitoring check complete: {len(user_ids)} user(s), {total_alerts} new alert(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
