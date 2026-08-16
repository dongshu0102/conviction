from src.application.use_cases.caching_detect_position_changes import (
    CachingDetectPositionChangesUseCase,
)


class FakeDetectPositionChanges:
    def __init__(self):
        self.calls = []

    def execute(self, filer_query, min_pct_change=0.0, as_of=None):
        self.calls.append((filer_query, min_pct_change, as_of))
        return f"result-for-{filer_query}"


def test_first_call_for_a_filer_genuinely_reaches_the_inner_use_case() -> None:
    inner = FakeDetectPositionChanges()
    cached = CachingDetectPositionChangesUseCase(inner)

    result = cached.execute("Vanguard")

    assert result == "result-for-Vanguard"
    assert inner.calls == [("Vanguard", 0.0, None)]
    assert cached.cache_hits == 0
    assert cached.cache_misses == 1


def test_second_call_for_the_same_filer_is_a_genuine_cache_hit_not_a_real_call() -> None:
    """The single most important test for this wrapper's entire
    purpose: a repeat lookup for the same filer must never reach the
    inner, expensive use case a second time."""
    inner = FakeDetectPositionChanges()
    cached = CachingDetectPositionChangesUseCase(inner)

    cached.execute("Vanguard")
    result = cached.execute("Vanguard")

    assert result == "result-for-Vanguard"
    assert inner.calls == [("Vanguard", 0.0, None)]  # still only one real call
    assert cached.cache_hits == 1
    assert cached.cache_misses == 1


def test_different_filers_are_cached_independently() -> None:
    inner = FakeDetectPositionChanges()
    cached = CachingDetectPositionChangesUseCase(inner)

    cached.execute("Vanguard")
    cached.execute("BlackRock")
    cached.execute("Vanguard")

    assert len(inner.calls) == 2
    assert cached.cache_hits == 1
    assert cached.cache_misses == 2


def test_different_min_pct_change_for_the_same_filer_is_a_genuinely_different_cache_key() -> None:
    """Real, deliberate correctness distinction: two different, real
    query parameters must never be silently conflated into the same
    cached answer."""
    inner = FakeDetectPositionChanges()
    cached = CachingDetectPositionChangesUseCase(inner)

    cached.execute("Vanguard", min_pct_change=0.0)
    cached.execute("Vanguard", min_pct_change=5.0)

    assert len(inner.calls) == 2
    assert cached.cache_hits == 0
    assert cached.cache_misses == 2
