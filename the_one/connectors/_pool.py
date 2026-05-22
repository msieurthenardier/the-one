"""Connector account pool — composite-keyed worker-task-per-entry registry.

Mirrors :mod:`the_one.mcp._pool` at the structural level: module-level
dict keyed on a composite ``(slot, account_id)`` tuple; ``asyncio.Lock``
for serialized mutations; per-entry worker task that holds the platform
connection on a SINGLE task — connect AND disconnect run on the same
task, satisfying anyio's cross-task ``CancelScope.__aexit__`` guard.

Two semantic primitives sit atop one composite-key dict:

  - :func:`agent_acquire` (MCP-style per-agent keying) — used by the F6
    resolver pattern where ``plugin.resolve(account, agent_name)``
    legitimately yields different credentials per agent. The slot
    portion of the key is the agent name.
  - :func:`account_acquire` (gateway-protocol account-keyed) — used by
    every connector-subsystem caller (lifespan listener-warmup,
    ``dispatch_inbound``, F4 platform-send tool, F8 auto-relay). The
    slot portion is the constant :data:`_ACCOUNT_POOL_AGENT_SLOT` so
    every connector caller resolves to ONE pool entry — and ONE
    gateway WebSocket — per account, regardless of how many agents
    are attached. Gateway-style protocols (Discord Gateway, Slack
    Socket Mode) are one-IDENTIFY-per-token by physical necessity;
    per-agent keying would multiplex N agents onto N gateway
    WebSockets carrying the same token and fail.

Both primitives walk the same composite-key dict; eviction, the reaper
loop, the encryption-rotation invariant, and the cycle-2 race-fix
invariant operate uniformly across both slot kinds.

Public API (re-exported from :mod:`the_one.connectors` at leg 8):
  - :func:`agent_acquire`
  - :func:`account_acquire`
  - :func:`shutdown_drain`

Internal symbols (underscore-prefixed; tests reach in for ``_clear_for_test``
and friends):
  - :class:`_RegistryEntry`, ``_pool``, ``_lock``, ``_shutting_down``
  - :data:`_ACCOUNT_POOL_AGENT_SLOT`
  - :func:`_load_account`, :func:`_entry_worker`, :func:`_evict`,
    :func:`_evict_all_for_account`, :func:`_clear_for_test`,
    :func:`_keys_for_test`

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
import os
import time
from dataclasses import dataclass, field

from the_one.config import settings
from the_one.connectors.base import ConnectorClient, ConnectorPlugin
from the_one.connectors.registry import resolve as _resolve_plugin
from the_one.db.models import ConnectorAccount
from the_one.encryption import Encryptor, get_encryptor

logger = logging.getLogger(__name__)


_DEFAULT_TTL_SECONDS = 1800
"""Default idle TTL for a connector pool entry, in seconds (30 min).

