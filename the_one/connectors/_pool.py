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
from the_one.connectors.base import (
    ConnectorClient,
    ConnectorPlugin,
    DiscoverableEntities,
    DiscoverableEntity,
)
from the_one.connectors.registry import resolve as _resolve_plugin
from the_one.db.models import Connector
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

_DISCOVERABLE_REFRESH_INTERVAL_SECONDS: float = 300.0
"""Discoverable-entities refresh sweep interval, in seconds (5 minutes
default). Sibling task to the reaper — see
:func:`_discoverable_refresh_loop`. Configurable via env var
``THE_ONE_CONNECTOR_DISCOVERABLE_REFRESH_INTERVAL_SECONDS`` (read at
call time via :func:`_resolve_discoverable_refresh_interval_seconds`).
Tests can monkeypatch this module-level constant for fast sweeps.

Mirrors :data:`_REAPER_INTERVAL_SECONDS`'s float type so per-test
monkeypatches can use sub-second values. 5 minutes is short enough for
operators to see post-platform-change updates within a reasonable
dropdown-open cadence but long enough not to thrash the SDK caches.
"""


def _resolve_discoverable_refresh_interval_seconds() -> float:
    """Resolve the discoverable refresh interval from env var or default.

    Resolution order: env var
    ``THE_ONE_CONNECTOR_DISCOVERABLE_REFRESH_INTERVAL_SECONDS`` (if set
    + parseable) → the current module-level
    ``_DISCOVERABLE_REFRESH_INTERVAL_SECONDS`` value (default 300.0).
    Env var is read at call time so test monkeypatching works.

    Mirrors :func:`_resolve_ttl_seconds`'s read-at-call-time pattern.
    Non-float env-var values fall back to the default with a warning —
    same "fail open, don't crash startup" stance.
    """
    raw = os.environ.get("THE_ONE_CONNECTOR_DISCOVERABLE_REFRESH_INTERVAL_SECONDS")
    if raw is None:
        return _DISCOVERABLE_REFRESH_INTERVAL_SECONDS
    try:
        return float(raw)
    except ValueError:
        logger.warning(
            "THE_ONE_CONNECTOR_DISCOVERABLE_REFRESH_INTERVAL_SECONDS=%r is not a float; "
            "falling back to %f",
            raw,
            _DISCOVERABLE_REFRESH_INTERVAL_SECONDS,
        )
        return _DISCOVERABLE_REFRESH_INTERVAL_SECONDS


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
    # M11 F3 L4: connector plugin type for the discoverable-entities
    # refresh sweep filter. Populated by :func:`agent_acquire` /
    # :func:`account_acquire` at entry-creation time. Empty-string
    # default keeps direct ``_RegistryEntry(...)`` test scaffolding
    # invisible to the sweep (the sweep filters entries where
    # ``account_type == ""``).
    account_type: str = ""
    # M11 F3 L4: cache of the most recent successful refresh of the
    # plugin's ``enumerate_discoverable_entities`` hook. ``None`` until
    # the first refresh lands.
    discoverable_entities_cache: DiscoverableEntities | None = None
    # M11 F3 L4: entries present in the previous refresh's cache but
    # absent from the latest refresh. Persists for exactly ONE refresh
    # cycle (next refresh re-derives from prior_cache - new_snapshot).
    discoverable_entities_stale_carry: DiscoverableEntities | None = None
    # M11 F3 L4: ``time.monotonic()`` at the moment of the most recent
    # successful refresh. Used by the API layer to compute
    # ``stale_seconds`` in the response. ``None`` until the first
    # refresh lands.
    discoverable_entities_fetched_at_monotonic: float | None = None
    # M11 F17 L1: per-account inbound/outbound disposition counters.
    # Keyed by disposition string (e.g. "stepped", "ok"). Incremented
    # best-effort by :func:`record_disposition` under ``_lock``. Resets
    # on pool eviction (accepted limitation — counters measure "since the
    # current pool entry warmed").
    inbound_counters: dict[str, int] = field(default_factory=dict)
    outbound_counters: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class _CountersSnapshot:
    """Immutable pair of counter dicts for the API handler.

    Captured under ``_lock`` by :func:`_get_account_counters_snapshot`;
    readable outside the lock with no consistency risk because the
    dataclass is frozen and the underlying dicts are copied at snapshot
    time (M11 F17 L1, mirrors :class:`_DiscoverableCacheSnapshot`).
    """

    inbound: dict[str, int]
    outbound: dict[str, int]


