# MCP runtime invariants

This document captures the runtime invariants that F2 (MCP client foundation), F3
(sandbox layer), and F4 (idle-TTL pool + lifespan integration) jointly establish.
Read this BEFORE modifying anything in `the_one/mcp/` — many of the invariants
below are load-bearing for tests AND for the operator's mental model of how MCPs
spawn and reap.

For project-wide conventions (`trust-the-runtime`,
`canonical-import + convenience-re-export`, `structural-Protocol-satisfaction`,
`verbatim-message-equality`), see `the_one/agents.md`'s "Project Conventions"
section.

For the F3 sandbox boundary catalog (catalog messages 1-3, verbatim text), see
`CLAUDE.md`'s F3 contracts §5.

## §1. Test-seam pattern

Each test seam in `the_one/mcp/` follows a 3-property contract:

  1. Underscore-prefixed name.
  2. Excluded from the module's `__all__`.
  3. `# TEST-ONLY` comment tag immediately above the seam declaration.

Live example: `the_one/mcp/transports/streamable_http.py:_test_http_client_override`.
Test fixtures monkeypatch this attribute to inject an ASGI-transport
`httpx.AsyncClient` for in-process FastMCP testing. The production code path
reads the attribute at call time and uses the override iff non-None; otherwise
it constructs a real `httpx.AsyncClient` from `build_request_headers`.

Production code paths NEVER read or write this attribute outside the function
that consumes it. Tests use
`monkeypatch.setattr(the_one.mcp.transports.streamable_http, "_test_http_client_override", client)`
and rely on the autouse fixture to clear it back to `None` between tests.

Future seams follow the same 3-property contract. Do NOT promote a seam to
public by removing the underscore — instead, expose a clean public API that
does not need the seam, and remove the seam together with the test that
depended on it. The underscore prefix + `__all__` exclusion + `# TEST-ONLY`
tag together are the contract that distinguishes "internal mutable point" from
"stable public surface."

The `_DEFAULT` sentinel in §4 and the `_PINNED_PROTOCOL_VERSION` constant in
§5 are NOT test seams (they are production internals exposed for monkeypatch);
the test-seam contract above applies specifically to module-level attributes
whose ONLY production-time value is `None` (or equivalent inert default) and
whose only consumer is its own enclosing function.

## §2. F4-pool-compat invariants

`MCPClient` (in `the_one/mcp/client.py`) exposes four invariants that the F4
pool depends on. Each invariant is stake-tested below.

- **`is_alive`**: `bool` property. Flips `False` BEFORE awaiting any close
  coroutines, so a concurrent reaper-task observes the disconnect-in-progress
  state correctly. Internally backed by `_alive: bool`.

  - Locked by: `tests/test_mcp_client.py::test_disconnect_idempotent`,
    `test_disconnect_swallows_close_errors`.

- **`last_activity`**: `float` property. `0.0` until the first successful
  operation; updated by `_touch_activity()` on each
  `connect`/`list_tools`/`call_tool`/warm-pool-acquire. The pool's `_reap_once`
  reads `entry.client.last_activity` to decide eviction; `0.0` is treated by
  the reaper as "never used" and combined with the entry's `register_time`
  to age out mid-connect entries. The pool's `_RegistryEntry` also carries an
  `entry.client is not None` guard so mid-connect entries (where the worker
  has not yet populated `entry.client`) are never considered expired.

  - Locked by: `tests/test_mcp_pool.py::test_acquire_warm_reuse_returns_same_client_instance`
    (asserts `_touch_activity.call_count == 2` after a second `acquire`).

- **Idempotent disconnect**: `disconnect()` is safe to call on a
  never-connected client AND safe to call twice. Never raises. Internally
  early-returns when `_alive is False AND _exit_stack is None`; otherwise it
  sets `_alive = False` first and then runs `_exit_stack.aclose()` inside a
  `try/except Exception:` that swallows everything to `logger.warning` (the
  cross-task safety net documented below).

  - Locked by: `tests/test_mcp_client.py::test_disconnect_idempotent` and
    `test_disconnect_swallows_close_errors`.

