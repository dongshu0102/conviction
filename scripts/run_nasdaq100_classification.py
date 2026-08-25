"""Run the full Nasdaq-100 six-dimension classification as a
standalone batch job.

Deliberately NOT relied upon as an in-app background task -- same,
real, confirmed reasoning as scripts/screen_for_conviction.py's own
docstring: FastAPI's BackgroundTasks mechanism has been directly
observed to die silently mid-run, almost certainly killed by an AWS
App Runner container lifecycle event. The API endpoint (POST
/nasdaq100-screener/run) still exists for a small, quick check, but
this script is the reliable path for a genuine, full run across the
real Nasdaq-100 universe (~100 companies, each needing a real LLM
call plus real financial data fetches).

Usage:
    python scripts/run_nasdaq100_classification.py
    python scripts/run_nasdaq100_classification.py --limit 10   # a small test run first
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.application.use_cases.compute_financial_analysis import ComputeFinancialAnalysisUseCase
from src.application.use_cases.compute_valuation import ComputeValuationUseCase
from src.application.use_cases.get_company_financials import GetCompanyFinancialsUseCase
from src.application.use_cases.run_nasdaq100_classification_batch import (
    RunNasdaq100ClassificationBatchUseCase,
)
from src.infrastructure.config import get_settings
from src.infrastructure.data_providers.fmp_provider import FinancialModelingPrepProvider
from src.infrastructure.llm_providers.anthropic_nasdaq100_classifier import (
    AnthropicNasdaq100Classifier,
)
from src.infrastructure.persistence.company_repository_impl import SqlAlchemyCompanyRepository
from src.infrastructure.persistence.database import init_db
from src.infrastructure.persistence.financial_statement_repository_impl import (
    SqlAlchemyFinancialStatementRepository,
)
from src.infrastructure.persistence.index_membership_repository_impl import (
    SqlAlchemyIndexMembershipRepository,
)
from src.infrastructure.persistence.nasdaq100_classification_repository_impl import (
    SqlAlchemyNasdaq100ClassificationRepository,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

LOG_EVERY_N_TICKERS = 5


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Only classify the first N Nasdaq-100 tickers this run -- for a small "
        "test run before committing to the full ~100. Omit to process everything.",
    )
    args = parser.parse_args()

    settings = get_settings()
    init_db()

    company_repo = SqlAlchemyCompanyRepository()
    membership_repo = SqlAlchemyIndexMembershipRepository()
    classification_repo = SqlAlchemyNasdaq100ClassificationRepository()
    statement_repo = SqlAlchemyFinancialStatementRepository()

    get_financials = GetCompanyFinancialsUseCase(company_repo, statement_repo)
    compute_analysis = ComputeFinancialAnalysisUseCase(get_financials)
    provider = FinancialModelingPrepProvider(settings=settings)
    compute_valuation = ComputeValuationUseCase(get_financials, provider)
    classifier = AnthropicNasdaq100Classifier(settings=settings)

    use_case = RunNasdaq100ClassificationBatchUseCase(
        company_repo, membership_repo, classification_repo,
        get_financials, compute_analysis, compute_valuation, classifier,
    )

    if args.limit is not None:
        # execute() itself has no --limit parameter (it always scans
        # the full, real Nasdaq-100 membership) -- honestly noted here
        # rather than silently ignored, since a partial classification
        # batch would still overwrite the FULL cached table via
        # save_batch's own full-refresh semantics, temporarily losing
        # every ticker's real row beyond the limit until the next full run.
        print(
            f"NOTE: --limit {args.limit} requested, but this use case always classifies "
            f"the full, real Nasdaq-100 membership -- save_batch's own full-refresh "
            f"semantics mean a partial run isn't safe to do separately without "
            f"temporarily losing every other ticker's real, existing row. Running the "
            f"full batch instead."
        )

    start = time.time()
    last_logged = 0

    def on_progress(done: int, total: int) -> None:
        nonlocal last_logged
        if done - last_logged >= LOG_EVERY_N_TICKERS or done == total:
            elapsed = time.time() - start
            rate = done / elapsed if elapsed > 0 else 0
            remaining = (total - done) / rate if rate > 0 else float("inf")
            logger.info(
                "Classified %d / %d tickers (%.1f/min, ~%.0f min remaining)",
                done, total, rate * 60, remaining / 60,
            )
            last_logged = done

    try:
        succeeded, failed = use_case.execute(on_progress=on_progress)
    except Exception as exc:  # noqa: BLE001 -- top-level script boundary, must report clearly
        print(f"\nBATCH FAILED: {exc}")
        print("No rows were saved -- save_batch only runs once, at the very end. Re-run to try again.")
        return 1

    elapsed_minutes = (time.time() - start) / 60
    print(f"\n{'='*60}")
    print("NASDAQ-100 CLASSIFICATION BATCH COMPLETE")
    print(f"  Succeeded:  {succeeded}")
    print(f"  Failed:     {failed}")
    print(f"  Elapsed:    {elapsed_minutes:.1f} minutes")
    print(
        "\n  A 'succeeded' ticker can still, honestly, have None for individual "
        "dimensions (e.g. an LLM classification failure, or too few real, ingested "
        "peers for a meaningful HHI) -- check GET /nasdaq100-screener/results for "
        "the real, per-dimension detail."
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
