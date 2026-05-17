"""Tests for ``the_one/connectors/_pool.py`` — worker-task-per-entry pool primitives.

Leg 05 coverage:
   1. lazy-spawn-on-first-acquire
   2. warm-reuse-on-second-acquire
   3. concurrent-acquire-same-key-shares-one-worker  (cycle-2 race-fix lock)
   4. different-keys-spawn-independent-workers
   5. connect-failure-propagates  (``ConnectorConnectionError``)
   6. concurrent-acquire-with-failure-pops-once
   7. ``_evict`` idempotent on missing key
   8. ``_evict_all_for_account`` flushes warm entries
   9. ``_clear_for_test`` round-trips across iterations
  10. ``_load_account`` runs OUTSIDE the lock
  11. entry ttl_seconds is resolved at acquire time (leg-6 contract; was
      the leg-5 placeholder handoff test)
  12. acquire with unknown account type raises ``ConnectorRegistrationError``
  13. acquire during shutdown raises ``RuntimeError``

Leg 06 coverage (reaper + drain + TTL resolution):
  14. ``_resolve_ttl_seconds`` default is 1800
  15. ``_resolve_ttl_seconds`` reads env override
  16. ``_resolve_ttl_seconds`` non-int falls back to default
  17. ``_resolve_ttl_seconds`` read-at-call-time invariant
  18. ``acquire`` spawns reaper on first call; idempotent on subsequent
  19. ``_reap_once`` evicts idle entries past their TTL
  20. ``_reap_once`` does NOT evict fresh entries
  21. ``_reap_once`` skips entries mid-connect (``client is None``)
  22. ``acquire`` updates ``last_activity`` on warm reuse
  23. ``shutdown_drain`` cancels reaper + drains pool + flips
      ``_shutting_down``
  24. ``_clear_for_test`` cancels reaper; subsequent acquire spawns fresh

Project-level pytest-asyncio is in ``auto`` mode (``pyproject.toml`` line
``asyncio_mode = "auto"``), so ``async def test_*`` functions and ``async``
fixtures run on the asyncio event loop without per-test decorators.
"""

from __future__ import annotations

import asyncio

import pytest

from the_one.connectors import _pool as pool_mod
from the_one.connectors._pool import (
    _evict,
    _evict_all_for_account,
    acquire,
)
from the_one.connectors.base import DoctorReport, SessionKey
from the_one.connectors.errors import (
    ConnectorConnectionError,
    ConnectorRegistrationError,
)
from the_one.connectors.registry import (
    register_for_test,
    restore_to_baseline_for_test,
)
from the_one.db.models import ConnectorAccount


# Autouse cleanup. Project uses pytest-asyncio in `auto` mode.
@pytest.fixture(autouse=True)
async def _clear_pool_after_each_test():
    yield
    await pool_mod._clear_for_test()
    restore_to_baseline_for_test()


def _make_stub_account(
    account_id: str = "acct-test",
    type_name: str = "stub",
    name: str = "Test Account",
) -> ConnectorAccount:
    return ConnectorAccount(
        id=account_id,
        name=name,
        type=type_name,
        config={},
        secrets={},
    )


class _StubClient:
    """Stub ConnectorClient that structurally satisfies the Protocol."""

    _instance_count = 0

    def __init__(self) -> None:
        type(self)._instance_count += 1
        self._alive = True

    def is_alive(self) -> bool:
        return self._alive


class _StubPlugin:
    """Stub ConnectorPlugin that records connect/disconnect calls.

    Subclass per scenario rather than mutating attributes — keeps test
    intent localized.
    """

    connect_count = 0
    disconnect_count = 0

    async def connect(self, account, encryptor):  # noqa: ANN001  (test stub)
        type(self).connect_count += 1
        return _StubClient()

    async def disconnect(self, client):  # noqa: ANN001
        type(self).disconnect_count += 1
        client._alive = False

    async def doctor(self, account, encryptor):  # noqa: ANN001
        return DoctorReport(status="ok", message="stub", details={})

    def normalize_session_key(self, inbound):  # noqa: ANN001
        return SessionKey(
            platform=inbound.platform,
            account_id=inbound.account_id,
            channel_id=inbound.channel_id,
        )


@pytest.fixture
def patch_plugin(monkeypatch):
    """Register the stub plugin under 'stub' and patch _load_account.

    Returns the plugin class so tests can read ``connect_count`` /
    ``disconnect_count``. Tests requiring per-scenario behavior subclass
    ``_StubPlugin`` (see ``_FailingPlugin`` below for the failure path).
    """
    _StubPlugin.connect_count = 0
    _StubPlugin.disconnect_count = 0
    _StubClient._instance_count = 0
    register_for_test("stub", _StubPlugin)

    async def _patched_load_account(account_id, encryptor):
        return _make_stub_account(account_id=account_id)

    monkeypatch.setattr(pool_mod, "_load_account", _patched_load_account)
    return _StubPlugin