@dataclass(frozen=True, slots=True)
class _StatusSnapshot:
    """Immutable connection-state snapshot for the status endpoint.

    Captured under ``_lock`` by :func:`_get_account_status_snapshot`
    (M11 F17 L5). The ``state`` field is one of
    ``connected | connecting | disconnected | error``.  ``alive`` is
    the live ``is_alive()`` return value at snapshot time.
    ``last_error`` / ``last_error_link`` carry the mapped connect-error
    message and action URL when ``state == "error"``; both are ``None``
    for non-error states.

    ``application_id`` is the bot's public OAuth2 client id, read from
    the warm client's ``application_id`` property (populated post-READY
    by the discord.py SDK). ``None`` for cold/connecting/error states and
    for plugin clients that don't expose the attribute. Not a secret —
    the invite URL is constructed from this public id. M11 F17 L5 fix.
    """

    state: str  # "connected" | "connecting" | "disconnected" | "error"
    alive: bool
    last_error: str | None
    last_error_link: str | None
    application_id: int | None = None


@dataclass(frozen=True, slots=True)
class _DiscoverableCacheSnapshot:
    """Immutable triple of cache state + account_type for the API handler.

    Captured under ``_lock`` by :func:`_get_account_cache_snapshot`;
    readable outside the lock with no consistency risk because the
    dataclass is frozen and the underlying :class:`DiscoverableEntities`
    instances are themselves frozen dataclasses (M11 F3 L3).

    The handler uses :attr:`account_type` to resolve the plugin (for
    the hook-presence check that gates 503 vs 200) without a second lock
    acquisition.
    """

    cache: DiscoverableEntities | None
    stale_carry: DiscoverableEntities | None
    fetched_at_monotonic: float | None
    account_type: str


# Module-level state. All mutations to ``_pool`` (other than the lazy lock
# construction itself) go through ``_lock``.
_pool: dict[tuple[str, str], _RegistryEntry] = {}
_lock: asyncio.Lock = asyncio.Lock()
_shutting_down: bool = False
_reaper_task: asyncio.Task[None] | None = None
# M11 F3 L4: discoverable-entities refresh sweep task. Spawned lazily on
# the first cold-entry creation in :func:`agent_acquire`; cancelled by
# :func:`shutdown_drain`. Mirrors ``_reaper_task`` lifecycle.
_discoverable_refresh_task: asyncio.Task[None] | None = None


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

    The override is the per-account ``Connector.idle_timeout_seconds``
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


