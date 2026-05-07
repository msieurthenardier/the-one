# Flight Log: Idle-TTL Lifecycle + Per-Source Process Registry

**Flight**: [Idle-TTL Lifecycle](flight.md)

## Summary

Execution started 2026-05-06. Phase 1 + 1b context-gathering and Phase 5b Architect review complete. Flight transitioned to `in-flight`. Branch `flight/04-idle-ttl-lifecycle` already exists and is clean. Orchestrator (Flight Director) is driving leg cycle for L1a → L1b → L2 → L3 → L4 → L5 (autonomous), then a single review + commit, then L6 HAT (interactive).

---

## Phase 1b Reconnaissance Report

F4 sources work items from THREE prior artifacts: Mission 07 Known Issues, F2 flight debrief, F3 flight debrief. All cited items walked against current code.

### Reconnaissance Table

| # | Item | Source | Classification | Evidence | Recommendation |
|---|------|--------|----------------|----------|----------------|
| 1 | A01 — disconnect raises `RuntimeError: generator didn't stop`; AsyncExitStack refactor needed | Mission Known Issues + F2 debrief Rec #1 | `confirmed-live` | `the_one/mcp/client.py::disconnect` lines 255-257 (`except Exception: logger.warning(...)` swallow); `the_one/mcp/transports/stdio.py::connect_stdio` lines 187-190 use nested `async with`, NOT `AsyncExitStack`; same in `streamable_http.py` | F4 L1 — fix BEFORE pool work; the swallow amplifies under pool eviction races |
| 2 | A02 — bwrap-side post-setup errors not translated to `MCPSandboxError` | F3 debrief Action Items + flight log Anomaly A02 | `confirmed-live` | `connect_stdio` does NOT inspect bwrap stderr/exit code; `client.py:255-257` catch-all swallows transport-side failures; `stdio.py:52-53` module docstring documents the gap; L5a Test #6 (`test_sandbox_writable_paths_nonexistent_raises_at_connect`) actively pins `MCPConnectionError` not `MCPSandboxError` | F4 — bundle stderr-scraping translation in the AsyncExitStack-refactored `connect_stdio` |
| 3 | A03 — bwrap argv emits `--bind` before `--tmpfs /tmp`; `writable_paths` under `/tmp` silently shadowed | F3 debrief Action Items + flight log Anomaly A03 | `confirmed-live` | `the_one/platform/sandbox/bubblewrap.py::prepare_spawn` lines 108-112: `bwrap_args.extend(["--bind", path, path])` loop precedes `bwrap_args.extend(["--tmpfs", "/tmp"])` | F4 — single-block argv reorder + update L3's `tests/test_sandbox_bubblewrap.py` argv-ordering tests |
| 4 | `mcp_fixture_sandbox_profile` dead code | F3 debrief technical debt #3 | `confirmed-live` | `tests/conftest.py::mcp_fixture_sandbox_profile` exists; `grep` of the rest of `tests/` finds zero callers | F4 — find consumer (likely the new pool integration tests) or delete |
| 5 | L5a Test #6 expectation must flip when A02 lands | F3 debrief Action Items | `confirmed-live` (lock) | `tests/test_mcp_sandbox_integration.py::test_sandbox_writable_paths_nonexistent_raises_at_connect` currently asserts `MCPConnectionError`; once A02 lands, must flip to `MCPSandboxError` | F4 — flip alongside A02 fix |
| 6 | `the_one/mcp/README.md` missing | F2 debrief Rec #2 (carried; explicitly removed from F3 scope per Architect feedback) | `confirmed-live` | `ls the_one/mcp/README.md` returns no file. F3 expanded the runtime invariants surface (sandbox layer); the README is more useful now than at F3 design time | F4 — write the README; scope to runtime invariants (test-seam pattern, F4-pool-compat invariants, AsyncExitStack pattern post-refactor, `_DEFAULT` sentinel rationale, env-var assembly contract, sandbox-wrap composition) |
| 7 | `UrlElicitationRequiredError` propagation test for `list_tools` missing | F2 debrief Action Items | `confirmed-live` (low) | `client.py:302-303` re-raises `UrlElicitationRequiredError` but `tests/test_mcp_*.py` test classes only exercise the call_tool re-raise branch | Defer to routine maintenance — NOT F4-blocking; orthogonal to lifecycle work |
| 8 | `App.adminFormHelpers` cross-namespace consumption | F2 debrief Action Items | `confirmed-live` | 6 call sites in `static/js/areas/studio/mcp-server-editor.js` (per F2 debrief lines 76, 149) | F8 territory — defer |
| 9 | `admin-` CSS class prefixes in studio markup | F2 debrief Action Items | `confirmed-live` | 24 + 4 occurrences across mcp-server-editor.js + mcp-servers-grid.js | Routine maintenance — defer |
| 10 | `_DEFAULT = object()` sentinel pattern un-documented | F2 debrief technical #1 | `confirmed-live` | `client.py:54` defines `_DEFAULT`; not documented in any README | Will be addressed by item #6 (README write) |

### Open Questions (Mission-level — to resolve at F4 design)

These are mission Open Questions whose resolution Mission §Open Questions assigns to F4:

- **Q-OPEN-1: Unit-of-warming for the local-MCP process registry** — per-`(agent, source)` (per-agent isolation; multiplies process count by agent count for shared sources) OR per-`source` (one warm process per registered MCP source, shared across agents) OR hybrid (per-source-when-no-override; per-`(agent, source)` when an override forces a per-agent process)? The override case forces per-agent processes regardless. The pty pattern from M05 F4 doesn't answer this — pty sessions are inherently per-agent. **Resolution required at F4 design.**
- **Q-OPEN-2: Connection lifecycle binding** — connect to attached MCP servers eagerly at `AgentFactory.create()` time (slow agent build but immediate tool availability), OR lazily on first tool call (fast build, first-call latency surprises the LLM), OR maintain a warm-pool with parallel connection-during-build? **Resolution required at F4 design.**

### Action Items NOT Carried Into F4 (with justification)

| Item | Reason |
|------|--------|
| F2 `_test_http_client_override` watch-list note | F5 (OAuth) territory; not F4 |
| `UrlElicitationRequiredError` propagation test for `list_tools` | Routine-maintenance scope; orthogonal to lifecycle |
| `App.adminFormHelpers` rename / shared module | F8 territory; not F4 |
| `admin-` CSS prefix migration | Routine maintenance; not F4 |
| Install affordance gap (operator-owned pip install) | Mission-debrief candidate; not F4 |

These are flagged for follow-up channels but explicitly NOT pulled into F4's scope.

---

## Phase 5b Architect Design Review

### Cycle 1 — overall assessment: **needs rework**

Architect raised 1 high + 6 medium + 3 low + suggestions + 6 questions.

**High-severity issue (load-bearing)**:
- `AsyncExitStack` alone does NOT solve the F2 "RuntimeError: generator didn't stop" issue under F4's pool-driven eviction. The SDK's `mcp.client.stdio.stdio_client` and `mcp.shared.session.BaseSession.__aenter__` both internally enter `anyio.create_task_group()`. anyio's `CancelScope.__aexit__` (`.venv/lib/python3.12/site-packages/anyio/_backends/_asyncio.py:454-458`) raises `RuntimeError("Attempted to exit cancel scope in a different task...")` on cross-task `__aexit__`. The PTY pool sidesteps this because `PtySession.close()` uses `loop.run_in_executor` (worker thread); F4 cannot — MCP session-level operations must run on the original task. **Resolution**: redesigned §2 + §5 + §11 to use worker-task-per-entry pattern. Each pool entry owns a dedicated `asyncio.Task` that holds connect AND disconnect on the same task. Reaper signals via `asyncio.Event`; worker's `finally` runs disconnect on its own task. Anyio guard satisfied mechanically.

**Medium-severity issues addressed inline**:
- §6 mechanism (a) `--info-fd` writes only on success per bwrap manpage — drops it. Mechanism (b) shell wrapper breaks `--die-with-parent` — drops it. **New mechanism**: SDK's `stdio_client(server, errlog=...)` parameter (verified at `mcp/client/stdio/__init__.py:127, 254`). Capture stderr post-exit via `os.pipe()`-backed file or `tempfile.SpooledTemporaryFile`; parse via committed regex patterns.
- L1 blast radius — pre-split to L1a (AsyncExitStack worker-task pattern) + L1b (A03 argv reorder + test updates). Different files, different concerns.
- Test count estimate +30-40 → reconciled to +25-35 (per-leg sum: L1a ~5-7 + L1b ~3-4 + L2 ~3 new + 1 flipped + L3 ~7-9 + L4 ~8-10 = ~26-33).
- L5 README scope ~200-300 → bumped to 300-450 lines (9 sections at 25-50 lines each).
- §13 `_DEFAULT` sentinel rationale → added explicit "DOCUMENT, do NOT refactor" directive.

**Low-severity issues addressed inline**:
- §11 public API name — kept `acquire` as the canonical name (project-wide MCP namespace via `the_one.mcp.acquire`), but documented that consumers MUST import from `the_one.mcp` (the public re-export), NOT from `the_one.mcp._pool` (underscore-private internal module).
- §10 / L6 step 4 timing — fixed: TTL must be set BEFORE register; wait must be `idle_ttl + reaper_interval` (40s) OR direct `_reap_once()` call.
- §3 env-var resolution — committed to register-time only (mirrors PTY pool); dropped the contradictory "process start" wording.

**Suggestions applied inline**:
- L1a stake-test probe explicitly verifies same-task vs cross-task contract.
- L4 lifespan-order spy test added (in-flight cancel → PTY drain → MCP drain → DB close).
- L1b updated to lock three-way ordering (`--ro-bind` → `--tmpfs` → `--bind`), not just two-way.
- `mcp_fixture_sandbox_profile` consumed in L3 explicitly (resolves F3 dead-code flag in this leg, not L4).
- L1a swallow disposition — KEPT as cross-task safety net, comment renamed to reflect its real purpose.

**Architect questions resolved in spec**:
- Q1 (cross-task disconnect): worker-task pattern — disconnect runs on same task as connect. Documented in §2 + §2-detail.
- Q2 (AsyncExitStack empirical verification): L1a stake-test probe runs at design time AND lands as a regression test.
- Q3 (§6 L2 design authority): minor pattern adjustments inline; major drop escalates per Adaptation Criteria.
- Q4 (named-patterns destination): `the_one/agents.md` (project-wide); README cross-links. Locked in §13 + L5.
- Q5 (`_pool.py` underscore vs public): underscore-private module; public API at `the_one.mcp.acquire` via re-export. Documented in §11.
- Q6 (L2 mechanism probe as committed script): yes, leg artifact captures the probe as a reusable stake-test.

**Cycle 1 disposition**: substantial rework; cycle-2 verification required to confirm no new high-severity issues introduced by the redesign.

### Cycle 2 — verification: **approve with changes** (1 NEW high; 2 med/low)

Architect verified all 10 cycle-1 fixes resolved correctly. SDK signatures cross-verified at the source: `stdio_client(server, errlog: TextIO = sys.stderr)` at `mcp/client/stdio/__init__.py:106`, `BaseSession.__aenter__` opens `anyio.create_task_group()` at `mcp/shared/session.py:222`, anyio cross-task `RuntimeError` at `anyio/_backends/_asyncio.py:444-458`. Worker-task pattern correctly addresses the cross-task constraint.

**1 NEW HIGH introduced by the cycle-1 rework**:
- §2 acquire pseudo-code had a duplicate-spawn race: `if entry is not None and entry.client is not None and entry.client.is_alive` falls through when entry exists but worker is still inside `connect()`, contradicting the stated invariant ("only one worker is ever created per key"). **Fix applied**: lock-held branch now checks `entry is None`, not `entry.client is None`. If entry exists in any state, `acquire` waits on `entry.client_ready` outside the lock. `_RegistryEntry` shape revised to hold `client`/`failure` directly (worker is the sole writer; written BEFORE `client_ready.set()`).

**Cycle-2 medium fixes applied**:
- `_load_source(source_id)` is now hoisted OUTSIDE `_lock` (lock no longer serializes acquires across different keys on F1-repository read).
- `_evict(key)` helper extracted per §2; explicitly awaits `entry.worker` after setting `evict_event` so `shutdown_drain` honours its "all entries drained before return" contract. 10s timeout + cancel-suppress on stuck workers.

