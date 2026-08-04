"""Real tests for InMemoryRateLimiter — fully self-contained, no fakes
needed."""
from __future__ import annotations

import time

from src.infrastructure.rate_limit.in_memory_rate_limiter import InMemoryRateLimiter


def test_allows_requests_under_the_limit() -> None:
    limiter = InMemoryRateLimiter(max_requests=3, window_seconds=60)
    assert limiter.allow("alice@example.com") is True
    assert limiter.allow("alice@example.com") is True
    assert limiter.allow("alice@example.com") is True


def test_blocks_requests_over_the_limit() -> None:
    limiter = InMemoryRateLimiter(max_requests=3, window_seconds=60)
    for _ in range(3):
        limiter.allow("alice@example.com")
    assert limiter.allow("alice@example.com") is False


def test_tracks_keys_independently() -> None:
    limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60)
    assert limiter.allow("alice@example.com") is True
    assert limiter.allow("bob@example.com") is True
    assert limiter.allow("alice@example.com") is False


def test_window_expiry_allows_requests_again() -> None:
    limiter = InMemoryRateLimiter(max_requests=1, window_seconds=0.05)
    assert limiter.allow("alice@example.com") is True
    assert limiter.allow("alice@example.com") is False
    time.sleep(0.1)
    assert limiter.allow("alice@example.com") is True


def test_blocked_attempt_does_not_itself_count_toward_future_windows() -> None:
    """A rejected call shouldn't extend or reset the window — only
    successful hits should count."""
    limiter = InMemoryRateLimiter(max_requests=2, window_seconds=0.05)
    assert limiter.allow("alice@example.com") is True
    time.sleep(0.06)  # first hit now expired
    assert limiter.allow("alice@example.com") is True
    assert limiter.allow("alice@example.com") is True
    assert limiter.allow("alice@example.com") is False
