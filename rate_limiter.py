"""Thread-safe in-memory per-user sliding-window rate limiter."""
from __future__ import annotations

import time
from collections import deque
from threading import Lock


class RateLimiter:
    def __init__(self, limit: int = 3, period_seconds: int = 60):
        if limit < 1 or period_seconds < 1:
            raise ValueError("limit and period_seconds must be positive")

        self.limit = limit
        self.period = period_seconds
        self._events: dict[int, deque[float]] = {}
        self._lock = Lock()
        self._calls = 0

    def _prune_user(self, user_id: int, now: float) -> deque[float]:
        events = self._events.get(user_id)
        if events is None:
            events = deque()
            self._events[user_id] = events

        while events and now - events[0] >= self.period:
            events.popleft()

        if not events:
            self._events.pop(user_id, None)
            return deque()

        return events

    def _prune_all(self, now: float) -> None:
        for user_id, events in list(self._events.items()):
            while events and now - events[0] >= self.period:
                events.popleft()
            if not events:
                del self._events[user_id]

    def allow(self, user_id: int, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now

        with self._lock:
            self._calls += 1

            # Periodically remove expired records belonging to inactive users.
            if self._calls % 128 == 0:
                self._prune_all(now)

            events = self._prune_user(user_id, now)

            if len(events) >= self.limit:
                return False

            events.append(now)
            self._events[user_id] = events
            return True
