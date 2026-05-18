"""Tests for the neutral ``the_one.sessions`` package.

F5 L2 lifted the per-session ``asyncio.Lock`` and the WS subscriber
set into a neutral module so the F3 dispatcher and the WS handler
converge on a single lock registry (closing the M10 mission Known
Issue) and a single subscribers registry (so leg 6's dispatcher can
broadcast inbound-driven events without an
``interfaces.web.app`` import).

These tests pin the new invariants the prior structure could not test:

- A WS-typed message and a dispatcher-inbound for the SAME session id
  serialize on the SAME lock (same-session_serializes_across_paths).
- Two different session ids do not serialize on each other
  (different_sessions_parallelize).
- The ``is_session_processing`` read helper MUST NOT trigger the
  defaultdict's lazy-create (is_session_processing_does_not_lazy_create).
- The broadcast helper is a clean no-op when no subscribers are
  registered (subscribers_zero_broadcast_is_noop).
- The subscriber add/remove API is round-trippable
  (subscribers_add_remove_round_trip).
"""

from __future__ import annotations

import asyncio

import pytest

from the_one.sessions import (
    add_subscriber,
    broadcast_to_session,
    clear_for_test,
    is_session_processing,
    remove_subscriber,
    session_locks,
    subscribers_for,
)


@pytest.fixture(autouse=True)
def _reset_session_registries():
    """Drop both registries between tests so locks bound to torn-down
    event loops and stale subscriber entries don't leak across tests."""
    clear_for_test()
    yield
    clear_for_test()


# ─── lock unification ────────────────────────────────────────────────────


async def test_same_session_serializes_across_paths() -> None:
    """A second acquirer for the SAME session id waits behind the first."""
    sid = "shared-sid"
    order: list[str] = []
    first_inside = asyncio.Event()
    first_release = asyncio.Event()

    # Task A — acquires the shared lock and holds it until released.
    async def hold_lock_path_a() -> None:
        async with session_locks[sid]:
            order.append("a-inside")
            first_inside.set()
            await first_release.wait()
            order.append("a-released")

    # Task B — acquires the SAME lock; should queue behind A.
    async def hold_lock_path_b() -> None:
        await first_inside.wait()
        async with session_locks[sid]:
            order.append("b-inside")

    task_a = asyncio.create_task(hold_lock_path_a())
    task_b = asyncio.create_task(hold_lock_path_b())

    await first_inside.wait()
    # Yield a few times — task B must NOT enter the critical section.
    for _ in range(5):
        await asyncio.sleep(0)
    assert order == ["a-inside"], order
    assert not task_b.done()

    first_release.set()
    await asyncio.gather(task_a, task_b)
    assert order == ["a-inside", "a-released", "b-inside"], order


async def test_different_sessions_parallelize() -> None:
    """Two different session ids do not block each other."""
    sid_a = "sid-A"
    sid_b = "sid-B"
    both_inside = asyncio.Event()
    release = asyncio.Event()
    inside_count = 0
    lock_inside_count = asyncio.Lock()

    async def hold(sid: str) -> None:
        nonlocal inside_count
        async with session_locks[sid]:
            async with lock_inside_count:
                inside_count += 1
                if inside_count == 2:
                    both_inside.set()
            await release.wait()

    task_a = asyncio.create_task(hold(sid_a))
    task_b = asyncio.create_task(hold(sid_b))

    # If parallel, both will reach the inside section concurrently.
    # If they shared a lock (bug), the second would be blocked and
    # both_inside would never set.
    await asyncio.wait_for(both_inside.wait(), timeout=1.0)
    assert inside_count == 2

    release.set()
    await asyncio.gather(task_a, task_b)


async def test_is_session_processing_does_not_lazy_create() -> None:
    """The read-path helper MUST NOT materialize a defaultdict entry.

    ``_build_session_joined_ok`` reads this on every healthy
    ``session_joined`` payload; a lazy-create would leak empty
    ``asyncio.Lock`` entries to the registry for every session id the
    client has ever joined.
    """
    sid = "unseen-sid"
    assert sid not in session_locks
    assert is_session_processing(sid) is False
    # The crucial assertion: the read did NOT create an entry.
    assert sid not in session_locks


async def test_is_session_processing_reports_held_state() -> None:
    """Held lock → True; lock present-but-unheld → False."""
    sid = "held-sid"
    lock = session_locks[sid]  # materialize
    assert is_session_processing(sid) is False
    async with lock:
        assert is_session_processing(sid) is True
    assert is_session_processing(sid) is False


# ─── subscribers registry ────────────────────────────────────────────────


class _FakeWS:
    """Test double for a WebSocket — captures ``send_json`` payloads."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)


async def test_zero_subscriber_broadcast_is_noop() -> None:
    """Broadcasting to a session with no subscribers does not raise."""
    sid = "no-subs"
    assert subscribers_for(sid) == set()
    # Should NOT raise, regardless of payload shape.
    await broadcast_to_session(sid, {"type": "hello", "content": "world"})


async def test_subscribers_round_trip() -> None:
    """``add_subscriber`` + ``subscribers_for`` + ``remove_subscriber`` round-trip."""
    sid = "round-trip-sid"
    ws1 = _FakeWS()
    ws2 = _FakeWS()

    # Add two.
    add_subscriber(sid, ws1)
    add_subscriber(sid, ws2)
    snapshot = subscribers_for(sid)
    assert snapshot == {ws1, ws2}

    # Snapshot semantics — mutating the live registry doesn't perturb
    # an in-flight iteration over a snapshot.
    remove_subscriber(sid, ws1)
    assert subscribers_for(sid) == {ws2}
    # Original snapshot unchanged.
    assert snapshot == {ws1, ws2}

    # Remove the other.
    remove_subscriber(sid, ws2)
    assert subscribers_for(sid) == set()

    # Idempotent: removing an absent subscriber is a no-op.
    remove_subscriber(sid, ws1)
    remove_subscriber(sid, ws2)
    assert subscribers_for(sid) == set()


async def test_broadcast_delivers_to_all_subscribers_and_excludes() -> None:
    """Each registered subscriber receives the payload; exclude is skipped."""
    sid = "broadcast-sid"
    ws1 = _FakeWS()
    ws2 = _FakeWS()
    ws3 = _FakeWS()
    add_subscriber(sid, ws1)
    add_subscriber(sid, ws2)
    add_subscriber(sid, ws3)

    await broadcast_to_session(sid, {"type": "ping"}, exclude=ws2)

    assert ws1.sent == [{"type": "ping"}]
    assert ws3.sent == [{"type": "ping"}]
    assert ws2.sent == []  # excluded


async def test_broadcast_prunes_dead_subscribers() -> None:
    """If ``send_json`` raises, the failing subscriber is dropped."""
    sid = "dead-prune-sid"
    good = _FakeWS()

    class _DeadWS:
        async def send_json(self, payload: dict) -> None:
            raise RuntimeError("socket already closed")

    dead = _DeadWS()
    add_subscriber(sid, good)
    add_subscriber(sid, dead)

    await broadcast_to_session(sid, {"type": "ping"})

    assert good.sent == [{"type": "ping"}]
    assert subscribers_for(sid) == {good}
    assert dead not in subscribers_for(sid)