- **State preservation across disconnect**: `_capabilities`,
  `_protocol_version`, `_last_activity` are NOT cleared on `disconnect`. Once
  disconnected they're stale-but-not-invalid; the F4 pool's `_clear_for_test`
  and `_evict` rely on this so post-disconnect introspection of evicted
  entries is meaningful in tests, and so a reconnect-after-disconnect path
  could in principle compare prior state to current state.

**Cross-task safety net**: `MCPClient.disconnect`'s
`except Exception: logger.warning(...)` swallow is documented (post-L1a) as a
cross-task safety net, NOT a no-op. The real fix for cross-task disconnect is
the F4 pool's worker-task pattern (see §3 and §8). The swallow catches
anyio's `CancelScope.__aexit__` `RuntimeError` if any caller accidentally
invokes `disconnect` on a different task than the one that ran `connect`.

  - Locked by: `tests/test_mcp_client.py::TestAsyncExitStackContract` — five
    tests verify (1) same-task no-warn, (2) cross-task warns via safety net
    (with anyio's REAL cross-task guard firing — not a mock), (3) worker-task
    pattern no-warn, (4) connect-failure runs `aclose`, (5)
    disconnect-idempotent-with-stack.

## §3. AsyncExitStack pattern + worker-task pattern

The MCP SDK's `mcp.client.stdio.stdio_client` and
`mcp.shared.session.BaseSession.__aenter__` both wrap their bodies in
`anyio.create_task_group()`. anyio's `CancelScope.__aexit__` (verified at
`.venv/lib/python3.12/site-packages/anyio/_backends/_asyncio.py:444-458`)
raises `RuntimeError("Attempted to exit cancel scope in a different task than
it was entered in")` on cross-task `__aexit__`. The error is structural:
anyio enforces single-task ownership of cancel scopes regardless of how the
user wraps the entry/exit.

**AsyncExitStack alone does NOT solve cross-task disconnect.**
`AsyncExitStack.aclose()` invokes registered exit functions on the calling
task — if that task differs from the one that ran the original `__aenter__`,
anyio's guard fires regardless of the AsyncExitStack wrapping. The stack is
a clean way to compose multiple `__aexit__`s with proper exception handling,
but it is NOT a cross-task bridge.

L1a's refactor accomplished two things:

  1. `MCPClient.connect/disconnect` use a single owned `AsyncExitStack`
     (cleaner exception handling vs F2's manual `__aenter__`/`__aexit__`
     calls). Same-task connect/disconnect pairs are now structurally
     guaranteed to release transport resources in reverse-of-acquire order
     even if intermediate steps raise.
  2. Documented the cross-task safety-net swallow in `disconnect` as the real
     cross-task fallback — for code paths that accidentally violate the
     same-task contract, the warning + return prevents a noisy uncaught
     `RuntimeError` from reaching the caller.

**L1a scope-reduction deviation** (transport modules unchanged): the transport
helpers (`connect_stdio`, `connect_streamable_http`) and the
`_transport_connect` dispatcher remain `@asynccontextmanager`-decorated, per
the L1a runtime decision documented in flight 04 flight-log under "L1a
runtime deviation — transport-API scope reduced (2026-05-07)". The original
L1a design rewrote them to non-CM `(session, stack)` returns; that change was
abandoned at implementation time because nine prior tests directly consumed
those helpers as async-CMs and rewriting them all was out of L1a's scope.

F4 L3's worker-task pattern wraps `MCPClient.connect/disconnect`, NOT the
transport helpers, so the transport API shape is opaque to L3 — the
deviation is invisible at the pool layer. A future flight that wants to
collapse the transport CM-shape can do so without disturbing the pool, and
vice versa.

