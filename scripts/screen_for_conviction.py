"""Run the full-universe Conviction Summary screener as a standalone
batch job.

Deliberately NOT relied upon as an in-app background task: a real,
confirmed production incident tonight showed the POST /screen
endpoint's FastAPI BackgroundTask genuinely dying silently mid-scan --
no exception logged, no completion logged, just gone -- almost
certainly killed by an AWS App Runner container lifecycle event
(a restart, a health-check-driven recycle) partway through a run that,
at the pace actually observed against real tickers, was well on track
to take over an hour for the full S&P 500. The API endpoint still
exists (useful for a small, quick scan, or once/if that reliability
gap is addressed some other way), but this script is the reliable path
for a genuine, full run -- exactly the same reasoning, and the same
proven pattern, as scripts/backfill_cusip_tickers.py, which ran
successfully for hours tonight as a standalone process, independent of
the web server's own container lifecycle.

Usage:
    python scripts/screen_for_conviction.py
    python scripts/screen_for_conviction.py --limit 20   # a small test run first
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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
from src.infrastructure.persistence.database import init_db
from src.infrastructure.persistence.institutional_holding_repository_impl import (
    SqlAlchemyInstitutionalHoldingRepository,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

LOG_EVERY_N_TICKERS = 10


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Only scan the first N ingested tickers this run -- for a small "
        "test run before committing to the full S&P 500. Omit to process everything.",
    )
    args = parser.parse_args()

    settings = get_settings()
    init_db()

    provider = FinancialModelingPrepProvider(settings=settings)
    company_repo = SqlAlchemyCompanyRepository()
    holding_repo = SqlAlchemyInstitutionalHoldingRepository()

    get_conviction_summary = GetConvictionSummaryUseCase(
        get_institutional_holders=GetInstitutionalHoldersUseCase(holding_repo, provider),
        detect_position_changes=DetectPositionChangesUseCase(holding_repo, provider),
        get_beneficial_ownership_disclosures=GetBeneficialOwnershipDisclosuresUseCase(provider),
        get_insider_transactions=GetInsiderTransactionsUseCase(provider),
        company_repository=company_repo,
    )
    use_case = ScreenForConvictionUseCase(get_conviction_summary, SqlAlchemyConvictionScreenerRepository())

    tickers = [c.ticker for c in company_repo.list_all()]
    if args.limit is not None:
        tickers = tickers[: args.limit]
    logger.info("Starting conviction screen: %d tickers", len(tickers))

    start = time.time()

    def on_progress(done: int, total: int) -> None:
        if done % LOG_EVERY_N_TICKERS == 0 or done == total:
            elapsed = time.time() - start
            rate = done / elapsed if elapsed > 0 else 0
            remaining = (total - done) / rate if rate > 0 else float("inf")
            logger.info(
                "Screened %d / %d tickers (%.1f/min, ~%.0f min remaining)",
                done, total, rate * 60, remaining / 60,
            )

    try:
        result = use_case.execute(tickers, on_progress=on_progress)
    except Exception as exc:  # noqa: BLE001 -- top-level script boundary, must report clearly
        print(f"\nSCREEN FAILED: {exc}")
        print("Any tickers already scanned before the failure were NOT saved -- "
              "save_batch only runs once, at the very end. Re-run to try again.")
        return 1

    elapsed_minutes = (time.time() - start) / 60
    print(f"\n{'='*60}")
    print("CONVICTION SCREEN COMPLETE")
    print(f"  Total tickers:     {result.total_tickers}")
    print(f"  Succeeded:         {result.succeeded}")
    print(f"  Failed:            {len(result.failed)}")
    print(f"  Elapsed:           {elapsed_minutes:.1f} minutes")
    if result.failed:
        print("\n  Failures:")
        for f in result.failed[:20]:
            print(f"    {f.ticker}: {f.error}")
        if len(result.failed) > 20:
            print(f"    ... and {len(result.failed) - 20} more")

    return 0


if __name__ == "__main__":
    sys.exit(main())
