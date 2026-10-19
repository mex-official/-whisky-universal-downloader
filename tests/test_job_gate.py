import asyncio

import pytest

from job_gate import JobGate


def test_rejects_when_active_and_waiting_capacity_is_full():
    async def scenario():
        gate = JobGate(max_active=1, max_waiting=1)

        assert await gate.acquire() is True
        waiter = asyncio.create_task(gate.acquire())
        await asyncio.sleep(0)

        assert gate.admitted == 2
        assert await gate.acquire() is False

        await gate.release()
        assert await waiter is True
        await gate.release()
        assert gate.admitted == 0

    asyncio.run(scenario())


def test_rejects_extra_jobs_when_no_waiting_capacity():
    async def scenario():
        gate = JobGate(max_active=1)
        assert await gate.acquire() is True
        assert await gate.acquire() is False
        await gate.release()

    asyncio.run(scenario())


def test_cancelled_waiter_releases_admission_slot():
    async def scenario():
        gate = JobGate(max_active=1, max_waiting=1)
        assert await gate.acquire() is True

        waiter = asyncio.create_task(gate.acquire())
        await asyncio.sleep(0)
        waiter.cancel()

        with pytest.raises(asyncio.CancelledError):
            await waiter

        assert gate.admitted == 1
        await gate.release()
        assert gate.admitted == 0

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "active,waiting",
    [(0, 0), (-1, 0), (1, -1)],
)
def test_rejects_invalid_capacity(active, waiting):
    with pytest.raises(ValueError):
        JobGate(active, waiting)


def test_release_without_acquire_is_rejected():
    async def scenario():
        gate = JobGate(max_active=1)
        with pytest.raises(RuntimeError):
            await gate.release()

    asyncio.run(scenario())
