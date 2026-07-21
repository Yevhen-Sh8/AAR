"""In-process sliding-window rate limiter (Wave 5 hardening).

Deliberately simple: no Redis dependency, since none is provisioned for this
pilot deploy (see docs/DEPLOY.md). State lives in process memory, so it
resets on container restart and only applies per-instance — acceptable for
a single-instance pilot protecting against basic password-guessing, not a
distributed attack. Upgrade to a Redis-backed limiter if this deploy ever
scales to multiple instances.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    def __init__(self, max_attempts: int, window_seconds: float) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> tuple[bool, float]:
        """Record an attempt for `key`. Returns (allowed, retry_after_seconds).

        retry_after_seconds is 0.0 when allowed; otherwise the number of
        seconds until the oldest hit in the window expires.
        """
        now = time.monotonic()
        hits = self._hits[key]
        cutoff = now - self.window_seconds
        while hits and hits[0] < cutoff:
            hits.popleft()
        if len(hits) >= self.max_attempts:
            return False, max(hits[0] + self.window_seconds - now, 0.0)
        hits.append(now)
        return True, 0.0

    def reset(self) -> None:
        """Test-only: clear all recorded attempts."""
        self._hits.clear()
