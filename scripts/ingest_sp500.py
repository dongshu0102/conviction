"""Run S&P 500 bulk ingestion as a standalone batch job.

Deliberately NOT an API endpoint: ~500 tickers with rate-limit-friendly
delays between requests takes many minutes, well past any sane HTTP
request timeout. This wires the same use cases and infrastructure the
API uses directly, run from the command line instead.

Usage:
    python scripts/ingest_sp500.py [--years 5] [--tickers AAPL,MSFT,...]

Requires DATABASE_URL and FMP_API_KEY set in the environment (.env is
loaded automatically via the app's existing Settings).
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Make this runnable as `python3 scripts/ingest_sp500.py` from anywhere,
# not just via `python3 -m` or with PYTHONPATH set manually — Python only
# auto-adds the script's own directory to sys.path, not the project root
# where `src/` lives.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.application.use_cases.ingest_company_data import IngestCompanyDataUseCase
from src.application.use_cases.ingest_sp500_universe import IngestSP500UniverseUseCase
from src.infrastructure.config import get_settings
from src.infrastructure.data_providers.fmp_provider import FinancialModelingPrepProvider
from src.infrastructure.persistence.company_repository_impl import (
    SqlAlchemyCompanyRepository,
)
from src.infrastructure.persistence.database import init_db
from src.infrastructure.persistence.financial_statement_repository_impl import (
    SqlAlchemyFinancialStatementRepository,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _load_tickers_file(path: str) -> list[str] | None:
    p = Path(path)
    if not p.exists():
        logger.warning(
            "Ticker file not found at %s — falling back to live FMP constituent "
            "endpoint (requires plan access to /stable/sp500-constituent).",
            path,
        )
        return None
    tickers = [
        line.strip().upper()
        for line in p.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    logger.info("Loaded %d tickers from %s", len(tickers), path)
    return tickers


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", type=int, default=5)
    parser.add_argument(
        "--tickers",
        type=str,
        default=None,
        help="Comma-separated ticker list to override the default source "
        "(useful for retrying just the failures from a previous run)",
    )
    parser.add_argument(
        "--tickers-file",
        type=str,
        default="scripts/sp500_tickers.txt",
        help="Path to a newline-separated ticker file, used when --tickers "
        "is not given and the live FMP constituent endpoint isn't available "
        "on your plan. One ticker per line, '#' comments allowed.",
    )
    args = parser.parse_args()

    settings = get_settings()
    init_db()

    provider = FinancialModelingPrepProvider(settings=settings)
    company_repo = SqlAlchemyCompanyRepository()
    statement_repo = SqlAlchemyFinancialStatementRepository()

    ingest_company = IngestCompanyDataUseCase(provider, company_repo, statement_repo)
    ingest_universe = IngestSP500UniverseUseCase(provider, ingest_company)

    tickers = args.tickers.split(",") if args.tickers else _load_tickers_file(args.tickers_file)
    result = ingest_universe.execute(years=args.years, tickers=tickers)

    print(f"\n{'='*60}")
    print(f"BULK INGESTION COMPLETE")
    print(f"  Total tickers:  {result.total_tickers}")
    print(f"  Succeeded:      {result.success_count}")
    print(f"  Failed:         {result.failure_count}")

    if result.failed:
        print(f"\nFAILED TICKERS:")
        for f in result.failed:
            print(f"  {f.ticker}: {f.error[:120]} (after {f.attempts} attempt(s))")
        print(
            "\nRe-run just these with:\n"
            f"  python scripts/ingest_sp500.py --tickers "
            f"{','.join(f.ticker for f in result.failed)}"
        )

    return 0 if result.failure_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
