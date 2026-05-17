# Leg: lifecycle-pool-core

**Status**: landed
**Flight**: [Connector Plugin Contract and Lifecycle Foundation](../flight.md)

## Objective

Create `the_one/connectors/_pool.py` Part 1 — the per-(agent, account) lifecycle pool primitives that the connector subsystem uses for warm-connection management. Mirrors `the_one/mcp/_pool.py`'s worker-task-per-entry pattern with M07's test-isolation lesson applied from the start. Ships `_RegistryEntry`, module-level state, `_load_account`, `_entry_worker`, `acquire`, `_evict`, `_evict_all_for_account`, and `_clear_for_test`. Does NOT ship `_resolve_ttl_seconds`, `_reap_*`, `_ensure_reaper_running_locked`, or `shutdown_drain` — those land in leg 6.

## Context

This is leg 5 of Flight 1 of Mission 10 — the heaviest implementation leg of the flight. Leg 4 landed the registry (the dispatch table from type-name to plugin). This leg lands the **warm-pool runtime** that holds open connections one per (agent, account) pair and serves them via `acquire()`.

### Patterns to mirror — and where to diverge

The structural template is `the_one/mcp/_pool.py` (561 LoC). The connector pool mirrors at the per-entry-worker level but diverges on three axes:

| Concern | MCP pool | Connector pool |
|---|---|---|
| **Client construction** | `MCPClient(source, auth_provider=...)` directly in worker | `plugin.connect(account, encryptor)` — plugin's responsibility |
| **OAuth context** | csid/tcid ContextVar lookup + synthetic-csid dance | NONE — connector auth is platform-specific, no shared OAuth flow |
| **Activity touch on acquire** | `client._touch_activity()` — MCPClient-specific | NOT YET — TTL touching arrives in leg 6 alongside the reaper |
| **`source_override`** | F6 L2 per-agent override | NOT in this flight; Flight 6 will introduce ACLs/overrides |

### Test-isolation fix — M07's `_shutting_down` lesson applied from day one

The mission's Known Issues section captures the M07 debt: `the_one/mcp/_pool.py` has `_shutting_down: bool = False` at module scope that can leak between tests when not scrupulously reset. The leg's flight-level design decision is: **connector pool gets the fix from the start**.

Concretely, the connector pool's `_clear_for_test` must:

1. Reset `_shutting_down = False` (it would have been set True by leg 6's `shutdown_drain`, but in this leg it never flips since we haven't shipped `shutdown_drain`)
2. Snapshot the pool's contents under `_lock`, then clear the dict
3. Set `evict_event` on every entry so workers wake up
4. Cancel every worker task
5. Await every cancelled worker (`with contextlib.suppress(BaseException)`)
6. Leave `_pool` empty, `_lock` available, `_shutting_down = False` — the post-import baseline

This is the same shape MCP's `_clear_for_test` ended up with after M07's debt was retroactively patched — we apply it correctly from day one rather than discovering the leak across tests later.

### Design constraints from the flight that bind this leg

