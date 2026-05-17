# Leg: lifecycle-pool-reaper-and-drain

**Status**: landed
**Flight**: [Connector Plugin Contract and Lifecycle Foundation](../flight.md)

## Objective

Complete `the_one/connectors/_pool.py` by adding the reaper loop, the env-var-driven TTL resolution, the idempotent reaper-spawn helper, and `shutdown_drain` — and wire `shutdown_drain` into the FastAPI lifespan in `interfaces/web/app.py`. Refines `acquire`, `_RegistryEntry`, and `_clear_for_test` from leg 5 so they cooperate with the reaper. Flips leg 5's `test_entry_ttl_seconds_placeholder_is_zero` handoff assertion to lock the new contract.

## Context

This is leg 6 of Flight 1 of Mission 10. Leg 5 landed the per-(agent, account) pool core (`_RegistryEntry`, `_pool`, `_lock`, `_load_account`, `_entry_worker`, `_evict`, `_evict_all_for_account`, `acquire`, `_clear_for_test`) with `ttl_seconds=0` as a placeholder. This leg ships the reaper machinery that consumes `ttl_seconds` and the lifespan integration that drains the pool on shutdown.

### Patterns to mirror

The structural template remains `the_one/mcp/_pool.py`. Specifically:

- `_resolve_ttl_seconds()` at `the_one/mcp/_pool.py:108-128` — env-var read at call time, default 300 (MCP) → 1800 (connector) per the flight Design Decisions
- `_REAPER_INTERVAL_SECONDS = 30.0` at `the_one/mcp/_pool.py:61` — module-level constant
- `_ensure_reaper_running_locked()` at `the_one/mcp/_pool.py:299-309` — idempotent reaper spawn under `_lock`
- `_reap_once()` at `the_one/mcp/_pool.py:312-356` — eviction is parallel via `asyncio.gather(..., return_exceptions=True)`
- `_reap_loop()` at `the_one/mcp/_pool.py:359-384` — sleep-reap loop with `CancelledError` drain
- `shutdown_drain()` at `the_one/mcp/_pool.py:387-428` — set `_shutting_down`, cancel reaper, gather `_evict`

### Activity tracking — new in this leg