Longer than MCP's 300s default because persistent gateway connections
(Discord Gateway, Slack Socket Mode) have meaningful reconnect cost and
operators reasonably expect minutes-long gaps in conversation. Per the
flight Design Decisions, configurable via
``THE_ONE_CONNECTOR_POOL_IDLE_TTL_SECONDS`` env var (read at call time
via :func:`_resolve_ttl_seconds`).
"""

_REAPER_INTERVAL_SECONDS = 30.0
"""Reaper sweep interval, in seconds. Entries idle past their TTL are
evicted on the next sweep. Tests can monkeypatch for fast sweeps."""


@dataclass
class _RegistryEntry:
    """A pool entry. Holds connection state shared between the entry
    worker and any concurrent :func:`agent_acquire` callers waiting on
    ``client_ready``.

    Mirrors :class:`the_one.mcp._pool._RegistryEntry`. ``ttl_seconds`` is
    resolved at :func:`agent_acquire` time via :func:`_resolve_ttl_seconds`;
    the reaper consumes this value to decide when the entry is idle past
    its budget.
    """

    ttl_seconds: int
    # Diverges from MCP: connectors track activity on the entry, not on
    # the client. MCP reads ``client.last_activity`` (an MCPClient
    # property); :class:`ConnectorClient` Protocol has no such field, and
    # widening the Protocol to add one would force every plugin to
    # maintain platform-time tracking when the pool's reaper is the only
    # consumer. See leg 6's "Activity tracking" design rationale. Flight
    # 3 must ratify the per-acquire-touch contract or amend it (mission
    # Known Issue).
    last_activity: float = field(default_factory=time.monotonic)
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
_reaper_task: asyncio.Task[None] | None = None


# Slot literal occupying the per-agent portion of the composite key
# when an entry is account-shared (i.e. created via
# :func:`account_acquire`). The two acquire primitives walk the same
# ``_pool`` dict; the slot value distinguishes per-agent entries
# (``slot == agent_name``) from account-shared entries
# (``slot == _ACCOUNT_POOL_AGENT_SLOT``).
#
# The literal value ``"__connector__"`` is preserved verbatim from the
# F8 L11 sentinel so the composite-key tuples in any pre-deploy warm
# pool match the post-deploy key shape — no eviction churn at swap
# time. (M11 F2 L2 split the public API into the two primitives; the
# F8 L11 retrofit was a tactical patch.) Treat as a module-private
# implementation detail: not exported, not part of the public API.
_ACCOUNT_POOL_AGENT_SLOT = "__connector__"


def _resolve_ttl_seconds(override: int | None = None) -> int:
    """Resolve the warm-entry idle TTL with per-account override support.

    Resolution order: explicit ``override`` (if not None) → env var
    ``THE_ONE_CONNECTOR_POOL_IDLE_TTL_SECONDS`` (if set + parseable) →
    ``_DEFAULT_TTL_SECONDS`` (1800). Env var is read at call time so test
    monkeypatching works; mirrors :func:`the_one.mcp._pool._resolve_ttl_seconds`.

    The override is the per-account ``ConnectorAccount.idle_timeout_seconds``
    value, passed through by :func:`agent_acquire`. The pool stays ignorant of
    which model field drives the override; the model owns the field name,
    the resolver owns the precedence. The ``override is not None`` guard
    short-circuits BEFORE the env-var read by design — the operator's
    explicit per-account choice always wins, regardless of what the env
    var says.

    Non-int env-var values fall back to the default with a warning — matches
    the MCP pool's "fail open, don't crash startup" stance.
    """
    if override is not None:
        return override
    raw = os.environ.get("THE_ONE_CONNECTOR_POOL_IDLE_TTL_SECONDS")
    if raw is None:
        return _DEFAULT_TTL_SECONDS
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "THE_ONE_CONNECTOR_POOL_IDLE_TTL_SECONDS=%r is not an int; falling back to %d",
            raw,
            _DEFAULT_TTL_SECONDS,
        )
        return _DEFAULT_TTL_SECONDS


async def _load_account(account_id: str, encryptor: Encryptor) -> ConnectorAccount:
    """Load a :class:`ConnectorAccount` by id from the leg-2 repository.

    Called OUTSIDE ``_lock`` so different-key acquires don't serialize on
    the DB read. Raises ``KeyError`` on miss (propagates the repository's
    exception unchanged).

    Takes ``encryptor`` explicitly rather than calling ``get_encryptor`` —
    avoids double-call drift if test fixtures swap ``settings.data_dir`` or
    wipe ``_encryptor_cache``. The single resolution point is :func:`agent_acquire`.

    ``get_connection`` and ``ConnectorAccountRepository`` are imported
    function-locally to break a module-import cycle: ``repositories.py``
    transitively imports ``the_one.mcp.__init__`` (via
    ``agent/__init__.py`` → ``agent.core`` → ``mcp.errors`` → ``mcp/__init__.py``),
    which loads ``mcp/_pool.py``, which re-imports ``repositories.py`` —
    failing mid-load when ``_pool`` is the FIRST module to touch
    ``repositories``. ``mcp/_pool.py`` only works because its callers
    always import ``the_one.mcp`` first, priming the cycle. Function-local
    import here makes ``connectors/_pool.py`` resilient regardless of
    import order.
    """
    from the_one.db.connection import get_connection
    from the_one.db.repositories import ConnectorAccountRepository

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
    (flight 2) so the next ``agent_acquire(agent_name, account_id)`` or
    ``account_acquire(account_id)`` for the same account spawns a fresh
    worker with the new credentials.
    Without this, the warm cache would hand out a stale-credential
    ``ConnectorClient`` indefinitely.

    Walks all ``(agent_name, aid)`` keys; calls :func:`_evict` for each
    match. Sequential — each evict has its own 10s timeout but in
    practice an account has 1-3 active agents max.

    Snapshot under lock; release; iterate. Each :func:`_evict` re-acquires
    the lock for its own pop — holding ``_lock`` across the loop would
    deadlock.

    Idempotent on no-match.
    """
    async with _lock:
        keys = [key for key in _pool if key[1] == account_id]
    for key in keys:
        await _evict(key)


