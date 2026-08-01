"""Tests for GetFactorScoresUseCase: staleness-gated refresh + always-
fresh composite weighting. Uses a call-counting stub refresh use case
so these tests isolate the CACHING logic from the (already separately
tested) data-collection logic in ComputeUniverseFactorSnapshotUseCase.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.domain.entities.factor_scores import (
    FactorRawMetrics,
    FactorScore,
    FactorWeights,
    FactorZScores,
)
from src.application.use_cases.get_factor_scores import GetFactorScoresUseCase
from tests.unit.fakes import FakeFactorScoreRepository


class _CountingRefresh:
    def __init__(self, repo: FakeFactorScoreRepository, scores: list[FactorScore]) -> None:
        self._repo = repo
        self._scores = scores
        self.call_count = 0

    def execute(self):
        self.call_count += 1
        self._repo.save_batch(self._scores)


def _score(ticker: str, as_of: datetime, value=1.0, quality=2.0, growth=None, momentum=3.0, size=-1.0) -> FactorScore:
    return FactorScore(
        ticker=ticker,
        as_of=as_of,
        raw=FactorRawMetrics(None, None, None, None, None),
        z_scores=FactorZScores(value=value, quality=quality, growth=growth, momentum=momentum, size=size),
    )


def test_missing_cache_triggers_refresh_exactly_once() -> None:
    repo = FakeFactorScoreRepository()
    now = datetime.now(timezone.utc)
    refresh = _CountingRefresh(repo, [_score("AAA", now)])
    use_case = GetFactorScoresUseCase(repo, refresh)

    result = use_case.execute()

    assert refresh.call_count == 1
    assert len(result) == 1


def test_fresh_cache_does_not_trigger_refresh() -> None:
    repo = FakeFactorScoreRepository()
    now = datetime.now(timezone.utc)
    repo.save_batch([_score("AAA", now)])
    refresh = _CountingRefresh(repo, [_score("AAA", now)])
    use_case = GetFactorScoresUseCase(repo, refresh, max_staleness=timedelta(hours=24))

    use_case.execute()

    assert refresh.call_count == 0


def test_stale_cache_triggers_refresh() -> None:
    repo = FakeFactorScoreRepository()
    old = datetime.now(timezone.utc) - timedelta(hours=48)
    repo.save_batch([_score("AAA", old)])
    fresh_now = datetime.now(timezone.utc)
    refresh = _CountingRefresh(repo, [_score("AAA", fresh_now)])
    use_case = GetFactorScoresUseCase(repo, refresh, max_staleness=timedelta(hours=24))

    use_case.execute()

    assert refresh.call_count == 1


def test_changing_weights_never_triggers_refresh_only_recomputes_composite() -> None:
    repo = FakeFactorScoreRepository()
    now = datetime.now(timezone.utc)
    repo.save_batch([_score("AAA", now, value=1.0, quality=2.0, growth=None, momentum=3.0, size=-1.0)])
    refresh = _CountingRefresh(repo, [])
    use_case = GetFactorScoresUseCase(repo, refresh, max_staleness=timedelta(hours=24))

    equal = use_case.execute(FactorWeights())  # cache fresh -> 0 refreshes
    value_only = use_case.execute(FactorWeights(value=1.0, quality=0, growth=0, momentum=0, size=0))

    assert refresh.call_count == 0  # weights never touch the cache
    # equal-weight composite: same 1.0/1.25 hand-verified shape as test_factor_math
    assert abs(equal[0].composite_score - 1.25) < 1e-9
    # value-only composite: just the value z-score itself
    assert abs(value_only[0].composite_score - 1.0) < 1e-9


def test_ranking_sorts_by_composite_descending_unscored_last() -> None:
    repo = FakeFactorScoreRepository()
    now = datetime.now(timezone.utc)
    repo.save_batch([
        _score("LOW", now, value=-2.0, quality=-2.0, growth=-2.0, momentum=-2.0, size=-2.0),
        _score("HIGH", now, value=2.0, quality=2.0, growth=2.0, momentum=2.0, size=2.0),
        _score("UNSCORED", now, value=None, quality=None, growth=None, momentum=None, size=None),
    ])
    refresh = _CountingRefresh(repo, [])
    use_case = GetFactorScoresUseCase(repo, refresh, max_staleness=timedelta(hours=24))

    result = use_case.execute()

    assert [r.ticker for r in result] == ["HIGH", "LOW", "UNSCORED"]
    assert result[-1].composite_score is None


def test_execute_for_ticker_not_found_returns_none() -> None:
    repo = FakeFactorScoreRepository()
    repo.save_batch([_score("AAA", datetime.now(timezone.utc))])
    refresh = _CountingRefresh(repo, [])
    use_case = GetFactorScoresUseCase(repo, refresh, max_staleness=timedelta(hours=24))

    assert use_case.execute_for_ticker("NOTFOUND") is None
    found = use_case.execute_for_ticker("AAA")
    assert found is not None and found.ticker == "AAA"
