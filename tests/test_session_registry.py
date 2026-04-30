"""Unit tests for the PTY session registry + idle reaper.

Uses a ``MockPtySession`` (in-memory, no real fork) so unit tests stay
fast and deterministic. The reaper itself is verified primarily via
``_reap_once()`` direct calls — no ``asyncio.sleep`` flakiness.
``test_reaper_loop_actually_runs`` is the single sleep-based integration
test for the loop wiring.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from tests._pty_fixtures import MockPtySession
from the_one.tools import _session_registry as reg
from the_one.tools._session_registry import (
    _clear_for_test,
    _reap_once,
    close,
    count_for_agent,
    get,
    list_for_agent,
    new_session_id,
    register,
    shutdown_drain,
)


@pytest.fixture(autouse=True)
async def _registry_cleanup():
    """Reset the module-level registry state after every test.

    Without this, the next test would inherit a stale ``_reaper_task``
    bound to a torn-down event loop AND any leftover ``_shutting_down``
    flag from a prior ``shutdown_drain`` test.
    """
    yield
    await _clear_for_test()


# ────────────────────────────────────────────────────────────────────────────
# Basic API
# ────────────────────────────────────────────────────────────────────────────


async def test_new_session_id_format() -> None:
    sid = new_session_id()
    assert sid.startswith("pty-")
    # ``pty-`` (4) + 32-char uuid4 hex = 36 total.
    assert len(sid) == 36


async def test_register_and_get() -> None:
    sid = new_session_id()
    session = MockPtySession()
    await register("agent-a", sid, session, ttl_seconds=300)
    got = await get("agent-a", sid)
    assert got is session


async def test_get_returns_none_for_unknown_session() -> None:
    assert await get("agent-a", "pty-does-not-exist") is None


async def test_get_returns_none_for_cross_agent() -> None:
    """Cross-agent isolation: agent B cannot read agent A's session."""
    sid = new_session_id()
    await register("agent-a", sid, MockPtySession(), ttl_seconds=300)
    assert await get("agent-b", sid) is None


async def test_close_removes_entry_and_calls_session_close() -> None:
    sid = new_session_id()
    session = MockPtySession()
    await register("agent-a", sid, session, ttl_seconds=300)
    assert await close("agent-a", sid) is True
    assert session.close_count == 1
    # Subsequent close returns False (already removed).
    assert await close("agent-a", sid) is False
    # And ``get`` returns None.
    assert await get("agent-a", sid) is None


async def test_close_returns_false_for_unknown() -> None:
    assert await close("agent-a", "pty-nope") is False


async def test_list_for_agent_filters_by_owner() -> None:
    sid_a1 = new_session_id()
    sid_a2 = new_session_id()
    sid_b = new_session_id()
    await register("agent-a", sid_a1, MockPtySession(), ttl_seconds=300)
    await register("agent-a", sid_a2, MockPtySession(), ttl_seconds=300)
    await register("agent-b", sid_b, MockPtySession(), ttl_seconds=300)

    a_ids = await list_for_agent("agent-a")
    b_ids = await list_for_agent("agent-b")

    assert set(a_ids) == {sid_a1, sid_a2}
    assert b_ids == [sid_b]


async def test_count_for_agent_filters_by_owner() -> None:
    await register("agent-a", new_session_id(), MockPtySession(), ttl_seconds=300)
    await register("agent-a", new_session_id(), MockPtySession(), ttl_seconds=300)
    await register("agent-b", new_session_id(), MockPtySession(), ttl_seconds=300)

    assert await count_for_agent("agent-a") == 2
    assert await count_for_agent("agent-b") == 1
    assert await count_for_agent("agent-c") == 0


# ────────────────────────────────────────────────────────────────────────────
# Reaper
# ────────────────────────────────────────────────────────────────────────────


async def test_reaper_lazy_spawn() -> None:
    """The reaper task is None at module-import time and spawns on the
    first ``register`` call."""
    assert reg._reaper_task is None
    await register("agent-a", new_session_id(), MockPtySession(), ttl_seconds=300)
    assert reg._reaper_task is not None
    assert not reg._reaper_task.done()


async def test_reaper_closes_idle_sessions() -> None:
    """``_reap_once`` closes sessions whose ``last_activity`` is older
    than their ``ttl_seconds``. Direct call — no sleep flakiness."""
    sid = new_session_id()
    # last_activity 600s ago; ttl 300s → expired.
    session = MockPtySession(last_activity=time.monotonic() - 600)
    await register("agent-a", sid, session, ttl_seconds=300)

    closed = await _reap_once()

    assert session in closed
    assert session.close_count == 1
    assert await get("agent-a", sid) is None