**F5 L1 update (2026-05-07)**: the `_transport_connect` dispatcher's body has
been rewritten to remove the the-one-owned `@asynccontextmanager` wrapper
layer (`connect_streamable_http` / `connect_stdio`) from the dispatcher's
exit chain. The dispatcher itself remains `@asynccontextmanager`-decorated
(one layer); the SDK's `streamable_http_client` / `stdio_client` ALSO remain
`@asynccontextmanager`-decorated (one layer); these two are now composed via
`AsyncExitStack` (returned by the new
`_open_streamable_http_transport_stack` / `_open_stdio_transport_stack`
helpers) instead of via nested `async with`. Total layer reduction: 3 → 2.
**This MAY retire the F4-HAT-Finding-#1 `RuntimeError: generator didn't stop`
warning for F4-pool-routed (same-task) disconnects.** Empirical verification
is at the F5 L6 HAT (Tier-1 in-repo OAuth fixture) — a caplog assertion
checks for absence of `MCPClient transport close failed` records during the
5-step OAuth-flow lifecycle. If that assertion fails, L1's mechanism didn't
help; the F2-known-issue is reinstated as Mission Known Issue and a follow-
up flight diagnoses the root cause. Cross-task disconnect on a direct
`MCPClient(source)` instance OUTSIDE the F4 pool STILL fires the safety-net
swallow — that contract is preserved (locked by
`tests/test_mcp_client.py::TestAsyncExitStackContract::test_direct_cross_task_still_warns`).
The existing `connect_streamable_http` / `connect_stdio`
`@asynccontextmanager` helpers stay UNCHANGED for back-compat with their
1 + 9 = 10 prior async-CM direct callers (citation-audit-verified at L1
design 2026-05-07).

The F4 pool's worker-task-per-entry pattern (see §8) is the canonical
cross-task-safe solution: each pool entry owns a dedicated `asyncio.Task`
that holds connect AND disconnect on the same task. Anyio's guard is
satisfied mechanically, NOT by `AsyncExitStack` wrapping. The pool does not
need to understand the transport's CM shape — it interacts only with the
`MCPClient` surface.

  - Locked by: `tests/test_mcp_client.py::TestAsyncExitStackContract::test_worker_task_pattern_no_safety_net_log`
    (verifies the worker-task pattern against real anyio task group; no
    `cross-task` warning emitted).

## §4. `_DEFAULT = object()` sentinel rationale

`the_one/mcp/client.py` defines `_DEFAULT = object()` as a sentinel for
"caller passed nothing" vs "caller explicitly passed None/0". Used by
`MCPClient.__init__`'s `timeout_seconds` and `call_timeout_seconds`
parameters.

**DO NOT REFACTOR to None-with-default** (i.e. do not replace `_DEFAULT` with `None` and a default value). The sentinel pattern is locked by this README and the F2 design decision; future maintainers should not "clean it up." Refactoring to `None` would:

  1. Break the distinction between "use the runtime default" and "explicitly
     disable timeout (None means infinite)". The F2 surface deliberately
     reserves `None` as a future-extensible value — currently treated as
     "use default" by callers, but the sentinel keeps the door open for
     "explicit None means infinite" without an API break.
  2. Make test monkeypatching of `the_one.mcp.MCP_DEFAULT_TIMEOUT_SECONDS`
     ineffective for already-instantiated clients, because the bound default
     would have been read at `__init__` time. The sentinel + lazy lookup
     pattern below preserves the read-at-call-time invariant.

The lazy read in `__init__` reads the default at construction time but
lazily, via attribute access on the package module:

```python
from the_one import mcp as the_one_mcp
if timeout_seconds is _DEFAULT:
    timeout_seconds = the_one_mcp.MCP_DEFAULT_TIMEOUT_SECONDS
```

This preserves the read-at-call-time invariant —
`monkeypatch.setattr(the_one.mcp, "MCP_DEFAULT_TIMEOUT_SECONDS", 5)` works
for clients constructed AFTER the patch. The sentinel is what makes the
lazy-read branch reachable; replacing it with `None` would force eager
evaluation of the default at function-definition time and break the
monkeypatch contract.

## §5. `_PINNED_PROTOCOL_VERSION` read-at-call-time invariant

`the_one/mcp/__init__.py` defines `_PINNED_PROTOCOL_VERSION = "2025-11-25"`.
`MCPClient.connect()` reads it via:

```python
from the_one import mcp as the_one_mcp
pinned = the_one_mcp._PINNED_PROTOCOL_VERSION
```

