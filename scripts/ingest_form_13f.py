"""Run Form 13F quarterly bulk ingestion as a standalone batch job.

Deliberately NOT an API endpoint: a single quarter's zip is 90+ MB and
the information table alone can run into the hundreds of thousands of
rows across thousands of filers — well past any sane HTTP request
timeout, exactly the same reasoning as scripts/ingest_sp500.py.

Usage:
    python scripts/ingest_form_13f.py --period-label 2026q1 --period-of-report 2026-03-31

    Find the correct --period-label for a given quarter from the real
    download links at:
    https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets
    Recent archives use a 3-month-window label like
    "01mar2026-31may2026" rather than a clean "2026q1" -- pass
    whatever label appears in the actual filename on that page.

Requires DATABASE_URL set in the environment (.env is loaded
automatically via the app's existing Settings). No API key needed for
SEC EDGAR itself -- only a compliant User-Agent, already configured via
SEC_EDGAR_USER_AGENT / the Settings default.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.application.use_cases.ingest_form_13f_quarter import IngestForm13FQuarterUseCase
from src.infrastructure.config import get_settings
from src.infrastructure.data_providers.sec_form_13f_downloader import SecForm13FDownloader
from src.infrastructure.persistence.database import init_db
from src.infrastructure.persistence.institutional_holding_repository_impl import (
    SqlAlchemyInstitutionalHoldingRepository,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--period-label", required=True,
        help='SEC\'s own file-naming label, e.g. "2026q1" or "01mar2026-31may2026" '
        '-- copy exactly from the real download link filename.',
    )
    parser.add_argument(
        "--period-of-report", required=True,
        help='The actual quarter-end date this data represents, YYYY-MM-DD, e.g. "2026-03-31".',
    )
    parser.add_argument(
        "--no-replace", action="store_true",
        help="Skip deleting existing rows for this period first (default: replace, "
        "so re-running an already-loaded period is idempotent rather than duplicating rows).",
    )
    args = parser.parse_args()

    try:
        period_of_report = date.fromisoformat(args.period_of_report)
    except ValueError:
        print(f"--period-of-report must be YYYY-MM-DD, got: {args.period_of_report}")
        return 1

    settings = get_settings()
    init_db()

    downloader = SecForm13FDownloader(settings=settings)
    repository = SqlAlchemyInstitutionalHoldingRepository()
    use_case = IngestForm13FQuarterUseCase(downloader, repository)

    try:
        result = use_case.execute(
            args.period_label, period_of_report, replace_existing=not args.no_replace,
        )
    except Exception as exc:  # noqa: BLE001 — top-level script boundary, must report clearly
        print(f"\nINGESTION FAILED: {exc}")
        return 1

    print(f"\n{'='*60}")
    print("FORM 13F INGESTION COMPLETE")
    print(f"  Period:              {result.period_label} ({result.period_of_report})")
    print(f"  Submissions parsed:  {result.submissions_parsed}")
    print(f"  Submissions kept:    {result.submissions_kept} (after de-duplicating amendments, excluding 13F-NT)")
    print(f"  Existing rows deleted: {result.holdings_deleted}")
    print(f"  Holdings inserted:   {result.holdings_inserted}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
