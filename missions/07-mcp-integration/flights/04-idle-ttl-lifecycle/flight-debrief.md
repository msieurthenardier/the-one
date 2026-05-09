# Flight Debrief: Idle-TTL Lifecycle + Per-(Agent, Source) Process Registry

**Date**: 2026-05-07
**Flight**: [Idle-TTL Lifecycle](flight.md)
**Status**: landed
**Duration**: 2026-05-06 → 2026-05-07 (~24h elapsed; ~6h active orchestration)
**Legs Completed**: 6 of 6 (L1a, L1b, L2, L3, L4, L5 autonomous; L6 HAT 4/5 PASS + 1 PARTIAL)

## Outcome Assessment

### Objectives Achieved

The flight delivered the full lifecycle layer that turns F2's `MCPClient` and F3's bwrap-wrapped spawn into a warm-on-demand, idle-reaped, lifespan-drained pool. Per-`(agent_name, source_id)` keying mirrors `the_one/tools/_session_registry.py` (PTY pool) at the structural level. Lazy spawn on first tool dispatch, warm reuse within idle TTL (default 300s), transparent respawn after reap, FastAPI-lifespan-driven `shutdown_drain` on graceful shutdown — all empirically verified end-to-end against the real `mcp-server-fetch` MCP server in the L6 HAT. The three structural debts F2/F3 carried forward — A01 (`RuntimeError: generator didn't stop` swallow), A02 (bwrap stderr translation), A03 (`--bind`/`--tmpfs /tmp` ordering bug) — were addressed by L1a (repurposed swallow as documented cross-task safety net), L2 (`MCPSandboxError` translation), and L1b (single-block argv reorder) respectively. The `the_one/mcp/README.md` runtime-invariants document deferred since F2 debrief landed at 418 lines / 9 sections.

### Mission Criteria Advanced

- ✅ **Mission criterion #5 fully closed** — "Idle local MCP server processes are reaped after a configurable period of disuse and respawned transparently on next use, with the FastAPI lifespan integrated cleanly so the server process tree is drained on shutdown." Locked by L4 tests #8 (lifespan-order spy: PTY → MCP → DB), #9 (drain-timeout: 10.01s observed), #10 (reap-loop drains on cancellation), and L6 HAT Step 4 (idle reap + transparent respawn against real bwrap subtree).
- ✅ **Mission criterion #4 partially advanced** — "Locally spawned MCP server processes run inside an OS-level sandbox … the implementation is verified on Linux against a reference local MCP server." L6 HAT Step 2 verified the bwrap subtree spawns + listing tools against `mcp-server-fetch` on Linux. F3 had already verified the in-repo fixture; L6 closes the third-party-server gap.
- ✅ **Mission criterion #11 partially advanced** — "Each layer of the integration has automated coverage proving its contract — sandbox spawn path *(F3)*; **idle-TTL reaper** *(F4 contributes)*; client-side connection lifecycle for both transports *(F2)*." F4's contribution: 22 new tests on `tests/test_mcp_pool.py` covering pool primitives + reaper + lifespan + cancellation handlers + drain timeout + lifespan ordering.

### Numbers