This lazy import + attribute access keeps the read at call time, NOT at
module import time.
`monkeypatch.setattr(the_one.mcp, "_PINNED_PROTOCOL_VERSION", "...")` works
for connects executed AFTER the patch, which is what the version-mismatch
test relies on to drive `MCPVersionMismatch` without forcing the production
code to ship a different pinned version.

Do NOT refactor to a top-of-file
`from the_one.mcp import _PINNED_PROTOCOL_VERSION` — the symbol would be
bound at module load and `monkeypatch.setattr` would have no effect, breaking
the version-mismatch test. The same anti-pattern applies to any future
module-level constant that tests must override at runtime: import the
package and read the attribute at call time, do NOT bind the name at module
load.

The fail-hard policy is narrower than the SDK's `SUPPORTED_PROTOCOL_VERSIONS`
whitelist: `MCPClient.connect()` raises `MCPVersionMismatch` on ANY mismatch,
not just on versions outside the SDK whitelist. This is the pre-1.0 stance
(revisit at SDK 1.0). The test that locks the policy passes a
non-pinned-but-SDK-supported version and asserts `MCPVersionMismatch` raises
— proving the gate is on the pinned constant, not the SDK whitelist.

## §6. 2-layer flat-merge env-var assembly contract

Subprocess environment for stdio MCP servers is assembled in two layers:

  1. **Allowlist**: `the_one.platform.env._ENV_ALLOWLIST` filters the host
     environ to a fixed 8-key set
     (`PATH, HOME, USER, LOGNAME, LANG, LC_ALL, TERM, TZ`). Materialized via
     `_build_subprocess_env()`.
  2. **Operator kv**: `MCPSource.config["env"]` (plaintext at rest)
     ∪ `MCPSource.secrets` (Fernet-encrypted at rest). Secrets win on
     collision — over BOTH allowlist and config.env.

The merge is flat (no nested-dict dispatch, no namespacing) and the
precedence order is fixed: allowlist → config.env → secrets, with later
entries overwriting earlier ones for the same key. The contract is:
**secrets always win**, regardless of what the operator put in plaintext
config or what the host environment contained.

Live implementation: `the_one/mcp/transports/stdio.py::build_stdio_environ`.

Streamable-http transport mirrors the pattern for HTTP headers:
`the_one/mcp/transports/streamable_http.py::build_request_headers`
flat-merges `config.headers` and `secrets`. Same shape, different content
(no allowlist layer because HTTP headers do not inherit from the host
environ — there is nothing to filter).

The "do NOT consume `MCPSource.merged_config()` for stdio environ" rule is
load-bearing: `merged_config()` is a flat top-level merge that injects
`command`/`args`/etc. as env-var keys, which would corrupt the subprocess
environment. Stdio environ assembly takes the segregated `(config, secrets)`
pair directly. `merged_config()` is convenient enough that a future
maintainer might reach for it; the rule in transports/stdio.py's docstring
exists to head off that mistake at code-review time.

## §7. Sandbox-wrap composition (F3 + post-L1b + post-L2)

F3's `BubblewrapSandbox.prepare_spawn` wraps every locally-spawned stdio MCP
server. Strict-by-default profile:

- `--clearenv` + per-key `--setenv` env-allowlist (the assembled
  `(allowlist + config.env + secrets)` dict from §6 is passed key-by-key,
  not via `--setenv-from-env`).
- `--ro-bind / /` + `--bind PATH PATH` filesystem scope (read-only host
  root, read-write only the operator-named paths).
- `--unshare-net` network policy when `network_allowed=False`.
- `--die-with-parent` process supervision (sandboxed subprocess dies with
  the python parent, no orphan).
- `HOME=/tmp` override regardless of operator-supplied env (sandbox policy,
  see CLAUDE.md F3 contracts §7).

**A03 RESOLVED (post-L1b)**: argv emits
`--ro-bind / /` → `--tmpfs /tmp` → `--bind PATH PATH` (post-L1b). Pre-A03
ordering had `--tmpfs /tmp` AFTER the `--bind` loop, which silently shadowed
any operator-configured `writable_paths` under `/tmp` (e.g.
`/tmp/mcp-data`) — the bind would land first, then the tmpfs would overlay
the same mount point, hiding the bind. Post-L1b, `/tmp`-scoped writable
paths persist correctly because the tmpfs lays down a fresh mount BEFORE the
operator binds land on top of it. Locked by
`tests/test_sandbox_bubblewrap.py::test_argv_orders_tmpfs_before_writable_path_binds`.