class _FailingPlugin(_StubPlugin):
    """Stub that raises ConnectorConnectionError from connect.

    NOTE: inherits ``disconnect`` from ``_StubPlugin``, but ``disconnect``
    is never reached in the failure path — the worker (`_entry_worker`)
    returns immediately on the connect-raise branch, before ``entry.client``
    is ever set. Do NOT add ``assert _FailingPlugin.disconnect_count == 0``
    expecting it to verify anything meaningful; the count is structurally
    zero in this scenario, not an asserted contract.
    """

    async def connect(self, account, encryptor):  # noqa: ANN001
        type(self).connect_count += 1
        raise ConnectorConnectionError("simulated connect failure")


# ─────────────────────────────────────────────────────────────────
# Test bodies
# ─────────────────────────────────────────────────────────────────


async def test_acquire_lazy_spawns_on_first_call(patch_plugin) -> None:
    client = await acquire("agent-a", "acct-1")
    assert isinstance(client, _StubClient)
    assert _StubPlugin.connect_count == 1


async def test_acquire_reuses_warm_entry(patch_plugin) -> None:
    client1 = await acquire("agent-a", "acct-1")
    client2 = await acquire("agent-a", "acct-1")
    assert client1 is client2
    assert _StubPlugin.connect_count == 1


async def test_concurrent_acquire_same_key_shares_one_worker(patch_plugin) -> None:
    """Cycle-2 race-fix lock: 10 concurrent acquires share ONE worker.

    Plugin connect yields control once so concurrent acquires can stack on
    the shared ``client_ready`` event before the worker resolves it. The
    yield is the structural reason all 10 awaits run concurrently rather
    than serializing on a synchronous connect.
    """

    class _SlowStubPlugin(_StubPlugin):
        connect_count = 0
        disconnect_count = 0

        async def connect(self, account, encryptor):  # noqa: ANN001
            type(self).connect_count += 1
            await asyncio.sleep(0.05)
            return _StubClient()

    register_for_test("stub", _SlowStubPlugin)

    results = await asyncio.gather(
        *(acquire("agent-a", "acct-1") for _ in range(10))
    )
    assert _SlowStubPlugin.connect_count == 1  # exactly ONE worker spawned
    first = results[0]
    for r in results:
        assert r is first


async def test_different_keys_spawn_independent_workers(patch_plugin) -> None:
    c1 = await acquire("agent-a", "acct-1")
    c2 = await acquire("agent-a", "acct-2")
    assert c1 is not c2
    assert _StubPlugin.connect_count == 2


async def test_connect_failure_propagates(patch_plugin, monkeypatch) -> None:
    register_for_test("stub", _FailingPlugin)
    _FailingPlugin.connect_count = 0
    with pytest.raises(ConnectorConnectionError, match="simulated connect failure"):
        await acquire("agent-a", "acct-1")
    # Entry popped on failure.
    assert pool_mod._pool == {}


async def test_concurrent_acquire_with_failure_pops_once(patch_plugin) -> None:
    register_for_test("stub", _FailingPlugin)
    _FailingPlugin.connect_count = 0
    results = await asyncio.gather(
        *(acquire("agent-a", "acct-1") for _ in range(5)),
        return_exceptions=True,
    )
    # All callers see the same exception type.
    assert all(isinstance(r, ConnectorConnectionError) for r in results)
    # Pool ends empty regardless of which caller popped first.
    assert pool_mod._pool == {}


async def test_evict_idempotent_on_missing_key() -> None:
    # Smoke: _evict on a key that was never inserted returns cleanly.
    await _evict(("never-spawned-agent", "never-spawned-account"))


async def test_evict_all_for_account_flushes_warm_entries(patch_plugin) -> None:
    # Spawn two warm entries for the same account under different agents.
    c1 = await acquire("agent-a", "acct-1")
    c2 = await acquire("agent-b", "acct-1")
    assert _StubPlugin.connect_count == 2
    # Different agents, same account → distinct keys, both warm.
    assert len(pool_mod._pool) == 2

    await _evict_all_for_account("acct-1")

    assert pool_mod._pool == {}
    assert _StubPlugin.disconnect_count == 2
    # Eviction marked both clients dead.
    assert not c1.is_alive()
    assert not c2.is_alive()


async def test_clear_for_test_round_trips_across_iterations(patch_plugin) -> None:
    """A test that leaves entries warm; _clear_for_test (via autouse)
    empties the pool; a second acquire in the same test re-spawns cleanly.

    Note: the autouse fixture runs AFTER each test, so to exercise the
    round-trip in a single test we call _clear_for_test manually.
    """
    await acquire("agent-a", "acct-1")
    assert len(pool_mod._pool) == 1
    assert pool_mod._shutting_down is False

    await pool_mod._clear_for_test()

    assert pool_mod._pool == {}
    assert pool_mod._shutting_down is False  # _clear_for_test does not leak True

    # Subsequent acquire works cleanly.
    client = await acquire("agent-a", "acct-1")
    assert isinstance(client, _StubClient)


