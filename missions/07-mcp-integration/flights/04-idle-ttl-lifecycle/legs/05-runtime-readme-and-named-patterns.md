# Leg: 05-runtime-readme-and-named-patterns

**Status**: completed
**Flight**: [Idle-TTL Lifecycle](../flight.md)

## Objective

Write `the_one/mcp/README.md` — a ~300-450 line runtime-invariants document covering 9 sections that capture what F2/F3/F4 jointly establish (test-seam pattern, F4-pool-compat invariants, AsyncExitStack pattern, `_DEFAULT` sentinel rationale, `_PINNED_PROTOCOL_VERSION` read-at-call-time invariant, env-var assembly contract, sandbox-wrap composition, F4 pool semantics, cross-references to project conventions). Add the four named patterns from F3 debrief to `the_one/agents.md` under a new "Project conventions" section (`trust-the-runtime`, `canonical-import + convenience-re-export`, `structural-Protocol-satisfaction`, `verbatim-message-equality`). Add a `### the_one/mcp/` Module Map pointer to `agents.md`. Update `CLAUDE.md` to cross-reference both. **Doc-only leg — zero source-code changes; zero new tests.**

## Context

### Flight design decisions

- **§13 (documentation)**: README is L5; covers the runtime invariants F2/F3/F4 jointly establish. Scope is ~300-450 lines, 9 substantive sections.
- **§13 (destination)**: per Architect cycle-1, the four named patterns are project-wide conventions and belong in `the_one/agents.md`, NOT in `the_one/mcp/README.md`. The README cross-links to `agents.md` for project-wide patterns; `agents.md` cross-links to the README for mcp-internal invariants.
- **§13 (`_DEFAULT` sentinel rationale)**: explicitly DOCUMENT, do NOT refactor to `None`-with-default. The sentinel pattern is locked by this README and the F2 design decision; future maintainers should not "clean it up".

### Carries forward

- F2 debrief Recommendation #2 (`the_one/mcp/README.md` missing) — addressed in this leg.
- F2 debrief technical #1 (`_DEFAULT = object()` sentinel un-documented) — addressed via README §`_DEFAULT` sentinel rationale.
- F3 debrief documentation gap #1 (`the_one/agents.md` missing `### the_one/mcp/` section pointer) — addressed in this leg.
- F3 debrief Key Learnings recommending the four named patterns be canonicalised — addressed via the `agents.md` Project Conventions section.
- L1a's AsyncExitStack refactor + cross-task safety net — documented in README §3.
- L1b's argv reorder (A03 RESOLVED) + L2's bwrap stderr translation (A02 RESOLVED) — documented in README §7 (sandbox-wrap composition, post-L2 status). The CLAUDE.md F3 contracts §5 already had its "L4 enforces" language dropped in L2; L5 cross-references the resolved status.
- L3's pool primitives + L4's reaper + lifespan + drain — documented in README §8 (F4 pool semantics).

### Why this leg lands sixth (after L1a, L1b, L2, L3, L4)

L5 documents the live runtime as it stands post-L4. Writing the README before all source changes land would be premature — the document would describe code that doesn't exist yet, or worse, describe code that diverges from what eventually lands. L5 lands AFTER L4 so the README's claims about reaper behavior, lifespan ordering, and drain semantics are anchored on shipped code, not speculation.

## Inputs

What exists before this leg runs:

