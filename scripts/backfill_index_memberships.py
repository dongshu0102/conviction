"""Backfill index_memberships for every already-ingested company,
cross-referencing this app's real S&P 500, Nasdaq-100, and Dow Jones
constituent lists against the existing companies table.

Needed because every ticker ingested before tonight (via
scripts/ingest_sp500.py and scripts/ingest_nasdaq100_dowjones.py) was
ingested without any membership tracking at all -- this table is
brand new. Builds one combined {ticker: [index_names]} map across all
three real constituent lists before writing anything, since
save_memberships REPLACES a ticker's full membership set in one call
-- calling it once per index for the same ticker would overwrite
rather than accumulate, silently dropping every earlier index for a
ticker that belongs to more than one.

Usage:
    python scripts/backfill_index_memberships.py
"""
from __future__ import annotations

import logging
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.infrastructure.config import get_settings
from src.infrastructure.data_providers.fmp_provider import FinancialModelingPrepProvider
from src.infrastructure.persistence.company_repository_impl import SqlAlchemyCompanyRepository
from src.infrastructure.persistence.database import init_db
from src.infrastructure.persistence.index_membership_repository_impl import (
    SqlAlchemyIndexMembershipRepository,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Display-friendly names, not the raw FMP endpoint names -- these are
# what the frontend will actually render as category tags.
SP500 = "S&P 500"
NASDAQ100 = "Nasdaq-100"
DOWJONES = "Dow Jones"


def main() -> int:
    settings = get_settings()
    init_db()

    provider = FinancialModelingPrepProvider(settings=settings)
    company_repo = SqlAlchemyCompanyRepository()
    membership_repo = SqlAlchemyIndexMembershipRepository()

    sp500 = set(provider.get_sp500_constituent_tickers())
    nasdaq100 = set(provider.get_nasdaq100_constituent_tickers())
    dowjones = set(provider.get_dowjones_constituent_tickers())
    logger.info("S&P 500: %d, Nasdaq-100: %d, Dow Jones: %d", len(sp500), len(nasdaq100), len(dowjones))

    memberships: dict[str, list[str]] = defaultdict(list)
    for ticker in sp500:
        memberships[ticker].append(SP500)
    for ticker in nasdaq100:
        memberships[ticker].append(NASDAQ100)
    for ticker in dowjones:
        memberships[ticker].append(DOWJONES)

    ingested_tickers = {c.ticker for c in company_repo.list_all()}
    saved, skipped_not_ingested = 0, 0
    for ticker, index_names in memberships.items():
        if ticker not in ingested_tickers:
            # A real constituent this app hasn't ingested company data
            # for at all yet -- honestly skipped, not silently
            # recorded as a membership for a ticker with no company
            # row to attach it to (the FK would reject it anyway).
            skipped_not_ingested += 1
            continue
        membership_repo.save_memberships(ticker, index_names)
        saved += 1

    print(f"\n{'='*60}")
    print("INDEX MEMBERSHIP BACKFILL COMPLETE")
    print(f"  Tickers with memberships saved:  {saved}")
    print(f"  Skipped (constituent, but not yet ingested as a company):  {skipped_not_ingested}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