**Cycle-2 low fixes applied**:
- §6 `errlog=` mechanism switched from "os.pipe()-backed file or SpooledTemporaryFile" → "SpooledTemporaryFile(mode='w+')" (matches `TextIO` directly; no `os.fdopen` dance).
- Acquire-cancellation behavior now explicitly documented: caller cancel mid-await → worker keeps running → entry reaps on idle TTL → no leak.

**Cycle-2 disposition**: rework correctly resolves all 10 cycle-1 issues; the 1 cycle-2 high (duplicate-spawn race in §2 pseudo-code) is fixed in the same edit pass; cycle-2 medium/low are absorbed inline. **No cycle-3 required** — the corrected pseudo-code is mechanically sound (entry-existence check is the atomic dispatch; `client_ready` is the single rendezvous Event for all waiters).

---

## Leg Progress

> Populated as legs land.

### L1a-async-exit-stack-and-cross-task-safety — landed

- **Status**: `landed` (flight-final commit will transition to `completed`)
- **Started (UTC)**: 2026-05-07
- **Completed (UTC)**: 2026-05-07
- **Pre-edit SHA**: `4ad63611008abcdbf3154e52c3209f3f413c7a44`

#### Changes Made

- `the_one/mcp/client.py`:
  - Import on line 18 extended: `from contextlib import AsyncExitStack, asynccontextmanager`.
  - `MCPClient.__init__`: `self._transport_cm: Any = None` → `self._transport_stack: AsyncExitStack | None = None`.
  - `MCPClient.connect()`: replaced `self._transport_cm = _transport_connect(self.source); session = await self._transport_cm.__aenter__()` with `self._transport_stack = await AsyncExitStack().__aenter__(); session = await self._transport_stack.enter_async_context(_transport_connect(self.source))`.
  - `MCPClient._cleanup_after_failed_connect()`: `await self._transport_cm.__aexit__(None, None, None)` → `await self._transport_stack.aclose()` (best-effort, with the existing `try/except → logger.debug` pattern).
  - `MCPClient.disconnect()`: `await self._transport_cm.__aexit__(None, None, None)` → `await self._transport_stack.aclose()`. Comment on the existing `except Exception: logger.warning(...)` swallow renamed from F2 noise reference to "Cross-task safety net — the real fix for cross-task disconnect is the F4 pool's worker-task pattern, NOT AsyncExitStack..." with explicit pointer to flight 04 §2-detail and L3's `_pool._entry_worker`.
  - Dead `yield  # type: ignore[unreachable]  # noqa: F821` at line 88 preserved unchanged.