**A02 RESOLVED (post-L2)**: bwrap-side post-setup errors (writable-path
nonexistent, generic exit-code != 0, EPERM on unshare) are translated to
`MCPSandboxError` with F3 §6 catalog messages. Mechanism: `connect_stdio`
opens a `tempfile.SpooledTemporaryFile` and passes it as `errlog=` to
`stdio_client(...)`. On post-CM failure, the captured stderr is read (≤500
chars stripped) and pattern-matched against three signatures:

  - `Can't find source path` → catalog #1 (`writable_paths` nonexistent).
  - `bwrap:` prefix + (`unshare`|`user ns`|`create user namespace`) +
    (`Operation not permitted`|`EPERM`) → catalog #3 (EPERM on unshare).
  - `bwrap:` prefix + no recognised pattern → catalog #2 (generic
    bwrap-failure fallback).
  - Captured stderr does NOT start with `bwrap:` → return None; F2's
    `MCPConnectionError` handles the (post-bwrap-success,
    child-process-failure) case.

The `bwrap:` prefix discriminator is the load-bearing test. Locked by
`tests/test_mcp_sandbox_integration.py::test_inner_process_failure_does_not_translate_to_sandbox_error`
(a child process that exits non-zero with a non-`bwrap:`-prefixed message
stays in `MCPConnectionError`, NOT `MCPSandboxError`).

**Test-mode bypass**: when `THE_ONE_SANDBOX_DISABLED=1 AND
THE_ONE_TEST_MODE=1` (the F3 §10 double-flag bypass), the sandbox layer is
skipped entirely and `connect_stdio` calls
`stdio_client(StdioServerParameters(...))` with the raw command/args/env.
NEVER set `THE_ONE_TEST_MODE` in production env, in any Dockerfile, in any
docker-compose service env, in any entrypoint script, in any k8s manifest,
or in any CI variable that is not pytest-scoped. The double-flag is the
structural guarantee that production cannot accidentally bypass the sandbox
via a single env-var slip.

See `CLAUDE.md` F3 contracts §5 for the full catalog message text and the
exception-class hierarchy contract.

## §8. F4 pool semantics

`the_one/mcp/_pool.py` is the per-`(agent_name, source_id)` keyed pool of
warm `MCPClient` instances.

**Per-`(agent, source)` keying** (§F4.1): each (agent, source) pair gets its
own `_RegistryEntry`. Per-agent credential overrides "for free" because
keys differ — agent A's `tokenA`-overridden process and agent B's
`tokenB`-overridden process never collide. The keying choice falls out of
M07's mission constraint that each agent's MCP traffic stays attributable
to that agent's identity.

**Lazy demand-paged spawn — worker-task-per-entry pattern** (§F4.2):
`AgentFactory.create()` does NOT spawn MCP processes. Pool entries
materialize on first tool dispatch via
`pool.acquire(agent_name, source_id)`. Each entry owns a dedicated
`asyncio.Task` (the entry worker) that holds connect AND disconnect on the
SAME task — anyio's cross-task `CancelScope.__aexit__` guard is satisfied
mechanically (see §3). The reaper signals via `entry.evict_event`; the
worker's `finally:` runs `MCPClient.disconnect()` on its own task.

**Concurrent-acquire-same-key races to a shared worker**: cycle-2 race-fix
invariant — the lock-held branch in `acquire` checks `entry is None`, NOT
`entry.client is None`. Concurrent same-key acquires share the worker by
waiting on `entry.client_ready`. The worker is the SOLE WRITER of
`entry.client` and `entry.failure`; both fields are written BEFORE
`entry.client_ready.set()`, so awaiters that proceed past the event observe
a fully-populated entry. Locked by
`tests/test_mcp_pool.py::test_concurrent_acquire_same_key_shares_one_worker`
(5 concurrent `gather` acquires, `_instance_count == 1`, all 5 awaiters see
the same client).

