"""A caching wrapper around DetectPositionChangesUseCase, used ONLY by
the market-wide screener (see screen_for_conviction.py and
scripts/screen_for_conviction.py) -- never by the single-ticker
Conviction Summary endpoint, which must stay genuinely live.

Real, confirmed motivation, not a speculative optimization: production
logs from tonight's own screener run showed the exact same filer CIKs
(Vanguard, BlackRock, State Street, Geode -- the largest, broadest
index managers) repeating across dozens of different tickers' top-5-
holder checks. detect_position_changes(filer_name)'s result depends
only on the filer, never on which ticker triggered the lookup, so
re-fetching an identical, large, expensive 13F filing hundreds of
times across a single scan (once per ticker that filer happens to
hold, which for a broad index manager is most of the S&P 500) is pure,
avoidable waste -- confirmed as the dominant, real cost behind the
screener's own, measured ~15 hour full-run estimate, not a hypothesis
left unverified.

A single scan run's cache is intentionally never reused across runs
(a fresh instance is constructed per script/API invocation): 13F data
refreshes quarterly, so staleness within one scan's runtime is a
non-issue, but a long-lived, cross-run cache would risk silently
serving data from a previous quarter.
"""
from __future__ import annotations

from src.application.use_cases.detect_position_changes import DetectPositionChangesUseCase


class CachingDetectPositionChangesUseCase:
    def __init__(self, inner: DetectPositionChangesUseCase) -> None:
        self._inner = inner
        self._cache: dict[tuple, object] = {}
        self.cache_hits = 0
        self.cache_misses = 0

    def execute(self, filer_query, min_pct_change=0.0, as_of=None):
        key = (filer_query, min_pct_change, as_of)
        if key in self._cache:
            self.cache_hits += 1
            return self._cache[key]

        self.cache_misses += 1
        result = self._inner.execute(filer_query, min_pct_change=min_pct_change, as_of=as_of)
        self._cache[key] = result
        return result