async def _ensure_reaper_running_locked() -> None:
    """Spawn the reaper Task if not already running.

    MUST be called under ``_lock`` — avoids a double-spawn race when two
    concurrent :func:`agent_acquire` calls for different keys both try to start
    the reaper in parallel. Mirrors
    :func:`the_one.mcp._pool._ensure_reaper_running_locked`.
    """
    global _reaper_task
    if _reaper_task is None or _reaper_task.done():
        _reaper_task = asyncio.create_task(_reap_loop())


async def _reap_once() -> list[tuple[str, str]]:
    """Run a single reap pass: evict every entry whose
    ``last_activity`` is older than its ``ttl_seconds``.

    Returns the list of evicted keys (test purchase). Per-entry
    eviction goes through :func:`_evict`, which has its own 10s timeout.

    Eviction parallelism: per-key ``_evict`` calls run CONCURRENTLY via
    ``asyncio.gather(..., return_exceptions=True)``. Bounds the worst-
    case reap-pass duration at ~10s regardless of pool size. Mirrors
    MCP — see :func:`the_one.mcp._pool._reap_once` for the rationale.

    Guards ``entry.client is not None`` — entries mid-connect have not
    yet had their ``client`` populated and are NOT reaped this pass.
    The worker that eventually populates ``entry.client`` also updates
    ``entry.last_activity``-style state through :func:`agent_acquire`'s
    return-path touch, so a freshly-connected entry is not immediately
    eligible for the next sweep either.
    """
    now = time.monotonic()
    async with _lock:
        expired = [
            key
            for key, entry in _pool.items()
            if entry.client is not None
            and (now - entry.last_activity) > entry.ttl_seconds
        ]
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
                    "Connector pool _evict raised during reap pass: key=%r exc=%r",
                    key,
                    result,
                )
    return expired


