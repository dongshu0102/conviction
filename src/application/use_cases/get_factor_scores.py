"""Use case: read factor scores, refreshing the cache only when stale.

This is the cheap half of factor scoring — composite weighting is a
weighted sum over already-computed z-scores, so it is recomputed fresh
on EVERY call regardless of cache state. Only the expensive cross-
sectional z-scoring itself is gated behind staleness — changing weights
never triggers a universe-wide refresh, only an old snapshot does.
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


class GetFactorScoresUseCase:
    def __init__(
        self,
        factor_repo: FactorScoreRepository,
        refresh_use_case: ComputeUniverseFactorSnapshotUseCase,
        max_staleness: timedelta = DEFAULT_MAX_STALENESS,
    ) -> None:
        self._factor_repo = factor_repo
        self._refresh_use_case = refresh_use_case
        self._max_staleness = max_staleness

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
        if as_of is None or datetime.now(timezone.utc) - as_of > self._max_staleness:
            self._refresh_use_case.execute()

    @staticmethod
    def _rank(score, weights: FactorWeights) -> RankedFactorScore:
        composite, used = composite_score(score.z_scores, weights)
        return RankedFactorScore(
            ticker=score.ticker, composite_score=composite, factors_used=used, score=score
        )
