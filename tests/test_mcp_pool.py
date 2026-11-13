"""Tests for ``the_one/mcp/_pool.py`` — worker-task-per-entry pool primitives.

Coverage:
   1. lazy-spawn-on-first-acquire  (mock ``MCPClient``)
   2. warm-reuse-on-second-acquire
   3. concurrent-acquire-same-key-shares-one-worker  (cycle-2 race-fix lock)
   4. different-keys-spawn-independent-workers
   5. spawn-failure-propagates-from-worker  (``SandboxError``)
   6. spawn-failure-pop-is-idempotent-under-concurrent-acquires
   7. acquire-cancellation-leaves-worker-running
   8. ``_load_source`` runs OUTSIDE the lock
   9. ``_clear_for_test`` cancels workers and empties pool
  10. real-bwrap end-to-end (integration; ``@pytest.mark.requires_bwrap``)
  11. ``_evict`` primitive (integration; ``@pytest.mark.requires_bwrap``)
  12. ``_evict`` idempotent on missing key (smoke)

Project-level pytest-asyncio is in ``auto`` mode (``pyproject.toml`` line
``asyncio_mode = "auto"``), so ``async def test_*`` functions and ``async``
fixtures run on the asyncio event loop without per-test decorators.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from the_one.db.models import MCPSource
from the_one.mcp import _pool as pool_mod
from the_one.mcp._pool import acquire
from the_one.mcp.errors import MCPConnectionError
from the_one.platform.sandbox.errors import SandboxError


# Autouse cleanup. The project uses pytest-asyncio in `auto` mode (verified
# via `grep asyncio_mode pyproject.toml` — line 47 sets `asyncio_mode = "auto"`),
# so a plain `@pytest.fixture(autouse=True)` async fixture works.
@pytest.fixture(autouse=True)
async def _clear_pool_after_each_test():
    yield
    await pool_mod._clear_for_test()


def _make_stub_source(source_id: str = "src-test", name: str = "test") -> MCPSource:
    """Return a minimal MCPSource. config["command"]="/bin/true" is never
    actually executed because tests monkeypatch ``pool_mod.MCPClient``."""
    return MCPSource(
        id=source_id,
        name=name,
        type="stdio",
        config={"command": "/bin/true", "args": [], "env": {}, "cwd": None},
        secrets={},
    )


class _MockClient:
    """Stub MCPClient. Overrides connect/disconnect/_touch_activity.

    Subclass per scenario rather than mutating the base class's
    ``_connect_impl`` (cycle-1 reviewer flagged that class-attribute
    mutation between instantiations is fragile because ``__init__`` binds
    ``self._connect_impl`` into an ``AsyncMock`` ``side_effect`` —
    late reassignment doesn't affect already-instantiated mocks).
    """

    _instance_count = 0

    def __init__(self, source, **kwargs):
        # **kwargs absorbs any constructor params the production MCPClient
        # accepts (e.g. auth_provider) so this mock stays compatible across
        # MCPClient signature changes. Tests don't exercise those kwargs;
        # they only care that the mock instantiates cleanly.
        type(self)._instance_count += 1
        self.source = source
        self.is_alive = False
        # L4 addition: settable mock attribute. Production ``MCPClient``
        # exposes ``last_activity`` as a read-only property backed by
        # ``_last_activity`` and updated via ``_touch_activity``; the
        # mock substitutes a plain attribute so L4 reaper tests can age
        # an entry by setting ``client.last_activity = 0.0`` directly.
        self.last_activity = 0.0
        self.connect = AsyncMock(side_effect=self._connect_impl)
        self.disconnect = AsyncMock(side_effect=self._disconnect_impl)
        self._touch_activity = MagicMock()

    async def _connect_impl(self):
        self.is_alive = True

    async def _disconnect_impl(self):
        self.is_alive = False


@pytest.fixture
def patch_client(monkeypatch):
    """Replace pool's ``MCPClient`` with the mock; reset instance counter.

    Returns the mock class so tests can read ``_instance_count``. Tests
    requiring per-scenario behavior subclass ``_MockClient`` explicitly
    (see ``_SlowClient`` / ``_FailingClient`` / ``_RetryClient`` below).
    """
    _MockClient._instance_count = 0

    async def _patched_load_source(source_id):
        return _make_stub_source(source_id)

    monkeypatch.setattr(pool_mod, "MCPClient", _MockClient)
    monkeypatch.setattr(pool_mod, "_load_source", _patched_load_source)
    return _MockClient


# ─────────────────────────────────────────────────────────────────
# Test bodies
# ─────────────────────────────────────────────────────────────────


async def test_acquire_lazy_spawn_creates_worker_and_returns_client(patch_client):
    client = await acquire("agent-a", "src-1")
    assert isinstance(client, _MockClient)
    assert client.is_alive is True
    assert _MockClient._instance_count == 1
    client._touch_activity.assert_called_once()
    # Worker task is registered in the pool entry.
    entry = pool_mod._pool[("agent-a", "src-1")]
    assert entry.worker is not None
    assert entry.client is client


async def test_acquire_warm_reuse_returns_same_client_instance(patch_client):
    c1 = await acquire("agent-a", "src-1")
    c2 = await acquire("agent-a", "src-1")
    assert c1 is c2
    assert _MockClient._instance_count == 1
    assert c1._touch_activity.call_count == 2


async def test_concurrent_acquire_same_key_shares_one_worker(monkeypatch):
    """Cycle-2 race-fix lock: 5 concurrent acquires for same key share ONE worker."""

    class _SlowClient(_MockClient):
        _instance_count = 0  # shadow the parent counter for isolation

        async def _connect_impl(self):
            await asyncio.sleep(0.05)
            self.is_alive = True

    async def _patched_load_source(source_id):
        return _make_stub_source(source_id)

    monkeypatch.setattr(pool_mod, "MCPClient", _SlowClient)
    monkeypatch.setattr(pool_mod, "_load_source", _patched_load_source)

    results = await asyncio.gather(*[acquire("agent-a", "src-1") for _ in range(5)])
    assert _SlowClient._instance_count == 1  # exactly ONE worker spawned
    assert all(r is results[0] for r in results)
    # All five callers touched activity on the shared client.
    assert results[0]._touch_activity.call_count == 5


async def test_different_keys_spawn_independent_workers(patch_client):
    c1 = await acquire("agent-a", "src-1")
    c2 = await acquire("agent-b", "src-1")
    assert c1 is not c2
    assert _MockClient._instance_count == 2
    # Both keys present in the pool with distinct workers.
    entry_a = pool_mod._pool[("agent-a", "src-1")]
    entry_b = pool_mod._pool[("agent-b", "src-1")]
    assert entry_a.worker is not entry_b.worker


async def test_spawn_failure_propagates_to_acquire_callers(monkeypatch):
    async def _patched_load_source(source_id):
        return _make_stub_source(source_id)

    class _FailingClient(_MockClient):
        _instance_count = 0

        async def _connect_impl(self):
            raise SandboxError("test sandbox failure")

    monkeypatch.setattr(pool_mod, "MCPClient", _FailingClient)
    monkeypatch.setattr(pool_mod, "_load_source", _patched_load_source)

    with pytest.raises(SandboxError, match="test sandbox failure"):
        await acquire("agent-a", "src-1")
    # Entry was popped during the failure-observation path; pool empty.
    assert ("agent-a", "src-1") not in pool_mod._pool


async def test_spawn_failure_pop_is_idempotent_under_concurrent_acquires(monkeypatch):
    """Cycle-1 reviewer fix: TWO concurrent failure-observers don't double-pop.

    Both gather'd acquires share ONE worker (cycle-2 race-fix invariant).
    The worker fails once and stores the same exception instance in
    ``entry.failure``; both observers re-raise that SAME instance and
    both call ``_pool.pop(key, None)`` — the second pop is a no-op
    because the first observer's pop already removed the key.
    """
    connect_attempts = {"n": 0}

    async def _patched_load_source(source_id):
        return _make_stub_source(source_id)

    class _FailingThenRecoveringClient(_MockClient):
        _instance_count = 0

        async def _connect_impl(self):
            connect_attempts["n"] += 1
            if connect_attempts["n"] == 1:
                # First worker fails — stall briefly so both gather'd
                # acquires queue on the same client_ready event.
                await asyncio.sleep(0.02)
                raise MCPConnectionError("attempt 1 fails")
            self.is_alive = True

    monkeypatch.setattr(pool_mod, "MCPClient", _FailingThenRecoveringClient)
    monkeypatch.setattr(pool_mod, "_load_source", _patched_load_source)

    # Two concurrent acquires on the SAME key; both should raise the
    # SAME MCPConnectionError instance.
    results = await asyncio.gather(
        acquire("agent-a", "src-1"),
        acquire("agent-a", "src-1"),
        return_exceptions=True,
    )
    assert all(isinstance(r, MCPConnectionError) for r in results)
    # SAME exception instance shared by both observers (worker stored
    # one entry.failure; both gather'd acquires re-raised the same obj).
    assert results[0] is results[1]
    # Cycle-2 race-fix invariant: only ONE worker spawned, only ONE client.
    assert _FailingThenRecoveringClient._instance_count == 1
    # Entry was popped (idempotent — no KeyError despite both raising).
    assert ("agent-a", "src-1") not in pool_mod._pool
    # The shared worker only ran connect ONCE.
    assert connect_attempts["n"] == 1

    # Retry: third sequential acquire spawns a fresh worker which succeeds.
    client = await acquire("agent-a", "src-1")
    assert client.is_alive
    assert _FailingThenRecoveringClient._instance_count == 2  # original-failed + retry-succeeded
    assert connect_attempts["n"] == 2


async def test_acquire_cancellation_leaves_worker_running(monkeypatch):
    """Caller cancellation mid-await leaves the worker running; subsequent
    acquire reuses it. NOT a leak."""

    class _VerySlowClient(_MockClient):
        _instance_count = 0

        async def _connect_impl(self):
            await asyncio.sleep(1.0)
            self.is_alive = True

    async def _patched_load_source(source_id):
        return _make_stub_source(source_id)

    monkeypatch.setattr(pool_mod, "MCPClient", _VerySlowClient)
    monkeypatch.setattr(pool_mod, "_load_source", _patched_load_source)

    # First acquire times out (caller cancels via wait_for).
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(acquire("agent-a", "src-1"), timeout=0.05)

    # Entry is still in the pool; worker is still running.
    assert ("agent-a", "src-1") in pool_mod._pool
    entry = pool_mod._pool[("agent-a", "src-1")]
    assert entry.worker is not None
    assert not entry.worker.done()

    # Second acquire (un-cancelled) waits for the worker, gets the client.
    client = await acquire("agent-a", "src-1")
    assert client.is_alive
    assert _VerySlowClient._instance_count == 1  # one worker, one client


async def test_load_source_runs_outside_the_lock(patch_client, monkeypatch):
    """Cycle-2 medium #2: different-key acquires must not serialize on the
    F1 DB read. The lock must NOT be held when ``_load_source`` runs."""
    lock_held_during_load: list[bool] = []
    prior_load_source = pool_mod._load_source  # the patched stub from patch_client

    async def _spy_load_source(source_id: str):
        lock_held_during_load.append(pool_mod._lock.locked())
        return await prior_load_source(source_id)

    monkeypatch.setattr(pool_mod, "_load_source", _spy_load_source)

    await acquire("agent-a", "src-1")
    # Stronger assertion: ALL invocations of _load_source ran outside
    # the lock, even if a future revision adds retry-on-miss paths.
    assert lock_held_during_load
    assert all(h is False for h in lock_held_during_load)


async def test_clear_for_test_cancels_workers_and_empties_pool(patch_client):
    await acquire("agent-a", "src-1")
    await acquire("agent-a", "src-2")
    await acquire("agent-b", "src-1")
    assert len(pool_mod._pool) == 3

    # Capture worker references BEFORE clearing.
    workers = [entry.worker for entry in pool_mod._pool.values()]

    await pool_mod._clear_for_test()
    assert pool_mod._pool == {}
    # All worker tasks are done (either evicted normally or cancelled).
    for w in workers:
        assert w is not None
        assert w.done()


# ─────────────────────────────────────────────────────────────────
# Integration tests — real bwrap subprocess
# ─────────────────────────────────────────────────────────────────


@pytest.mark.requires_bwrap
async def test_acquire_real_bwrap_end_to_end_with_strict_floor_profile(
    monkeypatch,
    mcp_fixture_sandbox_profile,
    mcp_fixture_stdio_params,
) -> None:
    """End-to-end: pool spawns real bwrap-wrapped MCP server, list_tools succeeds."""
    source = MCPSource(
        id="src-l3-integration",
        name="hello-fixture",
        type="stdio",
        config={
            **mcp_fixture_stdio_params,
            "sandbox": {
                "writable_paths": list(mcp_fixture_sandbox_profile.writable_paths),
                "network_allowed": mcp_fixture_sandbox_profile.network_allowed,
            },
        },
        secrets={},
    )

    async def _patched_load_source(source_id):
        assert source_id == source.id
        return source

    monkeypatch.setattr(pool_mod, "_load_source", _patched_load_source)

    client = await acquire("test-agent", source.id)
    tools = await client.list_tools()
    assert len(tools) > 0


@pytest.mark.requires_bwrap
async def test_acquire_then_evict_via_internal_helper(
    monkeypatch,
    mcp_fixture_sandbox_profile,
    mcp_fixture_stdio_params,
) -> None:
    """``_evict`` pops entry, runs disconnect on worker task, leaves pool empty.

    By the time ``_evict``'s ``await asyncio.wait_for(entry.worker, ...)``
    returns, the worker has fully completed its ``finally:`` block and
    ``client.disconnect()`` has run. The ``is_alive is False`` assertion
    below is race-free.
    """
    source = MCPSource(
        id="src-l3-evict",
        name="hello-fixture",
        type="stdio",
        config={
            **mcp_fixture_stdio_params,
            "sandbox": {
                "writable_paths": list(mcp_fixture_sandbox_profile.writable_paths),
                "network_allowed": mcp_fixture_sandbox_profile.network_allowed,
            },
        },
        secrets={},
    )

    async def _patched_load_source(source_id):
        return source

    monkeypatch.setattr(pool_mod, "_load_source", _patched_load_source)

    client = await acquire("test-agent", source.id)
    assert client.is_alive
    assert ("test-agent", source.id) in pool_mod._pool

    await pool_mod._evict(("test-agent", source.id))

    assert ("test-agent", source.id) not in pool_mod._pool
    assert client.is_alive is False


async def test_evict_idempotent_on_missing_key():
    """``_evict`` on a key that was never inserted is a no-op (no raise).

    Locks the ``if entry is None: return`` guard against future regressions
    where someone "simplifies" the None check.
    """
    # Pool starts empty (autouse fixture); the key has never been inserted.
    await pool_mod._evict(("never-inserted-agent", "never-inserted-src"))
    assert pool_mod._pool == {}


# ─────────────────────────────────────────────────────────────────
# Dead-client recovery (0.5.0)
#
# A pooled client can lose its connection mid-life — the server terminates
# the MCP session, or the transport breaks. ``MCPClient`` flips ``is_alive``
# off; ``acquire`` must notice and rebuild rather than hand back the corpse.
# The idle reaper cannot cover this: every failing ``call_tool`` calls
# ``_touch_activity()`` first, so a retrying agent keeps the entry looking
# fresh forever and only an operator's Reset connection ever cleared it.
# ─────────────────────────────────────────────────────────────────


async def test_acquire_rebuilds_entry_whose_client_died(patch_client):
    """The fix for 'works for a bit, then errors until I reset the connection'."""
    first = await acquire("agent-a", "src-1")
    assert patch_client._instance_count == 1

    # Simulate the server terminating the session under a warm pool entry.
    first.is_alive = False

    second = await acquire("agent-a", "src-1")

    assert second is not first, "dead client was handed back instead of rebuilt"
    assert second.is_alive is True
    assert patch_client._instance_count == 2
    # The dead entry was torn down, not merely dropped on the floor.
    first.disconnect.assert_awaited_once()
    # And the pool now holds exactly the replacement.
    assert pool_mod._pool[("agent-a", "src-1")].client is second


async def test_acquire_does_not_rebuild_a_healthy_warm_client(patch_client):
    """Scope guard: the warm-reuse path must survive the recovery change."""
    first = await acquire("agent-a", "src-1")
    second = await acquire("agent-a", "src-1")

    assert second is first
    assert patch_client._instance_count == 1
    first.disconnect.assert_not_awaited()


async def test_acquire_returns_second_attempt_client_without_spinning(monkeypatch, patch_client):
    """A client that dies again immediately must not loop forever.

    Attempt 2 hands its client back unconditionally; ``call_tool`` will raise
    and the NEXT acquire retries. Bounding it here is what stops a server that
    dies inside the same tick from wedging the caller in an eviction loop.
    """

    class _AlwaysDeadClient(_MockClient):
        async def _connect_impl(self):
            self.is_alive = False

    monkeypatch.setattr(pool_mod, "MCPClient", _AlwaysDeadClient)

    client = await acquire("agent-a", "src-1")

    assert client.is_alive is False
    # Exactly one rebuild attempt — not an unbounded retry loop.
    assert _AlwaysDeadClient._instance_count == 2


async def test_evict_stale_no_ops_when_entry_was_already_replaced(patch_client):
    """Identity guard: never evict a replacement installed by another caller.

    Without it, two callers noticing the same dead client would evict each
    other's fresh connections.
    """
    await acquire("agent-a", "src-1")
    key = ("agent-a", "src-1")
    original_entry = pool_mod._pool[key]

    # Stand in for "another task already rebuilt this key".
    replacement = pool_mod._RegistryEntry(
        ttl_seconds=300,
        evict_event=asyncio.Event(),
        client_ready=asyncio.Event(),
    )
    pool_mod._pool[key] = replacement

    await pool_mod._evict_stale(key, original_entry)

    assert pool_mod._pool[key] is replacement, "the replacement was wrongly evicted"


async def test_acquire_rebuilds_when_dead_entry_worker_already_ended_cancelled(patch_client):
    """Squawk 0354: a worker that ended cancelled counts as torn down.

    Awaiting a cancelled task raises CancelledError into the caller (the chat
    turn); acquire must absorb it and go on to its second attempt.
    """
    first = await acquire("agent-a", "src-1")
    entry = pool_mod._pool[("agent-a", "src-1")]
    entry.worker.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await entry.worker
    assert entry.worker.cancelled()
    first.is_alive = False

    second = await acquire("agent-a", "src-1")

    assert second is not first
    assert second.is_alive is True
    assert asyncio.current_task().cancelling() == 0


async def test_acquire_rebuilds_when_dead_entry_worker_ends_cancelled_during_teardown(
    patch_client,
):
    """Variant: the worker is still running and ends cancelled while awaited."""
    first = await acquire("agent-a", "src-1")
    entry = pool_mod._pool[("agent-a", "src-1")]
    assert entry.worker is not None

    async def _ends_cancelled():
        await entry.evict_event.wait()
        raise asyncio.CancelledError

    # Swap in a worker that ends cancelled once told to evict.
    real_worker = entry.worker
    entry.worker = asyncio.ensure_future(_ends_cancelled())
    first.is_alive = False

    second = await acquire("agent-a", "src-1")

    assert second is not first
    assert second.is_alive is True
    real_worker.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await real_worker


async def test_real_cancel_of_caller_during_teardown_still_propagates(patch_client):
    """The caller's own cancellation must not be swallowed by the fix."""
    first = await acquire("agent-a", "src-1")
    key = ("agent-a", "src-1")
    entry = pool_mod._pool[key]
    real_worker = entry.worker

    async def _slow():
        await entry.evict_event.wait()
        await asyncio.sleep(30)

    entry.worker = asyncio.ensure_future(_slow())
    first.is_alive = False

    task = asyncio.ensure_future(acquire("agent-a", "src-1"))
    await asyncio.sleep(0.05)  # acquire is now parked in teardown
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    entry.worker.cancel()
    real_worker.cancel()
    for t in (entry.worker, real_worker):
        with contextlib.suppress(asyncio.CancelledError):
            await t


# ─────────────────────────────────────────────────────────────────
# L4 — Reaper, drain, lifespan
# ─────────────────────────────────────────────────────────────────


async def test_reap_after_idle_evicts_entry_and_disconnects_client(monkeypatch, patch_client):
    monkeypatch.setenv("MCP_POOL_IDLE_TTL_SECONDS", "1")
    client = await acquire("agent-a", "src-1")
    # Manually age the entry by overriding last_activity (mock attr).
    client.last_activity = 0.0  # ancient

    evicted = await pool_mod._reap_once()
    assert ("agent-a", "src-1") in evicted
    assert ("agent-a", "src-1") not in pool_mod._pool
    client.disconnect.assert_awaited_once()


async def test_reap_active_entry_skipped(patch_client):
    client = await acquire("agent-a", "src-1")
    # Touch activity so ``last_activity`` is fresh (current monotonic).
    import time as _time

    client.last_activity = _time.monotonic()
    evicted = await pool_mod._reap_once()
    assert evicted == []
    assert ("agent-a", "src-1") in pool_mod._pool
    client.disconnect.assert_not_awaited()


async def test_reap_error_isolation_one_bad_evict_does_not_kill_loop(
    monkeypatch,
):
    """One bad ``client.disconnect`` raises but reap pass completes for the rest."""

    class _PartialFailingClient(_MockClient):
        _instance_count = 0

        async def _disconnect_impl(self):
            if self.source.id == "src-bad":
                raise RuntimeError("disconnect failed")
            self.is_alive = False

    _PartialFailingClient._instance_count = 0

    async def _patched_load_source(source_id):
        return _make_stub_source(source_id, name=source_id)

    monkeypatch.setattr(pool_mod, "MCPClient", _PartialFailingClient)
    monkeypatch.setattr(pool_mod, "_load_source", _patched_load_source)
    monkeypatch.setenv("MCP_POOL_IDLE_TTL_SECONDS", "1")

    c_good = await acquire("agent-a", "src-good")
    c_bad = await acquire("agent-a", "src-bad")
    c_good.last_activity = 0.0
    c_bad.last_activity = 0.0

    evicted = await pool_mod._reap_once()
    # Both keys reaped (one threw inside disconnect, but the entry was
    # still popped — _evict pops under _lock BEFORE awaiting the worker).
    assert set(evicted) == {("agent-a", "src-good"), ("agent-a", "src-bad")}
    assert pool_mod._pool == {}


async def test_respawn_after_reap_creates_fresh_entry(patch_client, monkeypatch):
    monkeypatch.setenv("MCP_POOL_IDLE_TTL_SECONDS", "1")
    c1 = await acquire("agent-a", "src-1")
    c1.last_activity = 0.0
    await pool_mod._reap_once()
    assert pool_mod._pool == {}

    c2 = await acquire("agent-a", "src-1")
    assert c1 is not c2
    assert _MockClient._instance_count == 2


async def test_parallel_warm_multiple_entries(patch_client, monkeypatch):
    import time as _time

    monkeypatch.setenv("MCP_POOL_IDLE_TTL_SECONDS", "300")
    c1 = await acquire("agent-a", "src-1")
    c2 = await acquire("agent-a", "src-2")
    c3 = await acquire("agent-b", "src-1")
    # Touch all three so they are fresh.
    now = _time.monotonic()
    c1.last_activity = now
    c2.last_activity = now
    c3.last_activity = now
    assert len(pool_mod._pool) == 3

    evicted = await pool_mod._reap_once()
    assert evicted == []  # all fresh
    assert len(pool_mod._pool) == 3

    # Age entries 1 and 3. Monotonic-relative: 0.0 is *within* the 300s TTL
    # on a freshly-booted host (CI runners), so it would never reap there.
    aged = _time.monotonic() - 360
    c1.last_activity = aged
    c3.last_activity = aged
    evicted = await pool_mod._reap_once()
    assert set(evicted) == {("agent-a", "src-1"), ("agent-b", "src-1")}
    assert len(pool_mod._pool) == 1
    assert ("agent-a", "src-2") in pool_mod._pool


async def test_shutdown_drain_cancels_reaper_and_evicts_all_entries(
    patch_client,
):
    c1 = await acquire("agent-a", "src-1")
    c2 = await acquire("agent-a", "src-2")
    assert pool_mod._reaper_task is not None

    await pool_mod.shutdown_drain()
    assert pool_mod._pool == {}
    assert pool_mod._reaper_task is None
    assert pool_mod._shutting_down is True
    c1.disconnect.assert_awaited_once()
    c2.disconnect.assert_awaited_once()


async def test_acquire_after_shutdown_drain_raises_runtime_error(
    patch_client,
):
    await pool_mod.shutdown_drain()
    with pytest.raises(RuntimeError, match="shutting down"):
        await acquire("agent-a", "src-1")


async def test_lifespan_shutdown_drain_order(monkeypatch):
    """Locks the lifespan startup/shutdown ordering across subsystems:
    connector-manager start (startup) then PTY drain → self-configuration
    surface eviction → MCP drain → OAuth sweep stop → connector-manager
    drain → DB close (shutdown).

    Mocks the four startup symbols (init_db, get_connection,
    migrate_json_to_sqlite, SQLiteAgentStore, AgentFactory) so lifespan's
    startup does not try to talk to a real DB. Then mocks every
    shutdown target and asserts call order.

    Squawk 0025: the evict-before-drain sequencing was previously
    unpinned against the real ``lifespan()`` — ``MCPSourceRepository``
    is monkeypatched to a fake whose ``list()`` returns one row marked as
    a self-configuration surface row (via the real
    ``_self_configuration_manage.is_surface_row`` predicate, unmocked),
    so the real evict/drain try block in ``app.py`` actually calls
    ``_evict_all_for_source`` before reaching ``_mcp_pool_shutdown_drain``.
    ``_evict_all_for_source`` is imported function-locally inside
    ``lifespan`` (``from the_one.mcp._pool import _evict_all_for_source``),
    so — mirroring the OAuth-sweep pattern below — it's monkeypatched on
    ``pool_mod`` (the source module) rather than on ``app_mod``: the local
    import re-resolves the module attribute at call time, after this
    test's ``monkeypatch.setattr`` has already run. Reordering the two
    ``try`` blocks in ``app.py`` (evict, then MCP drain) would flip
    "evict" and "mcp" in ``drain_steps`` and fail this assertion.

    Mission 23 Flight 1 (backend-removal leg, DD-8): the connector pool
    drain that M10 F1 L6 spliced in between the MCP drain and the OAuth
    sweep stop is deleted along with the connector package — the MCP
    evict/drain block itself (squawk 0025's pinned ordering concern) is
    untouched. The OAuth sweep (``start_periodic_sweep`` /
    ``stop_periodic_sweep``) is imported function-locally in
    ``lifespan``; monkeypatch it on the ``the_one.mcp.oauth`` module
    since that's where the import resolves.

    Mission 23 Flight 2 Leg 1: a NEW connector-manager start/drain pair
    is spliced in — start just before the startup ``yield`` (wrapped in
    its own try/except, mirroring the other startup blocks, per the
    Leg 1 design review), drain AFTER the OAuth sweep stop and BEFORE DB
    close. ``app_mod.ConnectorManager`` is monkeypatched to a fake class
    so this test never touches a real connector or a real repository
    query against ``_fake_conn`` (a bare, non-awaitable ``MagicMock``).
    """
    from the_one.interfaces.web import app as app_mod
    from the_one.mcp import oauth as oauth_mod

    calls: list[str] = []

    # Startup mocks — minimal no-ops so lifespan reaches ``yield``.
    async def _fake_init_db():
        pass

    _fake_conn = MagicMock()  # not awaited; just a sentinel

    async def _fake_get_connection():
        return _fake_conn

    async def _fake_migrate_json_to_sqlite(store):
        pass

    monkeypatch.setattr(app_mod, "init_db", _fake_init_db)
    monkeypatch.setattr(app_mod, "get_connection", _fake_get_connection)
    monkeypatch.setattr(app_mod, "migrate_json_to_sqlite", _fake_migrate_json_to_sqlite)
    monkeypatch.setattr(app_mod, "SQLiteAgentStore", MagicMock())
    monkeypatch.setattr(app_mod, "AgentFactory", MagicMock())
    # ``start_periodic_sweep`` is imported function-locally inside
    # ``lifespan``; stub it on the source module so the import resolves
    # to a no-op.
    monkeypatch.setattr(oauth_mod, "start_periodic_sweep", lambda: None)

    # Connector-manager spy — replaces the real class so `start_all` never
    # queries `_fake_conn` and `drain` never touches a real listener task.
    class _FakeConnectorManager:
        async def start_all(self, repo, encryptor):
            calls.append("connector_start")

        async def drain(self):
            calls.append("connector_drain")

    monkeypatch.setattr(app_mod, "ConnectorManager", _FakeConnectorManager)

    # M24 F03 L03: indexing-manager spy, mirroring the connector-manager
    # spy immediately above. `start_all` records "indexing_start" (no
    # args — unlike ConnectorManager.start_all, IndexingManager.start_all
    # takes none); `drain` records "indexing_drain".
    _indexing_manager_instances: list["_FakeIndexingManager"] = []

    class _FakeIndexingManager:
        def __init__(self):
            _indexing_manager_instances.append(self)

        async def start_all(self):
            calls.append("indexing_start")

        async def drain(self):
            calls.append("indexing_drain")

        def cancelled_kb_ids(self):
            # M24 F07 L01, AC-7: real IndexingManager.cancelled_kb_ids() —
            # this spy stands in for it here since ordering, not the
            # cancel-report plumbing itself, is what this test pins.
            # AC-7a (a separate test below) drives the real manager and
            # proves the value actually reaches close_vector_store.
            return frozenset()

    monkeypatch.setattr(app_mod, "IndexingManager", _FakeIndexingManager)

    # M24 F04 L03, DD-7: watch-manager spy, mirroring the indexing-manager
    # spy immediately above. Records the `index_manager` it was constructed
    # with (asserted below to be the `_FakeIndexingManager` instance
    # `app.py` passes it, proving construction happens after the indexing
    # manager's own `start_all`). `start_all` records "watch_start";
    # `drain` records "watch_drain".
    _watch_manager_instances: list["_FakeWatchManager"] = []

    class _FakeWatchManager:
        def __init__(self, *, index_manager):
            self.index_manager = index_manager
            _watch_manager_instances.append(self)

        async def start_all(self):
            calls.append("watch_start")

        async def drain(self):
            calls.append("watch_drain")

    monkeypatch.setattr(app_mod, "WatchManager", _FakeWatchManager)

    # Squawk 0025: fake source repository whose ``list()`` returns one row
    # the REAL ``is_surface_row`` predicate recognizes as a self-configuration
    # surface row — so the shutdown branch's eviction loop actually calls
    # ``_evict_all_for_source`` instead of finding nothing to iterate.
    # ``MCPSourceRepository`` is also instantiated once during STARTUP (the
    # self-configuration reconcile at ``app.py``'s ``reconcile_on_startup``
    # call) — that call must keep seeing an empty list, exactly like the
    # unmocked ``_fake_conn``-backed repository this test relied on before
    # (a plain ``MagicMock`` connection's chained ``execute()/fetchall()``
    # naturally yields ``[]``), otherwise the reconcile's rename/update
    # paths would run against a repo/agent-store this fake doesn't
    # implement. First ``list()`` call = startup reconcile → ``[]``.
    # Second ``list()`` call = the shutdown eviction branch → the surface
    # row.
    _surface_source = MCPSource(
        id="surface-src-1",
        name="surface",
        type="stdio",
        config={"self_configuration": {"agent": "test-agent"}},
    )
    _mcp_source_repo_list_calls = {"n": 0}

    class _FakeMCPSourceRepository:
        def __init__(self, conn, encryptor):
            pass

        async def list(self):
            _mcp_source_repo_list_calls["n"] += 1
            if _mcp_source_repo_list_calls["n"] < 2:
                return []
            return [_surface_source]

    monkeypatch.setattr(app_mod, "MCPSourceRepository", _FakeMCPSourceRepository)

    # Shutdown spies.
    async def _fake_pty_drain():
        calls.append("pty")

    async def _fake_evict_all_for_source(source_id):
        calls.append("evict")

    async def _fake_mcp_drain():
        calls.append("mcp")

    async def _fake_oauth_sweep_stop():
        calls.append("oauth")

    async def _fake_close_conn():
        calls.append("db")

    # M24 F07 L01, AC-7: vector-store shutdown-hook spy — extends the
    # drain-order pin with the hook's position, between the connector-
    # manager drain and the DB close (app.py calls it unconditionally,
    # right before `close_connection()`).
    _vector_close_calls: list[frozenset] = []

    async def _fake_close_vector_store(*, skip_kb_ids=frozenset()):
        calls.append("vector_close")
        _vector_close_calls.append(skip_kb_ids)

    monkeypatch.setattr(app_mod, "_session_registry_shutdown_drain", _fake_pty_drain)
    # ``_evict_all_for_source`` is imported function-locally inside the
    # shutdown branch (``from the_one.mcp._pool import _evict_all_for_source``);
    # patch it on the source module (``pool_mod``) so that local import
    # re-resolves to the spy when the shutdown branch executes.
    monkeypatch.setattr(pool_mod, "_evict_all_for_source", _fake_evict_all_for_source)
    monkeypatch.setattr(app_mod, "_mcp_pool_shutdown_drain", _fake_mcp_drain)
    monkeypatch.setattr(oauth_mod, "stop_periodic_sweep", _fake_oauth_sweep_stop)
    monkeypatch.setattr(app_mod, "close_connection", _fake_close_conn)
    monkeypatch.setattr(app_mod, "close_vector_store", _fake_close_vector_store)

    # Drive lifespan: enter (runs startup), exit (runs shutdown).
    from fastapi import FastAPI

    fake_app = FastAPI()
    async with app_mod.lifespan(fake_app):
        pass

    # Filter to the recognized steps; assert the full order. "evict" before
    # "mcp" is squawk 0025's pinned invariant — reordering the two try
    # blocks in app.py's shutdown branch flips this pair and fails here.
    drain_steps = [
        c
        for c in calls
        if c
        in (
            "connector_start",
            "indexing_start",
            "watch_start",
            "watch_drain",
            "indexing_drain",
            "pty",
            "evict",
            "mcp",
            "oauth",
            "connector_drain",
            "vector_close",
            "db",
        )
    ]
    assert drain_steps == [
        "connector_start",
        "indexing_start",
        "watch_start",
        "watch_drain",
        "indexing_drain",
        "pty",
        "evict",
        "mcp",
        "oauth",
        "connector_drain",
        "vector_close",
        "db",
    ]
    # AC-7: the hook runs exactly once, after the connector-manager drain
    # and before the DB close.
    assert _vector_close_calls == [frozenset()]
    # M24 F04 L03, DD-7: the watch manager was constructed with the SAME
    # indexing-manager instance app.py's startup block built — proof
    # construction happens after (not instead of) the indexing manager's
    # own start_all.
    assert len(_watch_manager_instances) == 1
    assert len(_indexing_manager_instances) == 1
    assert _watch_manager_instances[0].index_manager is _indexing_manager_instances[0]


async def test_lifespan_watch_manager_drain_runs_even_when_start_all_raises(monkeypatch):
    """M24 F04 L03, DD-7 (AC-1's behavioural variant): the watch manager's
    startup block wraps `start_all()` in its own try/except (mirroring the
    indexing-manager block), so a startup failure there still leaves the
    accessor holding a real instance and shutdown still drains it — and
    still reaches the indexing-manager drain right after. A leaner
    version of `test_lifespan_shutdown_drain_order`'s full setup, since
    only the watch/indexing pair's behavior is under test here."""
    from the_one.interfaces.web import app as app_mod
    from the_one.mcp import oauth as oauth_mod

    calls: list[str] = []

    async def _fake_init_db():
        pass

    _fake_conn = MagicMock()

    async def _fake_get_connection():
        return _fake_conn

    async def _fake_migrate_json_to_sqlite(store):
        pass

    monkeypatch.setattr(app_mod, "init_db", _fake_init_db)
    monkeypatch.setattr(app_mod, "get_connection", _fake_get_connection)
    monkeypatch.setattr(app_mod, "migrate_json_to_sqlite", _fake_migrate_json_to_sqlite)
    monkeypatch.setattr(app_mod, "SQLiteAgentStore", MagicMock())
    monkeypatch.setattr(app_mod, "AgentFactory", MagicMock())
    monkeypatch.setattr(oauth_mod, "start_periodic_sweep", lambda: None)

    class _FakeConnectorManager:
        async def start_all(self, repo, encryptor):
            pass

        async def drain(self):
            pass

    monkeypatch.setattr(app_mod, "ConnectorManager", _FakeConnectorManager)

    class _FakeIndexingManager:
        async def start_all(self):
            calls.append("indexing_start")

        async def drain(self):
            calls.append("indexing_drain")

        def cancelled_kb_ids(self):
            return frozenset()

    monkeypatch.setattr(app_mod, "IndexingManager", _FakeIndexingManager)

    class _FakeWatchManager:
        def __init__(self, *, index_manager):
            self.index_manager = index_manager

        async def start_all(self):
            calls.append("watch_start_attempted")
            raise RuntimeError("boom")

        async def drain(self):
            calls.append("watch_drain")

    monkeypatch.setattr(app_mod, "WatchManager", _FakeWatchManager)

    class _FakeMCPSourceRepository:
        def __init__(self, conn, encryptor):
            pass

        async def list(self):
            return []

    monkeypatch.setattr(app_mod, "MCPSourceRepository", _FakeMCPSourceRepository)

    async def _fake_pty_drain():
        pass

    async def _fake_mcp_drain():
        pass

    async def _fake_oauth_sweep_stop():
        pass

    async def _fake_close_conn():
        pass

    async def _fake_close_vector_store(*, skip_kb_ids=frozenset()):
        pass

    monkeypatch.setattr(app_mod, "_session_registry_shutdown_drain", _fake_pty_drain)
    monkeypatch.setattr(app_mod, "_mcp_pool_shutdown_drain", _fake_mcp_drain)
    monkeypatch.setattr(oauth_mod, "stop_periodic_sweep", _fake_oauth_sweep_stop)
    monkeypatch.setattr(app_mod, "close_connection", _fake_close_conn)
    monkeypatch.setattr(app_mod, "close_vector_store", _fake_close_vector_store)

    from fastapi import FastAPI

    fake_app = FastAPI()
    async with app_mod.lifespan(fake_app):
        pass

    assert calls == ["indexing_start", "watch_start_attempted", "watch_drain", "indexing_drain"]


async def test_lifespan_shutdown_threads_real_cancel_report_into_vector_hook(monkeypatch):
    """M24 F07 L01, AC-7a. AC-7's drain-order test replaces
    ``close_vector_store`` with a bare spy and never inspects what it was
    CALLED WITH; AC-8/9/10 (in ``test_vector_store_shutdown.py``) test the
    hook in isolation with a hand-built skip set. Neither proves the
    cancel report survives ``app.py``'s own
    ``_set_module_indexing_manager(None)`` / ``_indexing_manager = None``
    null-out (``app.py:426-427``) on its way to the hook.

    This test closes that gap by driving the REAL ``app.py`` shutdown
    branch with a fake ``IndexingManager`` whose ``drain()`` populates a
    non-empty ``cancelled_kb_ids()`` — mirroring what a real
    ``stop()`` cancel-fallback write does — and asserting the
    ``close_vector_store`` spy is called with that EXACT kb_id in
    ``skip_kb_ids``. An implementation that captures the manager
    reference (or calls ``cancelled_kb_ids()``) AFTER the null-out would
    either crash on ``None`` or (if defensively guarded) silently pass an
    empty skip set here — this test fails either way, which is the point.
    """
    from the_one.interfaces.web import app as app_mod
    from the_one.mcp import oauth as oauth_mod

    async def _fake_init_db():
        pass

    _fake_conn = MagicMock()

    async def _fake_get_connection():
        return _fake_conn

    async def _fake_migrate_json_to_sqlite(store):
        pass

    monkeypatch.setattr(app_mod, "init_db", _fake_init_db)
    monkeypatch.setattr(app_mod, "get_connection", _fake_get_connection)
    monkeypatch.setattr(app_mod, "migrate_json_to_sqlite", _fake_migrate_json_to_sqlite)
    monkeypatch.setattr(app_mod, "SQLiteAgentStore", MagicMock())
    monkeypatch.setattr(app_mod, "AgentFactory", MagicMock())
    monkeypatch.setattr(oauth_mod, "start_periodic_sweep", lambda: None)

    class _FakeConnectorManager:
        async def start_all(self, repo, encryptor):
            pass

        async def drain(self):
            pass

    monkeypatch.setattr(app_mod, "ConnectorManager", _FakeConnectorManager)

    # The fake manager's `drain()` populates `cancelled_kb_ids()` exactly
    # like a real DD-3a cancel-fallback `stop()` would — this is the
    # report app.py must capture before it nulls the manager out.
    class _FakeIndexingManager:
        def __init__(self):
            self._cancelled: frozenset[str] = frozenset()

        async def start_all(self):
            pass

        async def drain(self):
            self._cancelled = frozenset({"kb-cancelled-during-drain"})

        def cancelled_kb_ids(self):
            return self._cancelled

    monkeypatch.setattr(app_mod, "IndexingManager", _FakeIndexingManager)

    class _FakeWatchManager:
        def __init__(self, *, index_manager):
            self.index_manager = index_manager

        async def start_all(self):
            pass

        async def drain(self):
            pass

    monkeypatch.setattr(app_mod, "WatchManager", _FakeWatchManager)

    class _FakeMCPSourceRepository:
        def __init__(self, conn, encryptor):
            pass

        async def list(self):
            return []

    monkeypatch.setattr(app_mod, "MCPSourceRepository", _FakeMCPSourceRepository)

    async def _fake_pty_drain():
        pass

    async def _fake_mcp_drain():
        pass

    async def _fake_oauth_sweep_stop():
        pass

    async def _fake_close_conn():
        pass

    _vector_close_calls: list[frozenset] = []

    async def _fake_close_vector_store(*, skip_kb_ids=frozenset()):
        _vector_close_calls.append(skip_kb_ids)

    monkeypatch.setattr(app_mod, "_session_registry_shutdown_drain", _fake_pty_drain)
    monkeypatch.setattr(app_mod, "_mcp_pool_shutdown_drain", _fake_mcp_drain)
    monkeypatch.setattr(oauth_mod, "stop_periodic_sweep", _fake_oauth_sweep_stop)
    monkeypatch.setattr(app_mod, "close_connection", _fake_close_conn)
    monkeypatch.setattr(app_mod, "close_vector_store", _fake_close_vector_store)

    from fastapi import FastAPI

    fake_app = FastAPI()
    async with app_mod.lifespan(fake_app):
        pass

    # The hook received the exact kb_id the fake manager's drain()
    # recorded — proving app.py captured the report BEFORE the null-out,
    # not after (a post-null-out read would see None/empty here).
    assert _vector_close_calls == [frozenset({"kb-cancelled-during-drain"})]
    # And the null-out itself still happened (AC-6a's other half).
    assert app_mod._indexing_manager is None


async def test_drain_timeout_handles_stuck_worker(monkeypatch):
    """A worker stuck in disconnect for 30s gets cancelled at the 10s timeout."""

    class _StuckClient(_MockClient):
        _instance_count = 0

        async def _disconnect_impl(self):
            await asyncio.sleep(30)  # never returns within the test budget
            self.is_alive = False

    _StuckClient._instance_count = 0

    async def _patched_load_source(source_id):
        return _make_stub_source(source_id)

    monkeypatch.setattr(pool_mod, "MCPClient", _StuckClient)
    monkeypatch.setattr(pool_mod, "_load_source", _patched_load_source)
    # The per-entry teardown timeout is 10 s in production; shrink it so the stuck worker
    # (30 s) is still cancelled by the timeout branch, without a 10 s wait.
    monkeypatch.setattr(pool_mod, "_WORKER_TEARDOWN_TIMEOUT_SECONDS", 0.2)

    await acquire("agent-a", "src-1")

    # ``shutdown_drain`` must return within the (shrunk) per-entry timeout plus a
    # small overhead for the reaper-cancel; far below the worker's 30 s sleep. Measured
    # rather than wrapped in wait_for: wait_for would not fail if the drain swallowed the
    # cancellation and finished.
    started = time.monotonic()
    await pool_mod.shutdown_drain()
    assert time.monotonic() - started < 5.0

    assert pool_mod._pool == {}


async def test_reap_loop_drains_on_cancellation(patch_client, monkeypatch):
    """The reaper's CancelledError handler drains the registry."""
    # Speed up the loop's sleep so the test does not wait the full 30s.
    monkeypatch.setattr(pool_mod, "_REAPER_INTERVAL_SECONDS", 0.05)

    c1 = await acquire("agent-a", "src-1")
    c2 = await acquire("agent-a", "src-2")
    reaper = pool_mod._reaper_task
    assert reaper is not None and not reaper.done()

    reaper.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await reaper

    # Cancellation handler ran the drain.
    assert pool_mod._pool == {}
    c1.disconnect.assert_awaited_once()
    c2.disconnect.assert_awaited_once()


# ─────────────────────────────────────────────────────────────────
# F6 L2 — ``source_override`` kwarg widening
# ─────────────────────────────────────────────────────────────────


async def test_acquire_with_source_override(monkeypatch):
    """``acquire(..., source_override=fake)`` uses the override INSTEAD
    of calling ``_load_source``. Locks the F6 L2 widening so a future
    revision can't re-route override-applied sources back through the
    DB read silently.
    """
    load_source_calls: list[str] = []

    async def _spy_load_source(source_id: str):
        load_source_calls.append(source_id)
        return _make_stub_source(source_id, name="from-db")

    monkeypatch.setattr(pool_mod, "MCPClient", _MockClient)
    monkeypatch.setattr(pool_mod, "_load_source", _spy_load_source)

    override = _make_stub_source("src-1", name="from-override")
    client = await acquire("agent-a", "src-1", source_override=override)

    # The override propagated to the worker — the mock client stored
    # the source, so we can verify which source was used.
    assert client.source.name == "from-override"
    # _load_source was NOT called when the override was supplied.
    assert load_source_calls == []
    # And the entry is in the pool with the override's identity.
    entry = pool_mod._pool[("agent-a", "src-1")]
    assert entry.client is client


async def test_entry_worker_uses_synthetic_csid_when_tokens_present(
    monkeypatch,
) -> None:
    """F6.5 L4 — ``_entry_worker`` synthesizes ``f"agent_build:{source.id}"``
    when ``current_chat_session_id`` is unset AND the source has persisted
    OAuth tokens.

    Verifies the bootstrap path at ``_pool.py:197-200``: csid is None
    (ContextVar default), but ``source.secrets["access_token"]`` is set, so
    the worker synthesizes ``agent_build:{source.id}`` and forwards it to
    the OAuth provider factory. Without this, agent build via REST/CLI/
    tests would connect auth-less, the server would 401, and the source
    would graceful-skip even though valid tokens are sitting in the DB.

    The test patches ``the_one.mcp.oauth.build_oauth_provider_for_source``
    (NOT ``the_one.mcp._pool.build_oauth_provider_for_source`` — the
    function-local ``from … import …`` at ``_pool.py:196`` re-resolves the
    name from the source module on each call, so patching the source-module
    binding is the only target that intercepts the lookup). The mock raises
    a sentinel ``RuntimeError`` so the worker stops before ``MCPClient.connect``
    runs. The factory call lives OUTSIDE ``_entry_worker``'s
    ``except BaseException`` branch (which wraps only ``await client.connect()``
    at ``_pool.py:208-213``), so the RuntimeError propagates out of the
    worker — the test catches it via ``pytest.raises`` and then asserts
    on ``mock_factory.call_args`` (MagicMock records args before
    side_effect raises).
    """
    from the_one.agent._context import current_chat_session_id, current_tool_call_id
    from the_one.mcp._pool import _entry_worker, _RegistryEntry

    # Defensive: ensure no ambient chat session leaked into this test from
    # an earlier sibling. The ContextVar's ``get(None)`` default is what
    # the worker reads, but if a sibling test ``set()`` it without
    # resetting, the synthetic-csid branch would not be exercised.
    csid_token = current_chat_session_id.set(None)
    tcid_token = current_tool_call_id.set(None)
    try:
        source = MCPSource(
            id="src-pool-test",
            name="t",
            type="streamable-http",
            config={"url": "https://example.com/mcp"},
            secrets={
                "access_token": "tok-1",
                "dcr_credentials": {"client_id": "c1"},
            },
        )

        # MagicMock with side_effect=RuntimeError stops the worker before
        # MCPClient.connect runs. The mock still records call args even
        # when side_effect raises (verified at unittest.mock:1124-1183 —
        # _increment_mock_call records args BEFORE _execute_mock_call
        # consults side_effect).
        sentinel = RuntimeError("captured-and-stopped")
        mock_factory = MagicMock(side_effect=sentinel)
        # NOTE: target the source module, not _pool — the worker imports
        # ``build_oauth_provider_for_source`` lazily inside its body via
        # ``from the_one.mcp.oauth import build_oauth_provider_for_source``,
        # so the source-module attribute is the binding that re-resolves
        # on each invocation. Patching ``the_one.mcp._pool.<name>`` would
        # raise AttributeError because no module-level binding exists at
        # that path.
        monkeypatch.setattr("the_one.mcp.oauth.build_oauth_provider_for_source", mock_factory)

        entry = _RegistryEntry(
            ttl_seconds=300,
            client_ready=asyncio.Event(),
            evict_event=asyncio.Event(),
        )

        # Sortie 09 DD7: the provider build lives INSIDE the worker's ``try``
        # (so a failure there cannot orphan ``client_ready``), so the sentinel
        # is recorded as the entry's failure instead of escaping the worker.
        await _entry_worker(source, entry)
        assert entry.client_ready.is_set()
        assert entry.failure is sentinel

        # The factory was invoked; the synthetic csid was forwarded as the
        # third positional argument (per provider_factory.py:60 —
        # ``chat_session_id`` is the third positional parameter).
        mock_factory.assert_called_once()
        call_args = mock_factory.call_args
        assert call_args.args[2] == f"agent_build:{source.id}"
    finally:
        current_chat_session_id.reset(csid_token)
        current_tool_call_id.reset(tcid_token)


async def test_pool_worker_skips_oauth_provider_when_no_auth_posture_cached(
    monkeypatch,
) -> None:
    """F9 L1 Shape C — `_entry_worker` reads `source.config._cache.auth_posture`
    and SKIPS the OAuth provider construction when the persisted verdict is
    "no_auth". MCPClient is constructed with `auth_provider=None`.

    Without this short-circuit, the pool would build a provider for any
    source with `dcr_credentials` even when the test endpoint already
    confirmed (via Phase 0) that the server requires no auth.
    """
    from the_one.mcp._pool import _entry_worker, _RegistryEntry

    source = MCPSource(
        id="src-no-auth-cached",
        name="t",
        type="streamable-http",
        config={
            "url": "https://no-auth-server.example.com/mcp",
            "_cache": {
                "tools": [],
                "capabilities": {},
                "last_updated": 1_700_000_000.0,
                "auth_posture": "no_auth",
            },
        },
        secrets={},
    )

    # If the worker (incorrectly) calls the factory we want to know — the
    # mock raises a sentinel that would surface as a test failure.
    factory_called: list[bool] = []

    def _explode(*args, **kwargs):
        factory_called.append(True)
        raise AssertionError(
            "build_oauth_provider_for_source must NOT be called when "
            "_cache.auth_posture == 'no_auth'"
        )

    monkeypatch.setattr("the_one.mcp.oauth.build_oauth_provider_for_source", _explode)

    # Capture how MCPClient was constructed.
    constructed_with: dict = {}

    class _CapturingClient:
        def __init__(self, source, auth_provider=None):
            constructed_with["source"] = source
            constructed_with["auth_provider"] = auth_provider
            self.is_alive = False

        async def connect(self):
            # Stop the worker before it enters the evict-wait loop. The
            # outer ``except BaseException`` translates this into
            # ``entry.failure`` so the test can return cleanly.
            raise RuntimeError("stop-after-construction")

        async def disconnect(self):
            pass

        def _touch_activity(self):
            pass

    monkeypatch.setattr(pool_mod, "MCPClient", _CapturingClient)

    entry = _RegistryEntry(
        ttl_seconds=300,
        client_ready=asyncio.Event(),
        evict_event=asyncio.Event(),
    )

    await _entry_worker(source, entry)

    assert factory_called == [], "OAuth provider factory was invoked despite cached no_auth verdict"
    assert "auth_provider" in constructed_with
    assert constructed_with["auth_provider"] is None, (
        "MCPClient must receive auth_provider=None when _cache.auth_posture == 'no_auth'"
    )
    # Worker stored the sentinel as a connect failure (clean exit).
    assert isinstance(entry.failure, RuntimeError)
