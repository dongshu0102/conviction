"""Use case: refresh the cached cross-sectional factor snapshot for the
whole S&P 500 universe.

This is the expensive half of factor scoring — pulling a valuation and
financial-analysis for every universe ticker, plus a momentum lookup,
then z-scoring each factor across all of them. It is meant to be called
infrequently (triggered by GetFactorScoresUseCase when the cache goes
stale), not on every request — same rationale as the price-history
"don't store what's cheap to fetch fresh" principle, inverted: THIS is
expensive, so it IS cached.

Partial-failure isolation, same as IngestSP500UniverseUseCase: one bad
ticker (delisted, missing coverage) is skipped and recorded, never
aborts the other ~499.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.application.interfaces.data_provider import (
    DataProviderError,
    FinancialDataProvider,
)
from src.application.use_cases.compute_financial_analysis import (
    ComputeFinancialAnalysisUseCase,
)
from src.application.use_cases.compute_valuation import (
    ComputeValuationUseCase,
    NoFinancialDataError,
)
from src.application.use_cases.get_company_financials import CompanyNotFoundError
from src.domain.entities.factor_scores import FactorRawMetrics, FactorScore, FactorZScores
from src.domain.repositories.factor_score_repository import FactorScoreRepository
from src.domain.services.factor_math import zscore_cross_section

logger = logging.getLogger(__name__)

# Consistent with triage_watchlist's momentum definition — ~1 calendar
# month of trading days. Duplicated rather than imported to keep this
# module's only dependency on triage_watchlist at zero; both are
# independently a legitimate "1-month momentum," and drift between the
# two would only matter if they were required to agree bit-for-bit,
# which nothing here depends on.
TRADING_DAYS_1M = 21


@dataclass(frozen=True, slots=True)
class TickerFactorFailure:
    ticker: str
    error: str


@dataclass(frozen=True, slots=True)
class BatchFactorRefreshResult:
    total_tickers: int
    succeeded: int
    failed: list[TickerFactorFailure] = field(default_factory=list)
    as_of: datetime | None = None


class ComputeUniverseFactorSnapshotUseCase:
    def __init__(
        self,
        data_provider: FinancialDataProvider,
        compute_valuation: ComputeValuationUseCase,
        compute_analysis: ComputeFinancialAnalysisUseCase,
        factor_repo: FactorScoreRepository,
        request_delay_seconds: float = 0.5,
        max_retries: int = 3,
        base_backoff_seconds: float = 2.0,
    ) -> None:
        self._data_provider = data_provider
        self._compute_valuation = compute_valuation
        self._compute_analysis = compute_analysis
        self._factor_repo = factor_repo
        self._request_delay_seconds = request_delay_seconds
        self._max_retries = max_retries
        self._base_backoff_seconds = base_backoff_seconds

    def execute(self, tickers: list[str] | None = None) -> BatchFactorRefreshResult:
        """If `tickers` is omitted, fetches current S&P 500 membership
        from the data provider's live constituents endpoint. Passing an
        explicit list bypasses that endpoint entirely — useful when it
        isn't available on the current plan tier, since the tickers
        already ingested into CompanyRepository are just as valid a
        universe to score (same override pattern as
        IngestSP500UniverseUseCase.execute)."""
        tickers = tickers if tickers is not None else self._data_provider.get_sp500_constituent_tickers()
        as_of = datetime.now(timezone.utc)

        raw_by_ticker: dict[str, FactorRawMetrics] = {}
        failures: list[TickerFactorFailure] = []

        for ticker in tickers:
            raw, failure = self._collect_raw_with_retry(ticker)
            if raw is not None:
                raw_by_ticker[ticker] = raw
            else:
                failures.append(failure)
            time.sleep(self._request_delay_seconds)

        scores = self._zscore_universe(raw_by_ticker, as_of)
        self._factor_repo.save_batch(scores)

        return BatchFactorRefreshResult(
            total_tickers=len(tickers),
            succeeded=len(raw_by_ticker),
            failed=failures,
            as_of=as_of,
        )

    def _collect_raw_with_retry(
        self, ticker: str
    ) -> tuple[FactorRawMetrics | None, TickerFactorFailure | None]:
        """Same retry discipline as IngestSP500UniverseUseCase: 402/403/
        404 mean the vendor is telling us this will never work (plan
        restriction, delisted ticker) — retrying wastes calls against a
        rate/quota ceiling we're already bumping into. 429 and other
        transient failures get an exponential backoff retry, since a
        request that fails only because of a moment's rate-limit burst
        will very likely succeed a couple of seconds later."""
        last_error = ""
        for attempt in range(1, self._max_retries + 1):
            try:
                return self._collect_raw(ticker), None
            except (CompanyNotFoundError, NoFinancialDataError) as exc:
                # Permanently missing data — not ingested, or no
                # statements yet. Retrying wastes calls; this will not
                # resolve itself between attempts.
                last_error = str(exc)
                logger.warning("Factor snapshot: %s non-retryable (%s)", ticker, last_error)
                break
            except Exception as exc:  # noqa: BLE001 — one bad ticker must never abort the batch
                last_error = str(exc)
                if any(code in last_error for code in ("402", "403", "404")):
                    logger.warning("Factor snapshot: %s non-retryable (%s)", ticker, last_error)
                    break
                if attempt < self._max_retries:
                    backoff = self._base_backoff_seconds * (2 ** (attempt - 1))
                    logger.warning(
                        "Factor snapshot: %s attempt %d/%d failed (%s), retrying in %.1fs",
                        ticker, attempt, self._max_retries, last_error, backoff,
                    )
                    time.sleep(backoff)
        logger.warning("Factor snapshot: skipping %s: %s", ticker, last_error)
        return None, TickerFactorFailure(ticker=ticker, error=last_error)

    def _collect_raw(self, ticker: str) -> FactorRawMetrics:
        valuation = self._compute_valuation.execute(ticker)
        analysis = self._compute_analysis.execute(ticker)
        latest_year = analysis.yearly_ratios[-1] if analysis.yearly_ratios else None

        momentum = None
        if hasattr(self._data_provider, "get_daily_closes"):
            try:
                bars = self._data_provider.get_daily_closes(ticker, limit=TRADING_DAYS_1M + 1)
                if len(bars) > TRADING_DAYS_1M and bars[TRADING_DAYS_1M].close > 0:
                    baseline = bars[TRADING_DAYS_1M].close
                    momentum = (valuation.price - baseline) / baseline
            except (NotImplementedError, DataProviderError) as exc:
                logger.warning("Factor snapshot: momentum unavailable for %s: %s", ticker, exc)

        return FactorRawMetrics(
            price_to_earnings=valuation.price_to_earnings,
            return_on_equity=latest_year.return_on_equity if latest_year else None,
            revenue_growth_yoy=latest_year.revenue_growth_yoy if latest_year else None,
            momentum_1m_pct=momentum,
            market_cap=valuation.market_cap,
        )

    @staticmethod
    def _zscore_universe(
        raw_by_ticker: dict[str, FactorRawMetrics], as_of: datetime
    ) -> list[FactorScore]:
        # Value and Size are inverted: lower P/E and lower market cap
        # are the conventionally favorable direction for those two
        # factors, so a positive z-score means "attractive" uniformly
        # across all five factors.
        value_z = zscore_cross_section(
            {t: r.price_to_earnings for t, r in raw_by_ticker.items()}, invert=True
        )
        quality_z = zscore_cross_section({t: r.return_on_equity for t, r in raw_by_ticker.items()})
        growth_z = zscore_cross_section(
            {t: r.revenue_growth_yoy for t, r in raw_by_ticker.items()}
        )
        momentum_z = zscore_cross_section(
            {t: r.momentum_1m_pct for t, r in raw_by_ticker.items()}
        )
        size_z = zscore_cross_section(
            {t: r.market_cap for t, r in raw_by_ticker.items()}, invert=True
        )

        return [
            FactorScore(
                ticker=ticker,
                as_of=as_of,
                raw=raw,
                z_scores=FactorZScores(
                    value=value_z[ticker],
                    quality=quality_z[ticker],
                    growth=growth_z[ticker],
                    momentum=momentum_z[ticker],
                    size=size_z[ticker],
                ),
            )
            for ticker, raw in raw_by_ticker.items()
        ]