async def test_acquire_unknown_account_type_raises_registration_error(monkeypatch) -> None:
    """Registry returns ConnectorRegistrationError for an unregistered type."""

    async def _load_unknown_type(account_id, encryptor):
        return _make_stub_account(account_id=account_id, type_name="unregistered")

    monkeypatch.setattr(pool_mod, "_load_account", _load_unknown_type)

    with pytest.raises(ConnectorRegistrationError):
        await acquire("agent-a", "acct-1")


async def test_load_account_runs_outside_lock(patch_plugin, monkeypatch) -> None:
    """`_load_account` must NOT execute while `_lock` is held — different-key
    acquires should not serialize on the DB read. Mirrors test #8 in
    tests/test_mcp_pool.py (cycle-2 race-fix invariant from MCP)."""

    locked_during_load = False

    async def _checking_load_account(account_id, encryptor):
        nonlocal locked_during_load
        # `_lock.locked()` returns True if any task holds the lock right now.
        # Acquiring it without waiting verifies the lock is NOT held by us.
        if pool_mod._lock.locked():
            locked_during_load = True
        return _make_stub_account(account_id=account_id)

    monkeypatch.setattr(pool_mod, "_load_account", _checking_load_account)

    await acquire("agent-a", "acct-1")

    assert locked_during_load is False, (
        "_load_account ran while _lock was held — cycle-2 race-fix invariant violated"
    )


async def test_entry_ttl_seconds_is_resolved_at_acquire_time(patch_plugin) -> None:
    """Leg 6: ``acquire`` populates ``entry.ttl_seconds`` via
    :func:`_resolve_ttl_seconds`, NOT the leg-5 ``0`` placeholder. The
    reaper consumes this value to decide eviction. With no env var set
    (the default test environment), the resolved value is
    ``_DEFAULT_TTL_SECONDS``."""
    from the_one.connectors._pool import _DEFAULT_TTL_SECONDS

    await acquire("agent-a", "acct-1")
    entry = pool_mod._pool[("agent-a", "acct-1")]
    assert entry.ttl_seconds == _DEFAULT_TTL_SECONDS, (
        f"Expected {_DEFAULT_TTL_SECONDS}, got {entry.ttl_seconds}"
    )


async def test_acquire_during_shutdown_raises_runtime_error(patch_plugin) -> None:
    pool_mod._shutting_down = True
    try:
        with pytest.raises(RuntimeError, match="shutting down"):
            await acquire("agent-a", "acct-1")
    finally:
        pool_mod._shutting_down = False  # local cleanup; autouse fixture also restores


# ─────────────────────────────────────────────────────────────────
# Leg 06 tests: reaper, TTL resolution, shutdown_drain
# ─────────────────────────────────────────────────────────────────


async def test_resolve_ttl_seconds_default_is_1800(monkeypatch) -> None:
    """No env var set → returns the 1800s default (30 min)."""
    monkeypatch.delenv("THE_ONE_CONNECTOR_POOL_IDLE_TTL_SECONDS", raising=False)
    from the_one.connectors._pool import _resolve_ttl_seconds

    assert _resolve_ttl_seconds() == 1800


async def test_resolve_ttl_seconds_reads_env_override(monkeypatch) -> None:
    """Env var set to a parseable int → returns that int."""
    monkeypatch.setenv("THE_ONE_CONNECTOR_POOL_IDLE_TTL_SECONDS", "60")
    from the_one.connectors._pool import _resolve_ttl_seconds

    assert _resolve_ttl_seconds() == 60


async def test_resolve_ttl_seconds_non_int_falls_back(monkeypatch) -> None:
    """Env var set to a non-int → fall back to the default with a warning."""
    monkeypatch.setenv("THE_ONE_CONNECTOR_POOL_IDLE_TTL_SECONDS", "not-a-number")
    from the_one.connectors._pool import _resolve_ttl_seconds

    assert _resolve_ttl_seconds() == 1800


async def test_resolve_ttl_seconds_read_at_call_time(monkeypatch) -> None:
    """Live-read invariant: env var changes between calls are observed.

    A naive implementation that caches the value at module import would
    fail this test — the first call returns the default, then the second
    call (after setenv) returns the override.
    """
    from the_one.connectors._pool import _resolve_ttl_seconds

    monkeypatch.delenv("THE_ONE_CONNECTOR_POOL_IDLE_TTL_SECONDS", raising=False)
    assert _resolve_ttl_seconds() == 1800
    monkeypatch.setenv("THE_ONE_CONNECTOR_POOL_IDLE_TTL_SECONDS", "120")
    assert _resolve_ttl_seconds() == 120


