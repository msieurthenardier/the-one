"""MCP source pool — per-(agent, source) keyed worker-task-per-entry registry.

Mirrors ``the_one/tools/_session_registry.py`` (PTY pool) at the structural
level: module-level dict keyed on ``(agent_name, source_id)``;
``asyncio.Lock`` for serialized mutations; per-entry worker task that holds
the SDK's anyio-task-group-rooted CMs on a SINGLE task — connect AND
disconnect run on the same task, satisfying anyio's cross-task
``CancelScope.__aexit__`` guard (verified at L1a stake-test probe).

F4 lands the pool in three legs:
  - L3 (this module): ``_RegistryEntry``, ``_pool``, ``_lock``,
    ``_resolve_ttl_seconds``, ``_load_source``, ``_entry_worker``,
    ``_evict``, ``acquire``, ``_clear_for_test``.
  - L4: ``_reap_once``, ``_reap_loop``, ``_ensure_reaper_running_locked``,
    ``shutdown_drain``, FastAPI lifespan integration.
  - L5: ``the_one/mcp/README.md`` documents the runtime invariants.

Public API (re-exported from ``the_one.mcp``):
  - ``acquire(agent_name, source_id) -> MCPClient`` (this module)
  - ``shutdown_drain() -> None`` (L4)

Internal symbols (underscore-prefixed; tests reach in for
``_clear_for_test`` and friends):
  - ``_RegistryEntry``, ``_pool``, ``_lock``, ``_shutting_down``
  - ``_DEFAULT_TTL_SECONDS``, ``_REAPER_INTERVAL_SECONDS``
  - ``_resolve_ttl_seconds``, ``_load_source``, ``_entry_worker``,
    ``_evict``, ``_clear_for_test``

Race-handling invariant (cycle-2 fix, flight §2):
  The lock-held branch checks ``entry is None`` (NOT ``entry.client is
  None``). Concurrent same-key acquires share the worker by waiting on
  ``entry.client_ready``. The worker is the SOLE writer of
  ``entry.client`` and ``entry.failure``; both are written BEFORE
  ``entry.client_ready.set()``. asyncio's single-threaded event loop
  guarantees post-event reads observe those writes — no memory
  barriers needed (no other thread).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
from dataclasses import dataclass

from the_one.config import settings
from the_one.db.connection import get_connection
from the_one.db.models import MCPSource
from the_one.db.repositories import MCPSourceRepository
from the_one.encryption import get_encryptor
from the_one.mcp.client import MCPClient

logger = logging.getLogger(__name__)

_DEFAULT_TTL_SECONDS = 300
"""Default idle TTL for a pool entry, in seconds. Resolved at register-time
from ``MCP_POOL_IDLE_TTL_SECONDS`` (see ``_resolve_ttl_seconds``)."""

_REAPER_INTERVAL_SECONDS = 30.0
"""Reaper sweep interval. Defined here for forward-reference; UNUSED until
L4 wires the reaper. Tests can monkeypatch this for fast sweeps."""


@dataclass
class _RegistryEntry:
    """A pool entry. Holds connection state shared between the entry
    worker and any concurrent ``acquire`` callers waiting on
    ``client_ready``.

    The worker task holds the SDK's anyio-task-group-rooted CMs for the
    entry's lifetime. The reaper (L4) signals eviction via
    ``evict_event``; the worker's ``finally:`` runs disconnect on the
    SAME task that ran connect, avoiding anyio's cross-task ``__aexit__``
    guard.

    Worker is the SOLE writer of ``client`` and ``failure``. Both are
    written BEFORE ``client_ready.set()``, so post-event reads are
    race-free. ``acquire`` callers wait on ``client_ready`` and read
    the fields outside the lock.

    ``worker`` is typed ``asyncio.Task[None] | None`` — None during the
    brief construction window before ``acquire`` assigns the spawned
    Task. ``acquire`` and ``_evict`` ``assert entry.worker is not None``
    before awaiting it; the assignment in ``acquire`` happens
    immediately after dataclass construction (atomic from the
    perspective of any other caller, since ``_lock`` is held), so the
    assertion is sound.
    """

    ttl_seconds: int
    worker: asyncio.Task[None] | None = None
    evict_event: asyncio.Event | None = None
    client_ready: asyncio.Event | None = None
    client: MCPClient | None = None
    failure: BaseException | None = None


# Module-level state. All mutations to ``_pool`` (other than the lazy lock
# construction itself) go through ``_lock``.
_pool: dict[tuple[str, str], _RegistryEntry] = {}
_lock: asyncio.Lock = asyncio.Lock()
_shutting_down: bool = False
_reaper_task: asyncio.Task[None] | None = None


def _resolve_ttl_seconds() -> int:
    """Read ``MCP_POOL_IDLE_TTL_SECONDS`` env at call time; default 300.

    Read at call time so test ``monkeypatch.setenv`` works. Mirrors the
    PTY pool's per-entry TTL resolution (also read at register time).

    Non-int values fall back to the default with a warning — matches the
    PTY pool's "fail open, don't crash startup" stance.
    """
    raw = os.environ.get("MCP_POOL_IDLE_TTL_SECONDS")
    if raw is None:
        return _DEFAULT_TTL_SECONDS
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "MCP_POOL_IDLE_TTL_SECONDS=%r is not an int; falling back to %d",
            raw,
            _DEFAULT_TTL_SECONDS,
        )
        return _DEFAULT_TTL_SECONDS


async def _load_source(source_id: str) -> MCPSource:
    """Load an ``MCPSource`` by id from the F1 repository.

    Called OUTSIDE ``_lock`` so different-key acquires don't serialize
    on the F1 DB read. Per flight §3 / cycle-2 medium #2.

    Raises whatever the repo raises (typically ``KeyError`` on miss);
    the calling ``acquire`` propagates the exception to the caller.
    Mirrors the factory shape of
    ``the_one/interfaces/web/api.py::_mcp_repo``.
    """
    conn = await get_connection()
    encryptor = get_encryptor(settings.data_dir)
    repo = MCPSourceRepository(conn, encryptor)
    return await repo.get(source_id)


async def _entry_worker(source: MCPSource, entry: _RegistryEntry) -> None:
    """Hold the connection on a single task. Run teardown on same task.

    On connect-failure, populate ``entry.failure`` BEFORE setting
    ``client_ready``. On connect-success, populate ``entry.client``
    BEFORE setting ``client_ready``. Then idle until ``evict_event``
    fires; the ``finally:`` clause runs disconnect — anyio cross-task
    guard satisfied because connect and disconnect both run on this
    task.

    Memory ordering: ``failure`` / ``client`` written BEFORE
    ``client_ready.set()``; asyncio's single-threaded event loop
    guarantees post-event reads on ``acquire``'s side observe the
    writes. No memory barriers needed — there's no other thread.

    ``BaseException`` is caught (not just ``Exception``) so a
    ``CancelledError`` raised inside connect surfaces to acquire callers
    as ``entry.failure``. The reaper (L4) signals eviction by setting
    ``evict_event``, NOT by cancelling the worker, so this branch is
    unusual but defensible.
    """
    assert entry.client_ready is not None  # invariant: set at construction
    assert entry.evict_event is not None
    client = MCPClient(source)
    try:
        await client.connect()
    except BaseException as exc:
        entry.failure = exc
        entry.client_ready.set()
        return
    entry.client = client
    entry.client_ready.set()
    try:
        await entry.evict_event.wait()
    finally:
        # Disconnect on the SAME task that ran connect — anyio guard is
        # satisfied. ``MCPClient.disconnect`` is idempotent and never
        # raises (post-L1a contract); the cross-task safety-net swallow
        # is documented but not exercised here under the worker-task
        # pattern.
        try:
            await client.disconnect()
        except Exception:
            logger.exception(
                "MCPClient disconnect failed during entry teardown"
            )


async def _evict(key: tuple[str, str]) -> None:
    """Pop the entry, signal the worker to teardown, await the worker.

    ``await entry.worker`` is REQUIRED for ``shutdown_drain`` (L4) to
    honour its 'all entries drained before return' contract. 10s timeout
    + cancel-on-stuck per flight §2.

    Idempotent on missing key — a no-op if nothing was inserted under
    ``key``. ``test_evict_idempotent_on_missing_key`` locks this guard.
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
            "MCP pool worker for %r did not terminate within 10s", key
        )
        entry.worker.cancel()
        with contextlib.suppress(BaseException):
            await entry.worker