async def test_reaper_does_not_close_active_sessions() -> None:
    """Fresh ``last_activity`` → reaper leaves the session alone."""
    sid = new_session_id()
    session = MockPtySession()  # last_activity = now
    await register("agent-a", sid, session, ttl_seconds=300)

    closed = await _reap_once()

    assert closed == []
    assert session.close_count == 0
    assert await get("agent-a", sid) is session


async def test_reaper_mixed_active_and_idle() -> None:
    """Reaper closes only the idle session in a mixed batch."""
    sid_idle = new_session_id()
    sid_active = new_session_id()
    idle = MockPtySession(last_activity=time.monotonic() - 600)
    active = MockPtySession()
    await register("agent-a", sid_idle, idle, ttl_seconds=300)
    await register("agent-a", sid_active, active, ttl_seconds=300)

    closed = await _reap_once()

    assert closed == [idle]
    assert idle.close_count == 1
    assert active.close_count == 0
    assert await get("agent-a", sid_idle) is None
    assert await get("agent-a", sid_active) is active


async def test_reaper_per_session_ttl() -> None:
    """Each entry uses its own stored ``ttl_seconds`` — the reaper
    honors per-agent narrowing."""
    sid_short = new_session_id()
    sid_long = new_session_id()
    # Both 200s ago; short ttl=100 → expired, long ttl=600 → not expired.
    short = MockPtySession(last_activity=time.monotonic() - 200)
    long_ = MockPtySession(last_activity=time.monotonic() - 200)
    await register("agent-a", sid_short, short, ttl_seconds=100)
    await register("agent-a", sid_long, long_, ttl_seconds=600)

    closed = await _reap_once()

    assert closed == [short]
    assert short.close_count == 1
    assert long_.close_count == 0


async def test_reaper_continues_when_one_close_raises() -> None:
    """One bad ``session.close()`` must not block reaping the rest."""

    class BadCloseMock(MockPtySession):
        async def close(self) -> None:
            self.close_count += 1
            self._alive = False
            raise RuntimeError("close blew up")

    sid_bad = new_session_id()
    sid_ok = new_session_id()
    bad = BadCloseMock(last_activity=time.monotonic() - 600)
    ok = MockPtySession(last_activity=time.monotonic() - 600)
    await register("agent-a", sid_bad, bad, ttl_seconds=300)
    await register("agent-a", sid_ok, ok, ttl_seconds=300)

    # Should not raise.
    await _reap_once()

    assert bad.close_count == 1
    assert ok.close_count == 1
    # Both removed regardless.
    assert await count_for_agent("agent-a") == 0


async def test_reaper_loop_actually_runs(monkeypatch) -> None:
    """Single sleep-based integration test that verifies the loop is
    actually scheduled and reaping. Reserves the flaky ``asyncio.sleep``
    pattern to one place so most reaper tests stay deterministic."""
    monkeypatch.setattr(reg, "_REAPER_INTERVAL_SECONDS", 0.05)

    sid = new_session_id()
    session = MockPtySession(last_activity=time.monotonic() - 600)
    await register("agent-a", sid, session, ttl_seconds=300)

    # Wait long enough for at least one tick.
    await asyncio.sleep(0.2)

    assert session.close_count == 1
    assert await get("agent-a", sid) is None


# ────────────────────────────────────────────────────────────────────────────
# Shutdown drain
# ────────────────────────────────────────────────────────────────────────────


async def test_shutdown_drain_cancels_reaper_and_closes_sessions() -> None:
    sessions = [MockPtySession() for _ in range(3)]
    sids = [new_session_id() for _ in sessions]
    for sid, session in zip(sids, sessions):
        await register("agent-a", sid, session, ttl_seconds=300)

    assert reg._reaper_task is not None
    await shutdown_drain()

    assert reg._reaper_task is None
    for session in sessions:
        assert session.close_count == 1
    assert await count_for_agent("agent-a") == 0


async def test_shutdown_drain_with_no_sessions_is_noop() -> None:
    """``shutdown_drain`` with no registered sessions / no reaper should
    not raise."""
    assert reg._reaper_task is None
    await shutdown_drain()
    assert reg._reaper_task is None


async def test_register_after_shutdown_drain_raises() -> None:
    """``register`` after ``shutdown_drain`` raises ``RuntimeError`` —
    fail loudly rather than silently orphan."""
    await shutdown_drain()
    with pytest.raises(RuntimeError, match="session registry is shutting down"):
        await register(
            "agent-a", new_session_id(), MockPtySession(), ttl_seconds=300
        )
