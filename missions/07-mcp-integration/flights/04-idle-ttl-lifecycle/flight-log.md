# Flight Log: Idle-TTL Lifecycle + Per-Source Process Registry

**Flight**: [Idle-TTL Lifecycle](flight.md)

## Summary

Pre-execution. Phase 1 + 1b context-gathering complete; carrying forward F2 A01 (disconnect AsyncExitStack), F3 A02 (bwrap-side error translation), F3 A03 (`--bind`/`--tmpfs` ordering). Awaiting Architect design review.

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

---

## Decisions

> Runtime decisions not in original plan. Populated during execution.

---

## Anomalies

> Populated as encountered during execution.

---

## Flight Director Notes

> Populated by the orchestrator during agentic-workflow execution.