async def _ensure_reaper_running_locked() -> None:
    """Spawn the reaper Task if not already running.

    MUST be called under ``_lock`` — avoids a double-spawn race when two
    concurrent ``acquire``s for different keys both try to start the
    reaper in parallel. Mirrors
    ``the_one/tools/_session_registry.py::_ensure_reaper_running_locked``.
    """
    global _reaper_task
    if _reaper_task is None or _reaper_task.done():
        _reaper_task = asyncio.create_task(_reap_loop())


async def _reap_once() -> list[tuple[str, str]]:
    """Run a single reap pass: evict every entry whose
    ``client.last_activity`` is older than its ``ttl_seconds``.

    Returns the list of evicted keys for test purchase. Per-entry
    eviction goes through ``_evict``, which has its own 10s timeout.

    Eviction parallelism (cycle-1 reviewer Q1): per-key ``_evict`` calls
    run CONCURRENTLY via ``asyncio.gather(..., return_exceptions=True)``.
    Rationale: if N entries are stuck (each blocking ``_evict`` for the
    full 10s timeout), sequential awaits would block the reap pass for
    10s × N (during which the loop cannot honor cancellation). Parallel
    gather bounds the worst-case reap-pass duration at ~10s regardless
    of pool size, matching ``shutdown_drain``'s parallelism. The PTY
    pool template uses sequential close because subprocess
    SIGTERM-to-SIGKILL ladders are CPU-cheap (~1s each); MCP
    ``_evict``'s 10s wait is much larger, justifying the divergence.

    Guards ``entry.client is not None`` — entries mid-connect have not
    yet had their ``client`` populated and are NOT reaped this pass.
    """
    now = time.monotonic()
    async with _lock:
        expired = [
            key
            for key, entry in _pool.items()
            if entry.client is not None
            and (now - entry.client.last_activity) > entry.ttl_seconds
        ]
    # _evict each expired key OUTSIDE the lock, IN PARALLEL. _evict
    # re-acquires the lock for its own pop — fair-FIFO ordering means
    # parallel evicts serialize on the lock briefly but the actual
    # worker awaits run concurrently.
    if expired:
        results = await asyncio.gather(
            *(_evict(key) for key in expired),
            return_exceptions=True,
        )
        for key, result in zip(expired, results):
            if isinstance(result, BaseException) and not isinstance(
                result, asyncio.CancelledError
            ):
                logger.exception(
                    "MCP pool _evict raised during reap pass: key=%r exc=%r",
                    key,
                    result,
                )
    return expired


