"""Refresh the cross-sectional factor score snapshot for the whole
S&P 500 universe, as a standalone batch job.

Deliberately NOT triggered inline by a live chat/HTTP request —
GetFactorScoresUseCase defaults to auto_refresh=False specifically
because this refresh pulls valuation + financials + momentum for
500+ tickers (1000+ underlying API calls), which was confirmed in
production to be enough volume to trip the data provider's rate/plan
ceiling when fired synchronously inside a request that also has its
own timeout. Run this out-of-band instead — same pattern as
run_monitoring.py and ingest_sp500.py.

Usage:
    python scripts/refresh_factor_snapshot.py
    python scripts/refresh_factor_snapshot.py --delay 1.5   # gentler pacing

Suggested cron entry (once daily, off-peak — the cache is good for 24h
per GetFactorScoresUseCase's DEFAULT_MAX_STALENESS):
    0 5 * * * cd /path/to/fininsight && .venv/bin/python scripts/refresh_factor_snapshot.py
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.application.use_cases.compute_financial_analysis import (
    ComputeFinancialAnalysisUseCase,
)
from src.application.use_cases.compute_universe_factor_snapshot import (
    ComputeUniverseFactorSnapshotUseCase,
)
from src.application.use_cases.compute_valuation import ComputeValuationUseCase
from src.application.use_cases.get_company_financials import GetCompanyFinancialsUseCase
from src.infrastructure.config import get_settings
from src.infrastructure.data_providers.fmp_provider import FinancialModelingPrepProvider
from src.infrastructure.persistence.company_repository_impl import SqlAlchemyCompanyRepository
from src.infrastructure.persistence.factor_score_repository_impl import (
    SqlAlchemyFactorScoreRepository,
)
from src.infrastructure.persistence.financial_statement_repository_impl import (
    SqlAlchemyFinancialStatementRepository,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Gentler than the use case's own internal default (0.2s) — this script
# is meant to run unattended, off-peak, with no request timeout to race
# against, so there's no reason to rush it. Bump further with --delay if
# the data provider's plan still rate-limits at this pace.
DEFAULT_DELAY_SECONDS = 0.5


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--delay", type=float, default=DEFAULT_DELAY_SECONDS,
        help=f"Seconds to pause between tickers (default: {DEFAULT_DELAY_SECONDS})",
    )
    args = parser.parse_args()

    settings = get_settings()
    provider = FinancialModelingPrepProvider(settings=settings)
    company_repo = SqlAlchemyCompanyRepository()
    statement_repo = SqlAlchemyFinancialStatementRepository()
    factor_repo = SqlAlchemyFactorScoreRepository()

    get_financials = GetCompanyFinancialsUseCase(company_repo, statement_repo)
    compute_valuation = ComputeValuationUseCase(get_financials, provider)
    compute_analysis = ComputeFinancialAnalysisUseCase(get_financials)

    use_case = ComputeUniverseFactorSnapshotUseCase(
        provider, compute_valuation, compute_analysis, factor_repo,
        request_delay_seconds=args.delay,
    )

    logger.info("Starting factor snapshot refresh (delay=%.1fs between tickers)", args.delay)
    result = use_case.execute()

    print(
        f"\nFactor snapshot refresh complete: "
        f"{result.succeeded}/{result.total_tickers} tickers scored, "
        f"{len(result.failed)} failed, as_of={result.as_of.isoformat()}"
    )
    if result.failed:
        for failure in result.failed[:20]:
            logger.warning("FAILED [%s]: %s", failure.ticker, failure.error)
        if len(result.failed) > 20:
            logger.warning("... and %d more failures", len(result.failed) - 20)

    return 0


if __name__ == "__main__":
    sys.exit(main())
