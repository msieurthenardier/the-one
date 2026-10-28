"""``track_turn``: the one turn seam behind the Chats list's working/new-reply state.

Mission 31 Flight 6 leg 10b. A fake listener with ``asyncio.Event``s stands in
for the push; nothing here sleeps for the coalescing window.
"""

from __future__ import annotations

import asyncio

import pytest

from the_one.db import _session_changes
from the_one.sessions import (
    _locks,
    clear_locks_for_test,
    is_session_busy,
    is_session_processing,
    session_locks,
    track_turn,
    turn_seq,
)


@pytest.fixture(autouse=True)
def _clean():
    clear_locks_for_test()
    _locks._turn_counts.clear()
    _locks._session_inflight.clear()
    _session_changes.clear_for_test()
    yield
    clear_locks_for_test()
    _locks._turn_counts.clear()
    _locks._session_inflight.clear()
    _session_changes.clear_for_test()


def _n(sid: str) -> int:
    return int(turn_seq(sid).split(":")[1])


async def test_start_and_end_push_and_end_reads_idle() -> None:
    seen: list[tuple[bool, bool, str]] = []
    _session_changes.add_listener(
        lambda: seen.append((is_session_processing("s"), is_session_busy("s"), turn_seq("s")))
    )
    async with track_turn("s") as turn:
        turn.ran = True
        assert is_session_processing("s")
    assert len(seen) == 2
    start, end = seen
    assert start[0] is True and start[2].endswith(":0")
    assert end[0] is False and end[1] is False and end[2].endswith(":1")


async def test_end_push_fires_after_release_with_events() -> None:
    started, ended = asyncio.Event(), asyncio.Event()
    release = asyncio.Event()
    state: list[bool] = []

    def listener() -> None:
        if not started.is_set():
            started.set()
        else:
            state.append(is_session_processing("s"))
            ended.set()

    _session_changes.add_listener(listener)

    async def turn_body() -> None:
        async with track_turn("s") as turn:
            turn.ran = True
            await release.wait()

    task = asyncio.create_task(turn_body())
    await started.wait()
    assert is_session_processing("s")
    release.set()
    await ended.wait()
    await task
    assert state == [False]
    assert _n("s") == 1


async def test_cancel_before_acquire_neither_bumps_nor_notifies() -> None:
    calls: list[int] = []
    _session_changes.add_listener(lambda: calls.append(1))
    await session_locks["s"].acquire()
    entered = False

    async def waiter() -> None:
        nonlocal entered
        async with track_turn("s"):
            entered = True

    task = asyncio.create_task(waiter())
    await asyncio.sleep(0)  # let it reach the lock wait
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    session_locks["s"].release()
    assert entered is False
    assert calls == []
    assert _n("s") == 0


async def test_early_return_without_ran_does_not_bump() -> None:
    calls: list[int] = []
    _session_changes.add_listener(lambda: calls.append(1))
    async with track_turn("s"):
        pass  # connector early return: ran never set
    assert len(calls) == 2  # start and end pushes, so the row never sticks on busy
    assert _n("s") == 0


async def test_exception_before_ran_still_pushes_end() -> None:
    calls: list[int] = []
    _session_changes.add_listener(lambda: calls.append(1))
    with pytest.raises(RuntimeError):
        async with track_turn("s"):
            raise RuntimeError("boom")
    assert len(calls) == 2
    assert _n("s") == 0
    assert not is_session_processing("s")


async def test_cancel_during_turn_bumps() -> None:
    inside = asyncio.Event()

    async def body() -> None:
        async with track_turn("s") as turn:
            turn.ran = True
            inside.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(body())
    await inside.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert _n("s") == 1
    assert not is_session_processing("s")


async def test_error_during_turn_bumps_and_propagates() -> None:
    with pytest.raises(RuntimeError):
        async with track_turn("s") as turn:
            turn.ran = True
            raise RuntimeError("x")
    assert _n("s") == 1


async def test_busy_covers_inflight_registry() -> None:
    assert is_session_busy("s") is False
    _locks._session_inflight["s"] = {object()}  # type: ignore[arg-type]
    assert is_session_busy("s") is True


def test_turn_seq_format_and_never_creates_a_lock() -> None:
    boot, n = turn_seq("zzz").split(":")
    assert boot and n == "0"
    assert "zzz" not in session_locks
    assert is_session_busy("zzz") is False
    assert "zzz" not in session_locks
