"""Ingest the Nasdaq-100 and Dow Jones constituents, extending this
app's universe beyond the existing S&P 500 ingestion (see
scripts/ingest_sp500.py). Reuses IngestSP500UniverseUseCase directly
rather than duplicating its retry/backoff and partial-failure
isolation logic -- that use case already accepts an explicit
`tickers` override, so it's genuinely, fully reusable for any ticker
universe, not just its namesake.

Deliberately deduplicates against tickers already ingested (mostly
via S&P 500 -- substantial real overlap exists, e.g. AAPL, MSFT,
NVDA belong to all three indices) before calling the use case, so a
re-run only spends real API calls and time on genuinely new tickers,
not on re-fetching data this app already has.

Usage:
    python scripts/ingest_nasdaq100_dowjones.py
    python scripts/ingest_nasdaq100_dowjones.py --years 5
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.application.use_cases.ingest_company_data import IngestCompanyDataUseCase
from src.application.use_cases.ingest_sp500_universe import IngestSP500UniverseUseCase
from src.infrastructure.config import get_settings
from src.infrastructure.data_providers.fmp_provider import FinancialModelingPrepProvider
from src.infrastructure.persistence.company_repository_impl import SqlAlchemyCompanyRepository
from src.infrastructure.persistence.database import init_db
from src.infrastructure.persistence.financial_statement_repository_impl import (
    SqlAlchemyFinancialStatementRepository,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", type=int, default=5)
    args = parser.parse_args()

    settings = get_settings()
    init_db()

    provider = FinancialModelingPrepProvider(settings=settings)
    company_repo = SqlAlchemyCompanyRepository()
    statement_repo = SqlAlchemyFinancialStatementRepository()

    nasdaq100 = provider.get_nasdaq100_constituent_tickers()
    dowjones = provider.get_dowjones_constituent_tickers()
    logger.info("Nasdaq-100: %d tickers, Dow Jones: %d tickers", len(nasdaq100), len(dowjones))

    already_ingested = {c.ticker for c in company_repo.list_all()}
    combined = sorted(set(nasdaq100) | set(dowjones))
    new_tickers = [t for t in combined if t not in already_ingested]
    logger.info(
        "%d combined, unique tickers across both indices; %d already ingested "
        "(mostly via S&P 500 overlap); %d genuinely new to fetch",
        len(combined), len(combined) - len(new_tickers), len(new_tickers),
    )

    if not new_tickers:
        print("Nothing new to ingest -- every Nasdaq-100 and Dow Jones ticker is already in this app's universe.")
        return 0

    ingest_company = IngestCompanyDataUseCase(provider, company_repo, statement_repo)
    ingest_universe = IngestSP500UniverseUseCase(provider, ingest_company)
    result = ingest_universe.execute(years=args.years, tickers=new_tickers)

    print(f"\n{'='*60}")
    print("NASDAQ-100 / DOW JONES INGESTION COMPLETE")
    print(f"  New tickers attempted:  {result.total_tickers}")
    print(f"  Succeeded:              {result.success_count}")
    print(f"  Failed:                 {result.failure_count}")

    if result.failed:
        print("\nFAILED TICKERS:")
        for f in result.failed:
            print(f"  {f.ticker}: {f.error[:120]} (after {f.attempts} attempt(s))")

    return 0 if result.failure_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
