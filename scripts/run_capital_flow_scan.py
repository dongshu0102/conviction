"""Run a capital-flow scan, as a standalone batch job.

Deliberately NOT run inside the FastAPI app process — same rationale
as run_monitoring.py: an in-process scheduler would have every worker
independently fire the same scan, and a cron-invoked script sidesteps
that entirely. Unlike run_monitoring.py, this script takes no
--user-id/--all-users flag at all: Capital Flow is a broad,
market-wide scan with no watchlist to iterate over, so there's
genuinely nothing to scope per-user.

--include-volume-scan and --include-macro-scan are both OFF by
default and meant to run on their own, less-frequent cron entries —
volume data is end-of-day (updates once per day, not every 30
minutes) and costs real per-ticker API calls (500 for the S&P 500);
macro data is quarterly/monthly. Running either on the same 30-minute
cadence as insider/political scanning would be a real, wasted cost for
data that hasn't actually changed.

Usage:
    python scripts/run_capital_flow_scan.py
    python scripts/run_capital_flow_scan.py --include-volume-scan
    python scripts/run_capital_flow_scan.py --include-macro-scan

Suggested cron entries:
    # Insider + political disclosures — every 30 minutes during market hours
    */30 9-16 * * 1-5 cd /path/to/conviction && .venv/bin/python scripts/run_capital_flow_scan.py

    # Volume — once daily, after market close
    30 16 * * 1-5 cd /path/to/conviction && .venv/bin/python scripts/run_capital_flow_scan.py --include-volume-scan

    # Macro flow — once daily is already more than enough for quarterly/monthly data
    0 7 * * 1-5 cd /path/to/conviction && .venv/bin/python scripts/run_capital_flow_scan.py --include-macro-scan
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.api.routers.capital_flow import DEFAULT_MACRO_SERIES
from src.application.use_cases.run_capital_flow_scan import RunCapitalFlowScanUseCase
from src.infrastructure.config import get_settings
from src.infrastructure.data_providers.fmp_provider import FinancialModelingPrepProvider
from src.infrastructure.data_providers.fred_provider import FredProvider
from src.infrastructure.persistence.capital_flow_repository_impl import (
    SqlAlchemyCapitalFlowRepository,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--include-volume-scan", action="store_true",
        help="Also scan the S&P 500 for unusual volume (500 real API calls — run on its own daily cron entry).",
    )
    parser.add_argument(
        "--include-macro-scan", action="store_true",
        help="Also scan real FRED balance-of-payments series for unusual moves.",
    )
    args = parser.parse_args()

    settings = get_settings()
    provider = FinancialModelingPrepProvider(settings=settings)
    capital_flow_repo = SqlAlchemyCapitalFlowRepository()

    ticker_universe = provider.get_sp500_constituent_tickers() if args.include_volume_scan else None
    fred_provider = FredProvider(settings=settings) if args.include_macro_scan else None
    macro_series = DEFAULT_MACRO_SERIES if args.include_macro_scan else None

    use_case = RunCapitalFlowScanUseCase(
        provider, capital_flow_repo,
        ticker_universe=ticker_universe,
        macro_history_provider=fred_provider, macro_series=macro_series,
    )

    logger.info(
        "Running capital flow scan (volume_scan=%s, macro_scan=%s)",
        args.include_volume_scan, args.include_macro_scan,
    )
    new_events = use_case.execute()

    for event in new_events:
        logger.info("CAPITAL FLOW [%s]: %s", event.source.value, event.headline)

    print(f"\nCapital flow scan complete: {len(new_events)} new event(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
