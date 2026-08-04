"""A deliberately simple in-memory rate limiter.

Honest about its real limitation: this state lives in one process's
memory, not a shared store like Redis. If App Runner ever scales this
service to multiple instances, each instance enforces its own
independent limit — a determined attacker spread across instances
could exceed the intended total. For this project's actual scale
(personal/small-scale use, a single running instance in practice),
that's a reasonable, explicit tradeoff rather than standing up Redis
for a threat model that doesn't yet justify it. If this ever needs to
be bulletproof across instances, swap this for a Redis-backed sliding
window — the call site doesn't need to change, just this file.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict


class InMemoryRateLimiter:
    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        """Returns True and records a hit if under the limit, False
        (recording nothing) if the key is currently over it."""
        now = time.monotonic()
        with self._lock:
            recent = [t for t in self._hits[key] if now - t < self._window_seconds]
            if len(recent) >= self._max_requests:
                self._hits[key] = recent
                return False
            recent.append(now)
            self._hits[key] = recent
            return True
