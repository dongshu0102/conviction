"""Use case: triage the watchlist — rank items by attention-worthiness.

The score is a deterministic weighted composite of real, computed
signals (hand-verifiable constants below). HIGHER = more
attention-worthy; this is an urgency ranking, NOT a quality or buy
ranking — a stock can top the list because it's collapsing.

Missing data never fabricates a signal: a ticker with no prior
monitoring snapshot has day_move_pct=None (contributes 0 to the score
AND shows as absent), a ticker added before baselines existed has no
since-added or P/E-drift signal. This mirrors the missing-Greek
exclusion principle in compute_portfolio_greeks — honest incompleteness
over silent fabrication.

Weights are in percentage-point terms: a 5% day move contributes
5.0 * W_DAY_MOVE points. TARGET_CROSSED_BONUS is a flat boost because
crossing a user's own stated entry target is categorically
attention-worthy regardless of magnitude.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.application.interfaces.data_provider import (
    DataProviderError,
    FinancialDataProvider,
)
from src.domain.entities.watchlist_triage import (
    TriageSignals,
    WatchlistTriageItem,
    WatchlistTriageResult,
)
from src.domain.repositories.monitoring_repository import PriceSnapshotRepository
from src.domain.repositories.watchlist_repository import WatchlistRepository

logger = logging.getLogger(__name__)

W_DAY_MOVE = 1.0
W_MOMENTUM = 0.5
TRADING_DAYS_1M = 21  # ~one calendar month of trading days
W_SINCE_ADDED = 0.5
W_PE_DRIFT = 0.5
TARGET_CROSSED_BONUS = 10.0


class TriageWatchlistUseCase:
    def __init__(
        self,
        watchlist_repo: WatchlistRepository,
        data_provider: FinancialDataProvider,
        snapshot_repo: PriceSnapshotRepository,
        valuation_use_case=None,  # optional ComputeValuationUseCase for current P/E
    ) -> None:
        self._watchlist_repo = watchlist_repo
        self._data_provider = data_provider
        self._snapshot_repo = snapshot_repo
        self._valuation_use_case = valuation_use_case

    def execute(self, user_id: str, list_name: str | None = None) -> WatchlistTriageResult:
        items = self._watchlist_repo.list_for_user(user_id, list_name)
        triaged: list[WatchlistTriageItem] = []
        excluded: list[str] = []

        for item in items:
            try:
                quote = self._data_provider.get_quote(item.ticker)
            except DataProviderError:
                logger.warning("Triage: quote fetch failed for %s, excluding", item.ticker)
                excluded.append(item.ticker)
                continue

            current_price = quote.price
            current_pe = self._current_pe(item.ticker)
            momentum = self._momentum_1m(item.ticker, current_price)
            signals = TriageSignals(
                day_move_pct=self._day_move(item.ticker, current_price),
                move_since_added_pct=self._pct_change(item.added_price, current_price),
                momentum_1m_pct=momentum,
                pe_drift_pct=self._pct_change(item.added_pe, current_pe) if current_pe is not None else None,
                target_crossed=(
                    item.target_price is not None and current_price <= item.target_price
                ),
                current_price=current_price,
                current_pe=current_pe,
            )
            triaged.append(
                WatchlistTriageItem(
                    ticker=item.ticker,
                    list_name=item.list_name,
                    triage_score=self._score(signals),
                    signals=signals,
                    notes=item.notes,
                )
            )

        triaged.sort(key=lambda t: t.triage_score, reverse=True)

        return WatchlistTriageResult(
            user_id=user_id,
            as_of=datetime.now(timezone.utc),
            items=triaged,
            tickers_excluded=excluded,
        )

    def _day_move(self, ticker: str, current_price: float) -> float | None:
        prior = self._snapshot_repo.get_latest(ticker)
        if prior is None or prior.price <= 0:
            return None
        return (current_price - prior.price) / prior.price

    @staticmethod
    def _pct_change(baseline: float | None, current: float) -> float | None:
        if baseline is None or baseline <= 0:
            return None
        return (current - baseline) / baseline

    def _momentum_1m(self, ticker: str, current_price: float) -> float | None:
        """1-month momentum vs the close ~21 trading days ago, computed
        from live FMP EOD history (Starter-plan accessible — verified).
        hasattr-guarded so duck-typed providers without history support
        degrade to an honestly-absent signal, not a crash. There is
        deliberately no local price-history table."""
        if not hasattr(self._data_provider, "get_daily_closes"):
            return None
        try:
            bars = self._data_provider.get_daily_closes(ticker, limit=TRADING_DAYS_1M + 1)
        except (NotImplementedError, DataProviderError) as exc:
            logger.warning("Triage: momentum history unavailable for %s: %s", ticker, exc)
            return None
        if len(bars) <= TRADING_DAYS_1M:
            return None  # not enough history -> absent, never fabricated
        baseline = bars[TRADING_DAYS_1M].close
        if baseline <= 0:
            return None
        return (current_price - baseline) / baseline

    def _current_pe(self, ticker: str) -> float | None:
        if self._valuation_use_case is None:
            return None
        try:
            return self._valuation_use_case.execute(ticker).price_to_earnings
        except Exception as exc:  # best effort, same rationale as add-time baselines
            logger.warning("Triage: current P/E failed for %s: %s", ticker, exc)
            return None

    @staticmethod
    def _score(signals: TriageSignals) -> float:
        score = 0.0
        if signals.day_move_pct is not None:
            score += abs(signals.day_move_pct) * 100 * W_DAY_MOVE
        if signals.move_since_added_pct is not None:
            score += abs(signals.move_since_added_pct) * 100 * W_SINCE_ADDED
        if signals.pe_drift_pct is not None:
            score += abs(signals.pe_drift_pct) * 100 * W_PE_DRIFT
        if signals.momentum_1m_pct is not None:
            score += abs(signals.momentum_1m_pct) * 100 * W_MOMENTUM
        if signals.target_crossed:
            score += TARGET_CROSSED_BONUS
        return score
