"""Bounded admission control for asynchronous jobs."""

from __future__ import annotations

import asyncio


class JobGate:
    """Limit active and waiting jobs without creating an unbounded queue."""

    def __init__(self, max_active: int, max_waiting: int = 0) -> None:
        if isinstance(max_active, bool) or not isinstance(max_active, int):
            raise TypeError("max_active must be an integer")
        if isinstance(max_waiting, bool) or not isinstance(max_waiting, int):
            raise TypeError("max_waiting must be an integer")
        if max_active < 1:
            raise ValueError("max_active must be >= 1")
        if max_waiting < 0:
            raise ValueError("max_waiting must be >= 0")

        self.max_active = max_active
        self.max_waiting = max_waiting
        self._semaphore = asyncio.Semaphore(max_active)
        self._lock = asyncio.Lock()
        self._admitted = 0

    @property
    def admitted(self) -> int:
        """Number of active plus admitted waiting jobs."""
        return self._admitted

    async def acquire(self) -> bool:
        """Admit immediately if capacity exists; otherwise reject if full."""
        async with self._lock:
            capacity = self.max_active + self.max_waiting
            if self._admitted >= capacity:
                return False
            self._admitted += 1

        try:
            await self._semaphore.acquire()
            return True
        except BaseException:
            async with self._lock:
                self._admitted -= 1
            raise

    async def release(self) -> None:
        """Release one previously admitted job."""
        async with self._lock:
            if self._admitted <= 0:
                raise RuntimeError("release without a matching acquire")
            self._admitted -= 1
            self._semaphore.release()