The MCP reaper reads `entry.client.last_activity` — `MCPClient` exposes `last_activity` as a property that `client._touch_activity()` updates on every call. The connector `ConnectorClient` Protocol (leg 3) has no such field — Protocol widening to add it is undesirable (forces every future plugin to maintain platform-time tracking when the pool's reaper is the only consumer).

**Decision**: track activity on `_RegistryEntry`, not on `ConnectorClient`. The pool is the sole owner of the lifecycle clock; clients are platform-side opaque objects.

- Add `last_activity: float` to `_RegistryEntry`, default-factory `time.monotonic` (so a freshly constructed entry starts the TTL clock from "now")
- `acquire` updates `entry.last_activity = time.monotonic()` on every successful resolution (warm OR cold) — this is the "this connector was used" signal
- `_reap_once` filter is `(now - entry.last_activity) > entry.ttl_seconds`, gated on `entry.client is not None` (entries mid-connect are not reaped this pass)

**Trade-off** (deferred to Flight 3 for ratification): this measures "time since last `acquire()`", not "time since last platform activity." The assumption is that Flight 3's inbound message dispatcher will call `acquire()` per inbound (cheap — warm reuse) so this metric tracks "time since the connector was used to handle anything." If Flight 3 ends up using a different mechanism (e.g. a `current_client(key)` lookup without acquire-touching), the reaper could prematurely evict actively-used gateway connections — Flight 3's planning must validate this contract or amend it. The reaper exists for memory hygiene, not precise activity timing. **Carry-forward** to the mission's Known Issues: "Activity tracking on `_RegistryEntry.last_activity` assumes Flight 3's inbound dispatcher calls `acquire()` per message; Flight 3 must ratify or refine the contract." If a future flight needs precise platform-side timing (e.g. a Discord-gateway-specific "last keep-alive received" metric), it adds that separately without disturbing the pool's contract.

### Design constraints from the flight

- **`THE_ONE_CONNECTOR_POOL_IDLE_TTL_SECONDS` env var, default 1800 (30 min)** — per the flight's Design Decisions block. Read at call time, not at module import (live-read invariant per `agents.md`).
- **`_REAPER_INTERVAL_SECONDS = 30.0`** — same as MCP. The reaper checks every 30s; entries idle past their TTL get evicted next sweep.
- **`_reap_once` parallelizes evicts via `asyncio.gather(return_exceptions=True)`** — mirrors MCP's rationale: `_evict` has a 10s per-key timeout; sequential reap of N entries would block the reap pass for `10s × N` worst case. Parallel gather bounds the worst case at ~10s regardless of pool size.
- **`shutdown_drain` sets `_shutting_down = True` FIRST** — so any concurrent `acquire` sees the flag at its next lock acquisition. Then cancels the reaper (the reaper's `CancelledError` handler runs its own drain), then belt-and-suspenders gathers `_evict` for any remaining keys.
- **Lifespan integration in `app.py`** — slot `connectors._pool.shutdown_drain()` between MCP pool drain and OAuth periodic-sweep stop. Connector pool is parallel to MCP pool (both hold warm network connections); draining them sequentially is fine since each is `O(10s)` worst-case via parallel gather.
- **`_clear_for_test` from leg 5 now also cancels the reaper** — the reaper-cancel branch was deferred in leg 5; this leg adds it. Order: cancel reaper FIRST (so its `CancelledError`-drain doesn't race the worker-cancel loop), then snapshot+clear `_pool`, then cancel workers.

### Leg-5 handoff assertion flip

Leg 5 added `test_entry_ttl_seconds_placeholder_is_zero` to lock the placeholder. The test message reads: "If leg 6 has landed, flip this assertion to assert ttl_seconds > 0." This leg makes that flip happen — rename the test to `test_entry_ttl_seconds_is_resolved_at_acquire_time` (or similar) and assert `entry.ttl_seconds == _DEFAULT_TTL_SECONDS` (or whatever the resolved value is). Update the docstring to reflect the new contract.

## Inputs

What exists before this leg runs:

- Legs 1-5 landed (uncommitted on the feature branch)
- `the_one/connectors/_pool.py` exists with the leg-5 core surface (no reaper, no TTL resolution, no shutdown_drain)
- `_RegistryEntry` has `ttl_seconds: int` (no default — set to `0` by `acquire`); no `last_activity` field
- Module state: `_pool`, `_lock`, `_shutting_down` (no `_reaper_task`)
- Tests in `tests/test_connectors_pool.py` pass; `test_entry_ttl_seconds_placeholder_is_zero` is the explicit handoff signal
- FastAPI lifespan at `the_one/interfaces/web/app.py:lifespan` drains PTY → MCP pool → OAuth sweep → close_connection; the line `await _mcp_pool_shutdown_drain()` is at L114
- The MCP precedent for all reaper code is `the_one/mcp/_pool.py:108-128, 299-428`

## Outputs

What exists after this leg completes:

- Updated `the_one/connectors/_pool.py` with:
  - `_DEFAULT_TTL_SECONDS = 1800` (module constant)
  - `_REAPER_INTERVAL_SECONDS = 30.0` (module constant)
  - `_reaper_task: asyncio.Task[None] | None = None` (module state)
  - `last_activity: float` added to `_RegistryEntry` with `field(default_factory=time.monotonic)`
  - `_resolve_ttl_seconds()` function — reads `THE_ONE_CONNECTOR_POOL_IDLE_TTL_SECONDS` at call time; default 1800; fall-back on non-int with warning
  - `_ensure_reaper_running_locked()` — idempotent reaper spawn under `_lock`
  - `_reap_once()` — single sweep returning evicted keys; parallel `_evict` via `asyncio.gather`
  - `_reap_loop()` — sleep-reap loop with `CancelledError`-drain handler
  - `shutdown_drain()` — set `_shutting_down`, cancel reaper, gather remaining `_evict`s, reset `_reaper_task = None`
  - Updated `acquire`: populates `entry.ttl_seconds = _resolve_ttl_seconds()` (not 0); updates `entry.last_activity = time.monotonic()` on every successful resolution; calls `_ensure_reaper_running_locked()` under `_lock` on entry insert
  - Updated `_clear_for_test`: cancels reaper FIRST, then proceeds with worker-cancel; resets `_reaper_task = None` at end
- Updated `the_one/interfaces/web/app.py:lifespan`:
  - Add `from the_one.connectors._pool import shutdown_drain as _connector_pool_shutdown_drain` to the import block
  - Insert `await _connector_pool_shutdown_drain()` (with try/except logging) between the existing MCP pool drain and the OAuth periodic-sweep stop
- Updated `tests/test_connectors_pool.py`:
  - `test_entry_ttl_seconds_placeholder_is_zero` renamed + flipped to assert resolved value
  - New tests covering: reaper auto-spawn on first acquire; `_resolve_ttl_seconds` env override + default; `_reap_once` evicts idle entries past their TTL; `_reap_once` does NOT evict entries within TTL; `_reap_once` does NOT evict entries mid-connect (no `client` yet); `shutdown_drain` cancels reaper + drains pool + sets `_shutting_down=True` so subsequent acquire raises; `_clear_for_test` cancels reaper and resets state
- A new lifespan-ordering test (or extension of an existing one) verifying the drain order: PTY → MCP → connector → OAuth → close_connection
- All tests pass; `make test`, `make lint` clean
- Leg status `landed`
- Flight log gains a `### Leg 06: lifecycle-pool-reaper-and-drain` entry

## Acceptance Criteria

- [ ] `_DEFAULT_TTL_SECONDS = 1800` constant at module top of `the_one/connectors/_pool.py`
- [ ] `_REAPER_INTERVAL_SECONDS = 30.0` constant at module top
- [ ] Module state `_reaper_task: asyncio.Task[None] | None = None` declared after `_shutting_down`
- [ ] `_RegistryEntry.last_activity: float = field(default_factory=time.monotonic)` field added
- [ ] `_resolve_ttl_seconds()`:
    - Reads `THE_ONE_CONNECTOR_POOL_IDLE_TTL_SECONDS` via `os.environ.get` at call time
    - Returns the int value when present and parseable
    - Returns `_DEFAULT_TTL_SECONDS` when env var is unset
    - Returns `_DEFAULT_TTL_SECONDS` (with `logger.warning`) when env var is non-int
- [ ] `_ensure_reaper_running_locked()`:
    - Must be called under `_lock`
    - Spawns `_reap_loop()` as a task if `_reaper_task is None or _reaper_task.done()`
    - Idempotent — calling repeatedly does not stack tasks
- [ ] `_reap_once() -> list[tuple[str, str]]`:
    - Snapshots expired keys under `_lock` (filter: `entry.client is not None and (now - entry.last_activity) > entry.ttl_seconds`)
    - Calls `_evict` for each expired key OUTSIDE the lock, in parallel via `asyncio.gather(*..., return_exceptions=True)`
    - Logs (but does not raise) on `_evict` exceptions other than `CancelledError`
    - Returns the list of expired keys (test purchase)
- [ ] `_reap_loop()`:
    - Sleeps `_REAPER_INTERVAL_SECONDS` between sweeps
    - Wraps each `_reap_once` call in `try/except Exception` so one bad pass doesn't kill the loop
    - On `CancelledError`: drains the entire registry concurrently via `_evict`, then re-raises
- [ ] `shutdown_drain()`:
    - Sets `_shutting_down = True` FIRST
    - Cancels `_reaper_task`; suppresses `CancelledError` on its await
    - Belt-and-suspenders drain: snapshots any remaining keys under `_lock`, gathers `_evict(key)` with `return_exceptions=True`
    - Resets `_reaper_task = None` at end
- [ ] `acquire` updated:
    - Sets `entry.ttl_seconds = _resolve_ttl_seconds()` (NOT 0) at entry construction
    - Updates `entry.last_activity = time.monotonic()` on every successful resolution (warm and cold paths)
    - Calls `await _ensure_reaper_running_locked()` UNDER `_lock` on entry insert (after `_pool[key] = entry`)
- [ ] `_clear_for_test` updated:
    - FIRST cancels `_reaper_task` and awaits it with `contextlib.suppress(BaseException)`; resets `_reaper_task = None`
    - Then proceeds with the existing pool-snapshot + worker-cancel sequence from leg 5
    - Resets `_shutting_down = False` at end (already in leg 5; verify still present)
- [ ] `the_one/interfaces/web/app.py:lifespan`:
    - Imports `shutdown_drain as _connector_pool_shutdown_drain` from `the_one.connectors._pool`
    - Calls `await _connector_pool_shutdown_drain()` (with try/except `logger.exception("connector pool shutdown failed")`) immediately after the MCP pool drain and immediately before the OAuth sweep stop
- [ ] Leg-5 test `test_entry_ttl_seconds_placeholder_is_zero` renamed to `test_entry_ttl_seconds_is_resolved_at_acquire_time` (or similar); assertion flipped to `entry.ttl_seconds == _DEFAULT_TTL_SECONDS` (with the default value imported from the module)
- [ ] New tests in `tests/test_connectors_pool.py`:
    - `test_resolve_ttl_seconds_default_is_1800` — no env var set; returns 1800
    - `test_resolve_ttl_seconds_reads_env_override` — env var set to "60"; returns 60
    - `test_resolve_ttl_seconds_non_int_falls_back` — env var set to "abc"; returns 1800
    - `test_resolve_ttl_seconds_read_at_call_time` — set env var AFTER module import; subsequent call sees the new value
    - `test_acquire_spawns_reaper` — first acquire spawns `_reaper_task`; second acquire does NOT spawn a second
    - `test_reap_once_evicts_idle_entries` — acquire, age the entry (set `last_activity` to a past time), `_reap_once()` returns the key and evicts
    - `test_reap_once_does_not_evict_fresh_entries` — acquire, `_reap_once()` returns empty list and pool unchanged
    - `test_reap_once_skips_entries_mid_connect` — entry with `client is None` (mid-connect) is not reaped even if `last_activity` is ancient
    - `test_acquire_updates_last_activity_on_warm_reuse` — acquire twice; `entry.last_activity` increases between calls
    - `test_shutdown_drain_cancels_reaper_and_drains_pool` — acquire warm entries; `shutdown_drain()` returns; pool is empty; `_reaper_task` is None; `_shutting_down` is True; subsequent acquire raises `RuntimeError`
    - `test_clear_for_test_cancels_reaper` — acquire to spawn reaper; `_clear_for_test()`; `_reaper_task` is None; subsequent acquire spawns a fresh reaper
- [ ] Lifespan-ordering coverage:
    - Extend an existing lifespan-ordering test (e.g. in `tests/test_lifespan*.py` or similar) OR add a new test that asserts the drain order is PTY → MCP → connector → OAuth → close_connection (whichever pattern matches the existing project's test for this — search for the MCP drain-order spy mentioned in `app.py:112` and mirror it)
- [ ] `docker exec the-one pytest -x --timeout 30 tests/test_connectors_pool.py` clean
- [ ] `docker exec the-one pytest -x --timeout 30` full suite clean (the connector-pool suite gains ~12 tests; nothing regresses elsewhere)
- [ ] `make lint` clean
- [ ] Leg status `landed`
- [ ] `lifecycle-pool-reaper-and-drain` checkbox checked in flight.md's Legs section
- [ ] Flight log has `### Leg 06: lifecycle-pool-reaper-and-drain` entry under `## Leg Progress`

## Verification Steps

1. **Module exports**:
   - `docker exec the-one python -c "from the_one.connectors._pool import _resolve_ttl_seconds, _ensure_reaper_running_locked, _reap_once, _reap_loop, shutdown_drain, _DEFAULT_TTL_SECONDS, _REAPER_INTERVAL_SECONDS, _reaper_task; assert _DEFAULT_TTL_SECONDS == 1800; print('ok')"`

2. **TTL resolution**:
   - `docker exec the-one python -c "from the_one.connectors._pool import _resolve_ttl_seconds; assert _resolve_ttl_seconds() == 1800; print('ok')"`
   - `docker exec the-one bash -c "THE_ONE_CONNECTOR_POOL_IDLE_TTL_SECONDS=60 python -c 'from the_one.connectors._pool import _resolve_ttl_seconds; assert _resolve_ttl_seconds() == 60; print(\"ok\")'"`

3. **Reaper + drain contract**:
   - The `tests/test_connectors_pool.py` new tests are the canonical verifiers

4. **Lifespan integration**:
   - `grep -n "_connector_pool_shutdown_drain" the_one/interfaces/web/app.py` returns a match in the imports AND a match in the lifespan body
   - The lifespan-ordering test (existing or new) passes

5. **Test name flip from leg 5**:
   - `grep -n "test_entry_ttl_seconds_placeholder_is_zero" tests/` returns nothing (renamed)
   - `grep -n "test_entry_ttl_seconds_is_resolved_at_acquire_time" tests/` returns one match in `tests/test_connectors_pool.py`

6. **No regression**:
   - Full suite green; `make lint` clean

## Implementation Guidance

### Step 1: Module constants and state in `the_one/connectors/_pool.py`

At the top of the module (after the imports), add:

```python
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
```

Add `_reaper_task: asyncio.Task[None] | None = None` to module state (alongside the existing `_pool`, `_lock`, `_shutting_down`):

```python
_pool: dict[tuple[str, str], _RegistryEntry] = {}
_lock: asyncio.Lock = asyncio.Lock()
_shutting_down: bool = False
_reaper_task: asyncio.Task[None] | None = None  # leg 6
```

### Step 2: Add `last_activity` to `_RegistryEntry`

`time.monotonic` import already needed — add `import time` if not present (it likely is via the leg-5 imports, but verify). Update the dataclass:

```python
import time
# ... (other imports)

@dataclass
class _RegistryEntry:
    """A pool entry. ..."""

    ttl_seconds: int
    # Diverges from MCP: connectors track activity on the entry, not on the
    # client. MCP reads ``client.last_activity`` (an MCPClient property);
    # ConnectorClient Protocol has no such field, and widening the Protocol
    # to add one would force every plugin to maintain platform-time tracking
    # when the pool's reaper is the only consumer. See leg 6's "Activity
    # tracking" design rationale. Flight 3 must ratify the per-acquire-touch
    # contract or amend it (mission Known Issue).
    last_activity: float = field(default_factory=time.monotonic)  # leg 6
    worker: asyncio.Task[None] | None = None
    evict_event: asyncio.Event | None = None
    client_ready: asyncio.Event | None = None
    client: ConnectorClient | None = None
    failure: BaseException | None = None
```

Note: `field` import — add `from dataclasses import dataclass, field` if currently importing only `dataclass`.

### Step 3: `_resolve_ttl_seconds()` — mirror MCP

```python
def _resolve_ttl_seconds() -> int:
    """Read ``THE_ONE_CONNECTOR_POOL_IDLE_TTL_SECONDS`` env at call time; default 1800.

    Read at call time so test ``monkeypatch.setenv`` works. Mirrors
    :func:`the_one.mcp._pool._resolve_ttl_seconds`.

    Non-int values fall back to the default with a warning — matches the
    MCP pool's "fail open, don't crash startup" stance.
    """
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
```

Note: `os` import — add if missing.

### Step 4: `_ensure_reaper_running_locked()`, `_reap_once()`, `_reap_loop()` — mirror MCP

```python
async def _ensure_reaper_running_locked() -> None:
    """Spawn the reaper Task if not already running.

    MUST be called under ``_lock`` — avoids a double-spawn race when two
    concurrent :func:`acquire` calls for different keys both try to start
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
    case reap-pass duration at ~10s regardless of pool size. Mirrors MCP.

    Guards ``entry.client is not None`` — entries mid-connect have not
    yet had their ``client`` populated and are NOT reaped this pass.
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
            if isinstance(result, BaseException) and not isinstance(result, asyncio.CancelledError):
                logger.exception(
                    "Connector pool _evict raised during reap pass: key=%r exc=%r",
                    key,
                    result,
                )
    return expired


async def _reap_loop() -> None:
    """Background loop: sleep, reap, repeat.

    On ``CancelledError``: drain the entire registry concurrently via
    :func:`_evict` then re-raise. One bad ``_reap_once`` does not kill
    the loop (try/except Exception around the call).
    """
    try:
        while True:
            await asyncio.sleep(_REAPER_INTERVAL_SECONDS)
            try:
                await _reap_once()
            except Exception:
                logger.exception("Connector pool reap pass raised; continuing")
    except asyncio.CancelledError:
        async with _lock:
            keys = list(_pool.keys())
        if keys:
            await asyncio.gather(
                *(_evict(key) for key in keys),
                return_exceptions=True,
            )
        raise
```

### Step 5: `shutdown_drain()` — mirror MCP

```python
async def shutdown_drain() -> None:
    """Cancel the reaper task; evict every remaining entry.

    Wired into the FastAPI ``lifespan`` shutdown branch between the MCP
    pool drain and the OAuth periodic-sweep stop. After this runs,
    :func:`acquire` raises ``RuntimeError`` for any late-arriving caller.

    Order:
      1. Set ``_shutting_down = True`` FIRST so any concurrent ``acquire``
         sees the flag at the next lock acquisition.
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
```

### Step 6: Update `acquire`

Three changes to leg 5's `acquire`:

1. Replace `ttl_seconds=0` with `ttl_seconds=_resolve_ttl_seconds()`
2. Add `await _ensure_reaper_running_locked()` UNDER `_lock` immediately after `_pool[key] = entry`
3. Update `entry.last_activity = time.monotonic()` BEFORE the return (both warm and cold paths converge here, after the `assert client is not None`)

```python
async def acquire(agent_name: str, account_id: str) -> ConnectorClient:
    """..."""
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
                ttl_seconds=_resolve_ttl_seconds(),  # leg 6
                evict_event=asyncio.Event(),
                client_ready=asyncio.Event(),
            )
            entry.worker = asyncio.create_task(
                _entry_worker(plugin, account, encryptor, entry)
            )
            _pool[key] = entry
            await _ensure_reaper_running_locked()  # leg 6

    assert entry.client_ready is not None
    await entry.client_ready.wait()

    if entry.failure is not None:
        async with _lock:
            existing = _pool.get(key)
            if existing is entry:
                _pool.pop(key, None)
        raise entry.failure

    client = entry.client
    assert client is not None
    entry.last_activity = time.monotonic()  # leg 6 — touch on every resolve
    return client
```

### Step 7: Update `_clear_for_test`

Add the reaper-cancel branch BEFORE the existing pool-snapshot:

```python
async def _clear_for_test() -> None:
    """..."""
    global _reaper_task, _shutting_down

    # Cancel the reaper FIRST so its CancelledError handler doesn't race
    # the worker-cancel loop below.
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
```

### Step 8: Wire lifespan integration in `the_one/interfaces/web/app.py`

In the import block, add:

```python
from the_one.connectors._pool import shutdown_drain as _connector_pool_shutdown_drain
```

(Place it near `from the_one.mcp import shutdown_drain as _mcp_pool_shutdown_drain` at L53.)

In the `lifespan` function's shutdown branch, immediately after the existing MCP pool drain block (currently L107-116) and before the OAuth sweep stop (L117-125), insert:

```python
    # Drain the connector pool AFTER MCP pool drain. Like MCP, connectors
    # hold warm network connections; each subsystem's shutdown_drain bounds
    # its drain time at ~10s via parallel gather, so sequential subsystem
    # drains are fine. Connector pool drain runs BEFORE the OAuth sweep
    # stop (parallel to MCP's ordering) and BEFORE DB close.
    try:
        await _connector_pool_shutdown_drain()
    except Exception:
        logger.exception("connector pool shutdown failed")
```

### Step 9: Update tests in `tests/test_connectors_pool.py`

**Rename + flip the leg-5 handoff test**:

```python
async def test_entry_ttl_seconds_is_resolved_at_acquire_time(patch_plugin) -> None:
    """Leg 6: `acquire` populates `entry.ttl_seconds` via `_resolve_ttl_seconds()`,
    not the leg-5 placeholder. Flight 6's reaper consumes this value to decide
    eviction."""
    from the_one.connectors._pool import _DEFAULT_TTL_SECONDS

    await acquire("agent-a", "acct-1")
    entry = pool_mod._pool[("agent-a", "acct-1")]
    assert entry.ttl_seconds == _DEFAULT_TTL_SECONDS, (
        f"Expected {_DEFAULT_TTL_SECONDS}, got {entry.ttl_seconds}"
    )
```

**Add new tests** (12 total — the rename + 11 new):

```python
async def test_resolve_ttl_seconds_default_is_1800(monkeypatch) -> None:
    monkeypatch.delenv("THE_ONE_CONNECTOR_POOL_IDLE_TTL_SECONDS", raising=False)
    from the_one.connectors._pool import _resolve_ttl_seconds
    assert _resolve_ttl_seconds() == 1800


async def test_resolve_ttl_seconds_reads_env_override(monkeypatch) -> None:
    monkeypatch.setenv("THE_ONE_CONNECTOR_POOL_IDLE_TTL_SECONDS", "60")
    from the_one.connectors._pool import _resolve_ttl_seconds
    assert _resolve_ttl_seconds() == 60


async def test_resolve_ttl_seconds_non_int_falls_back(monkeypatch) -> None:
    monkeypatch.setenv("THE_ONE_CONNECTOR_POOL_IDLE_TTL_SECONDS", "not-a-number")
    from the_one.connectors._pool import _resolve_ttl_seconds
    assert _resolve_ttl_seconds() == 1800


async def test_resolve_ttl_seconds_read_at_call_time(monkeypatch) -> None:
    from the_one.connectors._pool import _resolve_ttl_seconds
    # First call sees the default.
    monkeypatch.delenv("THE_ONE_CONNECTOR_POOL_IDLE_TTL_SECONDS", raising=False)
    assert _resolve_ttl_seconds() == 1800
    # Set env AFTER first call; second call sees the override.
    monkeypatch.setenv("THE_ONE_CONNECTOR_POOL_IDLE_TTL_SECONDS", "120")
    assert _resolve_ttl_seconds() == 120


async def test_acquire_spawns_reaper(patch_plugin) -> None:
    assert pool_mod._reaper_task is None
    await acquire("agent-a", "acct-1")
    assert pool_mod._reaper_task is not None
    first_task = pool_mod._reaper_task
    # Second acquire does NOT spawn a second reaper.
    await acquire("agent-b", "acct-2")
    assert pool_mod._reaper_task is first_task


async def test_reap_once_evicts_idle_entries(patch_plugin) -> None:
    from the_one.connectors._pool import _reap_once

    await acquire("agent-a", "acct-1")
    # Age the entry by setting last_activity to the past.
    entry = pool_mod._pool[("agent-a", "acct-1")]
    entry.last_activity = 0.0  # very old

    expired = await _reap_once()
    assert expired == [("agent-a", "acct-1")]
    assert pool_mod._pool == {}


async def test_reap_once_does_not_evict_fresh_entries(patch_plugin) -> None:
    from the_one.connectors._pool import _reap_once

    await acquire("agent-a", "acct-1")
    expired = await _reap_once()
    assert expired == []
    assert ("agent-a", "acct-1") in pool_mod._pool


async def test_reap_once_skips_entries_mid_connect(patch_plugin) -> None:
    """Entries with client=None (worker mid-connect) are NOT reaped even
    if last_activity is ancient. Prevents reaping a worker that hasn't
    yet had a chance to populate the client."""
    from the_one.connectors._pool import _reap_once, _RegistryEntry
    import asyncio

    # Manually insert a half-constructed entry to simulate mid-connect.
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

    # Clean up the half-entry so _clear_for_test doesn't blow up.
    async with pool_mod._lock:
        pool_mod._pool.pop(key, None)


async def test_acquire_updates_last_activity_on_warm_reuse(patch_plugin) -> None:
    import time as time_mod

    await acquire("agent-a", "acct-1")
    entry = pool_mod._pool[("agent-a", "acct-1")]
    first_activity = entry.last_activity

    # Force a small delay so monotonic() advances. 50ms is conservative for
    # WSL2 / coarse-clock CI environments where 10ms gaps can return
    # identical monotonic readings.
    await asyncio.sleep(0.05)
    await acquire("agent-a", "acct-1")
    assert entry.last_activity > first_activity


async def test_shutdown_drain_cancels_reaper_and_drains_pool(patch_plugin) -> None:
    from the_one.connectors._pool import shutdown_drain

    await acquire("agent-a", "acct-1")
    await acquire("agent-b", "acct-2")
    assert len(pool_mod._pool) == 2
    assert pool_mod._reaper_task is not None

    await shutdown_drain()

    assert pool_mod._pool == {}
    assert pool_mod._reaper_task is None
    assert pool_mod._shutting_down is True

    # Subsequent acquire raises.
    with pytest.raises(RuntimeError, match="shutting down"):
        await acquire("agent-c", "acct-3")


async def test_clear_for_test_cancels_reaper(patch_plugin) -> None:
    await acquire("agent-a", "acct-1")
    assert pool_mod._reaper_task is not None
    first_task = pool_mod._reaper_task

    await pool_mod._clear_for_test()
    assert pool_mod._reaper_task is None

    # Subsequent acquire spawns a fresh reaper task.
    await acquire("agent-a", "acct-1")
    assert pool_mod._reaper_task is not None
    assert pool_mod._reaper_task is not first_task
```

### Step 10: Extend the lifespan drain-order test

The existing test is at `tests/test_mcp_pool.py:528` — `test_lifespan_order_pty_drain_before_mcp_drain_before_db_close`. It uses `monkeypatch.setattr(app_mod, "_mcp_pool_shutdown_drain", ...)` to record call order into a `calls: list[str]`. Extend it:

1. Rename it to `test_lifespan_shutdown_drain_order` (the old name no longer captures the full sequence)
2. Add a `monkeypatch.setattr(app_mod, "_connector_pool_shutdown_drain", ...)` that appends `"connector"` to the calls list
3. Update the assertion to `assert calls == ["pty", "mcp", "connector", "oauth", "db"]` (or whatever the existing pattern uses — match the existing markers verbatim)

This is one test edit, not a new file.

### Step 11: Run tests + lint + update artifacts

```bash
docker exec the-one pytest -x --timeout 30 tests/test_connectors_pool.py
docker exec the-one pytest -x --timeout 30
docker exec the-one bash -c "cd /workspace && make lint"
```

Append `### Leg 06: lifecycle-pool-reaper-and-drain` to flight-log.md; check off `lifecycle-pool-reaper-and-drain` in flight.md; set this leg's status to `landed`; signal `[HANDOFF:review-needed]`. Do NOT commit.

## Edge Cases

- **Reaper cancellation during `_clear_for_test`** — the reaper's `CancelledError` handler tries to `_evict` every entry. `_clear_for_test` cancels the reaper FIRST and awaits it; the reaper's drain runs (or fails to fully complete if the cancellation propagates fast). Then `_clear_for_test`'s own pool-snapshot+worker-cancel loop handles whatever the reaper didn't. Belt-and-suspenders.
- **Entry mid-connect when reaper sweeps** — `_reap_once` filter explicitly skips `client is None`. Such entries stay in the pool until their worker either succeeds (sets `client`, becomes reapable on next sweep) or fails (the failure path in `acquire` already pops the entry idempotently).
- **`last_activity` on a freshly constructed entry** — `field(default_factory=time.monotonic)` sets it at construction. Combined with `_resolve_ttl_seconds()` default of 1800s, the entry won't be reaped until 30 minutes of inactivity post-creation. Tests use `entry.last_activity = 0.0` to force expiry without waiting.
- **Env var read at call time vs cached** — `_resolve_ttl_seconds` is called every time `acquire` constructs a new entry. So a runtime env-var change between two acquires would result in entries with different TTLs. Acceptable — operators don't typically change env vars mid-run.
- **`_reaper_task` lifecycle on first acquire** — `_ensure_reaper_running_locked` is called UNDER `_lock` after `_pool[key] = entry`. The task creation is synchronous (just `asyncio.create_task`), so the lock isn't held while the reaper runs. The reaper starts in the background and immediately sleeps for `_REAPER_INTERVAL_SECONDS`; by the time it wakes for its first sweep, the lock is long-released.
- **Lifespan ordering** — the connector pool drain runs AFTER MCP because the MCP pool may need to be teardown first (if there's any dependency between them, e.g. an MCP source that wraps a connector — not the case today, but the ordering is forward-looking). Drain BEFORE OAuth sweep because OAuth is shared infrastructure both subsystems use; let it survive until both subsystems have drained their warm state.
- **The leg-5 test `test_clear_for_test_round_trips_across_iterations`** explicitly asserts `pool_mod._shutting_down is False` after `_clear_for_test`. This leg's update to `_clear_for_test` does NOT change that contract — `_shutting_down = False` is still set at the end. The test continues to pass unchanged.
- **The leg-5 test `test_acquire_during_shutdown_raises_runtime_error`** flips `_shutting_down = True` manually. Now that `shutdown_drain` is real, this test could alternatively call `shutdown_drain()` to flip the flag — but the existing manual flip is simpler and the autouse fixture's `_clear_for_test` resets cleanly. **Intentionally left as-is** — do NOT refactor.

## Files Affected

- `the_one/connectors/_pool.py` — extended with constants, reaper, TTL resolution, shutdown_drain; `acquire` and `_clear_for_test` updated; `_RegistryEntry.last_activity` added
- `the_one/interfaces/web/app.py` — import and lifespan-call addition
- `tests/test_connectors_pool.py` — leg-5 handoff test renamed/flipped; 11 new tests
- One existing lifespan-ordering test extended OR a new test file created (TBD by implementing agent after `grep`-ing for the current location)
- `missions/10-bi-directional-comms-connectors/flights/01-connector-plugin-contract-and-lifecycle-foundation/flight.md` — check off `lifecycle-pool-reaper-and-drain`
- `missions/10-bi-directional-comms-connectors/flights/01-connector-plugin-contract-and-lifecycle-foundation/flight-log.md` — append `### Leg 06` entry
- `missions/10-bi-directional-comms-connectors/flights/01-connector-plugin-contract-and-lifecycle-foundation/legs/06-lifecycle-pool-reaper-and-drain.md` (this file) — status to `landed`

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
| `the_one/mcp/_pool.py:61` `_REAPER_INTERVAL_SECONDS = 30.0` | OK |
| `the_one/mcp/_pool.py:108-128` `_resolve_ttl_seconds` shape | OK |
| `the_one/mcp/_pool.py:299-309` `_ensure_reaper_running_locked` | OK |
| `the_one/mcp/_pool.py:312-356` `_reap_once` (parallel gather) | OK |
| `the_one/mcp/_pool.py:359-384` `_reap_loop` (CancelledError drain) | OK |
| `the_one/mcp/_pool.py:387-428` `shutdown_drain` (4-step order) | OK |
| `the_one/interfaces/web/app.py:53` MCP shutdown_drain import | OK |
| `the_one/interfaces/web/app.py:107-116` MCP drain in lifespan | OK (connector drain slots immediately after) |
| `the_one/connectors/_pool.py:_RegistryEntry` (leg 5 deliverable) | OK — extends with `last_activity` |
| `the_one/connectors/_pool.py:acquire` (leg 5 deliverable) | OK — extends with TTL, reaper-spawn, activity touch |
| `tests/test_connectors_pool.py:test_entry_ttl_seconds_placeholder_is_zero` (leg 5 deliverable) | OK — renamed + flipped in this leg |
