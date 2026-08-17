"""Retry specific tickers that failed during a full conviction screen
run (see scripts/screen_for_conviction.py), without touching any of
the other, already-successfully-stored results.

Real, confirmed motivation, not hypothetical: tonight's own full
S&P 500 screen genuinely succeeded for 564 of 566 tickers over 12.7
hours, with 2 failures from transient, real infrastructure issues (an
SSL handshake timeout, a dropped database connection) rather than any
genuine problem with either ticker's own data. Re-running the full
screen just to fill in 2 missing rows would cost many more hours for
essentially no new information; naively re-running
screen_for_conviction.py itself with a --tickers-style override would
be actively dangerous, since save_batch() does a full, unconditional
delete of the entire table before inserting -- running it with only
the 2 retried tickers would wipe out the other 564 real results.
save_one, unlike save_batch, upserts a single ticker's row without
touching any other.

Usage:
    python scripts/retry_screen_tickers.py C MDT
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.application.use_cases.caching_detect_position_changes import (
    CachingDetectPositionChangesUseCase,
)
from src.application.use_cases.detect_position_changes import DetectPositionChangesUseCase
from src.application.use_cases.get_beneficial_ownership_disclosures import (
    GetBeneficialOwnershipDisclosuresUseCase,
)
from src.application.use_cases.get_conviction_summary import GetConvictionSummaryUseCase
from src.application.use_cases.get_insider_transactions import GetInsiderTransactionsUseCase
from src.application.use_cases.get_institutional_holders import GetInstitutionalHoldersUseCase
from src.domain.entities.conviction_summary import ConvictionScreenerResult
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tickers", nargs="+", help="Tickers to retry, e.g. C MDT")
    args = parser.parse_args()
    tickers = [t.upper() for t in args.tickers]

    settings = get_settings()
    init_db()

    provider = FinancialModelingPrepProvider(settings=settings)
    company_repo = SqlAlchemyCompanyRepository()
    holding_repo = SqlAlchemyInstitutionalHoldingRepository()
    screener_repo = SqlAlchemyConvictionScreenerRepository()

    get_conviction_summary = GetConvictionSummaryUseCase(
        get_institutional_holders=GetInstitutionalHoldersUseCase(holding_repo, provider),
        detect_position_changes=CachingDetectPositionChangesUseCase(
            DetectPositionChangesUseCase(holding_repo, provider)
        ),
        get_beneficial_ownership_disclosures=GetBeneficialOwnershipDisclosuresUseCase(provider),
        get_insider_transactions=GetInsiderTransactionsUseCase(provider),
        company_repository=company_repo,
    )

    as_of = datetime.now(timezone.utc)
    succeeded, failed = [], []
    for ticker in tickers:
        try:
            summary = get_conviction_summary.execute(ticker)
        except Exception as exc:  # noqa: BLE001 -- one ticker's failure must not abort the others
            logger.warning("Retry failed for %s: %s", ticker, exc)
            failed.append((ticker, str(exc)))
            continue

        screener_repo.save_one(ConvictionScreenerResult(
            ticker=summary.ticker, as_of=as_of,
            institutional_signal=summary.institutional_signal,
            activist_signal=summary.activist_signal,
            insider_signal=summary.insider_signal,
            signal_count=summary.signal_count,
        ))
        succeeded.append(summary.ticker)
        logger.info(
            "%s: saved (institutional=%s, activist=%s, insider=%s, signal_count=%d)",
            summary.ticker, summary.institutional_signal, summary.activist_signal,
            summary.insider_signal, summary.signal_count,
        )

    print(f"\n{'='*60}")
    print("RETRY COMPLETE")
    print(f"  Succeeded: {len(succeeded)} ({', '.join(succeeded) if succeeded else 'none'})")
    print(f"  Failed:    {len(failed)}")
    for ticker, error in failed:
        print(f"    {ticker}: {error}")

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