**Idle TTL** (§F4.3): default 300s. Configurable via
`MCP_POOL_IDLE_TTL_SECONDS` env var. Read at register time per-entry —
tests `monkeypatch.setenv` BEFORE `acquire` to control the resolved TTL for
new entries; existing entries retain their previously-resolved TTL. The
reaper runs every `_REAPER_INTERVAL_SECONDS` (60s) and evicts entries with
`now - entry.client.last_activity > entry.ttl_seconds`. Mid-connect
entries (where `entry.client is None`) are NOT considered expired by the
reaper because the `entry.client is not None` guard precedes the staleness
comparison.

**No hard pool size cap (v1)** (§F4.4): idle TTL is the only eviction
mechanism. Pathological multi-agent fanout is bounded by OS process limit.
If observable in practice, a future flight may add an LRU cap; for now the
operator's responsibility is to size their `pty_session_idle_ttl_seconds`
and operator-tool-config TTLs commensurate with observed usage. Watch list:

  - per-source unbounded fanout if an agent rotates source IDs faster than
    TTL expiry;
  - very-long-running sessions where TTL never elapses despite low activity.

**Lifespan ordering** (§F4.12): FastAPI's `lifespan` shutdown branch runs:

  1. Cancel in-flight per-message processing tasks.
  2. `_session_registry_shutdown_drain()` (PTY pool).
  3. `_mcp_pool_shutdown_drain()` (this pool — added in L4).
  4. `close_connection()` (DB).

MCP pool drains AFTER PTY because PTY may have shell-tool-spawned MCP-aware
code in flight; drain BEFORE DB close because drain may need source config
from DB (precautionary — current `_evict` does not actually read the DB,
but the contract is that drain-with-DB-still-open is safe).

  - Locked by:
    `tests/test_mcp_pool.py::test_lifespan_order_pty_drain_before_mcp_drain_before_db_close`
    (spies on the three drain calls and asserts the list is
    `["pty", "mcp", "db"]` exactly). Moving the MCP drain BEFORE PTY drain
    or AFTER DB close would now fail this test.

**Drain timeout**: each `_evict` has a 10s per-entry timeout
(cancel-on-stuck). `shutdown_drain` runs evicts in parallel via
`asyncio.gather(..., return_exceptions=True)`, bounding total drain time at
~10s regardless of pool size. Locked by
`tests/test_mcp_pool.py::test_drain_timeout_handles_stuck_worker` (a stuck
`disconnect` sleeping 30s is bounded by `_evict`'s 10s timeout; the test
passes empirically in ~10s per `--durations=10`).

## §9. Cross-references

- **Project-wide conventions** (`trust-the-runtime`,
  `canonical-import + convenience-re-export`,
  `structural-Protocol-satisfaction`, `verbatim-message-equality`): see
  `the_one/agents.md`'s "Project Conventions" section. Each pattern has a
  one-paragraph description, one or two live-code examples with file/symbol
  references, and a counter-example showing what NOT to do.
- **F2 (MCP Client Foundation) contracts**: see `CLAUDE.md`'s "F2 (MCP
  Client Foundation) Contracts" section for the SDK pin, protocol revision,
  and pool-compat surface.
- **F3 sandbox boundary catalog** (catalog messages 1-3 verbatim text): see
  `CLAUDE.md`'s "F3 (MCP Sandbox) Contracts" section, contract #5.
- **Cross-task anyio guard mechanism** (the `CancelScope.__aexit__` guard
  at the SDK + anyio layer): see flight 04 design `§2-detail` at
  `missions/07-mcp-integration/flights/04-idle-ttl-lifecycle/flight.md`.
- **L1a scope-reduction deviation** (transport modules left as
  `@asynccontextmanager`): see flight 04 flight-log entry "L1a runtime
  deviation — transport-API scope reduced (2026-05-07)".
- **F4 lifespan-ordering contract** (PTY → MCP → DB): see flight 04 flight
  design §12 (lifespan integration) and the L4 spy test cited in §8 above.
