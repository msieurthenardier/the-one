# Flight: Idle-TTL Lifecycle + Per-(Agent, Source) Process Registry

**Status**: ready
**Mission**: [MCP Integration](../../mission.md)

## Contributing to Criteria

- [ ] Idle local MCP server processes are reaped after a configurable period of disuse and respawned transparently on next use, with the FastAPI lifespan integrated cleanly so the server process tree is drained on shutdown
- [ ] Agent configurations referencing an MCP source that no longer exists, or attached to a server that fails to start, fail gracefully — the agent runtime continues to serve the remaining tools and surfaces the failure to the operator without taking the chat session down *(F4 contributes the pool's graceful-failure surface; F6 wires it into the agent loop)*
- [ ] Each layer of the integration has automated coverage proving its contract — sandbox spawn path *(F3)*; **idle-TTL reaper** *(F4 contributes)*; client-side connection lifecycle for both transports *(F2)*

---

## Pre-Flight

### Objective

Land the lifecycle layer that turns F2's `MCPClient` and F3's bwrap-wrapped spawn into a warm-on-demand, idle-reaped, lifespan-drained pool. Per-`(agent_name, source_id)` keying mirrors `the_one/tools/_session_registry.py` (PTY pool) at the structural level — same pattern, different content. Lazy spawn on first tool dispatch (no eager binding at `AgentFactory.create()`), warm reuse within the per-entry idle TTL, transparent respawn after reap, FastAPI-lifespan-driven `shutdown_drain` on graceful shutdown. F4 also clears the structural debt that F2 deferred and F3 carried forward: the `MCPClient.disconnect` `RuntimeError: generator didn't stop` swallow becomes a clean `contextlib.AsyncExitStack` teardown across both transports (A01); bwrap-side post-setup errors get translated to `MCPSandboxError` per F3 §6's catalog (A02); the `--bind` / `--tmpfs /tmp` argv ordering bug gets reordered (A03). Carries the `the_one/mcp/README.md` runtime-invariants doc that's been deferred since F2 debrief.

### Open Questions

All resolved at flight design (Phase 3 user input):

- [x] **Unit-of-warming** → per-`(agent_name, source_id)` keying. Mirrors `_session_registry.py` exactly. Per-agent credential overrides "for free" because keys differ — agent A's `tokenA`-overridden process and agent B's `tokenB`-overridden process never collide. See §1.
- [x] **Connection lifecycle binding** → lazy demand-paged spawn. No eager binding at `AgentFactory.create()`. First tool dispatch to source X under agent A → `pool.acquire(A, X)` → if absent, spawn (bwrap-wrapped MCPClient + initialize handshake); if present and `is_alive`, reuse. After call, entry stays warm until idle TTL elapses. Mirrors LLM lifecycle (load on demand, idle out — same mental model the operator already has). See §2.
- [x] **Idle TTL default** → 300s (5 minutes). Mirrors PTY pool's `pty_session_idle_ttl_seconds` default. Configurable globally via env var `MCP_POOL_IDLE_TTL_SECONDS`; per-source override deferred to a future flight if operator demand surfaces. See §3.
- [x] **Pool size cap** → no hard cap for v1. Idle TTL is the only eviction mechanism. Steady state with "1 active agent of dozens" = 3-5 warm bwrap processes. Pathological multi-agent fanout is bounded by OS process limit (~thousands); revisit if observed in practice. See §4.
- [x] **A01 timing** → L1a (first leg). The `mcp` SDK's `stdio_client` and `ClientSession` both enter `anyio.create_task_group()` internally; anyio raises `RuntimeError("Attempted to exit cancel scope in a different task...")` on cross-task `__aexit__`. AsyncExitStack alone does NOT solve this — F4 redesigns to a **worker-task-per-entry** pattern where each pool entry owns a dedicated `asyncio.Task` that holds connect AND disconnect on the same task. Reaper signals via `asyncio.Event`. See §5 (substantially revised).
- [x] **A02 inclusion** → bundled in F4 (L2). Mechanism: SDK's `stdio_client(server, errlog: TextIO)` parameter — pass an `os.pipe()`-backed file or `tempfile.SpooledTemporaryFile` as `errlog`, capture and inspect after teardown. NOT `--info-fd` (writes only on success per bwrap manpage) and NOT shell-wrapper-redirect (breaks `--die-with-parent` supervision contract). See §6 (revised).
- [x] **A03 inclusion** → bundled in F4 (L1b — pre-split per Architect cycle-1). Single-block argv reorder. See §7.
- [x] **L1 pre-split** → L1a (AsyncExitStack worker-task pattern; refactor `client.py` + both transports) and L1b (A03 argv reorder + L3 test updates). Different files, different concerns. Mirrors F3 debrief Key Learning #4 ("leg pre-splits reflect blast-radius isolation, not just complexity"). See §Legs.
- [x] **Cross-task verification probe** → flight-design Phase 1b STAKE-TEST probe runs at L1a design before locking the worker-task implementation. Per F2 debrief KL #1 ("flight-design Phase 1b reconnaissance should run a 10-line 'does this actually work' probe when integration tests stake on a specific SDK pattern"). See L1a leg sketch.
- [x] **`mcp_fixture_sandbox_profile`** → consumed by F4's pool integration tests (L4); not deleted. F4 strict-floor profile usage replaces L5a's `_build_naughty_source` ad-hoc construction in pool tests. See §8.
- [x] **L5a Test #6 expectation** → flipped from `MCPConnectionError` to `MCPSandboxError` alongside A02 fix in L2. See §9.
- [x] **HAT** → required (L6). 5-step verification against a real third-party MCP server: lazy spawn on first call, warm reuse, idle reap, transparent respawn, lifespan drain. F3 HAT was skipped because little F3-specific value; F4 has substantial lifecycle behavior that is hard to prove via unit tests alone. See §10.
- [x] **Module placement** → `the_one/mcp/_pool.py` (underscore-private; F6 is the consumer). See §11.
- [x] **FastAPI lifespan ordering** → MCP pool drain runs AFTER PTY session registry drain, BEFORE `close_connection()`. See §12.
- [x] **Documentation** → `the_one/mcp/README.md` written as L5; covers the runtime invariants F2/F3/F4 jointly establish. See §13.

### Design Decisions

**§1. Per-`(agent_name, source_id)` keying**

The pool is `dict[tuple[str, str], _RegistryEntry]` keyed on `(agent_name, source_id)`. `agent_name` is the same identifier the PTY pool uses; `source_id` is the canonical `MCPSource.id` from F1's persistence layer.

- Rationale: per-agent keying naturally satisfies F6's per-agent credential override requirement. When agent A configures `github_token=tokenA` and agent B configures `github_token=tokenB` for the same source, the bwrap subprocesses spawn with different env → must be different processes. Per-`(agent, source)` makes this fall out for free; per-`source` keying would force a `MCPSandbox.profile_changed(old, new)` Protocol method to detect override drift.
- Trade-off: process-count multiplier in pathological multi-agent-fanout cases. Mitigated by lazy spawn (only entries for actively-used (agent, source) pairs ever materialize) and idle TTL reaping.
- Mirrors `the_one/tools/_session_registry.py:73` — `_sessions: dict[tuple[str, str], _RegistryEntry]` — at the structural level. Different content (`PtySession` vs `MCPClient`); same shape.

**§2. Lazy demand-paged spawn — worker-task-per-entry pattern**

`AgentFactory.create()` does NOT spawn MCP processes. Pool entries materialize on first tool dispatch via `pool.acquire(agent_name, source_id)`. **Critically**, each entry owns a dedicated `asyncio.Task` (the "entry worker") that holds the SDK's `stdio_client` + `ClientSession` context for the lifetime of the entry — both `__aenter__` and `__aexit__` run on the SAME task, satisfying anyio's cancel-scope cross-task guard. The reaper task does NOT call `MCPClient.disconnect()` directly; it sets the entry's `evict_event` and the entry worker runs its own teardown.

Pseudo-code (final shapes pinned at L1a after the cross-task probe verifies the SDK behavior):

```python
@dataclass
class _RegistryEntry:
    """A pool entry. Holds connection-state shared between the entry worker
    and any concurrent `acquire` callers waiting on `client_ready`.

    The worker task holds the SDK's anyio task-group-rooted CMs for the
    entry's lifetime. The reaper signals eviction via `evict_event`; the
    worker's `finally` runs disconnect on the SAME task that ran connect,
    avoiding anyio's cross-task __aexit__ guard. `client_ready` lets all
    acquires (first + concurrent) wait for connect to complete; on success
    `client` is populated, on failure `failure` is populated. The worker
    is the SOLE writer of `client` and `failure`.
    """
    ttl_seconds: int
    worker: asyncio.Task[None]
    evict_event: asyncio.Event
    client_ready: asyncio.Event  # set when connect succeeds OR fails
    client: MCPClient | None = None        # populated by worker on connect-success
    failure: BaseException | None = None   # populated by worker on connect-failure


async def _entry_worker(
    source: MCPSource,
    entry: _RegistryEntry,
) -> None:
    """Hold the connection on a single task. Run teardown on the same task.

    On connect-failure, populate `entry.failure` and set `client_ready` so
    waiting acquires re-raise. On connect-success, populate `entry.client`
    and set `client_ready`, then idle until `evict_event` fires; the
    `finally` clause runs disconnect on this same task — anyio guard
    satisfied.
    """
    client = MCPClient(source)
    try:
        await client.connect()      # may raise MCPSandboxError / MCPConnectionError
    except BaseException as exc:
        entry.failure = exc
        entry.client_ready.set()    # unblock all waiters
        return
    entry.client = client
    entry.client_ready.set()        # unblock all waiters
    try:
        await entry.evict_event.wait()  # idle until reaper or shutdown_drain
    finally:
        # CRITICAL: disconnect runs on this same task — same task that
        # entered stdio_client and ClientSession. anyio cross-task guard
        # is satisfied.
        try:
            await client.disconnect()
        except Exception:
            logger.exception("MCPClient disconnect failed during entry teardown")


async def acquire(agent_name: str, source_id: str) -> MCPClient:
    """Look up the warm MCPClient for (agent, source); spawn worker if absent.

    Race-handling invariant: at most one `_entry_worker` task is ever
    created per key. Concurrent acquires for the same key share the
    worker by waiting on `entry.client_ready`. This is enforced by
    keying the pool dict insertion atomically under `_lock` — the first
    caller to hold the lock with a missing key spawns the worker; all
    later callers see the entry and wait.

    Returns a connected MCPClient. Caller is the F6 `MCPToolProvider`.
    Touches last_activity on return so the reaper sees the use.
    """
    # Pre-load the source OUTSIDE the lock to avoid serializing acquires
    # across DIFFERENT keys on the F1 repository read. Per Architect
    # cycle-2 medium #2: the lock should hold only for dict-mutation, not
    # for async I/O.
    source = await _load_source(source_id)

    async with _lock:
        if _shutting_down:
            raise RuntimeError("MCP pool is shutting down")
        entry = _pool.get((agent_name, source_id))
        if entry is None:
            # First-acquirer-for-this-key path. Spawn worker, insert entry.
            # Note: asyncio.create_task returns immediately; the worker body
            # runs on the next event-loop iteration. We're still under the
            # lock here only to make the dict-mutation atomic; the worker's
            # connect() runs on the worker task, NOT under our lock.
            entry = _RegistryEntry(
                ttl_seconds=_resolve_ttl_seconds(),
                worker=None,         # populated immediately below
                evict_event=asyncio.Event(),
                client_ready=asyncio.Event(),
            )
            entry.worker = asyncio.create_task(_entry_worker(source, entry))
            _pool[(agent_name, source_id)] = entry
            await _ensure_reaper_running_locked()
        # else: entry exists. Whether `client_ready` is set yet doesn't
        # matter — we wait on it outside the lock either way. The worker
        # writes `entry.client`/`entry.failure` BEFORE setting `client_ready`,
        # so by the time `client_ready` fires, the values are visible.
        # Capture the handle so we can wait on it after releasing the lock:
        ready, failure_ref, client_ref_entry = entry.client_ready, entry, entry

    # Lock released. All concurrent acquires for this key now wait on the
    # SAME `entry.client_ready` Event — the worker fires it once.
    await ready.wait()

    if client_ref_entry.failure is not None:
        # Connect failed. The first failure-observing acquire pops the
        # entry; subsequent acquires re-raise the same exception. The
        # pop is idempotent (KeyError suppressed via .pop(..., None)).
        async with _lock:
            existing = _pool.get((agent_name, source_id))
            if existing is client_ref_entry:
                _pool.pop((agent_name, source_id), None)
        raise client_ref_entry.failure

    client = client_ref_entry.client
    assert client is not None  # invariant: client_ready set + no failure → client populated
    client._touch_activity()
    return client


async def _evict(key: tuple[str, str]) -> None:
    """Pop the entry, signal the worker to teardown, await the worker.

    `await entry.worker` is REQUIRED for `shutdown_drain` to honour its
    "all entries drained before return" contract — the worker's `finally`
    runs disconnect AFTER `evict_event` fires, and we must not return
    until that finally completes. Per Architect cycle-2 low #3.
    """
    async with _lock:
        entry = _pool.pop(key, None)
    if entry is None:
        return
    entry.evict_event.set()
    try:
        await asyncio.wait_for(entry.worker, timeout=10.0)
    except asyncio.TimeoutError:
        logger.warning("MCP pool worker for %r did not terminate within 10s", key)
        entry.worker.cancel()
        with contextlib.suppress(BaseException):
            await entry.worker
```

The reaper does NOT call `MCPClient.disconnect()` directly. To evict an entry, it calls `_evict(key)` which pops the entry from the pool dict (under lock), sets `entry.evict_event`, and awaits the worker task. The entry worker then runs its `finally` clause, which calls `disconnect()` on the SAME task that ran `connect()` — anyio guard satisfied.

- Rationale: matches the operator's mental model from LLMs (load on demand, idle out). Agent build stays fast. Pathological "dozens of agents, only one in use" case has zero pool entries for dormant agents. Cross-task safety is mechanical, not advisory — anyio enforces it via `RuntimeError`.
- Trade-off: first-call latency includes bwrap spawn + initialize (~50-200ms). Subsequent calls within idle TTL pay zero spawn cost. Latency is rounding error vs LLM cost (~1-30s).
- Race-handling: same-key concurrent acquires share the worker. Mechanically enforced — the lock-held branch checks `entry is None`, not `entry.client is None`. If the entry exists in any state (worker still connecting OR worker connected OR worker failed), we wait on `entry.client_ready` outside the lock. The worker is the sole writer of `entry.client` and `entry.failure`; both are written BEFORE `entry.client_ready.set()`, so post-event reads are race-free.
- **Acquire cancellation**: if the caller cancels mid-`await ready.wait()`, the worker keeps running normally. The entry stays in `_pool` and reaps on idle TTL. NOT a leak; the worker still runs disconnect on its own task when evicted. Documented for L3 implementer.

**§2-detail. Why a worker task per entry, not just AsyncExitStack**

`mcp.client.stdio.stdio_client` (verified at `.venv/lib/python3.12/site-packages/mcp/client/stdio/__init__.py:106-216`) wraps its body in `async with anyio.create_task_group() as tg, await anyio.open_process(...) as process`. `mcp.shared.session.BaseSession.__aenter__` (parent of `ClientSession`, `.venv/lib/python3.12/site-packages/mcp/shared/session.py:220-238`) creates `self._task_group = anyio.create_task_group()`. anyio's `CancelScope.__aexit__` (`.venv/lib/python3.12/site-packages/anyio/_backends/_asyncio.py:454-458`) raises `RuntimeError("Attempted to exit cancel scope in a different task than it was entered in")` on cross-task exit. Wrapping with `contextlib.AsyncExitStack` does NOT change which task runs `__aexit__` — `stack.aclose()` still invokes the registered exit functions on the calling task. The PTY pool avoids this because `PtySession.close()` uses `loop.run_in_executor` (worker thread; sidesteps anyio entirely). F4 cannot use that approach because the SDK's session-level operations (`list_tools`, `call_tool`) MUST run on the original task to satisfy the same constraint. The worker-task-per-entry pattern is the canonical solution: connect, hold, and disconnect all run on the same task — exactly what anyio requires.

**§3. Idle TTL: 300s default, register-time resolved**

Each `_RegistryEntry` stores its resolved `ttl_seconds`. Default = 300s (5 minutes). Configurable via env var `MCP_POOL_IDLE_TTL_SECONDS`. Per-source override deferred — adding it would require extending `MCPSource.config` with a `pool.idle_ttl_seconds` field; not justified by current operator demand. F1 validator is NOT extended in this flight.

- Rationale: 300s mirrors PTY pool's `pty_session_idle_ttl_seconds` default. Long enough to span typical conversation turn-taking; short enough that idle agents reap their MCPs before they consume meaningful memory.
- **Resolution timing**: AT register-time (per-entry, in `_resolve_ttl_seconds()` called inside `acquire`'s lock-held branch), NOT at process start. This mirrors PTY pool's behavior (see `the_one/tools/_session_registry.py::register` lines 89-108 — `ttl_seconds` is passed in by the caller and stored per-entry). Tests `monkeypatch.setenv("MCP_POOL_IDLE_TTL_SECONDS", "10")` BEFORE the `acquire` call to control the resolved TTL for new entries; existing entries retain their previously-resolved TTL (no retro-active re-time).

**§4. No hard pool size cap (v1)**

The pool relies on idle TTL as the only eviction mechanism. No LRU cap, no per-agent limit. Steady-state expected size is 3-5 entries (1 active agent × 3-5 attached sources). Pathological multi-agent fanout bounded by OS process limit (`ulimit -u`, typically thousands). If the pathological case becomes observable, F4-followup adds an LRU cap with eviction-on-full.

- Rationale: simpler v1; matches PTY pool's lack of a global cap (PTY pool has per-agent "5 max concurrent" but no global cap).
- Trade-off: a truly pathological case (rapid agent rotation under load) could leave dozens of warm entries for ~5min before TTL evicts them. Worst-case memory: ~50 × ~50MB per bwrap-wrapped Python = ~2.5GB — uncomfortable but not crash-inducing on a dev box.
- Documented in `the_one/mcp/README.md` (L5).

**§5. AsyncExitStack refactor INSIDE the worker-task pattern (A01)**

The refactor has two layers — single-task usage (the `async with MCPClient(source) as c:` direct-construction pattern that F2 contracts kept) gets `AsyncExitStack`; pool usage gets the worker-task-per-entry pattern (§2 + §2-detail) that wraps the SDK's anyio-task-group-rooted CMs on a single owning task.

**For single-task `MCPClient` usage**: `connect_stdio` and `connect_streamable_http` switch from nested `@asynccontextmanager` + `async with` to returning `(session, stack)` from a non-CM helper. `MCPClient.connect()` stores `self._transport_stack`; `MCPClient.disconnect()` calls `await self._transport_stack.aclose()`. This works ONLY when `connect()` and `disconnect()` run on the same task — the F2 contract's `async with MCPClient(source) as c:` pattern satisfies that naturally; pool usage does NOT (which is why §2 needs the worker-task wrapper).

```python
# Before (F2 / F3) — nested async-CM pattern:
@asynccontextmanager
async def connect_stdio(source):
    params = _build_stdio_params(source)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            yield session

# After (F4 L1a) — explicit stack ownership for single-task callers:
async def connect_stdio(source) -> tuple[ClientSession, AsyncExitStack]:
    """Open a ClientSession + return the stack that owns it.

    SAME-TASK CONTRACT: caller MUST drive `aclose()` from the same task
    that received this return value. Cross-task aclose triggers anyio's
    cancel-scope guard and raises RuntimeError. Pool callers MUST use
    the worker-task pattern in `_pool.py` instead of calling this from
    one task and aclose-ing from another.
    """
    stack = contextlib.AsyncExitStack()
    try:
        params = _build_stdio_params(source)
        read, write = await stack.enter_async_context(stdio_client(params))
        session = await stack.enter_async_context(ClientSession(read, write))
        return session, stack
    except BaseException:
        await stack.aclose()
        raise
```

- `MCPClient.connect()` stores `self._transport_stack` instead of `self._transport_cm`.
- `MCPClient.disconnect()` becomes `await self._transport_stack.aclose()` — clean for same-task usage.
- The `except Exception: logger.warning("MCPClient transport close failed", ...)` swallow at `client.py:255-257` STAYS as defense-in-depth — it's the only thing standing between an accidental cross-task disconnect and an `MCPSandboxError`-pretending-to-be-internal-error log spam. Renamed in comment from "F2 noise" to "cross-task safety net (real fix is the F4 pool's worker-task pattern, not AsyncExitStack)". This preserves the existing contract for direct-construction callers while the pool wraps everything in worker tasks.
- L1a regression tests verify: (a) single-task `async with MCPClient(source) as c:` produces NO `WARNING` log line on disconnect (anyio guard not triggered when same-task); (b) cross-task disconnect explicitly hits the swallow and logs (locks the safety-net contract); (c) the worker-task pattern in `_pool.py` (L3) runs cross-task evict without triggering the swallow (because the worker-task does its own disconnect).
- Subprocess cleanup remains correct under all paths — verified via `/proc` inspection in L1a's regression test.

**§6. A02 bwrap-stderr capture translation (via SDK's `errlog=` parameter)**

`connect_stdio`'s error path (the new AsyncExitStack-wrapped version) captures bwrap's stderr via the SDK's existing `stdio_client(server, errlog=...)` parameter, parses post-exit, and translates to one of three `MCPSandboxError` messages from F3 §6 catalog:

- `"MCP sandbox setup failed: writable_paths entry {path!r} does not exist. Create the directory or remove from writable_paths."`
- `"MCP sandbox setup failed: bubblewrap exited with code {n}. Check that the dev/CI environment has cap_add: SYS_ADMIN AND security_opt: seccomp:unconfined per F3 design decision §10."`
- `"MCP sandbox setup failed: namespace creation refused (EPERM on unshare). The container likely lacks the privilege grants required by §10."`

**Mechanism (locked at flight design, post-Architect-cycle-1)**: pass a `tempfile.SpooledTemporaryFile(mode='w+')` as `errlog=` to `mcp.client.stdio.stdio_client(server, errlog=...)`. The SDK signature is `stdio_client(server: StdioServerParameters, errlog: TextIO = sys.stderr)` (verified at `.venv/lib/python3.12/site-packages/mcp/client/stdio/__init__.py:106`); the SDK forwards `errlog` to `anyio.open_process(stderr=errlog)` at line 254. After the SDK's transport CM raises (broken pipe / connect timeout / etc.), `errlog.seek(0); stderr_text = errlog.read()`; inspect the captured buffer for known bwrap-error signatures and translate to the matching catalog message.

`SpooledTemporaryFile(mode='w+')` is preferred over raw `os.pipe()` because it satisfies the SDK's `TextIO` type directly (no `os.fdopen` dance); no reader-side draining is needed (the file accumulates in memory up to the spool limit; post-exit `seek(0); read()` retrieves everything); cleanup is automatic via context-manager semantics.

**Why NOT the alternatives** (Architect-flagged):
- ❌ `bwrap --info-fd N`: writes only on successful container setup, NOT on failure (per bwrap manpage). Doesn't capture the failure modes we need to translate.
- ❌ `sh -c 'bwrap ... 2>"$ERR_FD"'` shell wrapper: interposes `sh` as bwrap's parent, breaking `--die-with-parent` supervision (bwrap dies when sh dies, NOT when the-one dies). Unacceptable supervision regression.
- ✅ SDK `errlog=` parameter: leverages existing SDK contract; preserves `--die-with-parent` direct parent-process linkage; clean post-exit inspection.

**Stderr signature matching** (precise patterns committed at L2 design):
- `"Can't find source path"` → catalog message #1 (writable_paths nonexistent)
- `"Operation not permitted"` AND (`"unshare"` OR `"create user namespace"`) → catalog message #3 (EPERM on unshare)
- bwrap exit-code != 0 with no recognised pattern → catalog message #2 (generic exit-code fallback)
- empty stderr + exit-code != 0 → catalog message #2 with `n=<exit code>`

L5a Test #6 (`test_sandbox_writable_paths_nonexistent_raises_at_connect`) flips from `MCPConnectionError` expectation to `MCPSandboxError` expectation with catalog message #1 substring match alongside A02's landing.

**L2 design authority**: if the stderr-signature probe at L2 design reveals that signatures (1) and (3) above are not reliably emitted by `bwrap` 0.11.0 (e.g., locale-dependent, version-dependent), L2 has authority to adjust the regex patterns inline OR to drop signature (3) and emit message #2 for both bwrap-exit and EPERM cases (still strictly better than F3's catch-all `MCPConnectionError`). Major scope changes (e.g., dropping the entire translation) escalate per Adaptation Criteria.

**§7. A03 argv reorder**

`bubblewrap.py::prepare_spawn` reorders the argv block: `--tmpfs /tmp` is emitted BEFORE the `--bind PATH PATH` loop (NOT after). This makes `writable_paths=["/tmp/foo"]` actually persist (the tmpfs lays down `/tmp` first; subsequent `--bind` binds layer on top).

- Single-block move: ~3 lines changed in `bubblewrap.py`.
- L3's argv-ordering tests in `tests/test_sandbox_bubblewrap.py` get updated: any test that asserts `--bind` comes before `--tmpfs /tmp` in the argv must flip.
- Operator-facing documentation updated: the L5b help text proposed in F3 debrief ("Paths under `/tmp` are not persisted; use `/var/tmp` or another mount.") is NO LONGER NEEDED — A03 fix makes `/tmp/foo` work as documented.

Bundled with §5 (A01) in L1 since both touch the sandbox-spawn path and L1's regression tests will exercise both fixes simultaneously.

**§8. `mcp_fixture_sandbox_profile` consumed by F4 pool tests**

L4's pool integration tests (and L6 HAT) build `MCPSource` instances via the F3-landed `mcp_fixture_sandbox_profile` fixture (strict-floor `SandboxProfile`) plus per-test command/args overrides. Eliminates the dead-code flag from F3 debrief; gives F4 a consistent profile-per-test pattern.

**§9. L5a Test #6 expectation flip**

`tests/test_mcp_sandbox_integration.py::test_sandbox_writable_paths_nonexistent_raises_at_connect` currently asserts `MCPConnectionError` (locking F3's deferred A02 gap as a positive test). When A02 lands in L2, this test flips to assert `MCPSandboxError` with the §6 message #2 substring. Same test file, same MCPSource construction; assertion changes only.

**§10. L6 HAT — required**

5-step verification against a real third-party MCP server (mcp-server-fetch or in-repo fixture):

1. **Pre-state**: install MCP server (`pip install mcp-server-fetch` in dev container); configure as stdio MCP source via Studio UI; pre-condition `pgrep -f mcp-server-fetch` returns empty (no warm processes).
2. **Lazy spawn**: invoke a tool via `await pool.acquire("agent-a", source.id)` from a Python REPL inside the dev container; confirm `pgrep -f mcp-server-fetch` now shows exactly ONE bwrap-spawned subprocess; confirm `client.is_alive == True`.
3. **Warm reuse**: invoke 5 successive `pool.acquire("agent-a", source.id)` calls; confirm the SAME PID (`pgrep -f mcp-server-fetch` returns the same PID throughout); confirm `client.last_activity` advances on each call.
4. **Idle reap**: BEFORE the entry was registered, the env had been monkeypatched to `MCP_POOL_IDLE_TTL_SECONDS=10` (TTL is resolved at register-time per §3, so this MUST precede the spawn — re-do step 2 if needed). Then EITHER (a) wait 40 seconds (idle TTL of 10s + one full `_REAPER_INTERVAL_SECONDS = 30s` reaper interval) OR (b) call `_pool._reap_once()` directly after `time.sleep(11)` for deterministic single-pass reap. Confirm `pgrep -f mcp-server-fetch` returns empty; confirm next `pool.acquire("agent-a", source.id)` respawns transparently (different PID, different `client` object).
5. **Lifespan drain**: with a warm pool entry, run `docker compose down` (or `kill -SIGTERM` the FastAPI process); confirm bwrap subprocess gone within 5s; confirm no orphan processes via `pgrep -f mcp-server-fetch` from the host (post-container-stop).

Bonus (per Architect cycle-1 suggestion): try `pool.acquire("agent-b", source.id)` (different agent, same source) from step 3 — confirm a SECOND bwrap PID exists, validating per-`(agent, source)` keying.

Binary go/no-go: all 5 required steps pass = ✓; any step fails or produces unexpected output = file a Known Issue and remediate before flight close.

**§11. Module placement: `the_one/mcp/_pool.py`; public API at `the_one.mcp.acquire` / `the_one.mcp.shutdown_drain`**

`the_one/mcp/_pool.py` — underscore-private module mirroring `the_one/tools/_session_registry.py` structurally. The underscore signals "internal implementation; do not import from here". F6 is the consumer (via `MCPToolProvider`); F6 imports via the public re-export, NOT directly from `_pool`:

```python
# F6 consumer (correct):
from the_one.mcp import acquire, shutdown_drain

# F6 consumer (incorrect — flagged by Architect cycle-1; do NOT use):
from the_one.mcp._pool import acquire   # underscore import is a smell
```

`the_one/mcp/__init__.py` extends `__all__` with `["acquire", "shutdown_drain"]` and re-exports them at module level. `acquire` is the canonical name despite its genericness — it's MCP-namespaced via the import path (`the_one.mcp.acquire`), and renaming to `acquire_mcp_client` would diverge from the PTY pool's internal API style (`register`, `close`, `get`, etc., all unqualified within the module).

Internal symbols (all underscore-private; tests reach in for `_clear_for_test` and friends): `_RegistryEntry`, `_pool`, `_lock`, `_reaper_task`, `_shutting_down`, `_REAPER_INTERVAL_SECONDS`, `_DEFAULT_TTL_SECONDS`, `_resolve_ttl_seconds`, `_load_source`, `_entry_worker`, `_reap_once`, `_reap_loop`, `_ensure_reaper_running_locked`, `_clear_for_test`.

**§12. FastAPI lifespan ordering**

`the_one/interfaces/web/app.py::lifespan` shutdown branch order:
1. Cancel in-flight per-message processing tasks (existing).
2. `await _session_registry_shutdown_drain()` (PTY pool — existing).
3. **NEW**: `await mcp_pool_shutdown_drain()` (MCP pool — F4 L4).
4. `await close_connection()` (DB — existing).

MCP pool drain runs AFTER PTY drain (PTY may have shell-tool-spawned MCP-aware code in flight; let it complete before MCP processes go away) and BEFORE DB close (drain may need to read source config from DB — though current design loads at register-time so this is precautionary, not load-bearing).

**§13. Documentation: `the_one/mcp/README.md`**

Carried from F2 debrief recommendation #2 (deferred to F4 per F2 debrief disposition). Scope: **~300-450 lines** (Architect cycle-1 raised earlier estimate — 9 substantive sections at 25-50 lines each is realistic). Sections:

- **Test-seam pattern** (~25 lines): `_test_http_client_override`; future seams follow the 3-property contract: underscore prefix, `__all__` exclusion, `# TEST-ONLY` tag.
- **F4-pool-compat invariants** (~40 lines): `is_alive`, `last_activity`, idempotent disconnect, `_capabilities`/`_protocol_version` preserved across disconnect — co-locate the test names that lock each invariant.
- **AsyncExitStack pattern + worker-task pattern** (~50 lines): why nested `async with` doesn't compose with anyio task-group-managed CMs (cross-task cancel-scope guard); the F4 worker-task-per-entry solution; the L1a single-task vs cross-task contract distinction.
- **`_DEFAULT = object()` sentinel rationale** (~20 lines): per F2 debrief technical #1. **EXPLICITLY DOCUMENT, do NOT refactor to `None`-with-default** — the sentinel pattern is locked by this README and the F2 design decision; future maintainers should not "clean it up".
- **`_PINNED_PROTOCOL_VERSION` read-at-call-time invariant** (~20 lines).
- **2-layer flat-merge env-var assembly contract** (~30 lines): allowlist + operator kv with secrets winning.
- **Sandbox-wrap composition (F3 + post-L2)** (~40 lines): strict-by-default profile, double-flag bypass, A02 RESOLVED status (post-L2 update — drop the deferred-translation caveat from CLAUDE.md F3 contracts §5).
- **F4 pool semantics** (~50 lines): per-`(agent, source)` keying, lazy demand-paged spawn, idle-TTL reap with worker-task ownership, lifespan drain ordering, no hard pool size cap (idle TTL only) + observed-pathological-case watch list.
- **Cross-references to project conventions** (~25 lines): pointer to `the_one/agents.md` for the four named patterns from F3 debrief (trust-the-runtime, canonical-import + convenience-re-export, structural-Protocol-satisfaction, verbatim-message-equality) — **the patterns themselves land in `agents.md` per Architect cycle-1 destination resolution**, not duplicated here. The README cross-links so a reader who lands here finds the project-wide patterns.

Per Architect cycle-1 destination question, the four named patterns are project-wide conventions and belong in `the_one/agents.md`, NOT in `the_one/mcp/README.md`. L5 lands BOTH the README AND the `agents.md` patterns section in a single doc-pass leg.

### Prerequisites

- [x] F1, F2, F3 all `completed`. Dev container has `bubblewrap 0.11.0` + `cap_add: SYS_ADMIN` + `seccomp:unconfined`.
- [x] `MCPClient` lifecycle in place: `connect`/`disconnect`/`is_alive`/`last_activity`/`_touch_activity` per F2 §9.
- [x] `BubblewrapSandbox.prepare_spawn` operational; `MCPSandboxError` canonical at `the_one/mcp/errors.py` per F3.
- [x] `connect_stdio` wraps via `BubblewrapSandbox.prepare_spawn` per F3 L4; double-flag bypass active under pytest.
- [x] FastAPI lifespan integration point exists at `the_one/interfaces/web/app.py:48-74` (PTY pool already drained on shutdown).
- [x] PTY pool reference implementation at `the_one/tools/_session_registry.py` — F4 mirrors its structural pattern.
- [x] F3 debrief Anomalies A02, A03 captured; F2 debrief Recommendation #1 (AsyncExitStack) and #2 (`mcp/README.md`) documented.
- [x] All open questions resolved (13 §§ above).
- [x] Architect-approved at Phase 5b — *to be filled in during design review*.

### Pre-Flight Checklist

- [x] All open questions resolved (13 + 2 added during cycle-1: L1 pre-split, cross-task verification probe)
- [x] Design decisions documented (§§1-13; §2 + §5 + §6 + §10 + §11 + §13 substantially revised post-cycle-1)
- [x] Prerequisites verified
- [x] Validation approach defined (test strategy in legs L1a, L1b, L2, L3, L4 + L6 HAT)
- [x] Legs defined (see In-Flight § Legs — pre-split to 6 legs + L6 HAT per cycle-1 recommendation)
- [x] Architect design review cycle 1 — needs rework. 1 high (AsyncExitStack alone insufficient — anyio cross-task guard) + 6 medium + 3 low. Resolved inline.
- [x] Architect design review cycle 2 — approve with changes. 1 NEW high (duplicate-spawn race in §2 acquire pseudo-code) + 2 med/low. All resolved inline (§2 race-fix: lock-held branch checks `entry is None` not `entry.client is None`; `_load_source` hoisted outside lock; `_evict` helper added per §2 with explicit `await entry.worker`; `errlog=` mechanism uses `SpooledTemporaryFile(mode='w+')`; acquire-cancellation behavior documented). No cycle-3 required.
- [x] User approval (Phase 6) — 2026-05-07. Confirmed: worker-task complexity acceptable; L1a swallow stays as safety net; A02 regex committed at L2 design via probe; no v1 size cap.

---

## In-Flight

### Technical Approach

The flight builds on F2's `MCPClient` and F3's `connect_stdio` sandbox wrap by introducing a per-`(agent_name, source_id)` keyed pool of warm `MCPClient` instances. The pool lives at `the_one/mcp/_pool.py` and structurally mirrors `the_one/tools/_session_registry.py` (PTY pool): module-level dict, `asyncio.Lock`, lazily-spawned reaper task, `shutdown_drain()` wired to FastAPI lifespan.

**Two structural cleanups precede pool work** (L1, L2):
1. **AsyncExitStack refactor** (A01): both transport modules + `MCPClient` switch from nested `async with` to `contextlib.AsyncExitStack`. Eliminates the `RuntimeError: generator didn't stop` swallow inherited from F2. Pool-eviction races then operate against a clean teardown contract.
2. **A02 stderr-scraping translation**: `connect_stdio` inspects bwrap's exit signal on transport failure and emits the F3 §6-cataloged `MCPSandboxError` messages instead of F2's catch-all `MCPConnectionError`. Mechanism (`--info-fd` vs stderr-capture vs exit-code) decided at L2 design via probe.

**A03 argv reorder** lands alongside A01 in L1 (single-block change in `bubblewrap.py`; same review surface).

**Pool primitives** (L3):
- `_RegistryEntry` dataclass: `client: MCPClient`, `ttl_seconds: int`.
- `_pool: dict[tuple[str, str], _RegistryEntry]` keyed on `(agent_name, source_id)`.
- `acquire(agent_name, source_id) -> MCPClient`: lazy-spawn pattern. Lock-snapshot, if-warm-reuse-and-touch, if-absent-spawn-outside-lock, re-check-on-insertion (race-handling).
- No reaper yet; just data structures + the acquire/release contract.

**Reaper + lifespan** (L4):
- Single async `_reap_loop` task. `_REAPER_INTERVAL_SECONDS = 30.0` (matches PTY pool).
- `_reap_once`: snapshot-under-lock + close-after-release pattern. One bad close logs and continues; doesn't kill the loop.
- `shutdown_drain()`: cancels reaper, drains all entries via `MCPClient.disconnect`, sets `_shutting_down = True` so `acquire()` raises `RuntimeError`. Wired into `lifespan` after PTY drain, before DB close.

**README** (L5): runtime invariants doc, ~200-300 lines. Cross-links to F2/F3/F4 design decisions.

**HAT** (L6): 5-step verification per §10.

**Bwrap argv structure post-A03** (only the `--tmpfs /tmp` and `--bind` ordering changes; everything else identical to F3):
- `--die-with-parent`, `--unshare-user`, `[--unshare-pid]`, `[--unshare-ipc]`, `[--unshare-uts]`, `[--unshare-net]`
- `--clearenv`, `--setenv KEY VALUE` per env entry
- `--ro-bind / /`
- **`--tmpfs /tmp`** (MOVED here — was after the `--bind` loop)
- `--bind PATH PATH` per `writable_paths` entry (now layers ON TOP of the tmpfs)
- `--proc /proc`, `--dev /dev`
- `[--chdir cwd]`, `--`, `command, *args`

### Checkpoints

- [ ] **C1a** — AsyncExitStack refactor lands; `connect_stdio` + `connect_streamable_http` return `(session, stack)` tuple; `MCPClient.connect/disconnect` use the stack for same-task callers; cross-task safety net (the existing `except Exception:` swallow) RETAINED with comment renamed to "cross-task safety net"; cross-task probe test verifies pool-style worker-task pattern works without triggering the swallow; F2's 30 + F3's 79 = 109 regression tests pass under the new teardown (L1a)
- [ ] **C1b** — A03 argv reorder lands (`--tmpfs /tmp` BEFORE `--bind` loop); L3's argv-ordering tests in `tests/test_sandbox_bubblewrap.py` updated to lock the new three-way order (`--ro-bind / /` → `--tmpfs /tmp` → `--bind PATH PATH`) (L1b)
- [ ] **C2** — A02 stderr-capture translation lands via SDK's `errlog=` parameter; `connect_stdio` emits F3 §6 catalog messages 1-3 from `MCPSandboxError`; L5a Test #6 flipped from `MCPConnectionError` to `MCPSandboxError`; CLAUDE.md F3 contracts §5 caveat dropped (L2)
- [ ] **C3** — `the_one/mcp/_pool.py` ships with worker-task pattern: `_RegistryEntry`, `_entry_worker`, `acquire` per §2; concurrent-same-key acquires verified to share one worker (no duplicate spawn); failure propagation from worker to acquire caller verified (`MCPSandboxError`/`MCPConnectionError` re-raise) (L3)
- [ ] **C4** — Idle-TTL reaper + `shutdown_drain` + FastAPI lifespan integration; reaper sweeps every 30s; reaper signals eviction via `evict_event` (NOT direct `disconnect()` call from reaper task); `MCP_POOL_IDLE_TTL_SECONDS` env var resolved at register-time per §3; lifespan ordering preserves in-flight-cancel → PTY drain → MCP drain → DB close sequence (verified via test that spies on call order); `register-after-drain-raises` invariant locked (L4)
- [ ] **C5** — `the_one/mcp/README.md` lands at ~300-450 lines covering all 9 sections per §13; the four named patterns from F3 debrief landed in `the_one/agents.md` (per cycle-1 destination resolution); CLAUDE.md updated to cross-reference the README; F3 §5 deferred-translation caveat dropped (L5)
- [ ] **C6** — L6 HAT 5-step verification: lazy spawn, warm reuse, idle reap, transparent respawn, lifespan drain — all PASS against a real third-party MCP server (mcp-server-fetch or in-repo fixture per L6 design); bonus per-(agent, source) keying probe also passes

### Adaptation Criteria

**Divert if**:

- L1a's cross-task probe finds the worker-task-per-entry pattern ALSO trips anyio's cancel-scope guard (e.g., the SDK has additional cross-task constraints beyond the documented `__aenter__`/`__aexit__` task identity). Fall back to: keep the F2 swallow indefinitely, document the SDK constraint as a Known Issue, defer pool work pending SDK upgrade. Escalate to user.
- L2's stderr-signature probe finds bwrap 0.11.0 doesn't reliably emit the patterns committed in §6 (e.g., locale-dependent error messages, output channel changes between bwrap minor versions). L2 has authority to adjust regex patterns inline OR drop EPERM-distinct message #3 (still emits #1 and #2). MAJOR scope drop (eliminating all bwrap-side translation entirely) escalates per §6 design authority clause.
- L3 design surfaces a per-(agent, source) keying edge case that F6 design needs as input (e.g., F6 wants per-(agent, source, tool-name) granularity) — pull forward F6 design input before locking L3's pool key shape.
- Per-source TTL configuration becomes a hard requirement during L4 design (e.g., operator demands different TTLs for OAuth-bearing remote MCPs vs stdio MCPs) — extend `MCPSource.config` with a per-source `pool.idle_ttl_seconds` field; F1 validator extends accordingly. F4-followup if scope grows.
- Pool stress under realistic conditions reveals OS process limit hit (~thousands of orphan bwrap subprocesses despite `--die-with-parent`) — add the LRU cap as L4 sub-leg or follow-up flight.

**Acceptable variations**:

- L2 splitting into L2a (mechanism probe + signature regex commit) + L2b (translation implementation + L5a Test #6 flip) if the probe takes more than half a leg's worth of work.
- L4 splitting into L4a (reaper logic + worker-task evict signaling) + L4b (lifespan integration + shutdown_drain + ordering test) if leg-design LOC estimate exceeds 500.
- Adding a `_pool.evict(agent_name, source_id)` test-seam to `_pool.py` for explicit-eviction tests (in addition to `_clear_for_test`). Decided at L4 design.
- L5 README scope adjusting up to 500 lines if any of the 9 sections grow during writing. Below 300 is the only divert (under-scope).
- L1a regression tests adopting the "stake-test probe" pattern from F2 debrief KL #1 — the cross-task probe is itself a stake-test for the worker-task pattern. Mark as a reusable pattern in the leg artifact.

### Legs

> **Note**: tentative suggestions, not commitments. Refined per leg as work progresses.
>
> **Conventions for all legs**: leg artifacts use anchor-by-symbol-name (NOT `file.py:LINE`) per F1 debrief recommendation; each leg's post-completion checklist includes lint clean (or "no NEW ruff errors") before `[HANDOFF:review-needed]` per F1 debrief Action Item; leg artifacts include "stake-test probe" scripts when integration tests stake on a specific OS/SDK pattern (per F2 debrief Recommendation #5); test-count reconciliation across Objective / Outputs / Acceptance Criteria sections (per F3 debrief recommendation #4); when a leg adds a non-textual form input or touches dirty-tracking / cancel-revert paths, leg-design traces them line-by-line (per F3 debrief recommendation #3).

- [ ] `01a-async-exit-stack-and-cross-task-safety` — Refactor `MCPClient` (`the_one/mcp/client.py`) and both transports (`the_one/mcp/transports/stdio.py` + `streamable_http.py`) from nested `@asynccontextmanager` + `async with` to non-CM `(session, stack)` returns + `contextlib.AsyncExitStack` ownership. `MCPClient.connect()` stores `self._transport_stack`; `disconnect()` calls `await self._transport_stack.aclose()`. **The cross-task safety net swallow at `client.py:255-257` STAYS** — renamed in comment to "cross-task safety net (real fix is the F4 pool's worker-task pattern, not AsyncExitStack)". L1a includes a STAKE-TEST PROBE script that explicitly verifies (a) same-task `async with MCPClient(source) as c:` produces NO WARNING log on disconnect, (b) cross-task `disconnect()` (constructed on task A, awaited on task B) DOES log via the safety net (locks the contract), (c) the worker-task pattern from §2 (probe simulates L3's structure) runs cross-task evict WITHOUT triggering the safety net (because worker-task does its own disconnect on its own task). The probe is committed to the leg artifact as a reusable stake-test per F2 debrief KL #1. F2's 30 + F3's 79 = 109 regression tests must pass unmodified under the new teardown. Subprocess cleanup verified via `/proc` inspection in regression tests. ~5-7 new tests + zero net change to F2/F3 test counts.

- [ ] `01b-bwrap-argv-reorder-tmpfs-before-bind` — Reorder `bubblewrap.py::prepare_spawn` argv so `--tmpfs /tmp` precedes the `--bind PATH PATH` loop. Three-line change in the source. Update L3's argv-ordering tests in `tests/test_sandbox_bubblewrap.py` to lock the new three-way order: `--ro-bind / /` → `--tmpfs /tmp` → `--bind PATH PATH` (per Architect cycle-1 suggestion — explicit three-way assertion, not just two-way). Update L5a documentation references that mention the `/tmp` shadowing edge case to remove the workaround language. Update F3 §2 cross-references in `the_one/agents.md` if they mention the shadowing. ~3-4 test-assertion flips; no new tests beyond the three-way ordering check. Smallest leg in the flight; can run in parallel with L1a if scheduling allows but specs as sequential for review-cycle simplicity.

- [ ] `02-bwrap-error-translation` — Implement A02 per §6 via SDK's `errlog=` parameter. L2 design includes a STAKE-TEST PROBE that triggers each of the three failure modes (writable_paths nonexistent, generic exit-code !=0, EPERM on unshare) inside the dev container and records the exact stderr emitted by bwrap 0.11.0; commits the precise regex patterns to the leg artifact. Implement in `connect_stdio`'s error path (post-L1a AsyncExitStack version). Translate to `MCPSandboxError` with F3 §6 catalog messages 1-3 verbatim. Flip `tests/test_mcp_sandbox_integration.py::test_sandbox_writable_paths_nonexistent_raises_at_connect` (L5a Test #6) from `MCPConnectionError` to `MCPSandboxError` expectation with the catalog #1 substring match; add 2 new tests for the bwrap-exit-non-zero and EPERM paths. Update CLAUDE.md F3 contracts §5 to reflect that all four §6 messages are now reachable (drop the "L4 deferred" caveat). ~3 new + 1 flipped + 1 doc update.

- [ ] `03-pool-primitives-worker-task` — Create `the_one/mcp/_pool.py` per §2 + §11. Implement `_RegistryEntry` per §2 (with `client`, `failure`, `client_ready`, `evict_event`, `worker`, `ttl_seconds`); `_pool: dict[tuple[str, str], _RegistryEntry]`; `_lock: asyncio.Lock`; `_resolve_ttl_seconds()` (reads `MCP_POOL_IDLE_TTL_SECONDS` env var; default 300s); `_load_source(source_id)` (reads `MCPSource` from F1 repository); `_entry_worker(source, entry)` (the worker task per §2 — owns connect, populates `entry.client`/`entry.failure` BEFORE setting `entry.client_ready`, holds via `evict_event.wait()`, runs disconnect on the SAME task); `_evict(key)` internal helper per §2 (pop + signal evict_event + await worker with 10s timeout). Implement `acquire(agent_name, source_id) -> MCPClient` per §2 pseudo-code — **CRITICAL: the lock-held branch checks `entry is None`, NOT `entry.client is None`**, so concurrent same-key acquires share the worker (the duplicate-spawn race the §2 narrative references is the cycle-2 fix). Pre-load `_load_source` OUTSIDE the lock to avoid serializing acquires across different keys (per Architect cycle-2 medium #2). NO reaper yet (just `acquire` + worker-task plumbing + `_evict`). Re-export `acquire` from `the_one/mcp/__init__.py` per §11. Use the F3 `mcp_fixture_sandbox_profile` fixture for MCPSource construction in pool integration tests (resolves the F3 dead-code flag — explicit consumer in this leg). Tests cover: lazy-spawn-on-first-acquire, warm-reuse-on-second-acquire, **concurrent-acquire-same-key-shares-one-worker** (verify only ONE `_entry_worker` task spawn for N concurrent acquires of the same key — directly tests the cycle-2 race-fix), different-keys-spawn-independent-workers (per-(agent, source) isolation), spawn-failure-propagates-from-worker (`MCPSandboxError` from L1a+L2 surfaces back through ALL waiting acquires via shared `entry.failure`), spawn-failure-pop-is-idempotent (only first failure-observer pops the entry; subsequent re-raise without double-pop), acquire-cancellation-leaves-worker-running (caller cancel mid-await; worker still runs disconnect on its own task at TTL), `_load_source` runs OUTSIDE the lock (verified by spy on lock-acquire vs source-load order), `_clear_for_test` autouse fixture for test isolation. ~9-11 tests. Mock `MCPClient` for unit tests; one or two integration tests with real bwrap-spawn for end-to-end validation.

- [ ] `04-reaper-and-lifespan` — Implement `_reap_once` (snapshot-under-lock identifying expired entries; for each: call `_evict(key)` per §2 — pop, signal `evict_event`, AWAIT the worker task with a 10s timeout). `_reap_loop` (sleep + reap; cancellation-handler triggers eviction on all remaining entries via `_evict`). `_ensure_reaper_running_locked`. `shutdown_drain` (cancel reaper, set `_shutting_down = True`, snapshot all keys, call `_evict(key)` for each — concurrently via `asyncio.gather(..., return_exceptions=True)` to bound total drain time at 10s regardless of pool size). After drain, `acquire()` raises `RuntimeError` per §2 invariant. Wire `shutdown_drain` into `the_one/interfaces/web/app.py::lifespan` AFTER `_session_registry_shutdown_drain` and BEFORE `close_connection`. Add a lifespan-order spy test that monkeypatches each shutdown step into a list-append-and-call confirming order: in-flight cancel → PTY drain → MCP drain → DB close (per Architect cycle-1 suggestion). Tests cover: reap-after-idle (worker task exits cleanly via evict_event; no orphan PIDs verified via /proc), reap-active-skipped, reap-error-isolation (one bad worker doesn't kill loop), respawn-after-reap, parallel-warm-multiple-entries, lifespan-drain-cancels-reaper, lifespan-drain-awaits-all-workers (entries are gone from `_pool` AND each worker task has run its `finally`), register-after-drain-raises, lifespan-order-spy, drain-timeout-handles-stuck-worker (per §2 `_evict`'s 10s timeout: cancel + suppress). ~9-11 tests.

- [ ] `05-runtime-readme-and-named-patterns` — Write `the_one/mcp/README.md` per §13 (~300-450 lines, 9 sections). Add the four named patterns from F3 debrief (trust-the-runtime, canonical-import + convenience-re-export, structural-Protocol-satisfaction, verbatim-message-equality) to `the_one/agents.md` under a new "Project conventions" section. README cross-links to `agents.md` for the project-wide patterns; agents.md cross-links to the README for mcp-internal invariants. Update `CLAUDE.md` to reference both ("see `the_one/mcp/README.md` for mcp-runtime invariants; see `the_one/agents.md`'s Project conventions section for cross-cutting patterns"). Add `### the_one/mcp/` section pointer to `the_one/agents.md` per F3 debrief documentation gap #1. ZERO new tests (doc only); lint passes trivially.

- [ ] `06-hat-real-mcp-lifecycle` *(optional but planned per user)* — Per §10. 5-step structured verification:
  1. Install `mcp-server-fetch` via `docker compose exec the-one pip install mcp-server-fetch`. Configure as stdio MCP source via Studio UI (`#studio/mcp-sources`) with `network_allowed=true`, `writable_paths=[]`, `command=python`, `args=["-m", "mcp_server_fetch"]`.
  2. Verify lazy spawn: from a Python REPL, `await pool.acquire("test-agent", source.id)`; confirm `pgrep -f mcp_server_fetch` shows ONE bwrap-wrapped subprocess (and `cat /proc/{pid}/ns/user` shows non-host namespace ID).
  3. Verify warm reuse: 5 successive `pool.acquire("test-agent", source.id)` calls; confirm SAME PID throughout; confirm `client.last_activity` advances on each.
  4. Verify idle reap: monkeypatch `MCP_POOL_IDLE_TTL_SECONDS=10`; wait 40s + reaper tick; confirm `pgrep` returns empty; next `acquire` respawns (different PID).
  5. Verify lifespan drain: with a warm pool entry, `docker compose down`; confirm bwrap subprocess gone within 5s; confirm no orphans on the host.

  Bonus: try a second source (different name, same command) and verify per-(agent, source) keying — different bwrap PIDs.

  Binary go/no-go: all 5 required steps pass = ✓; any step fails = file an Anomaly and remediate before flight close.

---

## Post-Flight

### Completion Checklist

- [ ] All required legs (L1a, L1b, L2, L3, L4, L5) completed; L6 HAT planned per §10
- [ ] All checkpoints (C1a, C1b, C2, C3, C4, C5) met; C6 contingent on L6 outcome
- [ ] `pytest --tb=no -q` green; new test count documented in flight-debrief; F1/F2/F3 regression unaffected (109 prior + F4 new)
- [ ] `ruff check the_one/ tests/` clean (per-leg gate; no accumulated drift)
- [ ] CLAUDE.md F3 contracts §5 updated to reflect A02 RESOLVED (drop deferred caveat)
- [ ] `the_one/mcp/README.md` lands with all sections per §13
- [ ] `the_one/agents.md` gains `### the_one/mcp/` section pointer
- [ ] FastAPI lifespan ordering verified end-to-end via L4 + L6 HAT step 5
- [ ] F5 design has F4 prerequisites met; F5 leg design can proceed without re-opening F4 contracts (F5 = OAuth, streamable-http only, doesn't touch the stdio pool)

### Verification

How to confirm the flight achieved its objective:

1. **AsyncExitStack refactor cleanly removes the F2 disconnect noise**: `pytest tests/test_mcp_*.py -v` green; manual smoke `async with MCPClient(source) as c: await c.list_tools()` followed by exit produces no `WARNING` log line.
2. **A02 + A03 verified**: `pytest tests/test_mcp_sandbox_integration.py::test_sandbox_writable_paths_nonexistent_raises_at_connect -v` passes with `MCPSandboxError` expectation; new tests for bwrap-exit-non-zero and EPERM paths pass; `pytest tests/test_sandbox_bubblewrap.py -v` passes with reordered argv invariants.
3. **Pool unit + integration tests pass**: `pytest tests/test_mcp_pool.py -v` — green.
4. **Lifespan drain integration**: `docker compose exec the-one python -m pytest tests/test_lifespan.py -v` green AND a manual smoke (`docker compose down` after warming a pool entry) leaves no orphan bwrap subprocesses.
5. **Manual smoke**: from a Python REPL inside the dev container,
   ```python
   from the_one.mcp import acquire
   c1 = await acquire("agent-a", source_id)
   c2 = await acquire("agent-a", source_id)
   assert c1 is c2  # warm reuse
   c3 = await acquire("agent-b", source_id)
   assert c3 is not c1  # per-(agent, source) keying
   ```
6. **L6 HAT smoke**: real third-party MCP end-to-end works under the pool (lazy spawn + warm reuse + idle reap + transparent respawn + lifespan drain — all 5 steps pass).
7. **Lint + existing-suite regression**: lint clean; F2's 1169 + F3's net new tests grow by F4's net new tests (estimated +25-35: L1a ~5-7 + L1b ~3-4 + L2 ~3 new + 1 flipped + L3 ~7-9 + L4 ~8-10 + L5 0 = ~26-33), no regressions.

The flight delivers the lifecycle foundation that F5 (OAuth — streamable-http only; doesn't touch the stdio pool), F6 (agent integration — calls `pool.acquire` from `MCPToolProvider`), and F7 (inspector — uses MCPClient directly without going through the pool) all consume. F4 closes mission criterion #5 ("Idle local MCP server processes are reaped after a configurable period of disuse and respawned transparently on next use, with the FastAPI lifespan integrated cleanly so the server process tree is drained on shutdown").