async def _reap_loop() -> None:
    """Background loop: sleep, reap, repeat.

    On ``CancelledError``: drain the entire registry concurrently via
    ``_evict`` then re-raise. One bad ``_reap_once`` does not kill the
    loop (try/except Exception around the call).
    """
    try:
        while True:
            await asyncio.sleep(_REAPER_INTERVAL_SECONDS)
            try:
                await _reap_once()
            except Exception:
                logger.exception("MCP pool reap pass raised; continuing")
    except asyncio.CancelledError:
        # Drain the registry on cancellation. Concurrent _evict for
        # parallelism; gather with return_exceptions so one bad evict
        # does not block the others.
        async with _lock:
            keys = list(_pool.keys())
        if keys:
            await asyncio.gather(
                *(_evict(key) for key in keys),
                return_exceptions=True,
            )
        raise


async def shutdown_drain() -> None:
    """Cancel the reaper task; evict every remaining entry.

    Wired into the FastAPI ``lifespan`` shutdown branch (between PTY
    pool drain and DB close per flight §12). After this runs,
    ``acquire`` raises ``RuntimeError`` for any late-arriving caller.

    Order:
      1. Set ``_shutting_down = True`` FIRST so any concurrent
         ``acquire`` sees the flag at the next lock acquisition.
      2. Cancel ``_reaper_task``; suppress ``CancelledError`` on its
         await (the reaper's own ``CancelledError`` handler runs the
         drain).
      3. Belt-and-suspenders: snapshot any remaining keys (rare — the
         reaper's drain already ran). Concurrent ``_evict`` via
         ``gather`` with ``return_exceptions``.
      4. Reset ``_reaper_task = None`` so the next test's
         ``_clear_for_test`` sees a clean slate.

    Total drain time is bounded at ~10s regardless of pool size because
    each ``_evict`` has a 10s per-entry timeout AND the gather'd
    evicts run in parallel.
    """
    global _reaper_task, _shutting_down
    _shutting_down = True

    task = _reaper_task
    if task is not None and not task.done():
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    # Belt-and-suspenders drain. Snapshot under lock; gather _evict.
    async with _lock:
        keys = list(_pool.keys())
    if keys:
        await asyncio.gather(
            *(_evict(key) for key in keys),
            return_exceptions=True,
        )

    _reaper_task = None


