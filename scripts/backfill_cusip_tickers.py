"""Run the one-time CUSIP-to-ticker backfill as a standalone batch job.

Deliberately NOT an API endpoint: ~37,000 distinct CUSIPs to resolve
(confirmed directly against real production data), well past any sane
HTTP request timeout, exactly the same reasoning as
scripts/ingest_form_13f.py.

Resumable by default: only genuinely unresolved CUSIPs are ever
attempted (see backfill_cusip_tickers's own docstring) -- re-running
this after an interruption, or after new quarters are ingested with
new CUSIPs, naturally picks up only what's actually missing.

A small, deliberate delay between each live FMP call keeps this well
under FMP's own Ultimate-tier rate limit (3,000 calls/min) without
needing to push anywhere near that ceiling for a one-time backfill --
responsible API use matters more here than raw speed.

Usage:
    python scripts/backfill_cusip_tickers.py
    python scripts/backfill_cusip_tickers.py --limit 100   # a small test run first
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.application.use_cases.backfill_cusip_tickers import BackfillCusipTickersUseCase
from src.application.use_cases.resolve_cusip_ticker import ResolveCusipTickerUseCase
from src.infrastructure.config import get_settings
from src.infrastructure.data_providers.fmp_provider import FinancialModelingPrepProvider
from src.infrastructure.persistence.cusip_ticker_map_repository_impl import (
    SqlAlchemyCusipTickerMapRepository,
)
from src.infrastructure.persistence.database import init_db
from src.infrastructure.persistence.institutional_holding_repository_impl import (
    SqlAlchemyInstitutionalHoldingRepository,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DELAY_SECONDS_BETWEEN_CALLS = 0.1  # ~10 calls/sec, ~600/min -- well under FMP's 3,000/min limit
LOG_EVERY_N_CUSIPS = 100


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Only attempt the first N genuinely unresolved cusips this run -- for a small "
        "test run before committing to the full backfill. Omit to process everything.",
    )
    args = parser.parse_args()

    settings = get_settings()
    init_db()

    holding_repository = SqlAlchemyInstitutionalHoldingRepository()
    ticker_map_repository = SqlAlchemyCusipTickerMapRepository()
    provider = FinancialModelingPrepProvider(settings=settings)
    resolver = ResolveCusipTickerUseCase(ticker_map_repository, provider)
    use_case = BackfillCusipTickersUseCase(holding_repository, ticker_map_repository, resolver)

    def on_progress(done: int, total: int) -> None:
        if done % LOG_EVERY_N_CUSIPS == 0 or done == total:
            logger.info("Backfilled %d / %d cusips", done, total)
        time.sleep(DELAY_SECONDS_BETWEEN_CALLS)

    try:
        result = use_case.execute(on_progress=on_progress, limit=args.limit)
    except Exception as exc:  # noqa: BLE001 -- top-level script boundary, must report clearly
        print(f"\nBACKFILL FAILED: {exc}")
        print("Re-run the exact same command to resume -- already-resolved cusips will be skipped.")
        return 1

    print(f"\n{'='*60}")
    print("CUSIP TICKER BACKFILL COMPLETE")
    print(f"  Total distinct cusips:           {result.total_distinct_cusips}")
    print(f"  Already resolved (skipped):      {result.already_resolved}")
    print(f"  Newly attempted:                 {result.newly_attempted}")
    print(f"  Newly resolved to a real ticker: {result.newly_resolved_to_a_ticker}")
    print(f"  Newly resolved to no ticker:     {result.newly_resolved_to_no_ticker}")
    print(f"  Errors (will retry next run):    {result.errors}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