- `the_one/mcp/transports/stdio.py` — **bit-identical** to pre-edit SHA (scope-reduction deviation; verified via `git diff <pre-edit-sha> -- ...` returning zero lines).
- `the_one/mcp/transports/streamable_http.py` — **bit-identical** to pre-edit SHA (scope-reduction deviation; verified).
- `the_one/mcp/client.py::_transport_connect` (the dispatcher) — **functionally unchanged** (only edits in `client.py` are to `MCPClient.__init__/connect/_cleanup_after_failed_connect/disconnect`; the dispatcher body and dead-yield are untouched).
- `tests/test_mcp_client.py`:
  - New module-scope helper `_anyio_backed_transport_cm` (immediately after `_mock_transport_cm`) that wraps its body in a real `anyio.create_task_group()` so cross-task `__aexit__` trips anyio's `CancelScope` guard for real (vs simulating it via a string-equal `RuntimeError`).
  - New `TestAsyncExitStackContract` class inserted right after `TestMCPClientLifecycle` (per leg artifact §6 placement). Class docstring is the stake-test probe comment block enumerating the four observable invariants and naming the test method that locks each (per F2 debrief KL #1, AC #11).
  - 5 new tests (no optional `/proc` test added — the leg lists it as optional and the cross-task probe is the load-bearing observability already; per leg §Outputs the optional test was an "if there's time" adjacency).
  - Imports extended: added `logging`, `AsyncExitStack`, and `unittest.mock.patch`.

#### Test counts (per-file)

| File | Before | After | Δ |
|------|--------|-------|---|
| `tests/test_mcp_client.py` | 54 | 59 | +5 |
| `tests/test_mcp_integration.py` | 14 | 14 | 0 |
| `tests/test_mcp_sandbox_integration.py` | 10 | 10 | 0 |
| `tests/test_mcp_stdio_sandbox.py` | 9 | 9 | 0 |
| `tests/test_sandbox_bubblewrap.py` | 16 | 16 | 0 |
| `tests/test_sandbox_contract.py` | 14 | 14 | 0 |
| **Total** | **117** | **122** | **+5** |

Final `pytest ... -q --timeout=30` returned `122 passed in 7.98s`. Zero regressions.

#### Notes

- **(a) Cross-task probe behavior — observed anyio error message**: `RuntimeError("Attempted to exit cancel scope in a different task than it was entered in")` raised from `anyio/_backends/_asyncio.py:455` during `await self._transport_stack.aclose()` → `AsyncExitStack.__aexit__` → `_anyio_backed_transport_cm` generator finally → `anyio.create_task_group().__aexit__` → `CancelScope.__exit__`. Captured in `WARNING the_one.mcp.client:client.py:269 MCPClient transport close failed` log line + traceback (verified live via `pytest --log-cli-level=WARNING` in Verification Step 8). L2 may use the regex `r"Attempted to exit cancel scope in a different task"` if it ever needs to baseline this string.
- **(b) L2 stderr-capture seam (`stdio_client(server, errlog=...)` parameter)**: trivially still reachable from `connect_stdio` because `the_one/mcp/transports/stdio.py` is bit-identical to the pre-edit SHA — the existing `@asynccontextmanager` body still owns the `stdio_client(...)` call and L2 will plumb `errlog=tempfile.SpooledTemporaryFile(...)` into that call site without touching the public CM contract.
- **(c) Per-test invariant mapping (per AC #11)**:
  - Invariant 1 (same-task no-warn): `test_same_task_disconnect_no_safety_net_log`
  - Invariant 2 (cross-task warns via safety net, real anyio guard): `test_cross_task_disconnect_logs_via_safety_net`
  - Invariant 3 (worker-task pattern no-warn, real anyio guard): `test_worker_task_pattern_no_safety_net_log`
  - Invariant 4 (aclose runs on connect-failure + disconnect idempotency 4-scenario): `test_connect_failure_runs_stack_aclose`, `test_disconnect_idempotent_with_stack`
- **(d) Deviations from the revised leg artifact**:
  - `test_connect_failure_runs_stack_aclose` and `test_disconnect_idempotent_with_stack` (sub-scenario d) use `ValueError("init failed")`/`ValueError("bad init")` for the failing `session.initialize` mock instead of the leg's suggested `RuntimeError("init failed")`. Reason: `MCPClient.connect()` has an explicit `except RuntimeError as e:` branch that translates ALL RuntimeErrors as `MCPVersionMismatch` via the unsupported-version regex (the regex falls back to `str(e)` if it doesn't match, so `RuntimeError("init failed")` becomes `MCPVersionMismatch(observed="init failed")` — NOT `MCPConnectionError`). `ValueError` is not caught by that branch and falls through to the catch-all that wraps as `MCPConnectionError`, which is what the test asserts. Behaviorally equivalent: the load-bearing observation (`_transport_stack` reset, `_session` cleared, `is_alive` False, `aclose` spy fired) is unaffected by the choice of exception class.
  - Optional `test_subprocess_cleanup_via_proc_inspection` was NOT added. Leg artifact lists it as optional ("optional in §Outputs"); the 5 required tests all pass and the cross-task probe already exercises the load-bearing anyio-guard observability. Skipping kept the diff narrow.
- **(e) Anomalies**: none beyond the deviation in (d). Lint clean (`ruff check the_one/mcp/ tests/test_mcp_client.py` → `All checks passed!`). Transports + dispatcher confirmed bit-identical to pre-edit SHA via `git diff 4ad63611 -- the_one/mcp/transports/...` (zero lines) and full `git diff 4ad63611 -- the_one/mcp/client.py` inspection (only `MCPClient` methods touched).

---

## Decisions

> Runtime decisions not in original plan. Populated during execution.

---

## Anomalies

> Populated as encountered during execution.

---

## Flight Director Notes

> Populated by the orchestrator during agentic-workflow execution.

### Phase file loaded

- 2026-05-06 — Loaded `the-one/.flightops/agent-crews/leg-execution.md` (project-specific). Crew: Developer (Sonnet) + Reviewer (Haiku); optional Accessibility Reviewer (Sonnet) — N/A for this flight (no UI changes; Settings UI lives in F1/F8). Validation: file has `## Crew`, `## Interaction Protocol`, `## Prompts` sections with all required prompt fenced blocks present.
- 2026-05-06 — Flight transitioned `ready` → `in-flight`. Branch `flight/04-idle-ttl-lifecycle` pre-existed at HEAD with clean working tree (likely created earlier in flight design); no `git checkout -b` needed.
- 2026-05-06 — Leg plan: L1a → L1b → L2 → L3 → L4 → L5 autonomous (per-leg design + design review + implement, NO per-leg commit per agentic-workflow §2c). Single Reviewer pass + commit after L5. L6 is HAT — orchestrator guides human through verification, no autonomous Developer/Reviewer.

### L1a design (cycles 1 + 2)

- 2026-05-06 — L1a leg artifact drafted. Spawned Developer for cycle-1 design review.
- Cycle 1 — **needs rework**. 2 high + 6 medium + 3 low. Highs: cross-task and worker-task tests didn't actually exercise anyio's `CancelScope` guard (mocked just the RuntimeError string). Mediums: `_cleanup_after_failed_connect` mirroring noted; AC #6 git-diff base (main vs leg-start); test-count baseline stale (file has 54 tests, not 30); two-statement stack init readable; missing AC for post-cleanup state. Lows: spy mechanism for `aclose`; redundant optional streamable-http test; import style.
- Resolved cycle-1 inline: introduced `_anyio_backed_transport_cm` helper using real `anyio.create_task_group()`; re-baselined to 115 prior tests; tightened spy to `patch.object(AsyncExitStack, "aclose", autospec=True, wraps=AsyncExitStack.aclose)` with `with` scope; dropped the redundant streamable-http optional test; collapsed init to `await AsyncExitStack().__aenter__()`; merged import to `from contextlib import AsyncExitStack, asynccontextmanager`. Added Edge Cases sections for two-layer architecture (intentional) and SDK version pin. Re-spawned Developer for cycle-2 verification.
- Cycle 2 — **approve with changes**. 1 NEW high + 3 medium + 1 low. New high: AC #4 said "EXACTLY one aclose call" — wrong under the two-layer architecture I documented (dispatcher's inner stack triggers a transitive `aclose`, so spy records `>= 2`). Mediums: class name `TestMCPClientConnect` doesn't exist (correct: `TestMCPClientLifecycle`); `tests/test_sandbox_runtime.py` doesn't exist (correct: `tests/test_sandbox_contract.py`); flight-log status verbiage `completed` vs `landed` mismatch.
- Resolved cycle-2 inline: AC #4 reworded to "spy recorded `>= 1` invocation; load-bearing observation is post-cleanup state"; class reference fixed to `TestMCPClientLifecycle (line 270)`; baseline command's file fixed to `tests/test_sandbox_contract.py`; Verification Step #11 status fixed to `landed`; reconnect-after-disconnect test switched from `id()` comparison to `is not` against live ref. No cycle-3 — agentic-workflow's max-2-cycle rule and the changes are mechanical inline edits, not architectural.
- L1a leg artifact status set to `ready`. Flight Director will spawn Developer (action: implement) next.

### L1a runtime deviation — transport-API scope reduced (2026-05-07)

- 2026-05-07 — First Developer attempts at L1a implementation hit Anthropic API 529 (Overloaded) twice; on the third attempt, the Developer ran the regression baseline, attempted the full leg refactor, and **signaled `[BLOCKED:design-conflict-on-AC#6-and-AC#8]`** before any commit.
- **The design conflict**: the leg's §Outputs lines 54-58 + AC #5/#6/#8 jointly require (a) `connect_stdio` and `connect_streamable_http` change from `@asynccontextmanager` to plain `async def` returning `(session, stack)`, AND (b) "all 115 prior tests pass UNMODIFIED". But 9 prior tests across `tests/test_mcp_stdio_sandbox.py` (8 callers of `connect_stdio` as `async with`) and `tests/test_mcp_client.py::test_production_path_constructs_client_with_assembled_headers` (1 caller of `connect_streamable_http` as `async with`) consume those helpers as async-CMs directly. Both design-review cycles missed this — they verified the leg's 8 cited locations but did NOT walk the test files for direct callers of the public CM-shaped transport functions. **Methodology gap captured for flight debrief: design-review citation audit must include "find direct callers of any public symbol whose signature changes".**
- **Test-count baseline correction**: Developer measured `tests/test_sandbox_bubblewrap.py` at **16 tests**, not the 14 the leg cited. Total prior tests in scope is **117**, not 115. (The leg's stale count traced back to F2/F3 era; F3 added two `tests/test_sandbox_bubblewrap.py` tests post-design.)
- **Resolution chosen by Flight Director (option c-lite from Developer's offered set)**: keep `connect_stdio` and `connect_streamable_http` as `@asynccontextmanager` UNCHANGED. Refactor ONLY `MCPClient` (`__init__`, `connect`, `_cleanup_after_failed_connect`, `disconnect`) to use a single `contextlib.AsyncExitStack` for ownership of the dispatcher CM. The F2 `_transport_connect` dispatcher also stays unchanged. The cross-task safety-net swallow at `client.py::disconnect` stays as documented contract.
- **Why option (c-lite) is correct**: F4 L3's worker-task pattern wraps `MCPClient.connect()` / `MCPClient.disconnect()` (per §2 pseudo-code), NOT the transport helpers directly. So as long as `MCPClient`'s stack is opened and closed on the same task (which the worker-task pattern guarantees by design), cross-task safety holds REGARDLESS of whether transports are CM or non-CM. The leg's original transport-API change was design-elegance, not load-bearing — and at the cost of 9 test-call-site updates that violated AC #6/#8. Option (a) was viable but caused real test churn; option (b) and (c-full) added indirection without benefit. (c-lite) achieves the actual design intent — cleaner exception handling in `MCPClient` + AsyncExitStack ownership — with zero prior-test churn.
- **Trade-off accepted**: the leg's ambition to make transport ownership explicit at the helper level is deferred. If a future leg ever needs non-CM transport access (e.g., a hypothetical F-N where MCPClient itself is bypassed and a caller wants raw transport ownership), that leg will introduce new underscore-private `_open_stdio_transport_stack` / `_open_streamable_http_transport_stack` helpers as a separate API surface — preserving today's CM-shaped public surface for back-compat. No such caller exists today.
- **Leg artifact updates required**: bump prior test count from 115 → 117; bump `tests/test_sandbox_bubblewrap.py` count from 14 → 16; remove transport-API changes from §Outputs (AC #5/#6 collapse); preserve AC #8 strict ("all 117 prior tests pass UNMODIFIED"); remove transport refactor steps from Implementation Guidance (steps 2 and 3); preserve the AsyncExitStack refactor for `MCPClient` (steps 4-9). Test sketches stay (the `_anyio_backed_transport_cm` mock helper exercises `MCPClient`'s stack-based teardown via the dispatcher, which still works because the dispatcher's CM is what `_transport_stack` enters).
- **Pre-edit SHA captured by Developer for the regression-test invariant**: `4ad63611008abcdbf3154e52c3209f3f413c7a44`.
- **Working tree at deviation time**: source files at HEAD (Developer reverted the partial transport refactor); only artifact edits + leg `Status: ready → in-flight → ready` round-trip outstanding.

The Flight Director will now: (1) edit the leg artifact to reflect option (c-lite) and the corrected test counts; (2) re-spawn the Developer with the updated leg. No additional design-review cycle — agentic-workflow's max-2-cycle rule applies to design reviews; this is an implementation-time clarification, not a re-design.

### L1a implementation complete (2026-05-07)

- Developer (third spawn — first two hit API 529) implemented L1a per the revised (post-deviation) artifact. 122 tests passing (117 prior + 5 new). Lint clean. Transport modules + dispatcher zero-diff vs pre-edit SHA `4ad63611008abcdbf3154e52c3209f3f413c7a44`. Leg status `landed`.
- Two minor implementer-discretion deviations (logged here for debrief): (a) `ValueError("init failed")` instead of `RuntimeError("init failed")` for failing-init mocks — the leg's suggested `RuntimeError` would route through `MCPClient.connect()`'s `except RuntimeError → MCPVersionMismatch` branch instead of the catch-all `MCPConnectionError` branch the test asserts; `ValueError` is behaviorally equivalent for the load-bearing observations. (b) Optional `test_subprocess_cleanup_via_proc_inspection` was NOT added — explicitly listed as optional in §Outputs, the 5 required tests cover the four observable invariants. Both are reasonable runtime decisions.
- Cross-task probe verified against real anyio: `RuntimeError("Attempted to exit cancel scope in a different task than it was entered in")` raised from `anyio/_backends/_asyncio.py:455` and caught by the safety-net swallow with `WARNING the_one.mcp.client:client.py:269 MCPClient transport close failed`. The L1a stake-test invariants are mechanically locked.

### L1b design + cycle-1 review (2026-05-07)

- L1b leg artifact drafted. Spawned Developer for cycle-1 design review.
- Cycle 1 — **needs rework**. 1 high + 2 medium/low. High: stale workaround language exists in FOUR docstring locations (not just `agents.md` as the original draft assumed) — `bubblewrap.py` class + method docstrings list the OLD argv order; `tests/test_mcp_sandbox_integration.py` module + `writable_scratch_dir` fixture docstrings carry the "operators must use writable_paths OUTSIDE `/tmp`" caveat. After the reorder lands, all four become factually false. Mediums/lows: AC #4 typo "Total: 124" vs actual sum 123 (self-flagged in Verification Step #4); minor readability on test-count breakdown.
- Resolved cycle-1 inline: extended §Outputs / §Files Affected / §Acceptance Criteria / §Implementation Guidance / §Citation Audit to cover all four docstring updates; renumbered Implementation Guidance steps to insert docstring-update steps 3 + 4 before the argv reorder; explicitly distinguished "test METHODS unmodified" (the load-bearing invariant) from "test FILES unmodified" (the stricter and unnecessary-here invariant); fixed AC #4 typo and removed the self-flagging aside in Verification Step #4. No cycle-2 — leg is mechanically simple, the cycle-1 fixes are inline edits not a re-design, and agentic-workflow's max-2-cycle rule isn't tripped by adding doc updates.
- L1b leg artifact status set to `ready`. Flight Director will spawn Developer (action: implement) next.

### L1b implementation complete (2026-05-07)

- Developer implemented L1b cleanly. 123 tests passing (122 prior + 1 new). Lint clean. Argv reorder + 4 docstring updates landed; `tests/test_sandbox_bubblewrap.py` test methods unmodified (only +1 added). Pre-edit SHA `4ad63611...` (same as L1a-start; flight branches accumulate uncommitted source for batched commit at flight-end). Leg status `landed`.

### L2 design + cycle-1 review (2026-05-07)

- L2 leg artifact drafted. Spawned Developer for cycle-1 design review.
- Cycle 1 — **needs rework**. 2 high + 5 medium/low. Highs: (1) `_translate_bwrap_stderr`'s `exit_code = 1 if stderr_text else None` proxy mistranslated any inner-process failure as `MCPSandboxError("bubblewrap exited with code 1")`, breaking F3 §6 directionality; (2) the EPERM regex `(?:Operation not permitted|EPERM).*?(?:unshare|create user namespace)` was directionally backwards — bwrap's actual format is `<context-with-unshare>: Operation not permitted`, NOT the reverse, so the pattern would never match real bwrap stderr. Mediums: vague `_has_sys_admin()` mechanism, vague Test #6b mechanism, convoluted AC #8 arithmetic, broken pre-edit SHA capture (working tree has L1a + L1b uncommitted), `SpooledTemporaryFile` "in-memory until 1KB" claim wrong on Py3.12 (anyio.open_process forces immediate rollover via .fileno()).
- Resolved cycle-1 inline: introduced `_BWRAP_OWN_PREFIX_RE` discriminator gate so catalog #2/#3 only fire when bwrap's own `bwrap:` prefix is in the captured stderr (catalog #1's "Can't find source path" is exempt — unambiguously a bwrap message). Made `_BWRAP_EPERM_UNSHARE_RE` bidirectional (matches either `unshare ... Operation not permitted` OR `Operation not permitted ... unshare`). Pinned `_has_sys_admin()` to `/proc/self/status` CapEff bit-21 parsing. Pinned Test #6b mechanism to `monkeypatch BubblewrapSandbox.prepare_spawn → inject --no-such-flag-for-test-6b` (the pattern bwrap will reject without matching #1/#3). Replaced AC #8's running arithmetic with a clean baseline-and-target statement. Added Test #6d (cycle-1 reviewer suggestion) locking the directionality contract from the inner-process-failure side. Updated catalog #2 wording to drop the misleading synthetic exit-code interpolation; embed a snippet of the actual bwrap stderr in the `MCPSandboxError` message instead. Captured the L1a + L1b uncommitted-tree caveat for the L2-start SHA capture (use `git diff > /tmp/l2-baseline.diff` instead of `git diff <sha>`). EPERM probe — explicit instruction to use `docker run --rm --user nobody mcr.microsoft.com/playwright/python:v1.58.0-jammy ...` instead of waiving with "documented pattern from manpage"; escalate to user if probe environment is unreachable.
- L2 leg artifact status set to `ready`. Flight Director will spawn Developer (action: implement) next.

### L2 implementation complete (2026-05-07)

- Developer implemented L2 cleanly. 126 tests collected (125 passed + 1 skipped — Test #6c EPERM skipped in dev container as designed). Lint clean. Two architectural deviations the Developer documented: (a) translation in `finally`, not `except`, because `MCPClient.connect()`'s outer except catches `McpError("Connection closed")` BEFORE AsyncExitStack walks back through `connect_stdio`'s `__aexit__(None, None, None)` — Developer used "non-empty buffer = failure signal" because probe-confirmed bwrap writes stderr ONLY on failure; (b) companion change to `_cleanup_after_failed_connect` to propagate `MCPClientError` subclasses (so `MCPSandboxError` reaches the test, not just `MCPConnectionError`). Both reasonable runtime decisions covered by L2 design-authority clauses. Probe captured all three bwrap signatures verbatim (writable-path-nonexistent, generic-flag-rejection, EPERM via `docker run --rm --user nobody ...`); regex extended to also match bwrap 0.6/0.9's `No permissions to create new namespace` wording. Leg status `landed`.

### L3 design + cycle-1 review (2026-05-07)

- L3 leg artifact drafted (the largest leg in the flight: `_pool.py` worker-task pattern + 12 tests). Spawned Developer for cycle-1 design review.
- Cycle 1 — **approve with changes**. 2 high + 5 medium + 4 low. Highs: (1) `_RegistryEntry.worker: asyncio.Task[None]` annotation forbade the temporary `None` value used during `acquire`'s construct-then-assign sequence — flagged by lint; (2) Test #6 (`test_spawn_failure_pop_is_idempotent`) had only ONE failure observer in the original sketch — didn't actually exercise the concurrent idempotent-pop contract under contention. Mediums: test #8 variable-naming (`original_load_source` was misleading post-monkeypatch); class-level `_MockClient._connect_impl = ...` mutation pattern fragile across tests (recommend subclass-per-scenario); test #11 race-comment for `is_alive is False` post-evict; `_clear_for_test` race-window documentation; integration tests #10/#11 lock SYS_ADMIN dependency. Lows: pytest-asyncio mode confirmation; idempotent-`_evict` smoke test missing; reconcile "9-11" vs concrete count.
- Resolved cycle-1 inline: changed `_RegistryEntry.worker` type annotation to `asyncio.Task[None] | None = None`; rewrote test #6 as `asyncio.gather(acquire, acquire, return_exceptions=True)` against `_FailingThenRecoveringClient` to lock concurrent idempotent-pop; refactored test bodies to use subclass-per-scenario pattern (`_SlowClient`, `_VerySlowClient`, `_FailingThenRecoveringClient`) instead of mutating `_MockClient._connect_impl` between tests; renamed spy variable `original_load_source` → `prior_load_source` and tightened assertion to `all(h is False for h in lock_held_during_load)`; added test #12 (`test_evict_idempotent_on_missing_key`); added pytest-asyncio mode pre-flight check to step 5; updated test count from "9-11" to a concrete 12; documented memory-ordering and `_clear_for_test` race-window in source docstrings. No cycle-2 — leg is mechanically refined, not re-designed; agentic-workflow's max-2-cycle rule isn't tripped by inline doc / test-pattern fixes.
- L3 leg artifact status set to `ready`. Flight Director will spawn Developer (action: implement) next.

### L1b-bwrap-argv-reorder-tmpfs-before-bind — landed

- **Status**: `landed` (flight-final commit will transition to `completed`)
- **Started (UTC)**: 2026-05-07
- **Completed (UTC)**: 2026-05-07
- **Pre-edit SHA**: `4ad63611008abcdbf3154e52c3209f3f413c7a44` (same as L1a-start; L1a's source changes are uncommitted in working tree per agentic-workflow batch-commit-at-flight-end policy)

#### Changes Made

- `the_one/platform/sandbox/bubblewrap.py`:
  - Class docstring (lines 36-43 area) — argv-structure listing updated: `--ro-bind / /` → `--tmpfs /tmp` → `--bind PATH PATH` per writable_paths entry → `--proc /proc` → `--dev /dev` (was: `--ro-bind` → `--bind` loop → `--proc` → `--dev` → `--tmpfs`).
  - `prepare_spawn` method docstring (lines 76-82 area) — same listing updated to match.
  - `prepare_spawn` body — moved `bwrap_args.extend(["--tmpfs", "/tmp"])` from after `--dev` to immediately after `--ro-bind / /`. Added 4-line explanatory comment referencing F3 anomaly A03 + the precedence rationale (tmpfs lays /tmp first; --bind layers on top).
- `tests/test_mcp_sandbox_integration.py`:
  - Module docstring (lines 42-46 area) — REMOVED "Edge case... `--bind` BEFORE `--tmpfs /tmp`... operators must use writable_paths OUTSIDE `/tmp`" workaround paragraph; REPLACED with one-line note that post-A03 (F4 L1b), `/tmp`-scoped writable paths persist correctly.
  - `writable_scratch_dir` fixture docstring (lines 131-144 area) — REMOVED "Uses /var/tmp (NOT /tmp) to dodge the L3 argv-compilation edge case..." paragraph; REPLACED with one-line rationale that `/var/tmp` is used for parallel-safe pytest-xdist isolation alongside the unconditional `HOME=/tmp` sandbox override.
  - Test METHODS unmodified (load-bearing invariant; verified — only docstring text changed).
- `tests/test_sandbox_bubblewrap.py`:
  - One new test ADDED: `test_prepare_spawn_argv_three_way_order_ro_bind_tmpfs_bind` (placed between `test_prepare_spawn_with_writable_paths` and `test_prepare_spawn_with_network_allowed`).
  - Asserts `index("--ro-bind") < index("--tmpfs") < index("--bind")` for `SandboxProfile(writable_paths=["/data"])`. Failure-mode message surfaces all three indices and the full argv.
  - Zero existing test methods modified or deleted (verified via `git diff 4ad63611 -- tests/test_sandbox_bubblewrap.py | grep -E '^-[^-]' | wc -l` → 0).

#### Test counts (per-file)

| File | Before | After | Δ |
|------|--------|-------|---|
| `tests/test_mcp_client.py` | 59 | 59 | 0 |
| `tests/test_mcp_integration.py` | 14 | 14 | 0 |
| `tests/test_mcp_sandbox_integration.py` | 10 | 10 | 0 (docstrings only) |
| `tests/test_mcp_stdio_sandbox.py` | 9 | 9 | 0 |
| `tests/test_sandbox_bubblewrap.py` | 16 | 17 | +1 |
| `tests/test_sandbox_contract.py` | 14 | 14 | 0 |
| **Total (post-L1a baseline → post-L1b)** | **122** | **123** | **+1** |

Final `pytest tests/test_sandbox_bubblewrap.py tests/test_sandbox_contract.py tests/test_mcp_stdio_sandbox.py tests/test_mcp_sandbox_integration.py tests/test_mcp_client.py tests/test_mcp_integration.py -q --timeout=30` returned `123 passed in 7.15s`. Zero regressions. New test alone: `pytest tests/test_sandbox_bubblewrap.py::test_prepare_spawn_argv_three_way_order_ro_bind_tmpfs_bind -v --timeout=10` → `1 passed in 0.03s`.

Lines changed in `bubblewrap.py`: 3 source lines moved (`--tmpfs /tmp` extend hoisted up, original deleted) + 4 added comment lines + 4 docstring-listing lines reflowed across the two docstrings.

#### Notes

- **(a) Lint**: `ruff check the_one/platform/sandbox/ tests/test_sandbox_bubblewrap.py` → `All checks passed!`. No new findings vs baseline.
- **(b) No-prior-test-modification verification**: `git diff 4ad63611008abcdbf3154e52c3209f3f413c7a44 -- tests/test_sandbox_bubblewrap.py | grep -E '^-[^-]' | wc -l` returns `0` (only the new test method ADDED; no deletions or modifications of existing tests).
- **(c) Docstring-only changes in `tests/test_mcp_sandbox_integration.py`**: confirmed via diff inspection that only the module docstring (lines 42-46) and `writable_scratch_dir` fixture docstring (lines 131-144) were modified; all 10 test methods are bit-identical to pre-edit content.
- **(d) Deviations from leg artifact**: none. All 9 Implementation Guidance steps executed in order; all 7 Acceptance Criteria met; all 7 Verification Steps green.
- **(e) Anomalies**: none.

### L2-bwrap-error-translation — landed

- **Status**: `landed` (flight-final commit will transition to `completed`)
- **Started (UTC)**: 2026-05-07
- **Completed (UTC)**: 2026-05-07
- **Pre-edit SHA**: `4ad63611008abcdbf3154e52c3209f3f413c7a44` (same as L1a-start / L1b-start; L1a + L1b source changes are uncommitted in working tree per agentic-workflow batch-commit-at-flight-end policy). L2-baseline diff captured at `/tmp/l2-baseline.diff` (689 lines — L1a + L1b artifact + source edits).

#### Stake-test probe results (2026-05-07)

Captured against bwrap inside the dev container (bwrap 0.11.0) for probes (a) and (b); against `docker run --rm mcr.microsoft.com/playwright/python:v1.58.0-jammy` + apt-installed bwrap 0.9.0 + `su nobody` for probe (c). Probe (c) under bwrap 0.6.1 (the playwright image's default apt source) emitted the same wording, indicating the message is bwrap-version-stable across 0.6.x → 0.9.x → 0.11.x.

**Probe (a) — writable_paths nonexistent**:
```
$ bwrap --die-with-parent --unshare-user --unshare-net --clearenv \
    --setenv HOME /tmp --ro-bind / / --tmpfs /tmp \
    --bind /this/path/does/not/exist /this/path/does/not/exist \
    --proc /proc --dev /dev -- /bin/echo hello
bwrap: Can't find source path /this/path/does/not/exist: No such file or directory
exit=1
```

**Probe (b) — generic bwrap failure (malformed flag)**:
```
$ bwrap --die-with-parent --unshare-user --unshare-net --clearenv \
    --setenv HOME /tmp --ro-bind / / --invalid-flag-xyz --tmpfs /tmp \
    --proc /proc --dev /dev -- /bin/echo hello
bwrap: Unknown option --invalid-flag-xyz
exit=1
```

**Probe (c) — EPERM on unshare (privilege-stripped container)**:
```
$ docker run --rm mcr.microsoft.com/playwright/python:v1.58.0-jammy \
    bash -c "apt-get update && apt-get install -y bubblewrap && \
    su nobody -s /bin/bash -c 'bwrap --die-with-parent --unshare-user \
    --unshare-net --clearenv --setenv HOME /tmp --ro-bind / / \
    --tmpfs /tmp --proc /proc --dev /dev -- /bin/echo hi'"
bwrap: No permissions to create new namespace, likely because the kernel does not allow non-privileged user namespaces. See <https://deb.li/bubblewrap> or <file:///usr/share/doc/bubblewrap/README.Debian.gz>.
exit=1
```

**Important probe (c) finding (deviation from leg artifact's recommended regex)**: the actual bwrap 0.6.1 / 0.9.0 / 0.11.0 EPERM-on-unshare emission is `bwrap: No permissions to create new namespace, likely because the kernel does not allow non-privileged user namespaces.` — NOT the `unshare ... Operation not permitted` form the leg artifact's draft regex assumed. Per F3 §6 + the leg's "L2 design authority" clause, expanded `_BWRAP_EPERM_UNSHARE_RE` to match BOTH variants: the kernel-disabled-userns form (`No permissions to create new namespace`) AND the raw errno-strerror form (`unshare ... Operation not permitted` and reverse). The bwrap-prefix discriminator gates both paths so inner-process failures still take F2's `MCPConnectionError` route.

#### Committed regex patterns (verbatim, in `the_one/mcp/transports/stdio.py`)

```python
_BWRAP_NONEXISTENT_PATH_RE = re.compile(
    r"Can't find source path '?(?P<path>[^'\n:]+?)'?(?:\s*:\s*[^\n]*)?$",
    re.MULTILINE,
)

_BWRAP_EPERM_UNSHARE_RE = re.compile(
    r"(?:No permissions to create new namespace)"
    r"|(?:(?:unshare|user ns|create user namespace).*?(?:Operation not permitted|EPERM))"
    r"|(?:(?:Operation not permitted|EPERM).*?(?:unshare|user ns|create user namespace))",
    re.IGNORECASE | re.DOTALL,
)

_BWRAP_OWN_PREFIX_RE = re.compile(r"^\s*bwrap:", re.MULTILINE)
```

The pattern-1 capture group is non-greedy and extracts the path while consuming an optional `: <strerror>` suffix (the dev container's bwrap 0.11.0 appends `: No such file or directory` after the path).

#### Architectural deviation: translation runs in `finally`, not `except`

The leg artifact's Implementation Guidance step 4 sketched the translation inside an `except BaseException` clause around the `stdio_client(... errlog=...)` context manager. Empirically that clause does NOT fire on the F4 L1a flow:

1. `MCPClient.connect()` calls `await session.initialize()` AFTER the `connect_stdio` yield.
2. `session.initialize()` raises `McpError("Connection closed")` (the SDK's downstream symptom of bwrap exiting before the handshake completes).
3. `MCPClient.connect()`'s outer `except Exception:` catches the `McpError` and calls `_cleanup_after_failed_connect()`.
4. `_cleanup_after_failed_connect()` calls `transport_stack.aclose()` → `aclose` walks the stack with `__aexit__(None, None, None)` (no exception propagation) → our `connect_stdio`'s yield resumes cleanly → `except BaseException` does NOT fire.
5. `MCPClient.connect()` raises `MCPConnectionError(McpError)`. Our `MCPSandboxError` was never produced.

**Fix**: relocated the buffer-read + translate-and-raise logic from `except BaseException` to a `finally` block. bwrap writes to stderr ONLY on failure (probe-confirmed: success path = empty stderr); a non-empty buffer matching the catalog patterns indicates bwrap failure regardless of how the upstream caller reported the symptom. The `finally` raise propagates through `aclose()` and surfaces in `_cleanup_after_failed_connect()`.

**Companion change in `the_one/mcp/client.py::_cleanup_after_failed_connect`** (small but necessary): the prior implementation suppressed ALL teardown exceptions via `except Exception: logger.debug(... suppressing ...)`. That suppressed our `MCPSandboxError` along with the cancel-scope-drift / broken-pipe noise the suppression was originally targeting. Updated to suppress only non-`MCPClientError` teardown exceptions; `MCPSandboxError` (an `MCPClientError` subclass) propagates and dominates the downstream `Connection closed` wrapping. Documented inline.

This is the minimum-viable surface change to make the F3 §6 catalog reachable through the F4 L1a flow.

#### Changes Made

- `the_one/mcp/transports/stdio.py`:
  - Added imports: `re`, `tempfile`, `MCPSandboxError`.
  - Added module-level probe-results comment block + three compiled regexes (`_BWRAP_NONEXISTENT_PATH_RE`, `_BWRAP_EPERM_UNSHARE_RE`, `_BWRAP_OWN_PREFIX_RE`).
  - Added module-private helper `_translate_bwrap_stderr(stderr_text) -> MCPSandboxError | None`. Pattern-#1 exempt from prefix gate; patterns #2/#3 prefix-gated; returns None on no-prefix-no-match (lets F2's `MCPConnectionError` handle inner-process failures).
  - `connect_stdio` body restructured: sandboxed path opens `tempfile.SpooledTemporaryFile(mode="w+", encoding="utf-8", errors="replace")` as `errbuf`, passes it as `errlog=errbuf` to `stdio_client`, runs the inner `async with` chain inside `try / except / finally`. The `finally` reads the buffer (success path → empty → no-op; failure path → matches one of the three signatures → raises). Bypass path (`_sandbox_disabled_for_tests()` True) preserves SDK's default `errlog=sys.stderr` passthrough verbatim.
  - Module docstring lines 49-54 — replaced the "currently not translated; see flight log Anomaly A02" caveat with "translated to ``MCPSandboxError`` via the SDK's ``errlog=`` parameter" + a forward reference to leg `02-bwrap-error-translation` and the `_BWRAP_OWN_PREFIX_RE` directionality contract.
  - `connect_stdio` docstring extended with the new errlog-capture mechanism description.

- `the_one/mcp/client.py`:
  - `_cleanup_after_failed_connect` now lets `MCPClientError` subclasses propagate; non-`MCPClientError` teardown exceptions still suppressed-with-debug-log. Inline docstring documents the rationale (F4 L2 bwrap-stderr translation).

- `tests/test_mcp_sandbox_integration.py`:
  - Module list (line 28-area) — Test #6 entry rewritten "MCPConnectionError per L4 Anomaly A02" → "MCPSandboxError catalog #1 per L2"; added entries for #6b, #6c, #6d.
  - Test #6 (`test_sandbox_writable_paths_nonexistent_raises_at_connect`) — `pytest.raises(MCPConnectionError)` → `pytest.raises(MCPSandboxError)`; added `assert "writable_paths entry" in message` and `assert "does not exist" in message`; REMOVED the `assert not isinstance(... MCPSandboxError)` defensive line; rewrote section header (`# #6 — Writable_paths nonexistent → MCPSandboxError catalog #1 per L2`); rewrote test docstring to reflect the new directionality.
  - Added `_has_sys_admin()` helper (parses `/proc/self/status` `CapEff` line; bit-21 check).
  - Added Test #6b `test_sandbox_bwrap_unrecognised_exit_code_raises_msc_sandbox_error_msg2` — monkeypatches `BubblewrapSandbox.prepare_spawn` to inject `--no-such-flag-for-test-6b` into the returned `SpawnSpec.args`; bwrap rejects with `bwrap: Unknown option ...` (prefix-gated, no #1/#3 match) → catalog #2; asserts `bubblewrap exited non-zero` + `bwrap stderr:` substrings.
  - Added Test #6c `test_sandbox_eperm_on_unshare_raises_mcp_sandbox_error_msg3` — `@pytest.mark.skipif(_has_sys_admin(), ...)`; SKIPPED in dev container (has SYS_ADMIN); asserts catalog #3 substring `namespace creation refused` when run in privilege-stripped envs.
  - Added Test #6d `test_inner_process_failure_does_not_translate_to_sandbox_error` — locks the directionality contract from the inner-process-failure side. Monkeypatches `prepare_spawn` to replace the inner command with `/bin/sh -c "echo 'unshare failed: Operation not permitted (inner process noise, not bwrap)' >&2; exit 1"`. The stderr noise WOULD match `_BWRAP_EPERM_UNSHARE_RE` if the prefix gate were absent; with the gate the captured stderr lacks `bwrap:` prefix → `_translate_bwrap_stderr` returns None → F2's `MCPConnectionError` handles. Asserts `MCPConnectionError` + `not isinstance(... MCPSandboxError)`.

- `tests/test_mcp_stdio_sandbox.py`:
  - `_stub_stdio_client_factory._stub` signature widened to accept the new `errlog=` kwarg added by L2's `connect_stdio` rewrite. The kwarg is captured-but-unused by these unit tests (real-subprocess sandbox tests cover the bwrap-stderr path). Existing test methods unchanged in behavior — only the stub's signature broadened so the 5 callers don't TypeError on the new kwarg.

- `CLAUDE.md`:
  - F3 contracts §5 (line 332): "L2 adds the exception class; L4 enforces the boundary in `connect_stdio`" → "L2 adds the exception class AND enforces the boundary in `connect_stdio` via stderr-capture-and-translate (via SDK `errlog=` parameter); flight 04 leg 02 lands the enforcement." Inline-listed the three §6 catalog message wordings (with the cycle-1-rework-amended #2 wording dropping the synthetic exit-code interpolation in favor of an embedded bwrap-stderr snippet).

- `the_one/agents.md`:
  - Line 73: "L2 adds the exception class; L4 enforces" → "L2 adds the exception class AND enforces the boundary in `connect_stdio` via stderr-capture-and-translate." Added a one-line note on the bwrap-prefix discriminator's role in the directionality contract.

#### Test counts (per-file)

| File | Before (post-L1b) | After (post-L2) | Δ |
|------|--------|-------|---|
| `tests/test_mcp_client.py` | 59 | 59 | 0 |
| `tests/test_mcp_integration.py` | 14 | 14 | 0 |
| `tests/test_mcp_sandbox_integration.py` | 10 | 13 | +3 (Test #6 flipped, #6b/#6c/#6d added) |
| `tests/test_mcp_stdio_sandbox.py` | 9 | 9 | 0 (stub signature widened; tests unchanged) |
| `tests/test_sandbox_bubblewrap.py` | 17 | 17 | 0 |
| `tests/test_sandbox_contract.py` | 14 | 14 | 0 |
| **Total** | **123** | **126** | **+3** |

Final `pytest tests/test_mcp_client.py tests/test_mcp_integration.py tests/test_mcp_sandbox_integration.py tests/test_mcp_stdio_sandbox.py tests/test_sandbox_bubblewrap.py tests/test_sandbox_contract.py -q --timeout=60` returned `125 passed, 1 skipped in 8.20s`. The skip is Test #6c (`_has_sys_admin()` true in the dev container per F3 §10's privilege-grant baseline). In a privilege-stripped CI environment without SYS_ADMIN, Test #6c would run and the suite would report `126 passed, 0 skipped`.

#### Notes

- **(a) Lint**: `ruff check the_one/mcp/transports/ tests/test_mcp_sandbox_integration.py` → `All checks passed!`. Also ran on `the_one/mcp/client.py` and `tests/test_mcp_stdio_sandbox.py` (incidentally touched) — clean.
- **(b) Deviations from leg artifact**:
  - `_BWRAP_EPERM_UNSHARE_RE` extended to match `No permissions to create new namespace` in addition to the leg's bidirectional `unshare ... Operation not permitted` form. Probe (c) revealed bwrap 0.6.1 / 0.9.0 emit the former under unprivileged-userns-disabled kernels; without this, Test #6c would have missed in privilege-stripped envs and the catalog #3 path would be unreachable in practice. Per the leg artifact's "L2 design authority" clause, this regex extension is in-scope. No catalog-message wording change.
  - Translation logic moved from `except BaseException` to `finally` (architectural deviation documented above). Necessary because `MCPClient.connect()`'s outer `except Exception` catches the downstream symptom before our async-context-manager's exception path can fire.
  - `the_one/mcp/client.py::_cleanup_after_failed_connect` updated to let `MCPClientError` subclasses propagate. The leg artifact's §Inputs paragraph claimed "no `connect()` changes needed" — that was based on the assumption that `MCPSandboxError` would be raised from `connect_stdio` BEFORE `MCPClient.connect()` reached its `except Exception` block. Empirically the order is reversed; this small companion change makes the leg's intent achievable without rewriting the L1a AsyncExitStack flow.
  - `tests/test_mcp_stdio_sandbox.py::_stub_stdio_client_factory` signature widened to accept `errlog=`. The leg artifact's Verification Step #8 mandates "no other test files modified"; this is a minor mechanical signature update (no test methods modified, only the test-helper stub broadened to accept the new kwarg) that's necessary because the real `stdio_client` signature changed at the call site. Logged here for debrief.
- **(c) Anomalies**: none operationally — all probes ran cleanly; all tests green; lint clean. The architectural deviation in (b) is documented but not anomalous (the leg artifact's "L2 design authority" + "implementer adapts to the actual live source state" clauses cover it).
- **(d) Verification of L1a + L1b changes still present**: `git status` shows modified `the_one/mcp/client.py`, `the_one/mcp/transports/stdio.py`, `the_one/platform/sandbox/bubblewrap.py`, `tests/test_mcp_client.py`, `tests/test_mcp_sandbox_integration.py`, `tests/test_sandbox_bubblewrap.py`, `tests/test_mcp_stdio_sandbox.py` (the last is L2's stub-signature update; others carry L1a + L1b + L2 source/test changes accumulated in the working tree). L1a's `_cleanup_after_failed_connect` debug-suppress logic and `tests/test_mcp_client.py` 5-test additions are present (verified the L1a tests still pass). L1b's `--tmpfs` argv hoist in `bubblewrap.py` and the `tests/test_sandbox_bubblewrap.py` argv-three-way-order test are present (verified via `pytest tests/test_sandbox_bubblewrap.py::test_prepare_spawn_argv_three_way_order_ro_bind_tmpfs_bind` → 1 passed).

### L3-pool-primitives-worker-task — landed

- **Status**: `landed` (flight-final commit will transition to `completed`)
- **Started (UTC)**: 2026-05-07
- **Completed (UTC)**: 2026-05-07
- **Pre-edit SHA**: `4ad63611008abcdbf3154e52c3209f3f413c7a44` (same as L1a-start / L1b-start / L2-start; L1a + L1b + L2 source changes are uncommitted in working tree per agentic-workflow batch-commit-at-flight-end policy). L3-baseline diff captured at `/tmp/l3-baseline.diff` (1430 lines — accumulated L1a + L1b + L2 artifact + source edits).

#### Pre-flight checks (before implementation)

- **pytest-asyncio mode**: `grep asyncio_mode pyproject.toml` → `pyproject.toml:47:asyncio_mode = "auto"`. Auto mode confirmed; the leg sketch's plain `@pytest.fixture(autouse=True)` async fixture works as-is (no `pytest_asyncio.fixture` swap needed).
- **Baseline regression**: `pytest tests/test_mcp_client.py tests/test_mcp_integration.py tests/test_mcp_sandbox_integration.py tests/test_mcp_stdio_sandbox.py tests/test_sandbox_bubblewrap.py tests/test_sandbox_contract.py -q --timeout=60` → `125 passed, 1 skipped in 7.05s`. Per-file counts `{59, 14, 13, 9, 17, 14}` exactly match L2-end target.
- **`MCPSourceRepository.get` exists**: verified at `the_one/db/repositories.py:251-256` (`async def get(self, source_id: str) -> MCPSource: ... raise KeyError(...)`). Factory shape mirrored from `the_one/interfaces/web/api.py::_mcp_repo` lines 55-58.
- **bwrap availability**: `shutil.which("bwrap")` returns a path in dev container (bwrap 0.11.0); integration tests #10 / #11 will run, not skip.

#### Changes Made

- **`the_one/mcp/_pool.py`** (new, 271 lines):
  - Module docstring credits the structural mirror of `the_one/tools/_session_registry.py`; documents the §2 + §11 worker-task-per-entry pattern; documents the cycle-2 race-fix invariant (lock-held branch checks `entry is None`, NOT `entry.client is None`); documents memory ordering (worker is sole writer of `client` / `failure`; both written BEFORE `client_ready.set()`).
  - `_DEFAULT_TTL_SECONDS = 300` and `_REAPER_INTERVAL_SECONDS = 30.0` constants. The latter is forward-referenced for L4 (UNUSED in this leg).
  - `_RegistryEntry` dataclass with all six fields per §2: `ttl_seconds: int`, `worker: asyncio.Task[None] | None = None` (cycle-1 reviewer fix — None during the brief construction window before `acquire` assigns the spawned Task), `evict_event: asyncio.Event | None = None` (constructed in `acquire` immediately after dataclass construction), `client_ready: asyncio.Event | None = None`, `client: MCPClient | None = None`, `failure: BaseException | None = None`. The `acquire` and `_evict` paths `assert entry.worker is not None` (and similarly for `evict_event` / `client_ready`) before awaiting; the assignment-immediately-under-lock invariant makes the assertions sound.
  - `_pool: dict[tuple[str, str], _RegistryEntry] = {}`, `_lock: asyncio.Lock = asyncio.Lock()`, `_shutting_down: bool = False`.
  - `_resolve_ttl_seconds() -> int` reads `MCP_POOL_IDLE_TTL_SECONDS` at call-time; ValueError on non-int falls back to `_DEFAULT_TTL_SECONDS` with a logger.warning.
  - `_load_source(source_id) -> MCPSource` constructs `MCPSourceRepository(get_connection(), get_encryptor(settings.data_dir))` and calls `repo.get(source_id)`. Called OUTSIDE `_lock` per cycle-2 medium #2 (different-key acquires must not serialize on the F1 DB read).
  - `_entry_worker(source, entry) -> None` is the worker task per §2. Constructs `MCPClient(source)`, awaits `client.connect()`. On `BaseException` (worker is cancelled-friendly), populates `entry.failure` BEFORE setting `entry.client_ready`, returns. On success, populates `entry.client`, sets `entry.client_ready`, awaits `entry.evict_event.wait()`. The `finally:` runs `await client.disconnect()` on the SAME task that ran connect (anyio cross-task guard satisfied; disconnect failures wrapped in `try/except Exception: logger.exception(...)` per L1a's idempotent-disconnect contract).
  - `_evict(key) -> None` pops the entry under `_lock`, sets `evict_event`, awaits the worker with `asyncio.wait_for(worker, timeout=10.0)`. On timeout, cancels the worker and `with contextlib.suppress(BaseException): await worker`. Idempotent on missing key (returns immediately if `_pool.pop(key, None)` is None).
  - `acquire(agent_name, source_id) -> MCPClient` follows the §2 pseudo-code exactly: pre-loads source OUTSIDE the lock; under the lock, `if _shutting_down: raise RuntimeError`, then `if entry is None: construct + spawn + insert`; outside the lock, `await entry.client_ready.wait()`; if `entry.failure is not None`, idempotent-pop (only if `_pool.get(key) is entry`) and re-raise; else `client._touch_activity()` and return. The lock-held branch checks `entry is None` (NOT `entry.client is None`) — cycle-2 race-fix invariant.
  - `_clear_for_test() -> None` snapshots `_pool` under the lock, clears the dict, sets `evict_event` on each entry, cancels each non-done worker, awaits with suppress, resets `_shutting_down = False`. Test seam mirroring `_session_registry.py::_clear_for_test`.

- **`the_one/mcp/__init__.py`** updated:
  - Added `from the_one.mcp._pool import acquire` (with the `# noqa: E402  (constants first per F2 contract)` comment matching the existing imports).
  - Added comment `# L4 will add: from the_one.mcp._pool import shutdown_drain` immediately below the import for forward-reference discipline.
  - Extended `__all__` with `"acquire"`.

- **`tests/test_mcp_pool.py`** (new, 12 tests, ~360 lines):
  - Module docstring lists all 12 test cases and their coverage.
  - Autouse fixture `_clear_pool_after_each_test` calls `await pool_mod._clear_for_test()` after every test.
  - `_make_stub_source()` helper returns a minimal `MCPSource(type="stdio", config={"command": "/bin/true", ...})` — never executed because tests monkeypatch `pool_mod.MCPClient`.
  - `_MockClient` base class with `AsyncMock`-wrapped `connect` / `disconnect` / `MagicMock` `_touch_activity`. Subclassed per scenario (`_SlowClient`, `_VerySlowClient`, `_FailingClient`, `_FailingThenRecoveringClient`) per cycle-1 reviewer pattern.
  - `patch_client` fixture monkeypatches `pool_mod.MCPClient` to `_MockClient` and `pool_mod._load_source` to a stub returning `_make_stub_source(source_id)`; resets `_MockClient._instance_count = 0`.
  - **Test #1** `test_acquire_lazy_spawn_creates_worker_and_returns_client` — first acquire returns connected `_MockClient`; `_instance_count == 1`; `_touch_activity` called once; entry registered in `_pool` with non-None `worker` and `client is client`.
  - **Test #2** `test_acquire_warm_reuse_returns_same_client_instance` — `c1 is c2`; `_instance_count == 1`; `_touch_activity.call_count == 2`.
  - **Test #3** `test_concurrent_acquire_same_key_shares_one_worker` (cycle-2 race-fix lock) — 5 concurrent `acquire("agent-a", "src-1")` via `asyncio.gather`; uses `_SlowClient` (50ms sleep in connect); asserts `_SlowClient._instance_count == 1` (exactly ONE worker); `all(r is results[0] for r in results)` (shared client); `results[0]._touch_activity.call_count == 5`.
  - **Test #4** `test_different_keys_spawn_independent_workers` — `acquire("agent-a", "src-1")` vs `acquire("agent-b", "src-1")` produce different clients; `_instance_count == 2`; entry workers distinct.
  - **Test #5** `test_spawn_failure_propagates_to_acquire_callers` — `_FailingClient.connect` raises `MCPSandboxError`; `pytest.raises(MCPSandboxError, match="test sandbox failure")`; key absent from `_pool` after failure.
  - **Test #6** `test_spawn_failure_pop_is_idempotent_under_concurrent_acquires` (cycle-1 reviewer fix — concurrent observers) — `asyncio.gather(acquire, acquire, return_exceptions=True)` against `_FailingThenRecoveringClient`; both raise the SAME `MCPConnectionError` instance (`results[0] is results[1]`); only ONE worker spawned (cycle-2 invariant: `_instance_count == 1`); `connect_attempts["n"] == 1` (shared worker only ran connect once); key popped (`("agent-a","src-1") not in pool_mod._pool`); third sequential acquire spawns fresh worker that succeeds (`_instance_count == 2`, `connect_attempts["n"] == 2`).
  - **Test #7** `test_acquire_cancellation_leaves_worker_running` — `_VerySlowClient` (1.0s connect); first acquire times out via `asyncio.wait_for(timeout=0.05)`; entry still in `_pool`, worker not done; second un-cancelled acquire reuses the still-running worker, gets the client; `_instance_count == 1`.
  - **Test #8** `test_load_source_runs_outside_the_lock` (cycle-2 medium #2 lock) — spy via `monkeypatch.setattr(pool_mod, "_load_source", _spy_load_source)`; spy records `pool_mod._lock.locked()` at call time; asserts list non-empty AND `all(h is False for h in lock_held_during_load)`.
  - **Test #9** `test_clear_for_test_cancels_workers_and_empties_pool` — registers 3 entries; captures worker references; calls `_clear_for_test()`; `_pool == {}`; all three workers `done()`.
  - **Test #10** `test_acquire_real_bwrap_end_to_end_with_strict_floor_profile` (`@requires_bwrap`) — uses real `mcp_fixture_sandbox_profile` + `mcp_fixture_stdio_params` to construct an `MCPSource` with strict-floor sandbox config; monkeypatches `_load_source` to return that source; calls `acquire("test-agent", source.id)`; awaits `client.list_tools()`; asserts `len(tools) > 0`. Locks F3 dead-code resolution for `mcp_fixture_sandbox_profile`.
  - **Test #11** `test_acquire_then_evict_via_internal_helper` (`@requires_bwrap`) — same source-construction pattern as #10; calls `acquire`, asserts `client.is_alive` and key in `_pool`; calls `await pool_mod._evict(key)`; asserts key absent and `client.is_alive is False`. Locks the `_evict` contract for L4's reaper.
  - **Test #12** `test_evict_idempotent_on_missing_key` (cycle-1 reviewer suggestion) — `await pool_mod._evict(("never-inserted-agent", "never-inserted-src"))`; no raise; `_pool == {}`. Locks the `if entry is None: return` guard.

#### Test counts (per-file)

| File | Before (post-L2) | After (post-L3) | Δ |
|------|--------|-------|---|
| `tests/test_mcp_client.py` | 59 | 59 | 0 |
| `tests/test_mcp_integration.py` | 14 | 14 | 0 |
| `tests/test_mcp_sandbox_integration.py` | 13 | 13 | 0 |
| `tests/test_mcp_stdio_sandbox.py` | 9 | 9 | 0 |
| `tests/test_sandbox_bubblewrap.py` | 17 | 17 | 0 |
| `tests/test_sandbox_contract.py` | 14 | 14 | 0 |
| `tests/test_mcp_pool.py` | 0 | 12 | +12 |
| **Total** | **126** | **138** | **+12** |

Final `pytest tests/test_mcp_client.py tests/test_mcp_integration.py tests/test_mcp_sandbox_integration.py tests/test_mcp_stdio_sandbox.py tests/test_sandbox_bubblewrap.py tests/test_sandbox_contract.py tests/test_mcp_pool.py -q --timeout=60` returned `137 passed, 1 skipped in 9.86s`. The single skip remains Test #6c (L2 EPERM probe — `_has_sys_admin()` true in dev container per F3 §10's privilege-grant baseline). Integration tests #10 and #11 PASSED against real bwrap 0.11.0 in the dev container (the worker-task-per-entry pattern correctly satisfies anyio's cross-task `CancelScope.__aexit__` guard — connect AND disconnect run on the same worker task). Full project suite cross-check: `pytest -q --timeout=60` → `1241 passed, 2 skipped, 299 deselected` (zero regressions outside the L3 surface).

#### Notes

- **(a) Cycle-2 race-fix lock confirmed**: Test #3 (`test_concurrent_acquire_same_key_shares_one_worker`) passes with `_SlowClient._instance_count == 1` after 5 concurrent `acquire` calls via `asyncio.gather`. Only ONE worker spawned; all 5 awaiters got the same client instance and called `_touch_activity` (call_count == 5). The lock-held branch checks `entry is None` (verified in source via `grep -A 5 "if entry is None" the_one/mcp/_pool.py`).
- **(b) Concurrent-idempotent-pop confirmed**: Test #6 passes with `results[0] is results[1]` — both gather'd acquires re-raise the SAME `MCPConnectionError` instance (the worker's stored `entry.failure`); both call `_pool.pop(key, None)` and the second is a no-op because the first already removed the key; `connect_attempts["n"] == 1` proves only ONE connect was issued (cycle-2 race-fix invariant). Subsequent retry succeeds with a fresh worker (`_instance_count == 2`, `connect_attempts["n"] == 2`), proving the pool recovers cleanly after a failure burst.
- **(c) Real-bwrap integration tests confirmed**: Tests #10 and #11 PASSED in the dev container. The worker-task-per-entry pattern satisfies anyio's cross-task guard mechanically — no `RuntimeError("Attempted to exit cancel scope in a different task")` log lines from the L1a safety-net swallow (verified: `pytest tests/test_mcp_pool.py -v --log-cli-level=WARNING --timeout=60 | grep -i "cancel scope"` is empty). The L1a stake-test invariants extend to the pool's worker-task pattern as designed.
- **(d) `_load_source` outside-the-lock confirmed**: Test #8 spy records `pool_mod._lock.locked() == False` at every `_load_source` invocation. `grep -B 2 -A 8 "_load_source\|async with _lock" the_one/mcp/_pool.py` confirms `source = await _load_source(source_id)` precedes `async with _lock:` in `acquire`'s body.
- **(e) `_clear_for_test` cleanup confirmed**: Test #9 registers 3 entries; after `_clear_for_test()`, `_pool == {}` and all 3 worker tasks are `done()`. The autouse fixture pattern guarantees no orphan workers leak between tests (verified across the full 12-test pool suite + 1241-test project suite).
- **(f) Lint clean**: `ruff check the_one/mcp/ tests/test_mcp_pool.py` → `All checks passed!`.
- **(g) Diff narrowness**: only `the_one/mcp/__init__.py` (+4 lines: re-export + comment + `__all__` entry) was modified by L3; `the_one/mcp/_pool.py` and `tests/test_mcp_pool.py` are new files. No changes to `the_one/mcp/client.py`, `the_one/mcp/transports/`, or any L1a/L1b/L2 surface (verified: `git status` shows no NEW modifications to those files vs L2-end).
- **(h) Deviations from leg artifact**: minor — `_RegistryEntry`'s `evict_event` and `client_ready` fields were also typed as `asyncio.Event | None = None` (with default `None`) for consistency with `worker: asyncio.Task[None] | None = None` (the cycle-1 reviewer fix). The dataclass's `acquire` constructor immediately populates them under `_lock` before insert; `_evict` / `_entry_worker` / `acquire`'s post-event branch all assert non-None before awaiting. The leg sketch had them required-at-construction with `field()`-defaults; making them all `Optional` keeps the dataclass uniform and the assertion pattern symmetric. No behavioral change. Also: `_load_source`'s docstring was extended to credit the `_mcp_repo` factory mirror explicitly (cosmetic).
- **(i) Anomalies**: none. All 12 pool tests passed on the first regression run; lint clean on the first run; cumulative 138-test surface green on the first run; full project suite (1241 tests) green.
- **(j) Verification of L1a + L1b + L2 changes still present**: `git diff --stat the_one/mcp/client.py the_one/mcp/transports/stdio.py the_one/platform/sandbox/bubblewrap.py` shows `client.py 52 ±, stdio.py 187 ±, bubblewrap.py 17 ±` (3 files, +232/-24 lines). All three carry their L1a / L1b / L2 modifications intact in the working tree per the agentic-workflow batch-commit-at-flight-end policy.

### L4 design + cycle-1 review (2026-05-07)

- L4 leg artifact drafted (reaper + lifespan integration). Spawned Developer for cycle-1 design review.
- Cycle 1 — **needs rework**. 2 high + 2 medium + 2 low. Highs: (1) tests #1/#3/#4/#5 set `client._last_activity = 0.0` on `_MockClient`, but `_MockClient` doesn't expose `last_activity` — `_reap_once` reads `entry.client.last_activity` and would `AttributeError`; (2) test #8 (lifespan-order spy) drives `app_mod.lifespan(fake_app)` which calls `init_db()`, `get_connection()`, `migrate_json_to_sqlite()`, `SQLiteAgentStore`, `AgentFactory` on startup — none mocked; lifespan crashes before `yield`. Mediums: `_reap_once` parallelism (sequential `await _evict(key)` blocks for up to 10s × N when N entries are stuck — diverges from PTY template without justification); §Outputs step 6 import-style contradictions. Lows: shutdown_drain re-entrancy edge case undocumented; verify-then-extend caveat for L3's `_clear_for_test` body absent.
- Resolved cycle-1 inline: extended `_MockClient.__init__` to add `self.last_activity = 0.0` (settable mock attr); rewrote test bodies to use `client.last_activity = 0.0` (NOT `_last_activity`); test #8 mocks all five startup symbols (`init_db`, `get_connection`, `migrate_json_to_sqlite`, `SQLiteAgentStore`, `AgentFactory`); switched `_reap_once` from sequential to `asyncio.gather(..., return_exceptions=True)` for per-key `_evict` parallelism (justified explicitly in docstring — diverges from PTY template because MCP `_evict`'s 10s wait is much larger than subprocess SIGTERM-to-SIGKILL); collapsed §Outputs step 6 to a single decision (`from the_one.mcp._pool import shutdown_drain`; consumers alias on import); added §Edge Cases note on reaper-cancel-vs-belt-and-suspenders interaction; added step 5 verify-then-extend caveat for L3's `_clear_for_test`. No cycle-2 — leg is mechanically refined, not re-designed.
- L4 leg artifact status set to `ready`. Flight Director will spawn Developer (action: implement) next.

### Leg L4 (04-reaper-and-lifespan) — landed (2026-05-07T14:09:40Z)

**Status**: landed. Implementation followed the leg artifact's 12 Implementation Guidance steps. All acceptance criteria met. Source changes uncommitted (per agentic-workflow flight-final-commit pattern).

#### Pre-flight checks (before implementation)

- **L4-start regression baseline**: `pytest tests/test_mcp_pool.py -v --timeout=60` → `12 passed in <1s` against the L3-end pool. Per-file counts `{59, 14, 13, 9, 17, 14, 12}` = 138 collected, 137 passed + 1 skipped — exactly matches L4-start expected state.
- **L3 `_clear_for_test` body verified**: `grep -B 1 -A 25 "async def _clear_for_test" the_one/mcp/_pool.py` confirmed `_shutting_down = False` reset is already present at the end of L3's body. L4 prepends the reaper-cancel block; no behavior change to the L3-defined entry-cancel + flag-reset pair.
- **PTY pool structural template re-verified**: `grep -n "shutdown_drain\|_reaper_task\|_reap_once\|_reap_loop" the_one/tools/_session_registry.py` confirmed the lines cited in the leg artifact (75, 165-205, 213-280) match the live source. L4 mirrors the template structurally, with the documented MCP-specific divergence (parallel gather instead of sequential close in `_reap_once`).

#### Changes Made

- **`the_one/mcp/_pool.py`** (added 142 lines on top of L3's body; L4-affected surface: ~462 lines total):
  - Added `import time` (used by `_reap_once`'s `time.monotonic()`).
  - Added `_reaper_task: asyncio.Task[None] | None = None` module-level state.
  - **`_ensure_reaper_running_locked() -> None`** — idempotent reaper-spawn helper. MUST be called under `_lock`. Spawns `_reap_loop` only if `_reaper_task is None or done()`. Mirrors `_session_registry.py:213-218`.
  - **`_reap_once() -> list[tuple[str, str]]`** — snapshot expired keys under `_lock` using `now - entry.client.last_activity > entry.ttl_seconds` (with `entry.client is not None` guard for mid-connect entries). Outside the lock, `await asyncio.gather(*(_evict(key) for key in expired), return_exceptions=True)`. Per-key `_evict` exceptions logged via `logger.exception`; `CancelledError` is NOT logged (filtered out as not an Exception via the `BaseException` + `not CancelledError` check). Returns the list of evicted keys.
  - **`_reap_loop() -> None`** — `try: while True: await asyncio.sleep(_REAPER_INTERVAL_SECONDS); try: await _reap_once(); except Exception: log+continue`. On `CancelledError`: snapshot remaining keys under `_lock`, parallel-`gather` evict, then re-raise. One bad `_reap_once` does not kill the loop.
  - **`shutdown_drain() -> None`** — public async function. Order: (1) `_shutting_down = True` FIRST, (2) cancel `_reaper_task` and suppress `CancelledError` on its await (the reaper's own handler runs the drain), (3) belt-and-suspenders snapshot+`gather`-`_evict`, (4) `_reaper_task = None`. Total drain bounded at ~10s regardless of pool size.
  - **`acquire`** modified — after `_pool[key] = entry` (under `_lock`), inserts `await _ensure_reaper_running_locked()`. Only the lazy-spawn branch (`if entry is None`) calls it; warm-reuse paths skip the call (idempotent helper makes this redundant safety, not a correctness issue).
  - **`_clear_for_test`** extended — at the top, BEFORE the existing snapshot+cancel-workers block, cancels `_reaper_task` (with `BaseException` suppress because the reaper's CancelledError handler may itself raise during drain) and resets `_reaper_task = None`. The existing entry-cancel + `_shutting_down = False` reset is preserved unchanged.

- **`the_one/mcp/__init__.py`** updated — replaced the L3 forward-reference comment with `from the_one.mcp._pool import (acquire, shutdown_drain)`; extended `__all__` with `"shutdown_drain"`.

- **`the_one/interfaces/web/app.py`** updated:
  - Added `from the_one.mcp import shutdown_drain as _mcp_pool_shutdown_drain` near line 37 (alongside the PTY-pool import; Ruff's import-sort puts it BEFORE the `tools._session_registry` import alphabetically).
  - In `lifespan`'s shutdown branch, after the existing `try: await _session_registry_shutdown_drain() except Exception: logger.exception(...)` block and BEFORE `await close_connection()`, inserted the same try/except wrapper around `_mcp_pool_shutdown_drain()`. Comment credits flight §12 lifespan-ordering contract.

- **`tests/test_mcp_pool.py`** gained 10 new tests in an "L4 — Reaper, drain, lifespan" section after the existing L3 tests. Total file: 22 tests (12 + 10). Also added `import contextlib` for test #10's `contextlib.suppress(asyncio.CancelledError)`. **`_MockClient.__init__` extended** with `self.last_activity = 0.0` so L4 reaper tests can age entries by direct assignment (the production `MCPClient` exposes `last_activity` as a read-only property — the mock substitutes a plain attribute).

#### Test counts (per-file)

| File | L4-start (post-L3) | L4-end (post-L4) | Δ |
|------|--------|-------|---|
| `tests/test_mcp_client.py` | 59 | 59 | 0 |
| `tests/test_mcp_integration.py` | 14 | 14 | 0 |
| `tests/test_mcp_sandbox_integration.py` | 13 | 13 | 0 |
| `tests/test_mcp_stdio_sandbox.py` | 9 | 9 | 0 |
| `tests/test_sandbox_bubblewrap.py` | 17 | 17 | 0 |
| `tests/test_sandbox_contract.py` | 14 | 14 | 0 |
| `tests/test_mcp_pool.py` | 12 | 22 | +10 |
| **Total** | **138** | **148** | **+10** |

Cumulative L4-surface regression: `pytest tests/test_mcp_client.py tests/test_mcp_integration.py tests/test_mcp_sandbox_integration.py tests/test_mcp_stdio_sandbox.py tests/test_sandbox_bubblewrap.py tests/test_sandbox_contract.py tests/test_mcp_pool.py -q --timeout=60` → `147 passed, 1 skipped in 19.44s`. The single skip remains Test L2 #6c (EPERM probe — `_has_sys_admin()` true in dev container per F3 §10's privilege-grant baseline). All 137 prior L4-surface tests still pass UNMODIFIED.

#### Notes

- **(a) Reaper-loop CancelledError-handler test confirmed**: Test #10 `test_reap_loop_drains_on_cancellation` PASSED. Registers 2 entries; cancels the live `_reaper_task`; suppresses `CancelledError`; asserts `_pool == {}` and both clients had `disconnect.assert_awaited_once()`. The reaper's CancelledError handler runs `asyncio.gather(*(_evict(key) for key in keys), return_exceptions=True)` over the remaining keys, then re-raises. The drain is fully visible BEFORE the awaiter sees the cancellation propagate.
- **(b) Drain-timeout test confirmed (10s bound observed empirically)**: Test #9 `test_drain_timeout_handles_stuck_worker` PASSED in **10.01s** (per `--durations=10`). A worker with `disconnect` sleeping 30s is bounded by `_evict`'s 10s `asyncio.wait_for` timeout; on timeout, the worker is cancelled and `await worker` returns. `shutdown_drain` returned within the test's 15s `wait_for` budget. The total-drain-bounded-at-~10s contract holds.
- **(c) Lifespan-order spy test confirmed**: Test #8 `test_lifespan_order_pty_drain_before_mcp_drain_before_db_close` PASSED. All five startup symbols mocked (`init_db`, `get_connection`, `migrate_json_to_sqlite`, `SQLiteAgentStore`, `AgentFactory`); three shutdown spies (`_session_registry_shutdown_drain`, `_mcp_pool_shutdown_drain`, `close_connection`) recorded calls into a shared list; `drain_steps` filtered list `== ["pty", "mcp", "db"]` exactly. Locks flight §12 against future regression — moving the MCP drain BEFORE PTY drain or AFTER DB close would now fail this test.
- **(d) Zero regressions in L1a / L1b / L2 / L3 surface**: per-file counts unchanged for all files except `test_mcp_pool.py`; 137 prior tests still pass; only addition is the +10 new L4 tests. `git diff --stat the_one/mcp/client.py the_one/mcp/transports/stdio.py the_one/platform/sandbox/bubblewrap.py the_one/mcp/_pool.py` shows L1a/L1b/L2/L3 file modifications still present in the working tree (`client.py 52 ±, stdio.py 187 ±, bubblewrap.py 17 ±`); `_pool.py` extended from L3-end's 320 lines to L4-end's ~462 lines (`_reap_once`, `_reap_loop`, `_ensure_reaper_running_locked`, `shutdown_drain` added; `acquire` and `_clear_for_test` extended; everything else preserved).
- **(e) Lint clean**: `ruff check the_one/mcp/ the_one/interfaces/web/app.py tests/test_mcp_pool.py` → `All checks passed!`.
- **(f) Deviations from leg artifact**: minor — (1) `shutdown_drain`'s reaper-cancel branch uses `contextlib.suppress(asyncio.CancelledError)`, but the leg artifact's `_clear_for_test` extension uses `contextlib.suppress(BaseException)` for the reaper-cancel; both are sound (the `BaseException` form in `_clear_for_test` is defensive against the reaper's CancelledError-handler raising a non-CancelledError during a torn-down event loop in tests; the `CancelledError`-only form in `shutdown_drain` matches the PTY pool's template). (2) `_reap_once` filters `isinstance(result, BaseException) and not isinstance(result, asyncio.CancelledError)` for logging, so a `CancelledError` mid-reap (rare but possible if the reap pass itself is cancelled mid-gather) is not double-logged as an unexpected exception. (3) The `asyncio.gather` `return_exceptions=True` returns `BaseException` instances (per the asyncio type contract; `Exception` subset is what the leg sketch wrote — practically identical for `_evict`'s actual raise surface).
- **(g) Anomalies**: none. All 22 pool tests passed on the first regression run; lint clean on the first run; cumulative 147+1 surface green on the first run.
- **(h) L1a + L1b + L2 + L3 changes still present in working tree**: `git status` shows the same 12 modified files + 2 untracked files (`tests/test_mcp_pool.py`, `the_one/mcp/_pool.py`) as L4-start. None reverted. The flight-final-commit pattern remains intact.


### L5 design + (skip cycle-1 review)

- L5 leg artifact drafted: `the_one/mcp/README.md` (~300-450 lines, 9 sections per flight §13) + four named patterns added to `the_one/agents.md` under a new "Project Conventions" section + `### the_one/mcp/` Module Map entry + `CLAUDE.md` cross-references. Doc-only leg — zero source code changes; zero new tests.
- **Flight Director runtime decision: SKIP per-leg cycle-1 design review for L5.** Rationale: (a) doc-only leg — no source code, no tests, no architectural decisions that could mis-execute; (b) prior cycle-1 reviews on L1a/L1b/L2/L3/L4 each caught real bugs in source/test logic, but for a docs-only leg the cost-benefit ratio inverts — at worst the docs are factually wrong or out-of-sync, which the flight-final code review will catch; (c) agentic-workflow's max-2-cycle rule applies to design review, not implementation review; the flight-final pass owns this leg's correctness. Documented here for debrief transparency.
- L5 leg artifact status set to `ready`. Flight Director will spawn Developer (action: implement) next.


### Leg L5 (05-runtime-readme-and-named-patterns) — landed (2026-05-07T14:30:17Z)

**Status**: landed. Doc-only leg — implementation followed the leg artifact's 7 Implementation Guidance steps. All acceptance criteria met. No source / test changes; markdown surface only.

#### Changes Made

- **`the_one/mcp/README.md`** (new file): 418 lines, 9 sections (`§1` test-seam pattern → `§9` cross-references). Structure follows the leg artifact's skeleton verbatim with prose expanded for line-count target. §3 reflects the L1a scope-reduction deviation (transport modules left as `@asynccontextmanager`); §7 carries A02 RESOLVED (post-L2) and A03 RESOLVED (post-L1b) status; §8 documents the lifespan order (PTY → MCP → DB close) and references the L4 spy test as the lock against future regression.
- **`the_one/agents.md`** updated:
  - **`### the_one/mcp/`** Module Map entry inserted alphabetically between `### the_one/llm/` and `### the_one/tools/` (was the requested "alphabetical position"). Contents: per-file table covering `__init__.py`, `client.py`, `errors.py`, `types.py`, `transports/stdio.py`, `transports/streamable_http.py`, `_pool.py` — each row cross-links to the relevant `the_one/mcp/README.md` section.
  - **`## Project Conventions`** new top-level section inserted BEFORE `## Dependency Graph` per the leg artifact's claimed slot. Four named patterns (`trust-the-runtime`, `canonical-import + convenience-re-export`, `structural-Protocol-satisfaction`, `verbatim-message-equality`), each ~15-25 lines covering name + description + live example + counter-example.
  - File grew from 1203 lines to 1267 lines (delta +64 lines). The delta is below the leg estimate of +90-115 because table-format Module Map rows are denser than the 80-100 line freeform estimate.
- **`CLAUDE.md`** updated:
  - One-line cross-reference appended to F3 contracts §5 (line 332): "**Post-L4 runtime invariants**: see `the_one/mcp/README.md` for the full sandbox-wrap composition + pool semantics (sections §7 and §8)."
  - One-line cross-reference appended to architecture summary (line 91): "Project-wide conventions (`trust-the-runtime`, `canonical-import + convenience-re-export`, `structural-Protocol-satisfaction`, `verbatim-message-equality`) live in `the_one/agents.md`'s 'Project Conventions' section."
  - File line count unchanged at 421 (both edits are extensions of existing lines, not new lines).

#### Verification

- **(a) README final line count**: `wc -l the_one/mcp/README.md` → `418 the_one/mcp/README.md`. In the 300-450 target range; specifically near the upper end of the leg's ~300-450 estimate.
- **(b) `agents.md` line-count delta**: 1203 → 1267 (+64 lines). Below the leg estimate of +90-115 because the Module Map entry is in dense table format. The four-pattern Project Conventions section is ~70 lines; the Module Map entry is ~10 lines.
- **(c) Source surface UNCHANGED**: `git diff --stat` of `the_one/` and `tests/` excluding `.md` files matches L4-end exactly: `client.py 52±, stdio.py 187±, bubblewrap.py 17±, app.py 11+, mcp/__init__.py 6+, test_mcp_client.py 261±, test_mcp_sandbox_integration.py 275±, test_mcp_stdio_sandbox.py 16±, test_sandbox_bubblewrap.py 26+`. Untracked source files `the_one/mcp/_pool.py` and `tests/test_mcp_pool.py` carried forward from L4 unchanged. Bit-identical to L4-end.
- **(d) Cumulative regression**: `pytest tests/test_mcp_client.py tests/test_mcp_integration.py tests/test_mcp_sandbox_integration.py tests/test_mcp_stdio_sandbox.py tests/test_sandbox_bubblewrap.py tests/test_sandbox_contract.py tests/test_mcp_pool.py -q --timeout=60` → `147 passed, 1 skipped in 20.68s`. Per-file counts `{59, 14, 13, 9, 17, 14, 22}` = 148 collected. **Identical to L4-end** — no new tests, no test impact.
- **(e) Lint clean**: `ruff check the_one/mcp/ tests/` → `All checks passed!`. (No source changes — lint pass is a sanity check.)
- **(f) README acceptance grep checks**: `grep -i 'do not refactor.*None-with-default'` matches one §4 line; `grep -A 1 "A02 RESOLVED\|A03 RESOLVED"` shows the post-L2 / post-L1b status in §7 with no "deferred" / "pending" language; `grep "PTY.*MCP.*DB"` shows the lifespan ordering in the §9 cross-references summary; the L4 spy test reference (`test_lifespan_order_pty_drain_before_mcp_drain_before_db_close`) is cited in §8 verbatim.
- **(g) `agents.md` acceptance grep checks**: `grep "## Project Conventions"` matches the new section header; the four named patterns each match exactly once via `grep -c "trust-the-runtime\|canonical-import\|structural-Protocol\|verbatim-message-equality"` (returns 5 — the four pattern headers plus one cross-reference in the Module Map's `the_one/mcp/__init__.py` row, exceeding the leg's "at least 4" threshold).
- **(h) `CLAUDE.md` acceptance grep checks**: `grep -E "the_one/mcp/README.md|Project Conventions" CLAUDE.md` returns two matches (one near line 91 for the architecture cross-ref; one in F3 contracts §5 for the runtime-invariants pointer). Meets the "at least two matches" threshold.
- **(i) Deviations from leg artifact**: minor — (1) `the_one/agents.md` file size delta (+64) is below the leg estimate (+90-115) because the Module Map entry uses a per-file table format (~10 lines) rather than freeform prose (~10-15). The information density is higher in table form, and the leg artifact left section sizing flexible. (2) The §6 "do NOT consume `merged_config()`" paragraph dropped a "deferred to design time" phrasing in favour of "head off that mistake at code-review time" — preferred wording during the verification pass to keep "deferred" out of the README entirely (the leg's verification step #4 forbids "deferred" in §7 specifically; ambiguity-elimination paid forward to §6).
- **(j) Anomalies**: none. Regression suite green on the first run; lint clean on the first run; all grep checks pass on the first verification.
- **(k) L1a + L1b + L2 + L3 + L4 changes still present in working tree**: `git status` shows the same 12 modified files + 4 untracked files (`tests/test_mcp_pool.py`, `the_one/mcp/_pool.py`, `the_one/mcp/README.md` (new this leg), `missions/07-mcp-integration/flights/04-idle-ttl-lifecycle/legs/`) as L4-end + L5-additions. Flight-final-commit pattern intact.

#### Notes

- **L5 doc-only correctness depends on the README being read AGAINST the post-L4 source**, not in isolation. Future maintainers landing changes to `_pool.py` or `client.py` should re-read this README before changing invariant-bearing surface (e.g. flipping `is_alive` order, introducing eager `_PINNED_PROTOCOL_VERSION` import) and update the README in the same change if the invariants shift. The README is the authoritative single-source-of-truth for the runtime invariants F2/F3/F4 jointly establish.
- **Cross-reference asymmetry**: the README references CLAUDE.md (for F3 §5 catalog text) and `agents.md` (for project-wide conventions); CLAUDE.md and agents.md both reference the README (for runtime invariants). The triangle is closed; future edits to any one of the three should preserve the cross-link integrity.
- **Project Conventions section placement**: per leg artifact, inserted BEFORE `## Dependency Graph` (line 171 post-mcp-Module-Map-entry). The leg's claimed insertion-point matched the actual file structure; no deviation needed.


### Flight-final review + commit (2026-05-07)

Review (Reviewer pass over all 6 legs' cumulative diff + new files): PASSED. Reviewer scope covered the flight-final surface as a single coherent change rather than re-litigating per-leg cycles — verified (a) the worker-task-per-entry pattern in `_pool.py` is internally consistent (lock-held branch checks `entry is None` not `entry.client is None`; `_load_source` runs OUTSIDE the lock; `_evict` helper is the single eviction path), (b) the cross-task safety net in `client.py:_cleanup_after_failed_connect` swallows `Exception` only and lets `MCPClientError` subclasses propagate per L2's companion fix, (c) bwrap argv ordering in `bubblewrap.py::prepare_spawn` is `--ro-bind / /` → `--tmpfs /tmp` → `--bind PATH PATH` per L1b, (d) the FastAPI lifespan ordering (PTY drain → MCP drain → DB close) is locked by `test_lifespan_order_pty_drain_before_mcp_drain_before_db_close`, (e) the README's runtime invariants (§7 sandbox-wrap composition, §8 lifespan order) match the source.

Cumulative test posture at flight-final: 148 collected, 147 passed + 1 skipped (L2 #6c — EPERM probe skipped because dev container has CAP_SYS_ADMIN per `/proc/self/status` bit-21). Net new tests across the flight: +30 (L1a +5, L1b +1, L2 +3 plus 1 flipped, L3 +12, L4 +10, L5 +0). F2's 30 + F3's 79 = 109 prior tests UNMODIFIED. Lint clean across the flight surface.

Anomalies resolved this flight: A01 (`RuntimeError: generator didn't stop` swallow at `client.py:255-257`) — repurposed as a documented cross-task safety net per L1a's design narrative; the real fix is the worker-task-per-entry pattern in `_pool.py`. A02 (bwrap stderr translation) — L2 implements via SDK `errlog=` parameter + `_BWRAP_OWN_PREFIX_RE` discriminator; CLAUDE.md F3 contracts §5 caveat dropped. A03 (`--bind` shadowing `--tmpfs /tmp`) — L1b reorders argv in a single block.

Runtime deviations carried forward: L1a transport-API scope reduction (kept `connect_stdio` / `connect_streamable_http` and the dispatcher as `@asynccontextmanager` to preserve 9 prior callers; the AsyncExitStack ownership lives at the `MCPClient.connect/disconnect` level instead). L2 EPERM regex extension (matches bwrap 0.9.0's "No permissions to create new namespace" wording in addition to "Operation not permitted ... unshare").

Commit composes all 12 modified files + 4 untracked files (`tests/test_mcp_pool.py`, `the_one/mcp/_pool.py`, `the_one/mcp/README.md`, `missions/07-mcp-integration/flights/04-idle-ttl-lifecycle/legs/`) under one flight-final commit per agentic-workflow §2c. Flight transitions to `landed` on commit; legs L1a-L5 transition to `completed`; mission-level Flight 4 checkbox flipped to `[x]`. L6 HAT remains `pending` — orchestrator-guided human verification step, scheduled post-commit.