- `the_one/agents.md` exists (1203 lines as of L5 design 2026-05-07). Has a `## Module Map` section with entries for `config.py`, `encryption.py`, `db/repositories.py`, `agent/`, `llm/`, `tools/`, `interfaces/`. **No `### the_one/mcp/` entry.** Has a `## Key Patterns` section (line 182) with various sub-patterns. **No "Project Conventions" section yet.**
- `CLAUDE.md` exists (421 lines). Has F3 contracts §5 already updated by L2 (drop "L4 enforces" language; embed `bwrap stderr:` snippet in catalog #2 message). **No reference to `the_one/mcp/README.md` yet** (because it doesn't exist).
- `the_one/mcp/` directory contains: `__init__.py` (post-L4: re-exports `MCPClient`, `acquire`, `shutdown_drain`, errors, types); `client.py`; `errors.py`; `types.py`; `transports/{stdio.py, streamable_http.py}`; `_pool.py` (post-L4: full pool + reaper + drain). **No `README.md` yet.**
- L1a + L1b + L2 + L3 + L4 source changes uncommitted in working tree.
- Test counts post-L4: 148 collected (`{59, 14, 13, 9, 17, 14, 22}`); 147 passed + 1 skipped.
- Project conventions (per F3 debrief, to be canonicalised in `agents.md`):
  1. **Trust-the-runtime**: don't validate at the API layer what the runtime will catch with a clear error. Example: F3's `BubblewrapSandbox.prepare_spawn` doesn't pre-validate `writable_paths` for existence — bwrap fails at exec time with `Can't find source path`, which L2 translates to a clean `MCPSandboxError` catalog #1.
  2. **Canonical-import + convenience-re-export**: each symbol has ONE canonical import path; lower-level packages re-export for convenience but the canonical path is authoritative. Example: `MCPSandboxError` is canonical at `the_one.mcp.errors`; `the_one.platform.sandbox.__init__` re-exports for convenience but the canonical import is `from the_one.mcp.errors import MCPSandboxError`.
  3. **Structural-Protocol-satisfaction**: classes structurally satisfy `runtime_checkable` Protocols WITHOUT inheriting from them. Example: `BubblewrapSandbox` structurally satisfies `MCPSandbox` Protocol but does NOT inherit from it.
  4. **Verbatim-message-equality**: error messages are tested via verbatim string equality, not regex or substring. Example: F3 §6 catalog messages are checked via `assert str(exc) == expected` (or substring `in str(exc)` when interpolation is involved).

## Outputs

What exists after this leg completes:

- **`the_one/mcp/README.md`** (new, ~300-450 lines, 9 sections):

  1. **Test-seam pattern** (~25 lines) — `_test_http_client_override` pattern from `transports/streamable_http.py`. Future seams follow the 3-property contract: underscore prefix, `__all__` exclusion, `# TEST-ONLY` tag. Co-locate with the seam declaration.
  2. **F4-pool-compat invariants** (~40 lines) — `is_alive`, `last_activity`, idempotent disconnect, `_capabilities`/`_protocol_version` preserved across disconnect. Co-locate the test names that lock each invariant. Reference L1a's stake-test probe in `tests/test_mcp_client.py::TestAsyncExitStackContract`.
  3. **AsyncExitStack pattern + worker-task pattern** (~50 lines) — why nested `async with` doesn't compose with anyio task-group-managed CMs (cross-task cancel-scope guard); the F4 worker-task-per-entry solution; the L1a single-task vs cross-task contract distinction; the deliberate scope-reduction deviation that left the transport modules as `@asynccontextmanager` (per the L1a runtime decision documented in flight log).
  4. **`_DEFAULT = object()` sentinel rationale** (~20 lines) — per F2 debrief technical #1. **EXPLICITLY DOCUMENT, do NOT refactor to `None`-with-default** — the sentinel pattern is locked by this README and the F2 design decision; future maintainers should not "clean it up".
  5. **`_PINNED_PROTOCOL_VERSION` read-at-call-time invariant** (~20 lines) — the lazy-import pattern in `MCPClient.connect()` that keeps `monkeypatch.setattr(the_one.mcp, "_PINNED_PROTOCOL_VERSION", ...)` working in tests; why module-level `from the_one.mcp import _PINNED_PROTOCOL_VERSION` would break this.
  6. **2-layer flat-merge env-var assembly contract** (~30 lines) — allowlist + operator kv with secrets winning. References `transports/stdio.py::build_stdio_environ` and `transports/streamable_http.py::build_request_headers` (the headers parallel).
  7. **Sandbox-wrap composition (F3 + post-L2)** (~40 lines) — strict-by-default profile, double-flag bypass (`THE_ONE_SANDBOX_DISABLED=1 AND THE_ONE_TEST_MODE=1`), A02 RESOLVED status (post-L2 update — the bwrap stderr capture + translation lives in `connect_stdio`), A03 RESOLVED status (post-L1b — `--tmpfs /tmp` precedes `--bind PATH PATH`). Cross-link to CLAUDE.md F3 contracts §5.
  8. **F4 pool semantics** (~50 lines) — per-`(agent, source)` keying, lazy demand-paged spawn via the worker-task-per-entry pattern, idle-TTL reap with worker-task ownership, lifespan drain ordering (PTY → MCP → DB close), no hard pool size cap (idle TTL only) + observed-pathological-case watch list. Cross-link to the L4 leg's lifespan-order spy test as the lock against future regression.
  9. **Cross-references to project conventions** (~25 lines) — pointer to `the_one/agents.md`'s "Project Conventions" section for the four named patterns; pointer to `CLAUDE.md` F3 contracts §5 for the sandbox boundary catalog; pointer to flight 04 design `§2-detail` for the cross-task anyio guard mechanism.

- **`the_one/agents.md`** updated:
  - **New section: `## Project Conventions`** (placed BEFORE `## Dependency Graph` so it lands within the conceptual organisation alongside `## Key Patterns`). ~80-100 lines covering the four named patterns:
    - **`trust-the-runtime`** — don't pre-validate what the runtime will catch with a clear error. Example: bwrap's "Can't find source path" + L2's catalog #1 translation. Counter-example: pre-validating `writable_paths` existence at the API layer would duplicate the runtime's check AND introduce a TOCTOU window.
    - **`canonical-import + convenience-re-export`** — each symbol has ONE canonical path; lower-level packages re-export for convenience. Authoritative path is the canonical one. Example: `MCPSandboxError` canonical at `the_one.mcp.errors`; `the_one.platform.sandbox.__init__` re-exports for convenience.
    - **`structural-Protocol-satisfaction`** — classes structurally satisfy `runtime_checkable` Protocols WITHOUT inheriting from them. Decouples implementation from the abstract contract; allows multiple unrelated classes to satisfy the same Protocol. Example: `BubblewrapSandbox` ↔ `MCPSandbox`.
    - **`verbatim-message-equality`** — error messages tested via verbatim string equality. Substring `in str(exc)` is acceptable when the message includes interpolated values; full-string regex is overkill and brittle. Example: F3 §6 catalog messages.
  - **New Module Map entry: `### the_one/mcp/`** (placed alphabetically among existing entries). Contents: brief description of `__init__.py`'s public surface (constants + classes + `acquire` + `shutdown_drain`); `client.py::MCPClient` lifecycle; `errors.py` hierarchy; `types.py` (MCPTool, MCPToolResult); `transports/` (stdio + streamable-http); `_pool.py` (per-(agent, source) worker-task pool — see `the_one/mcp/README.md` for runtime invariants).
  - The existing `### the_one/tools/` and `### the_one/interfaces/` entries are NOT modified.

- **`CLAUDE.md`** updated:
  - Add a one-line cross-reference to `the_one/mcp/README.md` in the F3 contracts section header (or wherever section §5 lives) — "see `the_one/mcp/README.md` for the post-L4 sandbox-wrap composition + pool semantics."
  - Add a one-line cross-reference to `the_one/agents.md`'s new "Project Conventions" section near the top (alongside the existing "see agents.md for architecture" pointers).
  - The two F3 contracts §5 wording fixes from L2 are already landed; L5 does NOT re-modify them.

- **`tests/`** — UNCHANGED. No new tests; no test modifications.

- **Source code** — UNCHANGED. No `the_one/` source files modified.

- **Flight log** — append Leg Progress entry with: (a) README final line count; (b) `agents.md` line-count delta (from 1203 → ~1290); (c) confirmation that source surface is bit-identical to L4-end via `git diff <l4-end-sha> -- the_one/ tests/` returning empty.

## Acceptance Criteria

- [ ] `the_one/mcp/README.md` exists at 300-500 lines (the leg estimates 300-450; reviewers may exceed by ~50 if individual sections grow during writing — under 300 is the only divert per flight Adaptation Criteria).
- [ ] All 9 README sections per §Outputs are present, in order.
- [ ] README §4 explicitly states "DO NOT refactor to None-with-default" for `_DEFAULT`.
- [ ] README §7 reflects A02 RESOLVED (post-L2) and A03 RESOLVED (post-L1b) status; no "deferred" or "pending" language.
- [ ] README §8 documents the lifespan ordering (PTY → MCP → DB close) and references the L4 lifespan-order spy test.
- [ ] `the_one/agents.md` gains a `## Project Conventions` section before `## Dependency Graph` covering the four named patterns with examples.
- [ ] `the_one/agents.md` gains a `### the_one/mcp/` Module Map entry that cross-links to `the_one/mcp/README.md`.
- [ ] `CLAUDE.md` gains cross-references to both `the_one/mcp/README.md` and `the_one/agents.md`'s "Project Conventions" section.
- [ ] **Source surface is UNCHANGED**. `git diff <l5-start-sha> -- the_one/ tests/` returns empty. Only `the_one/mcp/README.md`, `the_one/agents.md`, `CLAUDE.md`, and the flight log + leg artifact + flight artifact are modified.
- [ ] Cumulative test count UNCHANGED at 148 (`{59, 14, 13, 9, 17, 14, 22}`); 147 passed + 1 skipped (the EPERM probe).
- [ ] `ruff check the_one/mcp/ tests/` clean (lint shouldn't break — no source changes — but verify).
- [ ] Flight log Leg Progress entry added with: README line count, agents.md delta, confirmation of zero source changes.

## Verification Steps

1. **README exists and is in scope**: `wc -l the_one/mcp/README.md` returns 300-500.
2. **README section count**: `grep -c "^## " the_one/mcp/README.md` returns 9 (one `##` heading per section; the document title `# Runtime Invariants` doesn't count because it's `#`).
3. **`_DEFAULT` directive present**: `grep -i "do not refactor.*None-with-default" the_one/mcp/README.md` returns one match in §4.
4. **A02/A03 RESOLVED in §7**: `grep -A 3 "A02 RESOLVED\|A03 RESOLVED" the_one/mcp/README.md` shows post-L2 / post-L1b status statements with no "deferred" or "pending" language.
5. **Lifespan ordering in §8**: `grep -A 3 "PTY.*MCP.*DB\|lifespan order" the_one/mcp/README.md` shows the PTY → MCP → DB sequence and references the L4 spy test.
6. **`agents.md` Project Conventions section**: `grep -B 1 -A 1 "## Project Conventions" the_one/agents.md` shows the new section header.
7. **Four named patterns in `agents.md`**: `grep -c "trust-the-runtime\|canonical-import\|structural-Protocol\|verbatim-message-equality" the_one/agents.md` returns at least 4 (one per pattern; may have more from cross-references).
8. **`### the_one/mcp/` Module Map entry**: `grep -A 1 "^### \`the_one/mcp/\`" the_one/agents.md` shows the new entry.
9. **CLAUDE.md cross-references**: `grep -E "the_one/mcp/README.md|Project Conventions" CLAUDE.md` returns at least two matches.
10. **Zero source changes**: `git diff <l5-start-sha> -- the_one/ tests/ | wc -l` returns 0 (or a small number for newline-only changes; verify no functional changes).
11. **Cumulative regression invariant unchanged**: `docker compose exec the-one pytest tests/test_mcp_client.py tests/test_mcp_integration.py tests/test_mcp_sandbox_integration.py tests/test_mcp_stdio_sandbox.py tests/test_sandbox_bubblewrap.py tests/test_sandbox_contract.py tests/test_mcp_pool.py -q --timeout=60` returns 148 collected, 147 passed + 1 skipped.
12. **Lint clean**: `docker compose exec the-one ruff check the_one/mcp/ tests/` returns 0 exit (no source changes, no new findings).
13. **Flight log updated**: `grep -A 8 "05-runtime-readme" missions/07-mcp-integration/flights/04-idle-ttl-lifecycle/flight-log.md` shows a Leg Progress entry with status `landed`, README line count, agents.md delta, zero-source-changes confirmation.

## Implementation Guidance

1. **Capture L5-start SHA**: `git rev-parse HEAD` and note the value.

2. **Write `the_one/mcp/README.md`**. Structure (each `## ` heading is a numbered §):

   ```markdown
   # MCP runtime invariants

   This document captures the runtime invariants that F2 (MCP client foundation), F3 (sandbox layer), and F4 (idle-TTL pool + lifespan integration) jointly establish. Read this BEFORE modifying anything in `the_one/mcp/` — many of the invariants below are load-bearing for tests AND for the operator's mental model of how MCPs spawn and reap.

   For project-wide conventions (`trust-the-runtime`, `canonical-import + convenience-re-export`, `structural-Protocol-satisfaction`, `verbatim-message-equality`), see `the_one/agents.md`'s "Project Conventions" section.

   For the F3 sandbox boundary catalog (catalog messages 1-3), see `CLAUDE.md`'s F3 contracts §5.

   ## §1. Test-seam pattern

   Each test seam follows a 3-property contract:
     1. Underscore-prefixed name.
     2. Excluded from the module's `__all__`.
     3. `# TEST-ONLY` comment tag immediately above the seam declaration.

   Live example: `the_one/mcp/transports/streamable_http.py:_test_http_client_override`. Test fixtures monkeypatch this attribute to inject an ASGI-transport `httpx.AsyncClient` for in-process FastMCP testing. Production code paths NEVER read or write this attribute outside the function that consumes it.

   Future seams follow the same pattern. Do NOT promote a seam to public by removing the underscore — instead, expose a clean public API that doesn't need the seam.

   ## §2. F4-pool-compat invariants

   `MCPClient` exposes four invariants that the F4 pool depends on:

   - **`is_alive`**: bool. Flips False BEFORE awaiting any close coroutines, so a concurrent reaper-task observes the disconnect-in-progress state correctly.
     - Locked by: `tests/test_mcp_client.py::test_disconnect_idempotent`, `test_disconnect_swallows_close_errors`.

   - **`last_activity`**: float. `0.0` until the first successful operation; updated by `_touch_activity()` on each `connect`/`list_tools`/`call_tool`/warm-pool-acquire.
     - Locked by: `tests/test_mcp_pool.py::test_acquire_warm_reuse_returns_same_client_instance` (asserts `_touch_activity.call_count == 2` after second acquire).

   - **Idempotent disconnect**: `disconnect()` is safe to call on a never-connected client AND safe to call twice. Never raises.
     - Locked by: `tests/test_mcp_client.py::test_disconnect_idempotent` and `test_disconnect_swallows_close_errors`.

   - **State preservation across disconnect**: `_capabilities`, `_protocol_version`, `_last_activity` are NOT cleared on `disconnect`. Once disconnected they're stale but not invalid; the F4 pool's `_clear_for_test` and `_evict` rely on this.

   Cross-task safety net: `MCPClient.disconnect`'s `except Exception: logger.warning(...)` swallow is documented (post-L1a) as a cross-task safety net, NOT a no-op. The real fix for cross-task disconnect is the F4 pool's worker-task pattern (see §3 + §8). The swallow catches anyio's `CancelScope.__aexit__` `RuntimeError` if any caller accidentally invokes `disconnect` on a different task than the one that ran `connect`.

   - Locked by: `tests/test_mcp_client.py::TestAsyncExitStackContract` — five tests verify same-task no-warn, cross-task warns via safety net (with anyio's REAL cross-task guard firing), worker-task pattern no-warn, connect-failure runs aclose, disconnect-idempotent-with-stack.

   ## §3. AsyncExitStack pattern + worker-task pattern

   The MCP SDK's `mcp.client.stdio.stdio_client` and `mcp.shared.session.BaseSession.__aenter__` both wrap their bodies in `anyio.create_task_group()`. anyio's `CancelScope.__aexit__` (verified at `.venv/lib/python3.12/site-packages/anyio/_backends/_asyncio.py:444-458`) raises `RuntimeError("Attempted to exit cancel scope in a different task than it was entered in")` on cross-task `__aexit__`.

   **AsyncExitStack alone does NOT solve cross-task disconnect.** `AsyncExitStack.aclose()` invokes registered exit functions on the calling task — if that task differs from the one that ran the original `__aenter__`, anyio's guard fires regardless of the AsyncExitStack wrapping.

   L1a's refactor accomplished two things:
     1. `MCPClient.connect/disconnect` use a single owned `AsyncExitStack` (cleaner exception handling vs F2's manual `__aenter__`/`__aexit__` calls).
     2. Documented the cross-task safety net swallow as the real cross-task fallback.

   The transport helpers (`connect_stdio`, `connect_streamable_http`) and the `_transport_connect` dispatcher remain `@asynccontextmanager`-decorated, per the **L1a scope-reduction deviation** (see flight 04 flight-log entry). The original L1a design rewrote them to non-CM `(session, stack)` returns; that change was abandoned at implementation time because 9 prior tests directly consumed those helpers as async-CMs. F4 L3's worker-task pattern wraps `MCPClient.connect/disconnect`, NOT the transport helpers, so the transport API shape is opaque to L3.

   The F4 pool's worker-task-per-entry pattern (see §8) is the canonical cross-task-safe solution: each pool entry owns a dedicated `asyncio.Task` that holds connect AND disconnect on the same task. Anyio's guard is satisfied mechanically, NOT by `AsyncExitStack`.

   - Locked by: `tests/test_mcp_client.py::TestAsyncExitStackContract::test_worker_task_pattern_no_safety_net_log` (verifies the worker-task pattern against real anyio task group).

   ## §4. `_DEFAULT = object()` sentinel rationale

   `the_one/mcp/client.py:54` defines `_DEFAULT = object()` as a sentinel for "caller passed nothing" vs "caller explicitly passed None/0". Used by `MCPClient.__init__`'s `timeout_seconds` and `call_timeout_seconds` parameters.

   **DO NOT REFACTOR to `None`-with-default.** The sentinel pattern is locked by this README and the F2 design decision. Refactoring to `None` would:
     1. Break the distinction between "use the runtime default" and "explicitly disable timeout (None means infinite)".
     2. Make test monkeypatching of `the_one.mcp.MCP_DEFAULT_TIMEOUT_SECONDS` ineffective for already-instantiated clients, because the bound default would have been read at `__init__` time.

   The lazy read in `__init__` (`from the_one import mcp as the_one_mcp; if timeout_seconds is _DEFAULT: timeout_seconds = the_one_mcp.MCP_DEFAULT_TIMEOUT_SECONDS`) preserves the read-at-call-time invariant — `monkeypatch.setattr(the_one.mcp, "MCP_DEFAULT_TIMEOUT_SECONDS", 5)` works for clients constructed AFTER the patch.

   ## §5. `_PINNED_PROTOCOL_VERSION` read-at-call-time invariant

   `the_one/mcp/__init__.py` defines `_PINNED_PROTOCOL_VERSION = "2025-11-25"`. `MCPClient.connect()` reads it via:

   ```python
   from the_one import mcp as the_one_mcp
   pinned = the_one_mcp._PINNED_PROTOCOL_VERSION
   ```

   This lazy import + attribute access keeps the read at call time, NOT at module import time. `monkeypatch.setattr(the_one.mcp, "_PINNED_PROTOCOL_VERSION", "...")` works for connects executed AFTER the patch.

   Do NOT refactor to a top-of-file `from the_one.mcp import _PINNED_PROTOCOL_VERSION` — the symbol would be bound at module load and `monkeypatch.setattr` would have no effect, breaking the version-mismatch test.

   ## §6. 2-layer flat-merge env-var assembly contract

   Subprocess environment for stdio MCP servers is assembled in two layers:

     1. **Allowlist**: `the_one.platform.env._ENV_ALLOWLIST` filters the host environ to a fixed 8-key set (`PATH, HOME, USER, LOGNAME, LANG, LC_ALL, TERM, TZ`). Materialized via `_build_subprocess_env()`.
     2. **Operator kv**: `MCPSource.config["env"]` (plaintext at rest) ∪ `MCPSource.secrets` (Fernet-encrypted at rest). Secrets win on collision — over BOTH allowlist and config.env.

   Live implementation: `the_one/mcp/transports/stdio.py::build_stdio_environ`. Streamable-http transport mirrors the pattern for HTTP headers: `build_request_headers` flat-merges `config.headers` and `secrets`. Same shape, different content.

   ## §7. Sandbox-wrap composition (F3 + post-L1b + post-L2)

   F3's `BubblewrapSandbox.prepare_spawn` wraps every locally-spawned stdio MCP server. Strict-by-default profile: `--clearenv` + per-key `--setenv` env-allowlist; `--ro-bind / /` + `--bind PATH PATH` filesystem scope; `--unshare-net` network policy when `network_allowed=False`; `--die-with-parent` process supervision.

   **A03 RESOLVED (post-L1b)**: argv emits `--ro-bind / /` → `--tmpfs /tmp` → `--bind PATH PATH` (post-L1b). Pre-A03 ordering had `--tmpfs /tmp` AFTER the `--bind` loop, which silently shadowed any operator-configured `writable_paths` under `/tmp`. Post-L1b, `/tmp`-scoped writable paths persist correctly.

   **A02 RESOLVED (post-L2)**: bwrap-side post-setup errors (writable-path nonexistent, generic exit-code != 0, EPERM on unshare) are translated to `MCPSandboxError` with F3 §6 catalog messages. Mechanism: `connect_stdio` opens a `tempfile.SpooledTemporaryFile` and passes it as `errlog=` to `stdio_client(...)`. On post-CM failure, the captured stderr is read and pattern-matched against three signatures:
     - `Can't find source path` → catalog #1 (writable_paths nonexistent)
     - `bwrap:` prefix + (`unshare`|`user ns`|`create user namespace`) + (`Operation not permitted`|`EPERM`) → catalog #3 (EPERM on unshare)
     - `bwrap:` prefix + no recognised pattern → catalog #2 (generic bwrap-failure fallback)
     - Captured stderr does NOT start with `bwrap:` → return None; F2's `MCPConnectionError` handles the (post-bwrap-success, child-process-failure) case.

   The `bwrap:` prefix discriminator is the load-bearing test. Locked by `tests/test_mcp_sandbox_integration.py::test_inner_process_failure_does_not_translate_to_sandbox_error`.

   Test-mode bypass: when `THE_ONE_SANDBOX_DISABLED=1 AND THE_ONE_TEST_MODE=1` (the F3 §10 double-flag bypass), the sandbox layer is skipped entirely. NEVER set `THE_ONE_TEST_MODE` in production env.

   See `CLAUDE.md` F3 contracts §5 for the full catalog message text.

   ## §8. F4 pool semantics

   `the_one/mcp/_pool.py` is the per-`(agent_name, source_id)` keyed pool of warm `MCPClient` instances.

   **Per-`(agent, source)` keying** (§F4.1): each (agent, source) pair gets its own `_RegistryEntry`. Per-agent credential overrides "for free" because keys differ — agent A's `tokenA`-overridden process and agent B's `tokenB`-overridden process never collide.

   **Lazy demand-paged spawn — worker-task-per-entry pattern** (§F4.2): `AgentFactory.create()` does NOT spawn MCP processes. Pool entries materialize on first tool dispatch via `pool.acquire(agent_name, source_id)`. Each entry owns a dedicated `asyncio.Task` (the entry worker) that holds connect AND disconnect on the SAME task — anyio's cross-task `CancelScope.__aexit__` guard is satisfied mechanically. The reaper signals via `entry.evict_event`; the worker's `finally:` runs `MCPClient.disconnect()` on its own task.

   **Concurrent-acquire-same-key races to a shared worker**: cycle-2 race-fix invariant — the lock-held branch in `acquire` checks `entry is None`, NOT `entry.client is None`. Concurrent same-key acquires share the worker by waiting on `entry.client_ready`. Worker is the SOLE WRITER of `entry.client` and `entry.failure`; both written BEFORE `entry.client_ready.set()`. Locked by `tests/test_mcp_pool.py::test_concurrent_acquire_same_key_shares_one_worker`.

   **Idle TTL** (§F4.3): default 300s. Configurable via `MCP_POOL_IDLE_TTL_SECONDS` env var. Read at register time per-entry — tests `monkeypatch.setenv` BEFORE `acquire` to control the resolved TTL for new entries; existing entries retain their previously-resolved TTL.

   **No hard pool size cap (v1)** (§F4.4): idle TTL is the only eviction mechanism. Pathological multi-agent fanout is bounded by OS process limit. If observable in practice, a future flight may add an LRU cap.

   **Lifespan ordering** (§F4.12): FastAPI's `lifespan` shutdown branch runs:
     1. Cancel in-flight per-message processing tasks.
     2. `_session_registry_shutdown_drain()` (PTY pool).
     3. `_mcp_pool_shutdown_drain()` (this pool — added in L4).
     4. `close_connection()` (DB).

   MCP pool drains AFTER PTY because PTY may have shell-tool-spawned MCP-aware code in flight; drain BEFORE DB close because drain may need source config from DB (precautionary).

   - Locked by: `tests/test_mcp_pool.py::test_lifespan_order_pty_drain_before_mcp_drain_before_db_close` (spies on the three drain calls and asserts the list is `["pty", "mcp", "db"]`).

   **Drain timeout**: each `_evict` has a 10s per-entry timeout (cancel-on-stuck). `shutdown_drain` runs evicts in parallel via `asyncio.gather(..., return_exceptions=True)`, bounding total drain time at ~10s regardless of pool size. Locked by `test_drain_timeout_handles_stuck_worker`.

   ## §9. Cross-references

   - **Project-wide conventions** (`trust-the-runtime`, `canonical-import + convenience-re-export`, `structural-Protocol-satisfaction`, `verbatim-message-equality`): see `the_one/agents.md`'s "Project Conventions" section.
   - **F3 sandbox boundary catalog** (catalog messages 1-3): see `CLAUDE.md` F3 contracts §5.
   - **Cross-task anyio guard mechanism**: see flight 04 design `§2-detail` at `missions/07-mcp-integration/flights/04-idle-ttl-lifecycle/flight.md`.
   - **L1a scope-reduction deviation** (transport modules unchanged): see flight 04 flight-log §"L1a runtime deviation — transport-API scope reduced (2026-05-07)".
   ```

3. **Update `the_one/agents.md`**:
   - Find a suitable insertion point BEFORE `## Dependency Graph` (currently line 157). Insert a new `## Project Conventions` section. Each pattern gets ~15-25 lines: pattern name, one-paragraph description, one or two live-code examples with file:symbol references, counter-example showing what NOT to do.
   - Find the `## Module Map` section's existing entries (`### the_one/config.py`, `### the_one/encryption.py`, etc.). Insert `### the_one/mcp/` in alphabetical position (between `### the_one/llm/` and `### the_one/tools/`). Contents: brief description per §Outputs.

4. **Update `CLAUDE.md`**:
   - Find F3 contracts §5 (line 332-ish; already updated by L2). Add a one-line cross-reference: `**Post-L4 runtime invariants**: see \`the_one/mcp/README.md\` for the full sandbox-wrap composition + pool semantics.`
   - Find an early section that points readers at `agents.md` (probably the architecture section or "Where to find what" section). Add: `- Project-wide conventions (`trust-the-runtime`, etc.) live in \`the_one/agents.md\`'s "Project Conventions" section.`

5. **Run the regression suite** (sanity check — no source changes, but CI safety):
   ```bash
   docker compose exec the-one pytest tests/test_mcp_client.py tests/test_mcp_integration.py tests/test_mcp_sandbox_integration.py tests/test_mcp_stdio_sandbox.py tests/test_sandbox_bubblewrap.py tests/test_sandbox_contract.py tests/test_mcp_pool.py -q --timeout=60
   ```
   Expect: 148 collected, 147 passed + 1 skipped. Identical to L4-end.

6. **Lint** (sanity):
   ```bash
   docker compose exec the-one ruff check the_one/mcp/ tests/
   ```

7. **Update the flight log** with status `landed`, ISO 8601 UTC timestamps, README final line count, agents.md line-count delta, and confirmation that `git diff <l5-start-sha> -- the_one/ tests/` returns empty (zero source/test changes — doc-only leg).

## Edge Cases

- **README scope creep**: target is 300-450 lines. If a section grows beyond ~50 lines, prune detail rather than add new sections. The 9-section structure is locked.
- **`agents.md` "Project Conventions" placement**: the four named patterns are UNDERSPECIFIED if placed inside an existing section (e.g., `## Key Patterns`). Create a NEW top-level section to make them findable.
- **CLAUDE.md cross-references must not duplicate**: the existing F3 contracts §5 already has substantial content (post-L2 update). The L5 cross-reference is ONE additional line, not a rewrite.
- **No source changes — verify via diff at end**: it's easy to accidentally `# noqa` a docstring or rephrase a comment in a source file while writing the README. Run `git diff <l5-start-sha> -- the_one/ tests/` BEFORE signaling `[HANDOFF:review-needed]` and revert any unintended changes.

## Files Affected

- `the_one/mcp/README.md` (new) — ~300-450 lines, 9 sections.
- `the_one/agents.md` — add `## Project Conventions` section (~80-100 lines) + `### the_one/mcp/` Module Map entry (~10-15 lines). Net delta: ~+90-115 lines.
- `CLAUDE.md` — two one-line cross-references (~+2 lines).
- `missions/07-mcp-integration/flights/04-idle-ttl-lifecycle/flight-log.md` — append Leg Progress entry.
- `missions/07-mcp-integration/flights/04-idle-ttl-lifecycle/flight.md` — check off this leg.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`. Do NOT commit.**

- [ ] All acceptance criteria verified
- [ ] Regression suite green (148 collected; 147 passed + 1 skipped — same as L4-end)
- [ ] Lint clean
- [ ] `git diff <l5-start-sha> -- the_one/ tests/` returns empty (zero source/test changes)
- [ ] Flight log Leg Progress entry added
- [ ] Set this leg's status to `landed`
- [ ] Check off this leg in flight.md
- [ ] Do NOT commit. Do NOT signal `[COMPLETE:leg]`. Signal `[HANDOFF:review-needed]` and stop.

---

## Citation Audit

5 citations verified against current code at leg design time (2026-05-07).

- `the_one/agents.md` (current state, 1203 lines, has `## Module Map` and `## Key Patterns` but NO `## Project Conventions` section and NO `### the_one/mcp/` entry) — **OK** (verified at design 2026-05-07).
- `CLAUDE.md` (current state, 421 lines, F3 contracts §5 at line 332 already updated by L2) — **OK**.
- `the_one/mcp/__init__.py` (post-L4: re-exports `MCPClient`, `acquire`, `shutdown_drain`, errors, types) — **OK**.
- `the_one/mcp/_pool.py` (post-L4: full pool + reaper + `shutdown_drain`) — **OK**.
- `the_one/mcp/transports/streamable_http.py:_test_http_client_override` (the canonical test-seam pattern; lives at line 39) — **OK**.

## Design-review note

Per Flight Director runtime decision: L5 SKIPS the per-leg cycle-1 design review. Rationale: (a) the leg is doc-only — no source code, no tests, no architectural decisions that could mis-execute; (b) prior cycle-1 reviews on L1a/L1b/L2/L3/L4 all caught real bugs in source/test logic, but for a docs-only leg the cost-benefit ratio inverts — at worst the docs are factually wrong or out-of-sync, which the flight-final review at the end will catch; (c) agentic-workflow's max-2-cycle rule applies to design review, not implementation review; the flight-final pass is a separate check that owns this leg's correctness. Documented in flight log under "L5 design + (skip cycle-1 review)" so the methodology choice is transparent at debrief time.
