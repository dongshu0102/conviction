"""Use case: read factor scores, refreshing the cache only when stale.

This is the cheap half of factor scoring — composite weighting is a
weighted sum over already-computed z-scores, so it is recomputed fresh
on EVERY call regardless of cache state. Only the expensive cross-
sectional z-scoring itself is gated behind staleness — changing weights
never triggers a universe-wide refresh, only an old snapshot does.

auto_refresh=False is the default because a cold-cache refresh means
pulling valuation + financials + momentum for the ENTIRE S&P 500
universe (500+ tickers, 1000+ underlying API calls) — confirmed in
production to be enough volume to trip the data provider's rate/plan
ceiling (a 402) when triggered synchronously inside a live chat or HTTP
request, which also has its own timeout to worry about regardless.
With auto_refresh=False: a STALE-but-populated cache is served as-is
(staleness is visible via each score's as_of, already surfaced to
callers); a NEVER-populated cache raises FactorSnapshotNotReadyError
rather than attempting the expensive refresh inline. The refresh is
meant to happen out-of-band — see scripts/refresh_factor_snapshot.py —
by a caller that explicitly opts in with auto_refresh=True.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.application.use_cases.compute_universe_factor_snapshot import (
    ComputeUniverseFactorSnapshotUseCase,
)
from src.domain.entities.factor_scores import FactorWeights, RankedFactorScore
from src.domain.repositories.factor_score_repository import FactorScoreRepository
from src.domain.services.factor_math import composite_score

DEFAULT_MAX_STALENESS = timedelta(hours=24)


class FactorSnapshotNotReadyError(Exception):
    def __init__(self) -> None:
        super().__init__(
            "Factor scores have not been computed yet. This is a scheduled "
            "background refresh, not something that runs on demand — check "
            "back shortly, or an admin can run "
            "scripts/refresh_factor_snapshot.py to populate it now."
        )


class GetFactorScoresUseCase:
    def __init__(
        self,
        factor_repo: FactorScoreRepository,
        refresh_use_case: ComputeUniverseFactorSnapshotUseCase,
        max_staleness: timedelta = DEFAULT_MAX_STALENESS,
        auto_refresh: bool = False,
    ) -> None:
        self._factor_repo = factor_repo
        self._refresh_use_case = refresh_use_case
        self._max_staleness = max_staleness
        self._auto_refresh = auto_refresh

    def execute(self, weights: FactorWeights | None = None) -> list[RankedFactorScore]:
        """Whole-universe ranking, sorted by composite score descending.
        Tickers with no computable composite (every factor missing)
        sort last, not silently dropped — a caller asking "what's on my
        watchlist" should still see a row for a ticker outside normal
        coverage, honestly marked as unscored."""
        self._ensure_fresh()
        weights = weights or FactorWeights()
        ranked = [self._rank(score, weights) for score in self._factor_repo.get_all()]
        ranked.sort(key=lambda r: (r.composite_score is None, -(r.composite_score or 0)))
        return ranked

    def execute_for_ticker(
        self, ticker: str, weights: FactorWeights | None = None
    ) -> RankedFactorScore | None:
        self._ensure_fresh()
        score = self._factor_repo.get(ticker)
        if score is None:
            return None
        return self._rank(score, weights or FactorWeights())

    def _ensure_fresh(self) -> None:
        as_of = self._factor_repo.get_latest_as_of()
        if as_of is not None and datetime.now(timezone.utc) - as_of <= self._max_staleness:
            return  # populated and fresh — nothing to do
        if not self._auto_refresh:
            if as_of is None:
                raise FactorSnapshotNotReadyError()
            return  # populated but stale — serve it as-is, staleness visible via as_of
        self._refresh_use_case.execute()

    @staticmethod
    def _rank(score, weights: FactorWeights) -> RankedFactorScore:
        composite, used = composite_score(score.z_scores, weights)
        return RankedFactorScore(
            ticker=score.ticker, composite_score=composite, factors_used=used, score=score
        )