async def _reap_loop() -> None:
    """Background loop: sleep, reap, repeat.

    On ``CancelledError``: drain the entire registry concurrently via
    :func:`_evict` then re-raise. One bad :func:`_reap_once` does not
    kill the loop (try/except Exception around the call).
    """
    try:
        while True:
            await asyncio.sleep(_REAPER_INTERVAL_SECONDS)
            try:
                await _reap_once()
            except Exception:
                logger.exception("Connector pool reap pass raised; continuing")
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

    Wired into the FastAPI ``lifespan`` shutdown branch between the MCP
    pool drain and the OAuth periodic-sweep stop. After this runs,
    :func:`agent_acquire` raises ``RuntimeError`` for any late-arriving caller.

    Order:
      1. Set ``_shutting_down = True`` FIRST so any concurrent
         ``agent_acquire``/``account_acquire`` sees the flag at the next
         lock acquisition.
      2. Cancel ``_reaper_task``; suppress ``CancelledError`` on its await
         (the reaper's own ``CancelledError`` handler runs the drain).
      3. Belt-and-suspenders: snapshot any remaining keys (rare — the
         reaper's drain already ran). Concurrent ``_evict`` via gather
         with ``return_exceptions``.
      4. Reset ``_reaper_task = None`` so the next test's
         :func:`_clear_for_test` sees a clean slate.

    Total drain time is bounded at ~10s regardless of pool size because
    each ``_evict`` has a 10s per-entry timeout AND the gather'd evicts
    run in parallel.
    """
    global _reaper_task, _shutting_down
    _shutting_down = True

    task = _reaper_task
    if task is not None and not task.done():
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async with _lock:
        keys = list(_pool.keys())
    if keys:
        await asyncio.gather(
            *(_evict(key) for key in keys),
            return_exceptions=True,
        )

    _reaper_task = None


async def agent_acquire(agent_name: str, account_id: str) -> ConnectorClient:
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

    key = (agent_name, account_id)
    async with _lock:
        if _shutting_down:
            raise RuntimeError("Connector pool is shutting down")
        entry = _pool.get(key)
        if entry is None:
            entry = _RegistryEntry(
                ttl_seconds=_resolve_ttl_seconds(override=account.idle_timeout_seconds),
                evict_event=asyncio.Event(),
                client_ready=asyncio.Event(),
            )
            entry.worker = asyncio.create_task(
                _entry_worker(plugin, account, encryptor, entry)
            )
            _pool[key] = entry
            # leg 6: ensure the reaper is running. Idempotent — the helper
            # checks ``_reaper_task is None or done()`` before spawning.
            # Called UNDER ``_lock`` to avoid a double-spawn race when two
            # concurrent ``acquire``s for different keys insert at the
            # same time.
            await _ensure_reaper_running_locked()
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
    # leg 6: touch activity on every successful resolve (warm and cold paths
    # converge here). The pool is the sole owner of the lifecycle clock.
    entry.last_activity = time.monotonic()
    return client


async def account_acquire(account_id: str) -> ConnectorClient:
    """Acquire a connector-account-shared pool entry.

    Routes every caller through ONE pool entry per account by pinning
    the slot portion of the composite key to
    :data:`_ACCOUNT_POOL_AGENT_SLOT`. All connector-subsystem callers
    (lifespan listener-warmup, ``dispatch_inbound``, F4 platform-send
    tool, F8 auto-relay) MUST use this primitive instead of
    :func:`agent_acquire`.

    This expresses the gateway-protocol constraint structurally:
    Discord Gateway, Slack Socket Mode, and similar gateway-style
    protocols are one-IDENTIFY-per-token by physical necessity, so
    per-agent keying is incompatible with the protocol shape.
    :func:`agent_acquire` remains for MCP-style per-agent pools where
    the F6 resolver pattern legitimately produces different
    credentials per agent.
    """
    return await agent_acquire(_ACCOUNT_POOL_AGENT_SLOT, account_id)


async def _clear_for_test() -> None:
    """Test seam: cancel reaper + all worker tasks; empty the pool; reset state.

    Applies M07's lesson from day one: ``_shutting_down`` is explicitly
    reset to ``False`` so the next test does not inherit a leaked True
    value. Mirrors :func:`the_one.mcp._pool._clear_for_test`.

    Order: cancel the reaper FIRST so its ``CancelledError`` handler
    (which tries to ``_evict`` every entry) does not race the
    worker-cancel loop below. Then snapshot+clear ``_pool``, then cancel
    workers. Resets ``_reaper_task = None`` and ``_shutting_down = False``
    at the end.

    Tests should call this in an autouse fixture AFTER each test.
    """
    global _reaper_task, _shutting_down

    # Cancel the reaper FIRST so it does not race the worker-cancel
    # loop below. The reaper's own CancelledError handler tries to
    # _evict every entry — let it complete or be cancelled before we
    # cancel the workers ourselves.
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


def _keys_for_test() -> list[tuple[str, str]]:
    """Test seam: snapshot the current pool keys.

    Pure read — no lock acquisition required for the snapshot semantics
    tests need. Used by HAT inspection (L6) and by the L2 pinning tests
    that verify :func:`account_acquire` produces an entry at
    ``(_ACCOUNT_POOL_AGENT_SLOT, account_id)``.
    """
    return list(_pool.keys())