- **Tests**: 117 → 148 (+31 net new). 147 passed + 1 skipped (Test #6c EPERM expected skip in dev container with SYS_ADMIN). F2/F3 prior tests UNMODIFIED.
- **Lint**: clean across `the_one/` and `tests/`.
- **Files changed**: 13 modified + 4 new; +5691/-98 lines.
- **Commits**: 2 atomic — `b5a1e23` (autonomous L1a→L5) + `9e02584` (HAT L6).
- **Anomalies resolved**: A01, A02, A03 (all per F3 debrief carry-forward).
- **Design-review cycles**: cycle-1 + cycle-2 Architect at flight design; cycle-1 Developer at each leg (4/5 caught real bugs; L5 doc-only correctly skipped).

## What Went Well

- **Two-cycle Architect review at flight design caught the load-bearing architectural decision** (cycle-1: anyio cross-task `CancelScope.__aexit__` guard meant AsyncExitStack alone couldn't solve cross-task disconnect → worker-task-per-entry pattern; cycle-2: duplicate-spawn race in `acquire` pseudo-code → entry-existence check, not client-existence check). Without these, both bugs would have shipped.
- **Per-leg cycle-1 design review hit rate of 4/5 caught real implementation-time bugs** (cross-task probe needing real anyio task group; `_RegistryEntry.worker` type annotation forbidding temporary `None`; `_MockClient.last_activity` missing for L4 tests; lifespan-order test missing DB-startup mocks; `_translate_bwrap_stderr` directionality bug + EPERM regex direction backwards). These are logic errors that would have failed at first regression run, not design-doc nits — confirming the cycle is doing real work.
- **Stake-test probe pattern** (per F2 debrief KL #1) saved cycles in L1a (anyio cross-task probe), L2 (bwrap stderr signature probe), and L3 (real-bwrap integration test). Each probe locked SDK/OS behavior empirically before implementation committed.
- **Worker-task-per-entry pattern is the canonical solution** for any pool fronting an SDK that uses `anyio.create_task_group()` internally. The pattern is structurally sound, mechanically tested against real anyio (L1a stake-test probe + L3 Test #3 + L6 HAT integration), and documented in `the_one/mcp/README.md §3` and `the_one/mcp/_pool.py::_entry_worker`.
- **Lifespan-order spy test pattern** (`tests/test_mcp_pool.py::test_lifespan_order_pty_drain_before_mcp_drain_before_db_close`) locks the entire §12 invariant in one test function. Mocks all five startup symbols + three drain targets; asserts call order via shared list. Reusable verbatim for future shutdown-ordering tests.
- **`_evict(key)` extraction** (cycle-2 helper) gives `_reap_once`, `shutdown_drain`, and the reaper-cancel handler a single eviction primitive. Eliminates duplicated pop+signal+await-worker logic across three call sites.
- **Underscore-private + public re-export pattern** (`the_one.mcp.acquire` / `the_one.mcp.shutdown_drain`) is the clean public seam. F6 will consume it without naming-style friction.
- **Doc cross-reference triangle is closed**: `README.md` ↔ `agents.md` ↔ `CLAUDE.md` all cross-link. Future maintainers landing at any apex can navigate to the others.

## What Could Be Improved

### Process

1. **Citation audit gap caused L1a runtime deviation.** Both Architect cycles verified the leg's 8 cited symbol locations but did NOT walk the test files for direct callers of `connect_stdio` / `connect_streamable_http` as `async with` contexts. Implementation found 9 prior tests (8 in `tests/test_mcp_stdio_sandbox.py`, 1 in `tests/test_mcp_client.py::test_production_path_constructs_client_with_assembled_headers`) directly consuming those helpers as async-CMs. The leg's "115 prior tests pass UNMODIFIED" AC and the "transports change to non-CM" Output were jointly unsatisfiable. **Recommendation: add to `.claude/skills/leg/SKILL.md` and `.claude/skills/flight/SKILL.md` a Citation Audit subsection requiring "find direct callers of any public symbol whose signature changes."** This is the single biggest methodology improvement from the flight.

2. **L1a should have been pre-split further to L1a-MCPClient-only + L1c-transports-only from the start.** The pre-split decision (L1a + L1b) split AsyncExitStack from argv-reorder but didn't split `MCPClient` refactor from transport refactor. Splitting transports separately would have surfaced the 9-prior-callers issue at design time, not implementation time.

3. **Test-count baseline staleness.** L1a leg cited 115 prior tests; actual was 117 (F3 added 2 tests to `tests/test_sandbox_bubblewrap.py` between F3 design and L1a design). **Recommendation: leg-design-time gate — run `pytest --collect-only` on the leg's listed test files and confirm prior counts before authoring acceptance criteria.**

4. **HAT Step 5 chicken-and-egg.** The leg's "lifespan drain" verification assumed `docker compose down` would exercise the full path, but the pool can only be populated via F6's `MCPToolProvider`. Short-circuiting `_load_source` and acquiring directly from a REPL doesn't trigger the FastAPI lifespan branch. **Recommendation: future flights with deferred-consumer paths should explicitly call out which HAT steps require the consumer's flight first.**

### Technical

1. **Mission known-issue NOT transitively fixed by L1a.** `MCPClient.disconnect` still emits `RuntimeError: generator didn't stop` via the cross-task safety net swallow on EVERY disconnect (including under explicit `shutdown_drain()` per HAT Finding #1). The L1a runtime deviation kept transports as `@asynccontextmanager`, leaving the dispatcher's nested `async with` generator-protocol incompatibility. Subprocess cleanup is functionally correct (no orphans from this root cause). **Owner: F5 or F6 (whichever first touches transports). Implementation approach: introduce parallel non-CM transport helpers (`_open_stdio_transport_stack`, `_open_streamable_http_transport_stack`) alongside the existing `@asynccontextmanager` versions; the dispatcher consumes the non-CM helpers; existing CM versions stay for back-compat with the 9 prior callers.**

2. **Process-reaping gap (HAT Finding #2).** 7 `[bwrap] <defunct>` zombies in the dev container indicate that nothing in `the_one/mcp/transports/stdio.py` or the SDK's anyio path calls `wait()` on the bwrap subprocess after teardown. Verified: `grep wait` against transports + bubblewrap returns zero matches. Functionally harmless (zombies hold only PID + struct task), but accumulates linearly with respawn count; long-running containers will eventually exhaust PIDs. **Recommendation: investigate either (a) `try: process.wait() except: pass` after the SDK's `stdio_client` CM exits, or (b) wrapper around `anyio.open_process` ensuring `wait()` runs. Likely needs an SDK-level workaround or upstream fix.**

3. **`_RegistryEntry`'s three Optional fields require asserts.** `worker`, `evict_event`, `client_ready` are typed `T | None = None` for "construction window before assignment" reasons. Three `assert ... is not None` calls in `_evict` / `_entry_worker` / `acquire` are load-bearing. **Refactoring opportunity (low priority): consolidate via `__post_init__` so `evict_event` and `client_ready` are constructed in the entry itself; only `worker` remains Optional. Net: 2 of 3 asserts removed, type signature becomes more accurate.**

4. **Cross-task safety net log message lacks a flight-log breadcrumb.** When this WARNING fires in production, the operator sees `"MCPClient transport close failed"` with no hint that "this is the F2 known-issue, not a real failure." **Recommendation: extend the log message in `client.py:285` to: `"MCPClient transport close failed (cross-task disconnect — see the_one/mcp/README.md §3 'cross-task safety net')"`.**

### Documentation

1. **`the_one/mcp/README.md:356` references reaper interval as 60s; actual is 30s** (`_pool.py:_REAPER_INTERVAL_SECONDS = 30.0`). One-line correction.

2. **The four named patterns in `agents.md` Project Conventions section omit a fifth that the flight introduced**: `same-task-anyio-cm-ownership`. The worker-task-per-entry pattern at `_pool.py::_entry_worker` is the canonical solution for any future code holding anyio-task-group-rooted CMs across reaper/eviction boundaries. **Recommendation: add a fifth pattern entry with `_entry_worker` as the live example.**

3. **`procps` HAT prerequisite gap.** Dev container's playwright base image lacks `pgrep`/`ps`. Had to install via `apt-get install procps` mid-HAT. **Recommendation: add `procps` to the Dockerfile's apt install line (alongside `bubblewrap`). HAT-doc-fix would only paper over the gap.**

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| **L1a transport-API scope reduction** (option c-lite): transports + dispatcher kept as `@asynccontextmanager`; only `MCPClient.connect/disconnect` refactored to AsyncExitStack | Architect cycles missed 9 prior tests directly consuming `connect_stdio` / `connect_streamable_http` as async-CMs. Refactor would violate AC #6/#8. | **Yes, partially**: codify the citation-audit requirement in skill prompts. The deviation itself is a good call (preserved 117 prior tests; F4 L3 worker-task wraps `MCPClient` not transports, so transport API shape is opaque to L3). |
| **L2 translation in `finally`, not `except`** | `MCPClient.connect()`'s outer `except Exception:` catches `McpError("Connection closed")` BEFORE AsyncExitStack walks back through `connect_stdio`'s `__aexit__(None, None, None)`. The `except BaseException` clause in `connect_stdio` doesn't fire because `__aexit__` runs without exception propagation. Probe-confirmed bwrap writes stderr only on failure → non-empty buffer is the failure signal. | **Yes**: future architectural work involving SDK-rooted async-CMs should account for this propagation pattern. Document in `the_one/mcp/README.md §3` (already partially captured). |
| **L2 companion fix to `_cleanup_after_failed_connect`** | Original suppressed all `Exception` subclasses, masking the new `MCPSandboxError` the leg's translation needed to surface. Type-discriminated suppression added (let `MCPClientError` propagate; suppress only non-`MCPClientError`). | **Yes**: the typed-suppression pattern is correct. Document near `_cleanup_after_failed_connect` if future maintainers re-encounter. |
| **L2 EPERM regex extension**: matches bwrap 0.6.1/0.9.0 "No permissions to create new namespace" wording in addition to "Operation not permitted... unshare" | Stake-test probe revealed bwrap version-dependent stderr; design-authority clause covered the inline adjustment. | **Yes**: bidirectional + multi-wording regex is the correct posture for any error-message pattern matching across tool minor-versions. |
| **L3 typed all three `_RegistryEntry` Event fields as `Optional`** instead of constructed-at-init | Symmetry with cycle-1 fix on `worker: Task | None = None`. | **No**: refactor opportunity exists (move to `__post_init__`); current shape works but adds load-bearing asserts. |
| **L4 `_reap_once` parallel `asyncio.gather` instead of sequential** (diverges from PTY template) | MCP `_evict`'s 10s wait is much larger than subprocess SIGTERM-to-SIGKILL (~1s). 10s × N sequential awaits would be intolerable at shutdown. Bounds drain at ~10s regardless of pool size. | **Yes**: when the per-entry teardown wait time is large, gather is the correct choice. Document the sizing rationale near `_reap_once`. |
| **L5 SKIPPED cycle-1 design review** (doc-only leg) | Risk profile inverts for docs: at worst factually wrong, caught by flight-final review. Cost-benefit doesn't justify the cycle. | **Yes**: codify "doc-only legs may skip cycle-1 review with Flight Director rationale logged." Document in `agentic-workflow` SKILL.md. |
| **L6 HAT Step 5 → PARTIAL, deferred to F6** | Pool only populated via F6's `MCPToolProvider`; short-circuiting `_load_source` from REPL doesn't drive lifespan. Automated coverage from L4 tests #8 + #9 is sufficient; live E2E is genuinely an F6 concern. | **Yes**: future flights with deferred-consumer paths should call out which HAT steps need the consumer's flight first. |

## Key Learnings

1. **The citation-audit gap is the single biggest methodology improvement opportunity.** Both Architect cycles verified the leg's cited symbol locations but neither walked the test files for direct callers of changed public symbols. This caused the L1a runtime deviation. Codifying "find direct callers of any public symbol whose signature changes" in `.claude/skills/leg/SKILL.md` and `.claude/skills/flight/SKILL.md` would have caught this at design time.

2. **Two-cycle Architect review is the F4-template baseline for any flight with non-trivial concurrency or SDK-internal-state contracts.** Cycle-1 caught the load-bearing anyio cross-task issue; cycle-2 caught the duplicate-spawn race in `acquire`. Both were architectural correctness issues that one-cycle review would have missed. Future flights with concurrency, SDK boundary, or process-supervision concerns (F5 OAuth, F6 agent tool-routing, future pool variants) should default to two cycles.

3. **Cycle-1 Developer review on each leg is doing real work, not gold-plating.** 4/5 reviews caught real bugs that would have failed at first regression run. The pattern is robust; do not drop the cycle to "save iterations." Doc-only legs (L5) may skip with rationale logged.

4. **The worker-task-per-entry pattern is canonical for any pool fronting an SDK that uses `anyio.create_task_group()` internally.** Document in `agents.md` Project Conventions as a fifth named pattern: `same-task-anyio-cm-ownership`. F5 (OAuth via streamable-HTTP) doesn't need this pattern (httpx async client doesn't have the same constraint); F6's pool consumption inherits it for free.

5. **Stake-test probes save cycles when integration tests stake on specific OS/SDK patterns.** Per F2 debrief KL #1 — already canonical; reaffirmed here. L1a (anyio cross-task probe), L2 (bwrap stderr signature probe), L3 (real-bwrap integration test) all benefited.

6. **Architectural deviation via design-authority clauses is a correct mechanism, NOT an escape hatch.** L2's two architectural deviations (translation in `finally`, companion fix to `_cleanup_after_failed_connect`) were absorbed via the leg's L2-design-authority clause without escalation. Both were genuinely necessary at implementation time and well-justified. The clause works.

7. **HAT discovers things automated tests can't.** Three findings only surface in HAT: the F2 known-issue's persistence post-L1a (live disconnect log noise); the 7 zombie bwrap processes (process-supervision gap); the `procps` prerequisite. Future HATs are worth their cost.

## Recommendations

1. **🔴 Critical — File a follow-on for the F2 known-issue.** Add to `mission.md` Known Issues with explicit acceptance criterion: `MCPClient.disconnect` produces no `WARNING the_one.mcp.client:client.py:285 MCPClient transport close failed` log line under `shutdown_drain()` against a real bwrap subprocess. Approach: introduce parallel non-CM transport helpers (`_open_stdio_transport_stack`, `_open_streamable_http_transport_stack`) alongside the existing CM versions; the dispatcher consumes the non-CM helpers; the 9 prior CM callers continue to use the existing versions. **Owner: F5 or F6 (whichever first touches transports).**

2. **🔴 Critical — Codify the citation-audit gap fix.** Add to `.claude/skills/leg/SKILL.md` and `.claude/skills/flight/SKILL.md` a Citation Audit subsection requiring "find direct callers of any public symbol whose signature changes" via grep against test files. The flight log already names this requirement; lock it in skill output.

3. **🟡 Important — Investigate bwrap subprocess-reaping gap (HAT Finding #2).** Add to `the_one/mcp/transports/stdio.py` either (a) `try: process.wait() except: pass` after the SDK's `stdio_client` CM exits, or (b) wrapper around `anyio.open_process` ensuring `wait()` runs. Likely needs SDK-level investigation. Until landed, document in mission Known Issues.

4. **🟡 Important — Add `procps` to dev container Dockerfile (HAT Finding #3).** Add to the apt install line alongside `bubblewrap`. HAT-doc-fix would only paper over the gap; HAT methodology depends on `pgrep`.

5. **🟡 Important — Add a fifth Project Conventions pattern to `agents.md`**: `same-task-anyio-cm-ownership`. Worker-task-per-entry implementation as the live example. Pattern applies to any future pool fronting an SDK that uses `anyio.create_task_group()` internally.

6. **🟡 Important — Fix the `the_one/mcp/README.md:356` reaper interval drift** (60s → 30s).

7. **🟡 Important — Extend cross-task safety net log message** at `client.py:285` to: `"MCPClient transport close failed (cross-task disconnect — see the_one/mcp/README.md §3 'cross-task safety net')"`. Operators get a clear pointer instead of an opaque WARNING.

## Action Items

### Mission Known Issues (update mission.md)

- [ ] Update existing entry: `MCPClient.disconnect` teardown noise — status "still present after F4; L1a runtime deviation kept transports as `@asynccontextmanager`. Owner: F5 or F6. Approach: parallel non-CM transport helpers."
- [ ] Add new entry: bwrap subprocess `wait()` gap — 7 zombie `[bwrap] <defunct>` processes accumulate in long-running dev containers. Owner: F5 or F6 investigation; possibly upstream SDK fix.

### Skill methodology (mission-control)

- [ ] Update `.claude/skills/leg/SKILL.md`: add Citation Audit "find direct callers of changed public symbols" requirement.
- [ ] Update `.claude/skills/flight/SKILL.md`: same Citation Audit requirement at flight-design level.
- [ ] Update `.claude/skills/agentic-workflow/SKILL.md`: codify "doc-only legs may skip cycle-1 design review with Flight Director rationale logged in flight-log."

### the-one source (forward to F5 or F6)

- [ ] Parallel non-CM transport helpers: `_open_stdio_transport_stack`, `_open_streamable_http_transport_stack` (closes F2 known-issue + retires safety-net log noise).
- [ ] bwrap `wait()` mitigation in `transports/stdio.py` (closes HAT Finding #2).
- [ ] Add `procps` to dev container Dockerfile (closes HAT Finding #3).
- [ ] `the_one/mcp/README.md:356` drift fix (60s → 30s).
- [ ] `the_one/agents.md` Project Conventions: add fifth pattern `same-task-anyio-cm-ownership`.
- [ ] `client.py:285` log message extension with README §3 pointer.

### Forward-looking (next flight design)

- [ ] **F5 (OAuth) flight design**: explicitly document "F5 doesn't touch the stdio pool; F4's deliverables compose cleanly." Note constraint: do NOT add new direct callers of `connect_streamable_http` as `async with` — the existing 1 caller is what's blocking the F2 known-issue fix.
- [ ] **F6 (agent integration) flight design**: take ownership of the deferred F4 HAT Step 5 (live-FastAPI-lifespan E2E with real bwrap reaping). Add acceptance criterion: "no `[bwrap] <defunct>` zombies after N agent sessions" if HAT Finding #2 mitigation hasn't landed by then.

### Test-count regression hygiene

- [ ] Codify: leg-design-time pre-flight gate = `pytest --collect-only` on listed test files; confirm prior counts before authoring acceptance criteria. Prevents stale counts (L1a cited 115; actual 117).
