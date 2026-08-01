"""Tests for GetFactorScoresUseCase: staleness-gated refresh + always-
fresh composite weighting. Uses a call-counting stub refresh use case
so these tests isolate the CACHING logic from the (already separately
tested) data-collection logic in ComputeUniverseFactorSnapshotUseCase.

auto_refresh DEFAULTS to False (see module docstring on the use case
for the production incident that drove this) — tests of the actual
refresh-triggering mechanism explicitly opt in with auto_refresh=True;
everything else tests the new default (safe for live requests).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.domain.entities.factor_scores import (
    FactorRawMetrics,
    FactorScore,
    FactorWeights,
    FactorZScores,
)
from src.application.use_cases.get_factor_scores import (
    FactorSnapshotNotReadyError,
    GetFactorScoresUseCase,
)
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


# ---- auto_refresh=True (explicit opt-in — e.g. the background job) ----


def test_auto_refresh_missing_cache_triggers_refresh_exactly_once() -> None:
    repo = FakeFactorScoreRepository()
    now = datetime.now(timezone.utc)
    refresh = _CountingRefresh(repo, [_score("AAA", now)])
    use_case = GetFactorScoresUseCase(repo, refresh, auto_refresh=True)

    result = use_case.execute()

    assert refresh.call_count == 1
    assert len(result) == 1


def test_auto_refresh_fresh_cache_does_not_trigger_refresh() -> None:
    repo = FakeFactorScoreRepository()
    now = datetime.now(timezone.utc)
    repo.save_batch([_score("AAA", now)])
    refresh = _CountingRefresh(repo, [_score("AAA", now)])
    use_case = GetFactorScoresUseCase(repo, refresh, max_staleness=timedelta(hours=24), auto_refresh=True)

    use_case.execute()

    assert refresh.call_count == 0


def test_auto_refresh_stale_cache_triggers_refresh() -> None:
    repo = FakeFactorScoreRepository()
    old = datetime.now(timezone.utc) - timedelta(hours=48)
    repo.save_batch([_score("AAA", old)])
    fresh_now = datetime.now(timezone.utc)
    refresh = _CountingRefresh(repo, [_score("AAA", fresh_now)])
    use_case = GetFactorScoresUseCase(repo, refresh, max_staleness=timedelta(hours=24), auto_refresh=True)

    use_case.execute()

    assert refresh.call_count == 1


# ---- default (auto_refresh=False) — safe for live chat/REST requests ----


def test_default_never_populated_raises_not_ready_instead_of_refreshing() -> None:
    repo = FakeFactorScoreRepository()
    refresh = _CountingRefresh(repo, [_score("AAA", datetime.now(timezone.utc))])
    use_case = GetFactorScoresUseCase(repo, refresh)  # auto_refresh defaults to False

    try:
        use_case.execute()
        raise AssertionError("expected FactorSnapshotNotReadyError")
    except FactorSnapshotNotReadyError:
        pass
    assert refresh.call_count == 0  # never attempted the expensive refresh inline


def test_default_stale_but_populated_serves_stale_data_without_refreshing() -> None:
    repo = FakeFactorScoreRepository()
    old = datetime.now(timezone.utc) - timedelta(hours=48)
    repo.save_batch([_score("AAA", old)])
    refresh = _CountingRefresh(repo, [_score("AAA", datetime.now(timezone.utc))])
    use_case = GetFactorScoresUseCase(repo, refresh, max_staleness=timedelta(hours=24))

    result = use_case.execute()

    assert refresh.call_count == 0  # served what's there, never triggered a live refresh
    assert len(result) == 1
    assert result[0].score.as_of == old  # staleness is visible to the caller via as_of


def test_default_fresh_cache_serves_normally() -> None:
    repo = FakeFactorScoreRepository()
    now = datetime.now(timezone.utc)
    repo.save_batch([_score("AAA", now)])
    refresh = _CountingRefresh(repo, [])
    use_case = GetFactorScoresUseCase(repo, refresh, max_staleness=timedelta(hours=24))

    result = use_case.execute()

    assert refresh.call_count == 0
    assert len(result) == 1


def test_execute_for_ticker_also_raises_not_ready_when_never_populated() -> None:
    repo = FakeFactorScoreRepository()
    refresh = _CountingRefresh(repo, [])
    use_case = GetFactorScoresUseCase(repo, refresh)

    try:
        use_case.execute_for_ticker("AAA")
        raise AssertionError("expected FactorSnapshotNotReadyError")
    except FactorSnapshotNotReadyError:
        pass


# ---- behavior independent of auto_refresh setting ----


def test_changing_weights_never_triggers_refresh_only_recomputes_composite() -> None:
    repo = FakeFactorScoreRepository()
    now = datetime.now(timezone.utc)
    repo.save_batch([_score("AAA", now, value=1.0, quality=2.0, growth=None, momentum=3.0, size=-1.0)])
    refresh = _CountingRefresh(repo, [])
    use_case = GetFactorScoresUseCase(repo, refresh, max_staleness=timedelta(hours=24))

    equal = use_case.execute(FactorWeights())
    value_only = use_case.execute(FactorWeights(value=1.0, quality=0, growth=0, momentum=0, size=0))

    assert refresh.call_count == 0
    assert abs(equal[0].composite_score - 1.25) < 1e-9
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