async def acquire(agent_name: str, source_id: str) -> MCPClient:
    """Look up or spawn the warm ``MCPClient`` for ``(agent, source)``.

    Per flight §2: pre-load source OUTSIDE the lock; check
    ``entry is None`` under the lock (atomic existence dispatch); wait
    on ``entry.client_ready`` outside the lock; on failure, raise and
    pop idempotently; on success, ``_touch_activity`` and return.

    Concurrent same-key acquires SHARE one worker — the lock-held branch
    creates the worker on the first caller; subsequent callers find the
    entry already present and fall through to the ``client_ready.wait()``
    outside the lock. Cycle-2 race-fix invariant.

    Caller cancellation mid-``await client_ready.wait()`` leaves the
    worker running. The entry stays in ``_pool`` and reaps on idle TTL
    (L4). Subsequent acquire on the same key reuses the worker.

    Failure-propagation: if ``connect`` raises, the worker stores the
    exception in ``entry.failure`` and sets ``client_ready``. Every
    waiting caller observes the failure, pops the entry idempotently
    (using ``_pool.pop(key, None)``) and re-raises. The next acquire on
    the same key spawns a fresh worker.
    """
    # Pre-load OUTSIDE the lock (cycle-2 medium #2). Different-key
    # acquires must not serialize on the F1 DB read.
    source = await _load_source(source_id)

    async with _lock:
        if _shutting_down:
            raise RuntimeError("MCP pool is shutting down")
        key = (agent_name, source_id)
        entry = _pool.get(key)
        if entry is None:
            # First-acquirer-for-this-key path. Construct the entry,
            # spawn the worker, insert. Entry is not visible to other
            # callers until we release the lock.
            entry = _RegistryEntry(
                ttl_seconds=_resolve_ttl_seconds(),
                evict_event=asyncio.Event(),
                client_ready=asyncio.Event(),
            )
            entry.worker = asyncio.create_task(
                _entry_worker(source, entry)
            )
            _pool[key] = entry
            # Ensure the reaper is running. Idempotent — the helper
            # checks ``_reaper_task is None or done()`` before spawning.
            # Called UNDER ``_lock`` to avoid a double-spawn race when
            # two concurrent ``acquire``s for different keys insert at
            # the same time.
            await _ensure_reaper_running_locked()
        # else: entry exists. Wait on client_ready outside the lock.

    # Lock released. Concurrent same-key acquires now share the entry.
    assert entry.client_ready is not None
    await entry.client_ready.wait()

    if entry.failure is not None:
        # Connect failed. Pop the entry idempotently — only if it's
        # still THIS entry (a later acquire may have already replaced
        # it with a fresh worker; leave that one alone).
        async with _lock:
            existing = _pool.get((agent_name, source_id))
            if existing is entry:
                _pool.pop((agent_name, source_id), None)
        raise entry.failure

    client = entry.client
    # Invariant: client_ready set + no failure → client populated.
    assert client is not None
    client._touch_activity()
    return client


async def _clear_for_test() -> None:
    """Test seam: cancel reaper + all worker tasks; empty the pool.

    Tests must call this in an ``autouse=True`` fixture AFTER each test;
    otherwise the next test inherits stale entries / worker tasks /
    reaper task bound to a torn-down event loop. Resets
    ``_shutting_down = False`` and ``_reaper_task = None``.

    INVARIANT: do NOT call while another task is awaiting ``acquire`` on
    the same key — the awaiting task may receive the soon-to-be-
    disconnected client (post ``client_ready`` set, pre worker
    ``finally:`` block running disconnect). The autouse fixture pattern
    runs cleanup AFTER the test body completes, which guarantees this
    in normal usage.
    """
    global _reaper_task, _shutting_down

    # Cancel the reaper FIRST so it does not race the worker-cancel
    # loop below (the reaper's own CancelledError handler tries to
    # _evict every entry — let it complete or be cancelled before we
    # cancel the workers ourselves).
    task = _reaper_task
    if task is not None and not task.done():
        task.cancel()
        with contextlib.suppress(BaseException):
            await task
    _reaper_task = None

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