- **Mirror the worker-task-per-entry pattern from `mcp/_pool.py`** — the anyio cross-task `CancelScope.__aexit__` guard is the hardest invariant to maintain; deviating produces hard-to-reproduce test failures. Specifically: connect AND disconnect run on the same task (the entry worker); the eviction path signals via `evict_event` rather than cancelling the worker.
- **The pool's key is `(agent_name, account_id)`** mirroring MCP's `(agent_name, source_id)`. Tuple-keyed dict; module-level mutation through `_lock`.
- **Plugin dispatch** uses `the_one.connectors.registry.resolve(account.type)` to get a plugin instance, then `plugin.connect(account, encryptor)` to construct the client. The encryptor comes from `get_encryptor(settings.data_dir)`.
- **No TTL field usage in this leg.** The `_RegistryEntry` dataclass DOES include `ttl_seconds: int` (so leg 6's reaper can read it without dataclass shape changes), but `acquire` sets it to `0` here as a placeholder. Leg 6 will change `acquire` to use `_resolve_ttl_seconds()`.
- **`_entry_worker` is `BaseException`-tolerant on connect failure** — populates `entry.failure` BEFORE setting `client_ready`. Disconnect runs in `finally:` (best-effort, logs but does not raise).
- **`acquire` uses the cycle-2 race-handling invariant**: pre-load OUTSIDE the lock; lock-held branch checks `entry is None`; concurrent same-key acquires share the worker by waiting on `entry.client_ready` outside the lock; on connect failure, idempotently pop the entry (only if it's still THIS entry).
- **Asyncio single-threaded memory ordering** — `failure` / `client` written BEFORE `client_ready.set()`; post-event reads observe the writes. No memory barriers needed.
- **The pool does NOT use the connectors registry's `resolve()` to obtain a plugin during `_load_account`.** Plugin resolution happens AFTER `_load_account` returns the account model (`acquire` calls `resolve(account.type)`). This keeps `_load_account` a pure DB read.

## Inputs

What exists before this leg runs:

- Legs 1-4 landed (uncommitted on the feature branch)
- `the_one/connectors/base.py` exports `ConnectorPlugin`, `ConnectorClient`
- `the_one/connectors/registry.py` exports `resolve`, `register_for_test`, `restore_to_baseline_for_test`, `clear_for_test` (the registry's seam, distinct from this leg's pool seam)
- `the_one/db/models.py` exports `ConnectorAccount`
- `the_one/db/repositories.py` exports `ConnectorAccountRepository`
- `the_one/db/connection.py` exports `get_connection` (used by `_load_account`)
- `the_one/encryption.py` exports `get_encryptor` (used by `_load_account` and the worker)
- `the_one/config.py` exports `settings.data_dir`
- The MCP pool exists at `the_one/mcp/_pool.py` (561 LoC) — the structural template
- Tests for the MCP pool exist at `tests/test_mcp_pool.py` — the test-pattern template

## Outputs

What exists after this leg completes:

- New file `the_one/connectors/_pool.py` with:
  - Module docstring describing the leg-5 scope and what's deferred to leg 6
  - `_RegistryEntry` dataclass with fields: `ttl_seconds: int`, `worker: asyncio.Task[None] | None`, `evict_event: asyncio.Event | None`, `client_ready: asyncio.Event | None`, `client: ConnectorClient | None`, `failure: BaseException | None`
  - Module state: `_pool: dict[tuple[str, str], _RegistryEntry]`, `_lock: asyncio.Lock`, `_shutting_down: bool = False`
  - `_load_account(account_id) -> ConnectorAccount` — DB read OUTSIDE the lock
  - `_entry_worker(plugin, account, encryptor, entry)` — single-task connect-then-await-evict-then-disconnect
  - `_evict(key)` — pop, signal, await worker (10s timeout + cancel-on-stuck)
  - `_evict_all_for_account(account_id)` — flush all keys matching the account
  - `acquire(agent_name, account_id) -> ConnectorClient` — cycle-2 race-safe lookup-or-spawn
  - `_clear_for_test()` — test seam with the M07 fix applied
- New file `tests/test_connectors_pool.py` with at least 9 tests covering the leg-5 scope (see Acceptance Criteria)
- All tests pass; `make test`, `make lint` clean
- Leg status `landed`
- Flight log gains a `### Leg 05: lifecycle-pool-core` entry

## Acceptance Criteria

- [ ] `the_one/connectors/_pool.py` exists with module docstring naming the leg-5 vs leg-6 split
- [ ] `_RegistryEntry` dataclass defined with fields exactly as enumerated in Outputs; `worker`, `evict_event`, `client_ready`, `client`, `failure` all default to `None`; `ttl_seconds` is required (no default — populated by `acquire`)
- [ ] Module state `_pool: dict[tuple[str, str], _RegistryEntry]`, `_lock: asyncio.Lock`, `_shutting_down: bool = False` at module top
- [ ] `_load_account(account_id, encryptor) -> ConnectorAccount` reads from `ConnectorAccountRepository` using the passed-in encryptor; raises `KeyError` on miss (propagates the repository's exception)
- [ ] `_entry_worker(plugin, account, encryptor, entry)`:
    - Calls `plugin.connect(account, encryptor)` inside a `try:` block
    - On `BaseException`: sets `entry.failure = exc` BEFORE `entry.client_ready.set()`; returns
    - On success: sets `entry.client = client` BEFORE `entry.client_ready.set()`; awaits `entry.evict_event.wait()`; calls `plugin.disconnect(client)` in `finally:` (logs but does not raise)
- [ ] `_evict(key) -> None`:
    - Idempotent on missing key
    - Pops the entry under `_lock`, then signals `entry.evict_event.set()`, then awaits the worker
    - 10s timeout via `asyncio.wait_for`; on timeout, cancels the worker and suppresses the resulting exception
- [ ] `_evict_all_for_account(account_id) -> None`:
    - Snapshots matching keys under `_lock` (filter by `key[1] == account_id`)
    - Calls `_evict(key)` for each match (sequential — sub-second per evict in practice, no parallelism premature)
    - Idempotent on no-match
- [ ] `acquire(agent_name: str, account_id: str) -> ConnectorClient`:
    - Resolves the system encryptor ONCE via `get_encryptor(settings.data_dir)` (single cache hit)
    - Pre-loads the account OUTSIDE the lock via `_load_account(account_id, encryptor)`
    - Resolves the plugin via `registry.resolve(account.type)` — propagates `ConnectorRegistrationError` if the type isn't registered
    - Under `_lock`: if `_shutting_down`, raises `RuntimeError("Connector pool is shutting down")`; if the key has no entry, constructs one with `ttl_seconds=0` (leg-6 placeholder), spawns the worker via `asyncio.create_task(_entry_worker(...))`, inserts into `_pool`
    - Releases the lock; awaits `entry.client_ready`; if `entry.failure is not None`, idempotently pops the entry (only if it's still THIS entry by `is` check) and raises the failure
    - On success returns `entry.client` (asserts non-None — invariant guaranteed by the worker writing `client` before setting `client_ready`)
- [ ] `_clear_for_test() -> None`:
    - Snapshots `_pool` items under `_lock`; clears `_pool`
    - For each snapshotted entry: sets `evict_event` (if not None), cancels the worker, awaits the worker with `contextlib.suppress(BaseException)`
    - Sets `_shutting_down = False` at the end (idempotent — defense against future leg 6 changes)
- [ ] `tests/test_connectors_pool.py` exists with at minimum these tests passing:
    - `test_acquire_lazy_spawns_on_first_call` — stub plugin's `connect` called once; client returned matches the stub
    - `test_acquire_reuses_warm_entry` — second acquire on same key returns the same client object; stub plugin's `connect` called exactly once
    - `test_concurrent_acquire_same_key_shares_one_worker` — N concurrent acquires; stub's `connect` called once; all callers receive the same client
    - `test_different_keys_spawn_independent_workers` — two acquires with different (agent, account) pairs; stub's `connect` called twice; clients differ
    - `test_connect_failure_propagates` — stub raises `ConnectorConnectionError` from `connect`; acquire re-raises; pool is empty after (entry popped on failure)
    - `test_concurrent_acquire_with_failure_pops_once` — N concurrent acquires hit the same failed connect; all see the exception; pool ends empty (idempotent pop)
    - `test_evict_idempotent_on_missing_key` — `_evict(("agent", "nonexistent"))` returns cleanly
    - `test_evict_all_for_account_flushes_warm_entries` — register 2 entries for the same account under different agents; call `_evict_all_for_account`; both evicted; stub's `disconnect` called twice
    - `test_clear_for_test_round_trips_across_iterations` — after a test that leaves entries warm, `_clear_for_test` empties pool; next test sees clean state (verified by the autouse fixture pattern)
    - `test_load_account_runs_outside_lock` — `_load_account` is structurally NOT called while `_lock` is held (mirrors `tests/test_mcp_pool.py` test #8; locks the cycle-2 race-fix invariant against future regressions)
    - `test_entry_ttl_seconds_placeholder_is_zero` — `acquire` constructs entries with `ttl_seconds=0`; locks the leg-5 placeholder contract so leg 6's first work item is to flip this assertion
    - `test_acquire_unknown_account_type_raises_registration_error` — account.type isn't registered; `resolve()` propagates `ConnectorRegistrationError`
    - `test_acquire_during_shutdown_raises_runtime_error` — `_shutting_down = True`; acquire raises `RuntimeError`
- [ ] Tests use an autouse `_clear_pool_after_each_test` fixture analogous to `tests/test_mcp_pool.py`'s pattern; the fixture also calls `connectors.registry.restore_to_baseline_for_test()` so registry state is reset between tests
- [ ] `make test`, `make lint` clean for the full suite
- [ ] Leg status `landed`
- [ ] `lifecycle-pool-core` checkbox checked in flight.md's Legs section
- [ ] Flight log has `### Leg 05: lifecycle-pool-core` entry under `## Leg Progress`

## Verification Steps

1. **Module loads cleanly**:
   - `docker exec the-one python -c "from the_one.connectors import _pool; print('ok')"`

2. **Public API surface exists**:
   - `docker exec the-one python -c "from the_one.connectors._pool import acquire, _evict, _evict_all_for_account, _clear_for_test, _RegistryEntry, _pool, _lock, _shutting_down; print('ok')"`

3. **Pool behaviour**:
   - The `tests/test_connectors_pool.py` test suite is the canonical verifier — all 11 tests must pass

4. **No regression**:
   - `docker exec the-one pytest -x --timeout 30 tests/test_connectors.py tests/test_connectors_pool.py tests/test_mcp_pool.py` is clean (sanity-check that the MCP pool isn't disturbed)
   - `docker exec the-one pytest -x --timeout 30` full suite is clean
   - `make lint` clean

5. **Test-isolation invariant**:
   - Run the new tests twice in a row in the same session — `docker exec the-one pytest -x --timeout 30 tests/test_connectors_pool.py tests/test_connectors_pool.py` should pass both times (autouse fixture's `_clear_for_test` makes this idempotent)

## Implementation Guidance

### Step 1: Create `the_one/connectors/_pool.py`

Module docstring sets the scope. Mirror `mcp/_pool.py:1-37`'s shape.

```python
"""Connector account pool — per-(agent, account) keyed worker-task-per-entry registry.

Mirrors :mod:`the_one.mcp._pool` at the structural level: module-level
dict keyed on ``(agent_name, account_id)``; ``asyncio.Lock`` for serialized
mutations; per-entry worker task that holds the platform connection on a
SINGLE task — connect AND disconnect run on the same task, satisfying
anyio's cross-task ``CancelScope.__aexit__`` guard.

Flight 1 lands the pool in two legs:
  - L5 (this module): :class:`_RegistryEntry`, ``_pool``, ``_lock``,
    :func:`_load_account`, :func:`_entry_worker`, :func:`_evict`,
    :func:`_evict_all_for_account`, :func:`acquire`,
    :func:`_clear_for_test`.
  - L6: ``_resolve_ttl_seconds``, ``_reap_once``, ``_reap_loop``,
    ``_ensure_reaper_running_locked``, ``shutdown_drain``, FastAPI
    lifespan integration.

Public API (re-exported from :mod:`the_one.connectors` at leg 8):
  - :func:`acquire`
  - :func:`shutdown_drain` (lands in leg 6)

Internal symbols (underscore-prefixed; tests reach in for ``_clear_for_test``
and friends):
  - :class:`_RegistryEntry`, ``_pool``, ``_lock``, ``_shutting_down``
  - :func:`_load_account`, :func:`_entry_worker`, :func:`_evict`,
    :func:`_evict_all_for_account`, :func:`_clear_for_test`

Race-handling invariant (mirroring MCP's cycle-2 fix):
  The lock-held branch checks ``entry is None`` (NOT ``entry.client is
  None``). Concurrent same-key acquires share the worker by waiting on
  ``entry.client_ready`` outside the lock. The worker is the SOLE writer
  of ``entry.client`` and ``entry.failure``; both are written BEFORE
  ``entry.client_ready.set()``. asyncio's single-threaded event loop
  guarantees post-event reads observe those writes.

Test-isolation invariant (mission 10 design decision — fix M07's
``_shutting_down`` leak from day one):
  :func:`_clear_for_test` resets ``_shutting_down = False`` along with
  clearing ``_pool`` and cancelling worker tasks. Tests must call this
  in an autouse fixture AFTER each test; otherwise the next test
  inherits stale state.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass

from the_one.config import settings
from the_one.connectors.base import ConnectorClient, ConnectorPlugin
from the_one.connectors.registry import resolve as _resolve_plugin
from the_one.db.connection import get_connection
from the_one.db.models import ConnectorAccount
from the_one.db.repositories import ConnectorAccountRepository
from the_one.encryption import Encryptor, get_encryptor

logger = logging.getLogger(__name__)


@dataclass
class _RegistryEntry:
    """A pool entry. Holds connection state shared between the entry
    worker and any concurrent :func:`acquire` callers waiting on
    ``client_ready``.

    Mirrors :class:`the_one.mcp._pool._RegistryEntry`. ``ttl_seconds`` is
    a leg-5 placeholder (set to 0 by :func:`acquire`); leg 6's reaper
    populates it via ``_resolve_ttl_seconds()``.
    """

    ttl_seconds: int
    worker: asyncio.Task[None] | None = None
    evict_event: asyncio.Event | None = None
    client_ready: asyncio.Event | None = None
    client: ConnectorClient | None = None
    failure: BaseException | None = None


# Module-level state. All mutations to ``_pool`` (other than the lazy lock
# construction itself) go through ``_lock``.
_pool: dict[tuple[str, str], _RegistryEntry] = {}
_lock: asyncio.Lock = asyncio.Lock()
_shutting_down: bool = False


async def _load_account(account_id: str, encryptor: Encryptor) -> ConnectorAccount:
    """Load a :class:`ConnectorAccount` by id from the leg-2 repository.

    Called OUTSIDE ``_lock`` so different-key acquires don't serialize on
    the DB read. Raises ``KeyError`` on miss (propagates the repository's
    exception unchanged).

    Takes ``encryptor`` explicitly rather than calling ``get_encryptor`` —
    avoids double-call drift if test fixtures swap ``settings.data_dir`` or
    wipe ``_encryptor_cache``. The single resolution point is :func:`acquire`.
    """
    conn = await get_connection()
    repo = ConnectorAccountRepository(conn, encryptor)
    return await repo.get(account_id)


async def _entry_worker(
    plugin: ConnectorPlugin,
    account: ConnectorAccount,
    encryptor: Encryptor,
    entry: _RegistryEntry,
) -> None:
    """Hold the connection on a single task. Run teardown on same task.

    On connect-failure, populate ``entry.failure`` BEFORE setting
    ``client_ready``. On connect-success, populate ``entry.client``
    BEFORE setting ``client_ready``. Then idle until ``evict_event``
    fires; the ``finally:`` clause runs ``plugin.disconnect(client)`` —
    anyio cross-task guard satisfied because connect and disconnect both
    run on this task.

    ``BaseException`` is caught (not just ``Exception``) so a
    ``CancelledError`` raised inside connect surfaces to acquire callers
    as ``entry.failure``. :func:`_evict` signals eviction by setting
    ``evict_event``, NOT by cancelling the worker.
    """
    assert entry.client_ready is not None  # invariant: set at construction
    assert entry.evict_event is not None
    try:
        client = await plugin.connect(account, encryptor)
    except BaseException as exc:
        entry.failure = exc
        entry.client_ready.set()
        return
    entry.client = client
    entry.client_ready.set()
    try:
        await entry.evict_event.wait()
    finally:
        try:
            await plugin.disconnect(client)
        except Exception:
            logger.exception(
                "Connector plugin disconnect failed during entry teardown "
                "(account=%r, type=%r)",
                account.id,
                account.type,
            )


async def _evict(key: tuple[str, str]) -> None:
    """Pop the entry, signal the worker to teardown, await the worker.

    Idempotent on missing key. 10s timeout + cancel-on-stuck mirroring
    :func:`the_one.mcp._pool._evict`.
    """
    async with _lock:
        entry = _pool.pop(key, None)
    if entry is None:
        return
    assert entry.evict_event is not None
    assert entry.worker is not None  # set at acquire-time before insert
    entry.evict_event.set()
    try:
        await asyncio.wait_for(entry.worker, timeout=10.0)
    except asyncio.TimeoutError:
        logger.warning(
            "Connector pool worker for %r did not terminate within 10s", key
        )
        entry.worker.cancel()
        with contextlib.suppress(BaseException):
            await entry.worker


async def _evict_all_for_account(account_id: str) -> None:
    """Evict every pool entry whose key matches ``account_id`` across all agents.

    Called when an operator updates a connector account's credentials
    (flight 2) so the next ``acquire(agent_name, account_id)`` for the
    same account spawns a fresh worker with the new credentials.
    Without this, the warm cache would hand out a stale-credential
    ``ConnectorClient`` indefinitely.

    Walks all ``(agent_name, aid)`` keys; calls :func:`_evict` for each
    match. Sequential — each evict has its own 10s timeout but in
    practice an account has 1-3 active agents max.

    Idempotent on no-match.
    """
    async with _lock:
        keys = [key for key in _pool if key[1] == account_id]
    for key in keys:
        await _evict(key)


async def acquire(agent_name: str, account_id: str) -> ConnectorClient:
    """Look up or spawn the warm :class:`ConnectorClient` for ``(agent, account)``.

    Per the cycle-2 race-handling invariant inherited from MCP: pre-load
    the account OUTSIDE the lock; check ``entry is None`` under the lock
    (atomic existence dispatch); wait on ``entry.client_ready`` outside
    the lock; on failure, raise and pop idempotently; on success,
    return the client.

    Concurrent same-key acquires SHARE one worker — the lock-held branch
    creates the worker on the first caller; subsequent callers find the
    entry already present and fall through to the ``client_ready.wait()``
    outside the lock.

    Caller cancellation mid-``await client_ready.wait()`` leaves the
    worker running. The entry stays in ``_pool`` and (in leg 6) reaps
    on idle TTL. Subsequent acquire on the same key reuses the worker.

    Failure-propagation: if ``connect`` raises, the worker stores the
    exception in ``entry.failure`` and sets ``client_ready``. Every
    waiting caller observes the failure, pops the entry idempotently
    (using ``_pool.pop(key, None)``) and re-raises. The next acquire on
    the same key spawns a fresh worker.

    Plugin dispatch: the account's ``type`` field is resolved against
    the connector registry (leg 4); the produced plugin instance is
    pinned to this entry for its lifetime. If a future flight enables
    type re-registration (it shouldn't, per the registry's collision
    check), warm entries would keep using the original plugin until
    eviction.
    """
    encryptor = get_encryptor(settings.data_dir)
    account = await _load_account(account_id, encryptor)
    plugin = _resolve_plugin(account.type)

    async with _lock:
        if _shutting_down:
            raise RuntimeError("Connector pool is shutting down")
        key = (agent_name, account_id)
        entry = _pool.get(key)
        if entry is None:
            entry = _RegistryEntry(
                ttl_seconds=0,  # leg-5 placeholder; leg 6 populates via _resolve_ttl_seconds
                evict_event=asyncio.Event(),
                client_ready=asyncio.Event(),
            )
            entry.worker = asyncio.create_task(
                _entry_worker(plugin, account, encryptor, entry)
            )
            _pool[key] = entry
        # else: entry exists. Wait on client_ready outside the lock.

    assert entry.client_ready is not None
    await entry.client_ready.wait()

    if entry.failure is not None:
        async with _lock:
            existing = _pool.get(key)
            if existing is entry:
                _pool.pop(key, None)
        raise entry.failure

    client = entry.client
    assert client is not None  # invariant: client_ready set + no failure → populated
    return client


async def _clear_for_test() -> None:
    """Test seam: cancel all worker tasks; empty the pool; reset state.

    Applies M07's lesson from day one: ``_shutting_down`` is explicitly
    reset to ``False`` so the next test does not inherit a leaked True
    value. Mirrors :func:`the_one.mcp._pool._clear_for_test` but without
    the leg-6 reaper-cancel branch (no reaper exists yet).

    Tests should call this in an autouse fixture AFTER each test.
    """
    global _shutting_down

    async with _lock:
        snapshot = list(_pool.items())
        _pool.clear()
    for _key, entry in snapshot:
        if entry.evict_event is not None:
            entry.evict_event.set()
        worker = entry.worker
        if worker is not None and not worker.done():
            worker.cancel()
        if worker is not None:
            with contextlib.suppress(BaseException):
                await worker

    _shutting_down = False
```

### Step 2: Create `tests/test_connectors_pool.py`

Mirror `tests/test_mcp_pool.py`'s shape — autouse cleanup fixture, in-test stub plugin + client, monkeypatch of `_load_account`.

```python
"""Tests for ``the_one/connectors/_pool.py`` — worker-task-per-entry pool primitives (leg 05)."""

from __future__ import annotations

import asyncio

import pytest

from the_one.connectors import _pool as pool_mod
from the_one.connectors._pool import (
    _evict,
    _evict_all_for_account,
    acquire,
)
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
        from the_one.connectors.base import DoctorReport
        return DoctorReport(status="ok", message="stub", details={})

    def normalize_session_key(self, inbound):  # noqa: ANN001
        from the_one.connectors.base import SessionKey
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
    results = await asyncio.gather(
        *(acquire("agent-a", "acct-1") for _ in range(10))
    )
    assert _StubPlugin.connect_count == 1
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
    with pytest.raises(ConnectorConnectionError, match="simulated connect failure"):
        await acquire("agent-a", "acct-1")
    # Entry popped on failure.
    assert pool_mod._pool == {}


async def test_concurrent_acquire_with_failure_pops_once(patch_plugin) -> None:
    register_for_test("stub", _FailingPlugin)
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


async def test_entry_ttl_seconds_placeholder_is_zero(patch_plugin) -> None:
    """Leg-5 placeholder: entries are constructed with ttl_seconds=0.
    Leg 6's first work item flips this assertion when the reaper lands —
    this test is the explicit handoff signal between legs."""
    await acquire("agent-a", "acct-1")
    entry = pool_mod._pool[("agent-a", "acct-1")]
    assert entry.ttl_seconds == 0, (
        f"Leg-5 entries should have ttl_seconds=0 placeholder; got {entry.ttl_seconds}. "
        f"If leg 6 has landed, flip this assertion to assert ttl_seconds > 0."
    )


async def test_acquire_during_shutdown_raises_runtime_error(patch_plugin) -> None:
    pool_mod._shutting_down = True
    try:
        with pytest.raises(RuntimeError, match="shutting down"):
            await acquire("agent-a", "acct-1")
    finally:
        pool_mod._shutting_down = False  # local cleanup; autouse fixture also restores
```

### Step 3: Run targeted tests + full suite + lint

```bash
docker exec the-one pytest -x --timeout 30 tests/test_connectors_pool.py
docker exec the-one pytest -x --timeout 30 tests/test_connectors.py tests/test_connectors_pool.py tests/test_mcp_pool.py
docker exec the-one pytest -x --timeout 30
docker exec the-one bash -c "cd /workspace && make lint"
```

### Step 4: Update flight artifacts + leg status

- Append `### Leg 05: lifecycle-pool-core` entry under `## Leg Progress` in flight-log.md
- Check off `lifecycle-pool-core` in flight.md's Legs section
- Set this leg's status to `landed`
- Signal `[HANDOFF:review-needed]`; do NOT commit

## Edge Cases

- **Worker on `BaseException` (including `CancelledError`)** — populates `entry.failure` and returns. The post-event read in `acquire` re-raises the exception. `CancelledError` is unusual but possible if a test cancels mid-connect; this is the MCP precedent (mcp/_pool.py:163-167).
- **Idempotent pop on failure** — multiple callers may concurrently see `entry.failure is not None`; each calls `_pool.pop(key, None)`. The `existing is entry` check ensures we don't pop a successor entry that a later acquire spawned in our place. The dict mutation is under `_lock`.
- **`_load_account` failures** — `KeyError` from the repository propagates to the `acquire` caller before the lock-held branch. The pool is never mutated. This is the desired behaviour.
- **Plugin resolution failure** — `_resolve_plugin(account.type)` raises `ConnectorRegistrationError` for unknown types. Like `_load_account` failures, this fires outside the lock; pool unchanged.
- **`encryptor` is loaded fresh in `acquire` AND passed to the worker** — the worker re-uses the encryptor reference for the entry's lifetime. If `get_encryptor` returns a singleton (which it does — `the_one/encryption.py:_encryptor_cache`), this is the same instance each call; post-rotation propagation via `install_key` is automatic.
- **`_evict` on an entry whose worker hasn't yet set `client_ready`** — the worker can be mid-connect when eviction fires. `_evict` sets `evict_event`; the worker, after its connect-success branch, awaits `evict_event.wait()` — but only after setting `client_ready`. If `_evict` fires BEFORE the worker reaches the await, the worker still completes the connect, then immediately sees `evict_event` set and falls through to `finally:` to disconnect. The race is benign — the connect runs to completion, then disconnects cleanly. The worker task completes normally; `await asyncio.wait_for(entry.worker, timeout=10.0)` resolves quickly.
- **Tests that mutate `_shutting_down` directly** — the autouse `_clear_for_test` fixture resets it after every test. Tests that flip it inline (like `test_acquire_during_shutdown_raises_runtime_error`) include local cleanup as defense-in-depth but the autouse fixture is the primary safety net.

## Files Affected

- `the_one/connectors/_pool.py` (NEW) — pool primitives (leg-5 scope)
- `tests/test_connectors_pool.py` (NEW) — 11 tests covering the leg-5 contract
- `missions/10-bi-directional-comms-connectors/flights/01-connector-plugin-contract-and-lifecycle-foundation/flight.md` — check off `lifecycle-pool-core`
- `missions/10-bi-directional-comms-connectors/flights/01-connector-plugin-contract-and-lifecycle-foundation/flight-log.md` — append `### Leg 05` entry under `## Leg Progress`
- `missions/10-bi-directional-comms-connectors/flights/01-connector-plugin-contract-and-lifecycle-foundation/legs/05-lifecycle-pool-core.md` (this file) — status to `landed`

**NOT** affected:
- `the_one/connectors/__init__.py` — pool is private (`_pool.py`); no re-export needed. Leg 8 may add `acquire` to the public API at __init__.py time.
- `the_one/connectors/registry.py` — only consumed via `resolve` (already exported).
- `the_one/mcp/_pool.py` — left untouched (deferred-debt commitment from flight Design Decisions).

---

## Post-Completion Checklist

- [ ] All acceptance criteria verified
- [ ] All listed tests passing
- [ ] `make lint` clean
- [ ] Flight log + flight artifact updated
- [ ] Leg status `landed`
- [ ] `[HANDOFF:review-needed]`; do NOT commit

---

## Citation Audit

11 citations verified against current code at leg design time:

| Citation | Verification |
|---|---|
| `the_one/mcp/_pool.py:1-37` module docstring + invariants | OK — read in full |
| `the_one/mcp/_pool.py:66-98` `_RegistryEntry` dataclass | OK — verified |
| `the_one/mcp/_pool.py:100-105` module-level state declarations | OK — verified |
| `the_one/mcp/_pool.py:131-145` `_load_source` shape | OK — verified |
| `the_one/mcp/_pool.py:148-248` `_entry_worker` | OK — read in full (note: MCP version is denser due to OAuth handling at L171-220; connector version skips that) |
| `the_one/mcp/_pool.py:250-273` `_evict` | OK — verified |
| `the_one/mcp/_pool.py:276-296` `_evict_all_for_source` | OK — verified; connector version mirrors structurally |
| `the_one/mcp/_pool.py:431-517` `acquire` | OK — read in full; cycle-2 race-fix invariant adopted verbatim |
| `the_one/mcp/_pool.py:520-561` `_clear_for_test` | OK — verified; connector version is simpler (no reaper to cancel yet) |
| `tests/test_mcp_pool.py:1-110` test fixture patterns | OK — verified |
| `the_one/connectors/registry.py:resolve` + `register_for_test` | OK — leg-4 deliverables |
