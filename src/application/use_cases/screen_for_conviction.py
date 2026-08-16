"""Use case: scan an entire universe of tickers (the ingested S&P 500,
by default, same tickers admin.py's own factor-snapshot refresh uses)
for Conviction Summary signals, storing one lightweight result row per
ticker for fast, live-call-free browsing afterward.

Genuinely slow and expensive by design -- hundreds of tickers, each
requiring several chained calls through GetConvictionSummaryUseCase
(company lookup, up to 5 detect_position_changes calls, a 13D lookup,
an insider transactions lookup). Meant to run as a background task
(see the /admin trigger endpoint), never inline in an HTTP request a
caller is waiting on.

Partial-failure isolation, same principle as IngestSp500UniverseUseCase:
one ticker's genuine, unexpected failure (a transient API error, a
malformed record) must never abort the other ~499. Every ticker's
outcome is captured independently and the batch always completes with
whatever succeeded.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.application.use_cases.get_conviction_summary import GetConvictionSummaryUseCase
from src.domain.entities.conviction_summary import ConvictionScreenerResult
from src.domain.repositories.conviction_screener_repository import ConvictionScreenerRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TickerScanFailure:
    ticker: str
    error: str


@dataclass(frozen=True, slots=True)
class ScreenForConvictionResult:
    total_tickers: int
    succeeded: int
    failed: tuple[TickerScanFailure, ...] = field(default_factory=tuple)


class ScreenForConvictionUseCase:
    def __init__(
        self,
        get_conviction_summary: GetConvictionSummaryUseCase,
        repository: ConvictionScreenerRepository,
    ) -> None:
        self._get_conviction_summary = get_conviction_summary
        self._repository = repository

    def execute(self, tickers: list[str]) -> ScreenForConvictionResult:
        as_of = datetime.now(timezone.utc)
        results: list[ConvictionScreenerResult] = []
        failures: list[TickerScanFailure] = []

        for ticker in tickers:
            try:
                summary = self._get_conviction_summary.execute(ticker)
            except Exception as exc:
                # A genuinely unexpected failure -- GetConvictionSummaryUseCase
                # itself already degrades each of its own three signal
                # categories gracefully, so reaching this branch means
                # something outside that (a DB error, a real bug) --
                # isolated here, not allowed to abort the other tickers.
                logger.warning("Conviction screen failed for %s: %s", ticker, exc)
                failures.append(TickerScanFailure(ticker=ticker, error=str(exc)))
                continue

            results.append(ConvictionScreenerResult(
                ticker=summary.ticker, as_of=as_of,
                institutional_signal=summary.institutional_signal,
                activist_signal=summary.activist_signal,
                insider_signal=summary.insider_signal,
                signal_count=summary.signal_count,
            ))

        self._repository.save_batch(results)

        return ScreenForConvictionResult(
            total_tickers=len(tickers), succeeded=len(results), failed=tuple(failures),
        )
