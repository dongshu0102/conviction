"""Use case: ingest the full S&P 500 universe.

Built on top of IngestCompanyDataUseCase rather than duplicating its
logic — this is orchestration over an existing use case, not a new data
path. Two concerns specific to bulk operation that a single-ticker
ingest doesn't need:

1. Retry/backoff: a single flaky request shouldn't be treated the same
   as a genuinely bad ticker. Transient failures (timeouts, momentary
   rate-limit blips) get retried with exponential backoff; persistent
   failures are recorded and the batch moves on.

2. Partial-failure isolation: one bad ticker (delisted, renamed,
   missing from the vendor's coverage) must never abort the other ~499.
   Every ticker's outcome is captured independently.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from src.application.interfaces.data_provider import (
    DataProviderError,
    FinancialDataProvider,
)
from src.application.use_cases.ingest_company_data import (
    IngestCompanyDataUseCase,
    IngestCompanyDataResult,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TickerFailure:
    ticker: str
    error: str
    attempts: int


@dataclass(frozen=True, slots=True)
class BatchIngestResult:
    total_tickers: int
    succeeded: list[IngestCompanyDataResult] = field(default_factory=list)
    failed: list[TickerFailure] = field(default_factory=list)

    @property
    def success_count(self) -> int:
        return len(self.succeeded)

    @property
    def failure_count(self) -> int:
        return len(self.failed)


class IngestSP500UniverseUseCase:
    def __init__(
        self,
        data_provider: FinancialDataProvider,
        ingest_company: IngestCompanyDataUseCase,
        max_retries: int = 3,
        base_backoff_seconds: float = 2.0,
        request_delay_seconds: float = 0.3,
    ) -> None:
        self._data_provider = data_provider
        self._ingest_company = ingest_company
        self._max_retries = max_retries
        self._base_backoff_seconds = base_backoff_seconds
        # Deliberate pause between tickers regardless of retry state — keeps
        # a 500-ticker batch from bursting the vendor's per-minute rate limit
        # even when every request succeeds on the first try.
        self._request_delay_seconds = request_delay_seconds

    def execute(self, years: int = 5, tickers: list[str] | None = None) -> BatchIngestResult:
        """If `tickers` is omitted, fetches current S&P 500 membership from
        the data provider. Passing an explicit list is mainly for testing
        or re-running a batch against a known subset (e.g. retrying just
        the tickers that failed last time).
        """
        universe = tickers if tickers is not None else self._data_provider.get_sp500_constituent_tickers()
        logger.info("Starting bulk ingestion for %d tickers", len(universe))

        succeeded: list[IngestCompanyDataResult] = []
        failed: list[TickerFailure] = []

        for i, ticker in enumerate(universe, start=1):
            logger.info("[%d/%d] Ingesting %s", i, len(universe), ticker)
            result, failure = self._ingest_with_retry(ticker, years)
            if result is not None:
                succeeded.append(result)
            else:
                failed.append(failure)

            time.sleep(self._request_delay_seconds)

        batch_result = BatchIngestResult(
            total_tickers=len(universe), succeeded=succeeded, failed=failed
        )
        logger.info(
            "Bulk ingestion complete: %d/%d succeeded",
            batch_result.success_count,
            batch_result.total_tickers,
        )
        return batch_result

    def _ingest_with_retry(
        self, ticker: str, years: int
    ) -> tuple[IngestCompanyDataResult | None, TickerFailure | None]:
        last_error = ""
        for attempt in range(1, self._max_retries + 1):
            try:
                result = self._ingest_company.execute(ticker, years=years)
                return result, None
            except DataProviderError as exc:
                last_error = str(exc)
                # 402/403/404 are the vendor telling us "this will never
                # work" (plan restriction, delisted ticker, wrong symbol) —
                # retrying identical requests wastes calls against a daily
                # quota. Only back off and retry on errors that plausibly
                # self-resolve (timeouts, 5xx, transient rate limits).
                if any(code in last_error for code in ("402", "403", "404")):
                    logger.warning("%s: non-retryable (%s)", ticker, last_error)
                    break
                if attempt < self._max_retries:
                    backoff = self._base_backoff_seconds * (2 ** (attempt - 1))
                    logger.warning(
                        "%s: attempt %d/%d failed (%s), retrying in %.1fs",
                        ticker, attempt, self._max_retries, last_error, backoff,
                    )
                    time.sleep(backoff)
            except Exception as exc:  # noqa: BLE001 — deliberate: any failure
                # for one ticker must not propagate and abort the batch.
                last_error = f"{type(exc).__name__}: {exc}"
                logger.exception("%s: unexpected error", ticker)
                break

        return None, TickerFailure(ticker=ticker, error=last_error, attempts=attempt)