async def _load_account(account_id: str, encryptor: Encryptor) -> Connector:
    """Load a :class:`Connector` by id from the leg-2 repository.

    Called OUTSIDE ``_lock`` so different-key acquires don't serialize on
    the DB read. Raises ``KeyError`` on miss (propagates the repository's
    exception unchanged).

    Takes ``encryptor`` explicitly rather than calling ``get_encryptor`` —
    avoids double-call drift if test fixtures swap ``settings.data_dir`` or
    wipe ``_encryptor_cache``. The single resolution point is :func:`agent_acquire`.

    ``get_connection`` and ``ConnectorRepository`` are imported
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
    from the_one.db.repositories import ConnectorRepository

    conn = await get_connection()
    repo = ConnectorRepository(conn, encryptor)
    return await repo.get(account_id)


async def _entry_worker(
    plugin: ConnectorPlugin,
    account: Connector,
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


async def release_agent_on_account(agent_name: str, account_id: str) -> None:
    """Release the per-(agent, account) pool entry, if any.

    M11 F9 L5 — operator-driven detach. Idempotent on missing key
    (inherits :func:`_evict`'s contract). Releases ONLY the specified
    slot; if the account is also warm under :func:`account_acquire`
    (system-outbound, keyed by :data:`_ACCOUNT_POOL_AGENT_SLOT`), that
    entry stays — other agents may still depend on the account being
    live.

    Public counterpart to :func:`_evict_all_for_account` (which evicts
    every slot for the account, e.g. on credentials rotation). The
    per-slot scope here is appropriate for operator-driven detach where
    only one agent is being disconnected.
    """
    await _evict((agent_name, account_id))


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


async def _reap_once() -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Run a single reap pass with two sub-sweeps.

    **Idle-eviction sweep** — evicts every per-agent entry
    (``key[0] != _ACCOUNT_POOL_AGENT_SLOT``) whose ``last_activity`` is
    older than its ``ttl_seconds``.  Account-keyed entries
    (``key[0] == _ACCOUNT_POOL_AGENT_SLOT``) whose gateway ``is_alive()``
    returns ``True`` are **exempt** — the Discord gateway WebSocket must
    stay connected through an arbitrarily long traffic lull.

    **Dead-listener sweep** — account-keyed entries whose client is
    present but ``is_alive()`` returns ``False`` (gateway has died) are
    evicted so the worker teardown runs.  The caller
    (:func:`_reap_loop`) re-warms them via
    :func:`_rewarm_dead_listeners` so the bot self-heals within one
    reaper interval.

    Returns a 2-tuple ``(idle_evicted, dead_evicted)``:

    - ``idle_evicted`` — keys evicted by the idle-TTL sweep (test
      purchase; callers that only care about the idle pass use index 0).
    - ``dead_evicted`` — account-keyed keys evicted by the liveness
      sweep; the loop re-acquires these.

    Per-entry eviction goes through :func:`_evict`, which has its own
    10s timeout.  Eviction parallelism: per-key ``_evict`` calls run
    CONCURRENTLY via ``asyncio.gather(..., return_exceptions=True)``.
    Bounds the worst-case reap-pass duration at ~10s regardless of pool
    size.  Mirrors MCP — see :func:`the_one.mcp._pool._reap_once` for
    the rationale.

    Guards ``entry.client is not None`` — entries mid-connect have not
    yet had their ``client`` populated and are NOT reaped this pass.
    The worker that eventually populates ``entry.client`` also updates
    ``entry.last_activity``-style state through :func:`agent_acquire`'s
    return-path touch, so a freshly-connected entry is not immediately
    eligible for the next sweep either.
    """
    now = time.monotonic()
    async with _lock:
        idle_evicted: list[tuple[str, str]] = []
        dead_evicted: list[tuple[str, str]] = []
        for key, entry in _pool.items():
            if entry.client is None:
                # Mid-connect — skip both sweeps.
                continue
            if key[0] == _ACCOUNT_POOL_AGENT_SLOT:
                # Account-keyed gateway-listener entry.
                is_alive_fn = getattr(entry.client, "is_alive", None)
                if is_alive_fn is None:
                    # Plugin has no is_alive() method — exempt from both idle
                    # and liveness sweeps.  Churning a Protocol-non-compliant
                    # entry every ~30s would be disruptive; treat it the same
                    # as a live gateway entry and leave it in the pool.
                    continue
                if is_alive_fn():
                    # Gateway is alive — exempt from idle eviction regardless
                    # of last_activity age.  (M11 F17 L4 exemption)
                    continue
                # Gateway is dead (is_alive returns False): collect for the
                # liveness sweep so the bot can self-heal.
                dead_evicted.append(key)
            else:
                # Per-agent entry — standard idle-TTL eviction.
                if (now - entry.last_activity) > entry.ttl_seconds:
                    idle_evicted.append(key)

    all_to_evict = idle_evicted + dead_evicted
    if all_to_evict:
        results = await asyncio.gather(
            *(_evict(key) for key in all_to_evict),
            return_exceptions=True,
        )
        for key, result in zip(all_to_evict, results):
            if isinstance(result, BaseException) and not isinstance(
                result, asyncio.CancelledError
            ):
                logger.exception(
                    "Connector pool _evict raised during reap pass: key=%r exc=%r",
                    key,
                    result,
                )
    return idle_evicted, dead_evicted


async def _rewarm_dead_listeners(keys: list[tuple[str, str]]) -> None:
    """Re-acquire each dead account-keyed gateway listener — only when the
    connector still has ≥1 attached agent.

    Called by :func:`_reap_loop` after :func:`_reap_once` evicts
    terminally-dead account-keyed entries.  Before rewarming, checks the
    agent store for attached agents (mirrors the lifespan warmup gate in
    ``interfaces/web/app.py``).  If the connector has no attached agents
    (e.g. all agents were detached after boot), the entry is left cold and
    logged at INFO — no gateway is re-established for a connector that
    serves no traffic.  If agents are still attached, ``account_acquire``
    re-establishes the gateway WebSocket so the bot self-heals within one
    reaper interval (~30s) with no operator action.

    Errors are logged but do NOT kill the reaper — a single reconnect
    failure is retried on the next sweep.
    """
    from the_one.db.connection import get_connection
    from the_one.db.repositories import SQLiteAgentStore

    for key in keys:
        account_id = key[1]
        try:
            conn = await get_connection()
            agent_store = SQLiteAgentStore(conn)
            attached = await agent_store.list_by_connector(account_id)
            if not attached:
                logger.info(
                    "Connector pool: dead gateway listener for account_id=%r "
                    "has no attached agents; leaving cold (not rewarming)",
                    account_id,
                )
                continue
            await account_acquire(account_id)
            logger.info(
                "Connector pool: re-warmed dead gateway listener for account_id=%r "
                "(%d attached agent(s))",
                account_id,
                len(attached),
            )
        except Exception:
            logger.exception(
                "Connector pool: failed to re-warm dead gateway listener "
                "for account_id=%r; will retry on next reaper sweep",
                account_id,
            )


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
                _idle_evicted, dead_listeners = await _reap_once()
                if dead_listeners:
                    await _rewarm_dead_listeners(dead_listeners)
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


async def _ensure_discoverable_refresh_running_locked() -> None:
    """Spawn the discoverable-entities refresh sweep task if not already running.

    MUST be called under ``_lock`` — avoids a double-spawn race when two
    concurrent ``agent_acquire`` / ``account_acquire`` calls for
    different keys both try to start the sweep in parallel. Mirrors
    :func:`_ensure_reaper_running_locked`.
    """
    global _discoverable_refresh_task
    if _discoverable_refresh_task is None or _discoverable_refresh_task.done():
        _discoverable_refresh_task = asyncio.create_task(_discoverable_refresh_loop())


async def _refresh_discoverable_entities_for_account(account_id: str) -> bool:
    """Refresh the discoverable-entities cache for one account-pool entry.

    Returns ``True`` if the cache was updated successfully; ``False`` for
    any bail-out (cold entry, mid-connect, evicted-mid-refresh, plugin
    missing the hook, plugin raised, shutdown in flight). Per the
    flight design decisions, this helper is the SINGLE write path for
    the cache fields; both the periodic sweep and the inline GET /
    POST-refresh paths funnel through here so the write-back race is
    serialized at the re-acquired lock.

    Race-safety contract (M11 F3 L4 cycle-1 review):
      - First lock acquisition: capture ``client`` and ``account_type``;
        bail if entry is cold, mid-connect, or has no account_type.
      - Plugin resolve + hook call OUTSIDE the lock.
      - Re-acquire the lock: bail if shutting down; identity-check the
        entry (use-after-evict guard); read ``prior_cache`` INSIDE this
        re-acquired lock so the stale-carry computation observes the
        most recent prior write regardless of any concurrent refresh.
      - Write the three cache fields. Do NOT touch ``last_activity`` —
        the 5-minute refresh would otherwise reset the 30-minute idle
        TTL and per-agent entries would never reap.  (Note: account-keyed
        entries are now exempt from idle eviction by slot kind — M11 F17
        L4 — so the TTL concern no longer applies to them; the
        ``last_activity`` contract here matters only for per-agent
        ``agent_acquire`` entries.)
    """
    from the_one.connectors.errors import ConnectorRegistrationError

    key = (_ACCOUNT_POOL_AGENT_SLOT, account_id)
    async with _lock:
        entry = _pool.get(key)
        if entry is None or entry.client is None:
            return False
        if entry.account_type == "":
            return False
        if entry.client_ready is not None and not entry.client_ready.is_set():
            return False
        client = entry.client
        account_type = entry.account_type

    try:
        plugin = _resolve_plugin(account_type)
    except ConnectorRegistrationError:
        logger.warning(
            "Discoverable refresh: unknown account_type=%r for account_id=%s",
            account_type,
            account_id,
        )
        return False

    hook = getattr(plugin, "enumerate_discoverable_entities", None)
    if hook is None:
        return False

    try:
        new_snapshot = hook(client)
    except Exception as exc:
        logger.warning(
            "Discoverable refresh failed for account_id=%s account_type=%s: %r",
            account_id,
            account_type,
            exc,
        )
        return False

    async with _lock:
        if _shutting_down:
            return False
        current = _pool.get(key)
        if current is None or current.client is not client:
            return False
        # Read prior_cache INSIDE this re-acquired lock — guards the
        # write-side race when two refresh paths overlap.
        prior_cache = current.discoverable_entities_cache
        stale_carry = _compute_stale_carry(prior_cache, new_snapshot)
        current.discoverable_entities_cache = new_snapshot
        current.discoverable_entities_stale_carry = stale_carry
        current.discoverable_entities_fetched_at_monotonic = time.monotonic()
        # Deliberately do NOT touch current.last_activity — see docstring.
    return True


def _compute_stale_carry(
    prior_cache: DiscoverableEntities | None,
    new_snapshot: DiscoverableEntities,
) -> DiscoverableEntities:
    """Compute the 1-cycle stale-carry as ``prior_cache - new_snapshot``
    per-axis, by ``entity.id``.

    Retained entities are emitted from ``prior_cache``'s axis lists so
    their old labels/metadata are preserved for the operator's
    stale-display rendering. Entities present in BOTH cycles are
    excluded (their NEW form lives in the fresh ``cache``).

    If ``prior_cache`` is ``None`` (first refresh), returns an empty
    :class:`DiscoverableEntities` (no entries to carry).
    """
    if prior_cache is None:
        return DiscoverableEntities()

    def _diff_axis(
        prior_axis: list[DiscoverableEntity],
        new_axis: list[DiscoverableEntity],
    ) -> list[DiscoverableEntity]:
        new_ids = {e.id for e in new_axis}
        return [e for e in prior_axis if e.id not in new_ids]

    return DiscoverableEntities(
        peers=_diff_axis(prior_cache.peers, new_snapshot.peers),
        channels=_diff_axis(prior_cache.channels, new_snapshot.channels),
        groups=_diff_axis(prior_cache.groups, new_snapshot.groups),
        roles=_diff_axis(prior_cache.roles, new_snapshot.roles),
    )


async def _discoverable_refresh_once() -> int:
    """Run a single refresh pass across every eligible warm pool entry.

    Snapshots eligible ``account_id``s under ``_lock`` (entries where
    ``key[0] == _ACCOUNT_POOL_AGENT_SLOT`` AND ``entry.client is not
    None`` AND ``entry.account_type`` is non-empty), then calls
    :func:`_refresh_discoverable_entities_for_account` for each
    concurrently via ``asyncio.gather(..., return_exceptions=True)``.

    Returns the count of entries that were refreshed successfully
    (``True`` returns from the helper). Per-call exceptions are
    absorbed by the helper's own ``try/except`` + ``logger.warning``;
    the gather's ``return_exceptions=True`` is belt-and-suspenders.
    """
    async with _lock:
        account_ids = [
            key[1]
            for key, entry in _pool.items()
            if key[0] == _ACCOUNT_POOL_AGENT_SLOT
            and entry.client is not None
            and entry.account_type != ""
        ]
    if not account_ids:
        return 0
    results = await asyncio.gather(
        *(_refresh_discoverable_entities_for_account(aid) for aid in account_ids),
        return_exceptions=True,
    )
    refreshed = 0
    for aid, result in zip(account_ids, results):
        if isinstance(result, BaseException):
            if not isinstance(result, asyncio.CancelledError):
                logger.exception(
                    "Discoverable refresh raised for account_id=%s: %r",
                    aid,
                    result,
                )
            continue
        if result:
            refreshed += 1
    return refreshed


async def _discoverable_refresh_loop() -> None:
    """Background loop: sleep, refresh, repeat.

    Sleeps on :func:`_resolve_discoverable_refresh_interval_seconds` so
    test monkeypatches of the module-level constant and env-var
    overrides take effect across iterations. On ``Exception`` from a
    sweep pass, logs and continues. On ``CancelledError``, re-raises —
    nothing to drain because the cache is in-memory state that clears
    when the pool clears.
    """
    while True:
        try:
            await asyncio.sleep(_resolve_discoverable_refresh_interval_seconds())
        except asyncio.CancelledError:
            raise
        try:
            await _discoverable_refresh_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Discoverable refresh sweep raised; continuing")


async def _get_account_cache_snapshot(
    account_id: str,
) -> _DiscoverableCacheSnapshot | None:
    """Return an immutable frozen-triple snapshot of the warm pool entry's
    cache fields, captured atomically under ``_lock``. Readable outside
    the lock with no consistency risk — the snapshot is by-value, not a
    live entry reference.

    Returns ``None`` if no warm entry exists for ``account_id`` (the
    account is cold — the operator must run Test Connection first). The
    snapshot's ``cache`` may itself be ``None`` when the entry is warm
    but the first refresh has not yet landed (first-call inline-refresh
    edge case).
    """
    key = (_ACCOUNT_POOL_AGENT_SLOT, account_id)
    async with _lock:
        entry = _pool.get(key)
        if entry is None or entry.client is None:
            return None
        return _DiscoverableCacheSnapshot(
            cache=entry.discoverable_entities_cache,
            stale_carry=entry.discoverable_entities_stale_carry,
            fetched_at_monotonic=entry.discoverable_entities_fetched_at_monotonic,
            account_type=entry.account_type,
        )


def record_disposition(account_id: str, kind: str, disposition: str) -> None:
    """Increment the per-account disposition counter best-effort (synchronous).

    M11 F17 L1. Called from :func:`the_one.connectors._observability.log_disposition`
    (not a method — mirrors the module-level :func:`account_acquire` import
    pattern in :mod:`_inbound`).

    WITHOUT acquiring ``_lock``, locate the warm account entry at
    ``(_ACCOUNT_POOL_AGENT_SLOT, account_id)`` and increment the matching
    ``inbound_counters`` / ``outbound_counters`` dict, or no-op if no warm
    entry exists.

    **Concurrency**: asyncio is single-threaded. This function is always
    called from within the event loop (the inbound dispatcher and the Discord
    send path are both async contexts). The pool lock is an asyncio.Lock —
    it cannot be acquired synchronously without blocking the event loop. To
    avoid a synchronous lock acquisition, we read under a NON-LOCKING fast
    path: reading and incrementing a dict entry is an atomic operation in
    CPython's GIL model, and the asyncio single-threaded model guarantees no
    concurrent mutation between two ``await`` points. No lock needed here.

    Resets on pool eviction — counters measure "since the current pool entry
    warmed." This accepted limitation is documented in the flight spec.
    """
    key = (_ACCOUNT_POOL_AGENT_SLOT, account_id)
    entry = _pool.get(key)
    if entry is None or entry.client is None:
        # No warm entry — best-effort no-op.
        return
    if kind == "inbound":
        counters = entry.inbound_counters
    else:
        counters = entry.outbound_counters
    counters[disposition] = counters.get(disposition, 0) + 1


async def _get_account_counters_snapshot(
    account_id: str,
) -> _CountersSnapshot | None:
    """Return an immutable frozen-pair snapshot of the warm pool entry's
    disposition counters, captured atomically under ``_lock``. Readable
    outside the lock with no consistency risk — the snapshot is by-value.

    Returns ``None`` if no warm entry exists for ``account_id``.
    Mirrors :func:`_get_account_cache_snapshot`.

    M11 F17 L1.
    """
    key = (_ACCOUNT_POOL_AGENT_SLOT, account_id)
    async with _lock:
        entry = _pool.get(key)
        if entry is None or entry.client is None:
            return None
        return _CountersSnapshot(
            inbound=dict(entry.inbound_counters),
            outbound=dict(entry.outbound_counters),
        )


async def _get_account_status_snapshot(
    account_id: str,
    last_error: str | None = None,
    last_error_link: str | None = None,
) -> _StatusSnapshot:
    """Return a connection-state snapshot for the status endpoint.

    Reads pool-entry state under ``_lock`` (atomic snapshot); the
    ``is_alive()`` call happens OUTSIDE the lock on the client object
    already captured — safe because :class:`ConnectorClient` implementors
    (e.g. :class:`DiscordClient`) make ``is_alive`` a lock-free flag
    read. Mirrors :func:`_get_account_counters_snapshot`.

    State determination:
      - No warm entry (or entry without a client) → ``disconnected``
      - Entry present but ``client_ready`` not yet set → ``connecting``
      - Entry present, ready, ``is_alive()`` True → ``connected``
      - Entry present, ready, ``is_alive()`` False → ``disconnected``
        (gateway dropped — reaper will evict on next sweep)
      - Entry present, ``failure`` set → ``error``

    ``last_error`` / ``last_error_link`` are passed by the caller (the
    status endpoint reads them from a separate store keyed on account_id
    that the save-warm background task writes on failure). This function
    returns them as-is when state is ``error``; ignores them otherwise.

    M11 F17 L5.
    """
    key = (_ACCOUNT_POOL_AGENT_SLOT, account_id)
    async with _lock:
        entry = _pool.get(key)
        if entry is None:
            # No pool entry. If the caller surfaced a connect-error (the
            # save-warm background task wrote it after connect failed and
            # the entry was popped), return "error" so the UI shows the
            # PrivilegedIntentsRequired message rather than silently
            # reporting "disconnected" and swallowing it.
            if last_error:
                return _StatusSnapshot(
                    state="error", alive=False,
                    last_error=last_error, last_error_link=last_error_link,
                )
            return _StatusSnapshot(
                state="disconnected", alive=False,
                last_error=None, last_error_link=None,
            )
        if entry.failure is not None:
            return _StatusSnapshot(
                state="error", alive=False,
                last_error=last_error, last_error_link=last_error_link,
            )
        if entry.client_ready is None or not entry.client_ready.is_set():
            return _StatusSnapshot(
                state="connecting", alive=False,
                last_error=None, last_error_link=None,
            )
        client = entry.client

    # Check is_alive() and application_id OUTSIDE the lock — both are
    # flag/attribute reads that don't need serialization.
    if client is None:
        return _StatusSnapshot(
            state="disconnected", alive=False,
            last_error=None, last_error_link=None,
        )
    # Read application_id from the client if exposed (DiscordClient exposes it
    # post-READY via the .application_id property; other plugin clients that
    # don't expose the attribute get None via getattr default). Safe outside
    # the lock: it's a simple attribute read with no async involvement.
    app_id: int | None = getattr(client, "application_id", None)
    is_alive_fn = getattr(client, "is_alive", None)
    if is_alive_fn is None:
        # Plugin has no is_alive() — treat as connected (same exemption
        # the reaper uses at _pool.py:~496-503).
        return _StatusSnapshot(
            state="connected", alive=True,
            last_error=None, last_error_link=None,
            application_id=app_id,
        )
    alive = bool(is_alive_fn())
    return _StatusSnapshot(
        state="connected" if alive else "disconnected",
        alive=alive,
        last_error=None,
        last_error_link=None,
        application_id=app_id if alive else None,
    )


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
      3. Cancel ``_discoverable_refresh_task`` (M11 F3 L4): same
         cancel-suppress-await shape; there is no drain because the
         refresh sweep holds no per-entry resources.
      4. Belt-and-suspenders: snapshot any remaining keys (rare — the
         reaper's drain already ran). Concurrent ``_evict`` via gather
         with ``return_exceptions``.
      5. Reset ``_reaper_task = None`` and
         ``_discoverable_refresh_task = None`` so the next test's
         :func:`_clear_for_test` sees a clean slate.

    Total drain time is bounded at ~10s regardless of pool size because
    each ``_evict`` has a 10s per-entry timeout AND the gather'd evicts
    run in parallel.
    """
    global _reaper_task, _discoverable_refresh_task, _shutting_down
    _shutting_down = True

    task = _reaper_task
    if task is not None and not task.done():
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    refresh_task = _discoverable_refresh_task
    if refresh_task is not None and not refresh_task.done():
        refresh_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await refresh_task

    async with _lock:
        keys = list(_pool.keys())
    if keys:
        await asyncio.gather(
            *(_evict(key) for key in keys),
            return_exceptions=True,
        )

    _reaper_task = None
    _discoverable_refresh_task = None


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
                account_type=account.type,
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
            # M11 F3 L4: ensure the discoverable-entities refresh sweep
            # is running. Same idempotence and double-spawn-race posture
            # as the reaper. Spawned on cold-entry creation only — warm-
            # reuse paths do NOT respawn (matches the reaper precedent).
            await _ensure_discoverable_refresh_running_locked()
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
    global _reaper_task, _discoverable_refresh_task, _shutting_down

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

    # M11 F3 L4: cancel the discoverable-entities refresh sweep
    # alongside the reaper. No drain path on cancel — see
    # :func:`_discoverable_refresh_loop`.
    refresh_task = _discoverable_refresh_task
    if refresh_task is not None and not refresh_task.done():
        refresh_task.cancel()
        with contextlib.suppress(BaseException):
            await refresh_task
    _discoverable_refresh_task = None

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