async def test_acquire_spawns_reaper(patch_plugin) -> None:
    """First ``acquire`` spawns the reaper; the second does NOT spawn a second.

    The reaper is module-level state; ``_ensure_reaper_running_locked``
    is idempotent — calling it from a second concurrent acquire (for a
    different key) finds the existing task and skips the spawn.
    """
    assert pool_mod._reaper_task is None

    await acquire("agent-a", "acct-1")
    assert pool_mod._reaper_task is not None
    first_task = pool_mod._reaper_task

    await acquire("agent-b", "acct-2")
    assert pool_mod._reaper_task is first_task


async def test_reap_once_evicts_idle_entries(patch_plugin) -> None:
    """Age an entry by stamping ``last_activity`` to a very old value;
    ``_reap_once`` returns the key and evicts the entry."""
    from the_one.connectors._pool import _reap_once

    await acquire("agent-a", "acct-1")
    entry = pool_mod._pool[("agent-a", "acct-1")]
    entry.last_activity = 0.0  # very old — definitely past any TTL

    expired = await _reap_once()
    assert expired == [("agent-a", "acct-1")]
    assert pool_mod._pool == {}


async def test_reap_once_does_not_evict_fresh_entries(patch_plugin) -> None:
    """A freshly-acquired entry has ``last_activity`` set to ``now``;
    ``_reap_once`` returns the empty list and the pool is unchanged."""
    from the_one.connectors._pool import _reap_once

    await acquire("agent-a", "acct-1")
    expired = await _reap_once()
    assert expired == []
    assert ("agent-a", "acct-1") in pool_mod._pool


async def test_reap_once_skips_entries_mid_connect(patch_plugin) -> None:
    """Entries with ``client is None`` (worker mid-connect) are NOT
    reaped even if ``last_activity`` is ancient. Prevents reaping a
    worker that has not yet had a chance to populate the client."""
    from the_one.connectors._pool import _reap_once, _RegistryEntry

    key = ("agent-a", "acct-mid-connect")
    entry = _RegistryEntry(
        ttl_seconds=10,
        last_activity=0.0,  # ancient
        evict_event=asyncio.Event(),
        client_ready=asyncio.Event(),
        client=None,  # NOT YET CONNECTED
    )
    async with pool_mod._lock:
        pool_mod._pool[key] = entry

    expired = await _reap_once()
    assert expired == []
    assert key in pool_mod._pool

    # Clean up the half-constructed entry so the autouse cleanup
    # doesn't trip on the None worker.
    async with pool_mod._lock:
        pool_mod._pool.pop(key, None)


async def test_acquire_updates_last_activity_on_warm_reuse(patch_plugin) -> None:
    """Second acquire on the same key updates ``last_activity`` even
    though the warm worker is reused — the touch is unconditional in the
    return path. A small sleep ensures ``time.monotonic`` advances on
    coarse-clock hosts (WSL2 / CI)."""
    await acquire("agent-a", "acct-1")
    entry = pool_mod._pool[("agent-a", "acct-1")]
    first_activity = entry.last_activity

    await asyncio.sleep(0.05)
    await acquire("agent-a", "acct-1")
    assert entry.last_activity > first_activity


async def test_shutdown_drain_cancels_reaper_and_drains_pool(patch_plugin) -> None:
    """``shutdown_drain`` cancels the reaper, evicts every remaining
    entry, flips ``_shutting_down``, and resets ``_reaper_task``.
    Subsequent acquire raises ``RuntimeError``."""
    from the_one.connectors._pool import shutdown_drain

    await acquire("agent-a", "acct-1")
    await acquire("agent-b", "acct-2")
    assert len(pool_mod._pool) == 2
    assert pool_mod._reaper_task is not None

    await shutdown_drain()

    assert pool_mod._pool == {}
    assert pool_mod._reaper_task is None
    assert pool_mod._shutting_down is True

    with pytest.raises(RuntimeError, match="shutting down"):
        await acquire("agent-c", "acct-3")


async def test_clear_for_test_cancels_reaper(patch_plugin) -> None:
    """``_clear_for_test`` cancels the reaper FIRST (before the worker-
    cancel loop) and resets ``_reaper_task = None``. A subsequent acquire
    spawns a fresh reaper distinct from the one we just cancelled."""
    await acquire("agent-a", "acct-1")
    assert pool_mod._reaper_task is not None
    first_task = pool_mod._reaper_task

    await pool_mod._clear_for_test()
    assert pool_mod._reaper_task is None

    await acquire("agent-a", "acct-1")
    assert pool_mod._reaper_task is not None
    assert pool_mod._reaper_task is not first_task
