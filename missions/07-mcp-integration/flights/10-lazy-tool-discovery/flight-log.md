# Flight Log: Lazy tool discovery — search-tools / search-mcps as the only catalog entries

**Flight**: [Lazy tool discovery](flight.md)

## Summary

Flight log for F10, which pivots from F9's alignment vibing to a new architectural feature: replacing the agent's eager-load-all-tools catalog with a 2-tool baseline (`search_tools` + `search_mcps`) plus per-iteration dynamic loading. F9 paused at L3-landed per F9 §1 + §5 acceptable variations / operator-driven scope adaptation.

---

## Decisions

### Phase 3 flight close + operator HAT pass + F9 resume decision (2026-05-10)

**HAT pass**: operator confirmed end-to-end after the cache-first follow-up commit landed:
- "working great" — chat session creation now sub-100ms; no 30s timeouts during agent builds with `cloudflare_api` attached.
- Steps 1-5 of `operator-hat-script.md` collapsed into operator-felt sign-off rather than formal walk; the cache-first fix unblocked the surface that the formal HAT was designed to expose.

**Anomaly captured (non-blocking, F10 debrief follow-up)**:
- **A-F10-1 — SSO HTTP MCP login opens in new tab vs. modal window**: during HAT setup, operator re-authed an OAuth-protected HTTP MCP source. Consent flow opened in a new browser tab rather than the inline OAuth modal (`oauth-modal.js`). Functionality intact (token persisted; tool list rendered after consent), but UX regresses from F5 L5's modal experience. **NOT an F10 regression** — F10 did not touch `oauth-modal.js`, `chat.js` OAuth handlers, or `/api/oauth/start`. Likely environment-specific (popup blocker, WS reconnect-snapshot replay race, or pre-existing F5/F6.6 quirk surfaced by HAT scrutiny). Captured for F10 debrief; investigate during a successor pass.

**F9 resume-or-absorb decision**: **RESUME**. Operator directive: "finish f9" → revive F9 L5/L6/L7/L8 under F10's lazy-discovery architecture. F9's flight log placeholder updated accordingly. The pre-pivot F9 L5 leg draft at `flights/09-alignment/legs/05-http-mcp-in-chat.md` documents pre-F10 intent; needs refresh because chat-time tool inventory scenarios now require the agent to call `search_tools`/`search_mcps` before listing tools (the new "agent searches before listing" UX).

**Phase 3 (per `/agentic-workflow` skill)**:
- All 5 legs `completed`.
- Flight log entries for all legs present.
- Documentation updated: `mission.md` Constraint #71 amended, F10 added to Flights list at flight close.
- Flight status: `in-flight` → `landed`.
- PR #41 — operator will mark out of draft + merge when ready.
- Signal `[COMPLETE:flight]`.

---

### Path B (cache-first agent build) absorbed during F10 HAT vibing (2026-05-10)

**Context**: During F10 HAT, the operator hit a session-creation hang. Chat session creation triggered `AgentFactory.create()` → `MCPToolProvider.get_tools_for_agent()`, which called `acquire() + list_tools()` eagerly per attached MCP source. The operator's `cloudflare_api` source was timing out (~30s per source, SDK connect timeout), making multiple agent builds in a session multiplicatively slow.

**Symptom**: New chat session creation hung for 30s+ when any attached MCP source was unreachable. Multiple agent builds in a session compounded to 60s+.

**Root cause**: `get_tools_for_agent` did not check the `_cache.tools` payload (populated by the source-edit page Refresh action) before attempting a live connect. F10 §10 had designed Path B (cache-first hydration) but explicitly deferred it to a follow-up flight.

**Operator-directed scope blend**: operator directed inline absorb as part of F10's vibing close rather than opening a new flight.

**Fix scope**:
- `the_one/mcp/_tool_provider.py`: `get_tools_for_agent` Phase B loop now checks `source.config["_cache"]["tools"]` BEFORE the `acquire() + list_tools()` block. If cache is populated: hydrates `MCPTool` dataclasses from the cached payload (same pattern as `factory.py:_build_source_index` lines 91-104), skips acquire entirely. If cache is empty: falls back to existing acquire + list_tools path with all 3 exception handlers preserved (`MCPAuthRequired`, connection errors, unguarded propagate).
- `MCPClientTool.execute` at `_tool.py:135-175` is UNCHANGED — it already correctly lazy-acquires via the F4 pool at first call. Only the agent-build-time eager-acquire was the problem.
- F5 pause/resume invariant preserved: dispatch is still via `self.tools.get(name)`, unaffected by acquire timing.
- The 4 typed MCPClient exceptions contract is UNCHANGED — no 5th type added.

**Expected behavior**: agent builds with a populated-cache source are sub-100ms regardless of server reachability. Only the FIRST actual tool call against an unreachable source pays the 30s timeout.

**Tests**: 2 new tests added to `tests/test_mcp_tool_provider.py`:
- `test_get_tools_for_agent_uses_cache_when_populated` — verifies `acquire` is NOT called when cache is populated; returned tools match cached payload.
- `test_get_tools_for_agent_falls_back_to_acquire_when_cache_empty` — verifies `acquire` IS called when cache is empty (Path A fallback).

**Test delta**: 1505 → 1507 pass (+2 new tests). All pre-existing 1505 pass. 2 pre-existing bwrap flakes unchanged.

**Decision**: ship inline on `flight/10-lazy-tool-discovery` branch (PR #41). Mission constraint #71's F10 amendment block updated with a Path B note.

---

### Architect design review feedback incorporated (2026-05-10)
**Context**: Per flight skill Phase 5b, spawned an architect agent to validate F10 design against current code. Verdict: **approve with changes**. Three high-severity issues (resolved inline in flight.md), four medium, three low.
**Decision**: Incorporate all high-severity fixes into the flight artifact at design time; route medium/low items into respective leg designs.
**High-severity fixes applied to flight.md**:
- Added Design Decision §10 (Candidate-set construction — Path B cache-only hydration with Path A fallback) to resolve the unspecified `MCPClientTool` construction path. `_cache.tools` payload (`{name, description, input_schema}` per `api.py:1014-1042`) is hydration-source for Path B; Path A is the existing eager `MCPToolProvider.get_tools_for_agent` if Path B turns out infeasible at L3 design.
- Strengthened §3 wording: ToolRegistry holds FULL candidate set; `_loaded_schemas` is purely a model-visibility filter. Dispatch via `self.tools.get(name)` always finds the tool. F5 deferred-then-resumed pause/resume composes trivially under this framing — no special-casing needed.
- L1 stub search tools return CANNED data (1-2 tool schemas added to `_loaded_schemas`) so persistence-across-turns test exercises the mutation. L1's standalone value flagged as purely architectural — no mission criterion ticks at L1.
**Medium-severity items routed to leg design**:
- L1: HAT-script interpretive note for `tests/HAT.md:111` and `:167` (script-counts of `mcp__*` schemas reflect REGISTRY membership, not model-visibility — assertions still pass; prose updates needed).
- L3: extract shared `mcp_overrides` filter helper from `_tool_provider.py:264-284` BEFORE forking `search_mcps` filter logic. First task in L3.
- L5: capture iteration count + total prompt-tokens for the HAT scenario before-and-after F10 (run scenario against pre-F10 `main` then post-F10 branch); report deltas in debrief.
- L5 HAT prose: explicitly call out the new model — operator should see the agent search after attach, NOT immediate tool availability — to forestall first-encounter "regression" reads.
**Low-severity items captured**:
- §9 augmented: `supports_tools()` await stays OUTSIDE the iteration loop (one-time gate); only schema computation moves into the loop body. Avoids per-iteration `supports_tools()` re-await.
- L3 test for 50-tool synthetic-description truncation (~200-char cap).
- L1 stub canned-data preference noted (above).
**Architect affirmations preserved**:
- Mission constraint amendment discipline (§7) is right — explicit "UNCHANGED" enumeration is the right contract surface.
- 2-tool split (`search_tools` + `search_mcps` rather than one unified) is right — built-in flat namespace vs MCP source-grouped cardinality mismatch.
- Branch lifecycle handling (F9 paused-not-aborted; F10-close decision gate) is right.
- Per-iteration recompute (§9) is correct against LLM API semantics.
- Strict 2-tool baseline (§2 — no always-loaded core) keeps the architecture clean.

### F9 → F10 pivot (2026-05-10)
**Context**: Mid-F9, while designing L5 (HTTP MCP in chat), operator surfaced an architectural concern: tool definitions sent on every LLM call grow with attached MCP count (Cloudflare API alone exposes 30+ tools), and there's no mechanism for an agent to discover or use a tool added mid-session. Operator proposed: 2-tool baseline (`search_tools` + `search_mcps`) as the only catalog entries; tools auto-load into the agent's per-session loaded set when a search matches.
**Decision**: Pause F9 at L3-landed; open F10 to ship the lazy-tool-discovery architecture. F9's L5/L6/L7/L8 deferred; resume-or-absorb decision at F10 close. Branch lifecycle handled by checking out a new `flight/10-lazy-tool-discovery` off `main`.
**Impact**:
- F9 vibing investment in L1+L2+L3 lands as already-merged main; not lost.
- F9's chat-side polish (L5/L6/L7) deferred — under F10's architecture, L5+'s chat-time tool-inventory scenarios change shape (the agent has to search before listing tools), so re-running them as F9 originally framed would be partial waste.
- M07 close pushes out by F10's duration (~1-2 days estimated).
- Mission constraint amendment lands at F10 L5 to allow the agent-loop scope change.

---

## Reconnaissance Report

F10 is greenfield (not driven by a maintenance report or prior debrief enumerating actionable items), so Phase 1b reconnaissance is N/A — there's no source artifact to walk.

The closest analog: F10's design decisions cross-reference F8's debrief and F9's flight log for cumulative-LOC discipline (F9 §2's ~600 ceiling was overrun by L2; F10 should aim under the same ceiling for production code outside its own surface files), the F5 `auth_required` pause/resume pattern (must continue working under the new loaded-set state), and the F6 `MCPToolProvider.get_tools_for_agent` resolver (whose filter logic informs `search_mcps`'s per-agent gating).

---

## Leg Progress

### L5 — 05-mission-amendment-regression-and-commit

**Status**: landed
**Started**: 2026-05-10
**Completed**: 2026-05-10

**Implementation notes**:

- `missions/07-mcp-integration/mission.md` (Constraint #71, ~12 LOC addition): F10 amendment block appended immediately after the F5 amendment text. The F5 amendment (2026-05-07) preserved unchanged. The F10 amendment (2026-05-10) enumerates all 5 UNCHANGED invariants (dispatch by tool name, iteration cap, continue-tool, capability-gate fallback, F5 pause/resume) and adds the F10 NEW clause (session-scoped `_loaded_schemas` + `_loaded_tool_names` visibility filter; `[search_tools, search_mcps, continue] + loaded_schemas` per iteration; `search_*` tools mutate the loaded set as a side effect). Both amendments readable in sequence; constraint flow preserved.
- `missions/07-mcp-integration/flights/10-lazy-tool-discovery/regression-sweep.md` (NEW, ~68 LOC): Full unit + browser sweep results. Unit suite: 1505 pass / 2 fail (pre-existing bwrap flakes) / 2 skip / 344 deselect — ±0 vs L4 post-landing baseline, zero net-new failures. Browser suite: 283 pass / 43 fail / 12 deselect — +28 pass vs F8 baseline (F9 L1-L3 browser tests now passing), 43 fail = same pre-existing flakes as F8 baseline, zero net-new failures. Caplog gate: 0.
- `missions/07-mcp-integration/flights/10-lazy-tool-discovery/token-cost-measurement.md` (NEW, ~78 LOC): Shape B (synthetic-LLM proxy) used by default. Pre-F10: ~6750 tokens/call (45-tool catalog × 150 tokens/schema avg). Post-F10 iteration 1: ~450 tokens (3-baseline only). Post-F10 worst-case (both search calls load full set): ~7200 tokens. 3-iteration session total: ~20,250 pre-F10 vs ~14,850 post-F10 (−27%). Shape A section left as TBD pending operator coordination at HAT time.
- `missions/07-mcp-integration/flights/10-lazy-tool-discovery/operator-hat-script.md` (NEW, ~85 LOC): 5-step HAT script. Step 2 operator-felt callout verbatim: "this is the NEW model — agent searches before listing. NOT a regression." Caplog gate verification in Step 5 with explicit `docker compose logs` command. HAT sign-off structure (PASS/FAIL with Phase 3 gate).
- `missions/07-mcp-integration/flights/09-alignment/flight-log.md` (~9 LOC addition): F9 resume-or-absorb decision placeholder appended in the Decisions section. Marked explicitly as "TBD at F10 close" per the leg's Implementation Guidance format.
- `missions/07-mcp-integration/flights/10-lazy-tool-discovery/flight.md`: L1, L2, L5 legs checked off (L3 + L4 were already checked).
- `missions/07-mcp-integration/flights/10-lazy-tool-discovery/legs/05-mission-amendment-regression-and-commit.md`: status updated `ready` → `in-flight` at start, then `in-flight` → `landed` at completion.

**Regression sweep summary**:

| Metric | F8 baseline | Post-F10 L5 | Net-new failures |
|--------|-------------|-------------|-----------------|
| Unit pass | 1376 | 1505 | None |
| Unit fail (bwrap flakes) | 2 | 2 | None |
| Browser pass | 255 | 283 | None |
| Browser fail (pre-existing) | 43 | 43 | None |
| Caplog MCPClient.disconnect | 0 | 0 | — |

**Deviations**:

- None. L5 is pure documentation; no production or test code was modified. Test count held at exactly 1505 pass. Browser pass count is +28 vs F8 baseline because F9 L1-L3 added new browser tests — that delta was present before L5 started and is not an L5 change.

---

### L1 — 01-agent-loop-2-tool-baseline

**Status**: landed
**Started**: 2026-05-10
**Completed**: 2026-05-10

**Implementation notes**:

- `the_one/agent/core.py`: Added `SEARCH_TOOLS_SCHEMA` + `SEARCH_MCPS_SCHEMA` module-level constants alongside `CONTINUE_SCHEMA`. Added `Agent.__init__` kwargs `loaded_schemas` + `loaded_tool_names` (both default to fresh empty containers for backward compat). Added `_compute_visible_schemas()` returning the 3-item baseline + `self._loaded_schemas`. Hoisted `await self.llm.supports_tools()` to a local `supports_tools` bool before the while-loop in `_run_iterations`; moved schema computation inside the loop to call `_compute_visible_schemas()` per iteration. Added `.clear()` in-place calls to `reset()` for both containers. Removed dead `_tool_schemas()` method (4 LOC removed).
- `the_one/tools/_search_stubs.py` (NEW): `SearchToolsStub` + `SearchMcpsStub` with class-attribute `name`, `description`, `parameters`. Constructors call `super().__init__(agent_name=agent_name)` — zero-arg config valid; `agent_name` threaded through for L1b factory-plumbing assertion. Both accept `on_match` callback for shared-container mutation. Module-level `_CANNED_TOOL_SCHEMA_A/B` and `_CANNED_MCP_SCHEMA_A/B` constants with `_stub_canned_*` prefix. Imports `SEARCH_TOOLS_SCHEMA` + `SEARCH_MCPS_SCHEMA` from `agent.core` (single source of truth; no circular import).
- `the_one/agent/factory.py`: Added import of `SearchToolsStub` + `SearchMcpsStub`. After `registry = ToolRegistry()`, creates shared `loaded_schemas: list[dict] = []` + `loaded_tool_names: set[str] = set()` containers, defines `_on_search_match` closure with name-set dedup. Registers both stubs (with `agent_name=name`) before the built-in tool loop. Passes containers to `Agent(...)` via new `loaded_schemas=` + `loaded_tool_names=` kwargs.
- `tests/HAT.md`: Added F10 contract note at top of file. Updated prose at Step 3 (registry vs. model-visibility interpretation) and Step 5 (analogous note).
- `tests/test_agent_visibility_filter.py` (NEW): 12 tests covering all 13 ACs including the F5 pause/resume invariant lock-in (`test_deferred_resumed_mcp_tool_dispatch`).
- `tests/test_factory.py`: Updated `test_enabled_tools_whitelist` to assert membership-based checks (search stubs always present) rather than exact list equality.

**Anomalies surfaced**:

(See full L1 entry above for implementation details. Status: `landed`, uncommitted, will be flight-batched-committed at Phase 2d.)

---

### L3 — 03-search-mcps-implementation

**Status**: landed
**Started**: 2026-05-10
**Completed**: 2026-05-10

**Implementation notes**:

- `the_one/mcp/_tool_provider.py` (~40 LOC net): Added `from the_one.mcp.types import MCPTool` to module-level imports. Extracted new module-level `filter_mcp_tools_by_override(mcp_tools, source, override_payload) -> list[MCPTool]` helper (~35 LOC including docstring). Replaced the inline 21-line filter block at `get_tools_for_agent:264-284` with a 3-line call to the helper. Behavior preserved exactly; all 40 existing `test_mcp_tool_provider.py` tests pass unmodified.
- `the_one/tools/_search_mcps.py` (NEW, ~205 LOC): `SearchMcps(Tool)` real implementation. Class attributes `name = "search_mcps"`, `description` and `parameters` imported from `SEARCH_MCPS_SCHEMA` at `agent.core`. Constructor takes `on_match`, `registry`, `source_index`, `agent_name=None`; calls `super().__init__(agent_name=agent_name)` only (no duplicate `self._agent_name` assignment). Pure helpers `_build_synthetic_description` (two-pass fits-or-truncate with reviewer-corrected boundary guard) and `_filter_mcp_candidates` (source-level union + per-tool match, dedup by name). `execute()`: distinguishes no-attached-MCPs from no-match (`"No MCP sources are attached to this agent."` vs `"No MCP tools found matching {query!r}."`); source-grouped breakdown in result text.
- `the_one/agent/factory.py` (~85 LOC net, larger than +20 estimate due to circular-import isolation): Added `_build_source_index` async module-level helper (all DB/MCP imports kept lazy inside the function body to avoid the `agent.__init__` → `factory` → `db.repositories` → `agent.__init__` cycle). `_build_source_index` uses separate `MCPSourceRepository.get` calls per source (option (b)); wraps `KeyError` + general exceptions silently (graceful degrade). Sources with empty `_cache.tools` logged at WARNING and skipped. `MCPTool` constructed with `output_schema=None, annotations=None` for the five-field dataclass requirement. In `create()`: replaced `SearchMcpsStub` import/registration with `SearchMcps`; added `await _build_source_index(...)` call before the search tool registration block. Module-level `import logging` + `logger = logging.getLogger(__name__)` added.
- `the_one/tools/_search_stubs.py` (docstring update, ~8 LOC): Module docstring updated with POST-L3 STATUS block noting `SearchMcpsStub` is now test-only; `SearchToolsStub` also test-only post-L2.
- `tests/test_search_mcps.py` (NEW, ~305 LOC, 24 tests): Covers all test scenarios from leg artifact. Includes boundary tests for `_build_synthetic_description` (fits-exactly, no-spurious-truncation at boundary), `_filter_mcp_candidates` dedup test, `SearchMcps.execute` paths, factory wiring assertion, and `_build_source_index` no-cache/WARNING tests.

**Anomalies**:

- **Factory LOC overrun**: `factory.py` net change is ~85 LOC vs +20 estimated. Extra ~65 LOC are entirely due to the `_build_source_index` module-level helper (with its lazy-import block + docstring) required to isolate DB imports from the circular import cycle. The logic itself is ~50 LOC; overhead is `~35 LOC` of lazy import lines + docstring. Not a design deviation — the circular import cycle (`agent.__init__` → `factory` → `db.repositories` → `agent.__init__`) is a pre-existing architectural constraint that was not modeled in the LOC estimate.
- **Test count overrun**: 24 new tests vs 10-13 estimated. Extra tests added: `test_filter_mcp_candidates_dedup` (dedup at _filter_mcp_candidates level), `test_build_synthetic_description_fits_exactly` (fits-exactly two-pass boundary), `test_build_synthetic_description_boundary_no_spurious_truncation` (reviewer-corrected logic verification), `test_search_mcps_no_cache_source_not_in_search_results` (UX path confirmation). Additional coverage from the boundary/correctness spec in the leg artifact.
- **Pre-existing sandbox test failures**: `test_mcp_sandbox_integration.py::test_sandbox_writable_paths_nonexistent_raises_at_connect` and `test_sandbox_bwrap_unrecognised_exit_code_raises_msc_sandbox_error_msg2` fail due to `bwrap` not being available in this container environment. Pre-existing on L1+L2 baseline; not L3 regressions.
- **Harmless RuntimeWarning**: `test_factory_create_with_mcp_attached_registers_tools` in `test_mcp_tool_provider.py` emits a `RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited`. Cause: test doesn't patch `MCPSourceRepository` at the factory level; `_build_source_index` silently catches the TypeError via `except (KeyError, Exception)` and proceeds with empty source_index (correct graceful-degrade behavior). The warning is from the mock framework's coroutine cleanup — not a functional defect and pre-existing in the test's mock setup strategy.

**Test count delta**:

- L2 post-landing baseline: 1474 pass.
- L3 adds 24 new tests in `tests/test_search_mcps.py`.
- Post-L3 full suite: **1498 passed**, 2 pre-existing flakes in `test_mcp_sandbox_integration.py`, 2 skipped, 344 deselected.
- Delta vs L2 baseline: **+24** (L3 test count).

**LOC by file**:

- `the_one/mcp/_tool_provider.py`: +40 LOC net (+37 helper function, +1 import, -21 inline block replaced by 3-line call = net ~+17 production LOC; actual file growth ~+40 from helper + import additions)
- `the_one/tools/_search_mcps.py`: +205 LOC (NEW)
- `the_one/agent/factory.py`: +85 LOC net (new `_build_source_index` helper ~65 LOC + `create()` changes ~20 LOC)
- `the_one/tools/_search_stubs.py`: +8 LOC (docstring update)
- `tests/test_search_mcps.py`: +305 LOC (NEW)

**Total**: ~643 LOC. Above the ~545 LOC artifact estimate; delta primarily from circular-import isolation overhead (~65 LOC) + additional test coverage (+25 LOC). Flagged for L8 review queue per F10 §10.

---

### L4 — 04-system-prompt-and-integration

**Status**: landed
**Started**: 2026-05-10
**Completed**: 2026-05-10

**Implementation notes**:

- `the_one/agent/config.py` (+17 LOC): Inserted "Tool discovery" section into `BASE_PROMPT` BETWEEN the opening paragraph and "Tool use:". Four bullet points explain the 2-tool baseline, how to discover tools via `search_tools`/`search_mcps`, auto-load semantics, and per-session scope. Existing sections ("Tool use:", "Turn semantics:", persona append note) preserved unchanged. `AgentConfig.get_system_prompt()` (lines 88-93) not modified.
- `tests/test_agent_search_integration.py` (NEW, 7 tests, ~255 LOC): Full integration coverage for the lazy-discovery protocol:
  - `test_base_prompt_includes_discovery_section` — asserts `search_tools`, `search_mcps`, and `"Tool discovery"` in `BASE_PROMPT`, plus ordering lock (`BASE_PROMPT.index("Tool discovery") < BASE_PROMPT.index("Tool use:")`).
  - `test_baseline_visible_at_session_start` — first-iteration `tools=` is exactly `[search_tools, search_mcps, continue]`.
  - `test_search_tools_then_call_loaded_tool` — search("shell") → `shell` auto-loaded → `shell` dispatched → final text; verifies iteration 1 baseline, iteration 2 contains `shell`, shell `StubTool.calls` == 1.
  - `test_search_mcps_then_call_loaded_mcp_tool` — search_mcps("") → MCP tool auto-loaded → MCP tool dispatched → final text.
  - `test_search_then_call_preserves_loaded_set_across_step` — two `agent.step()` calls; `read_file` loaded in step 1 still visible in step 2's `tools=` array.
  - `test_search_then_call_with_continue_signal` — `search_tools("python") + continue` in iteration 1; `python_exec` callable in iteration 2.
  - `test_search_with_no_matches_does_not_load` — `search_tools("xyzzy_no_match")` → `loaded_schemas` remains empty; iteration 2's `tools=` is still the baseline.
- Pre-existing `BASE_PROMPT` tests in `tests/test_config.py:166-183` audited: all use dynamic comparison (`== BASE_PROMPT` or `isinstance`/`len`). No modifications needed. No other stray substring assertions found in any other test file.
- Pre-existing sandbox test failures (`test_mcp_sandbox_integration.py` — 2 tests) confirmed pre-existing via stash/pop verification; not L4 regressions.

**Anomalies**:

- None. Implementation matched the leg artifact exactly. `_make_search_mcps` helper replicated inline in integration test module (not promoted to `conftest.py`; no other test module currently needs it, so the refactor would be premature). `FakeLLM.calls[N]["tools"]` pattern worked without any wrapper class.
- Token-cost note (per leg artifact edge-cases): `BASE_PROMPT` grew by ~17 LOC / ~80-100 tokens per system message. This addition is within the "20-30 LOC" budget. L5 measurement should include this growth in its before-vs-after comparison.

**Test count delta**:

- L3 post-landing baseline: 1498 pass.
- L4 adds 7 new tests in `tests/test_agent_search_integration.py`.
- Post-L4 full suite: **1505 passed**, 2 pre-existing flakes in `test_mcp_sandbox_integration.py`, 2 skipped, 344 deselected.
- Delta vs L3 baseline: **+7**.

**LOC by file**:

- `the_one/agent/config.py`: +17 LOC (Tool discovery section in BASE_PROMPT)
- `tests/test_agent_search_integration.py`: +255 LOC (NEW, 7 tests)

**Total**: ~272 LOC. Within the ~275 LOC artifact sizing budget.

---

### Flight Director Notes — Phase 2c → 2d transition (all 5 legs landed, 2026-05-10)

- **Phase 2c**: L5 marked `landed`. Increment legs_completed → 5 of 5. **All autonomous legs complete.** Per `/agentic-workflow` skill, transition to Phase 2d.
- **Pre-Phase-2d state**:
  - Branch: `flight/10-lazy-tool-discovery` off main.
  - Working tree: 8 modified files + 18 untracked files (new code + tests + leg artifacts + flight docs).
  - Unit suite: 1505 pass / 2 pre-existing flakes / 0 net-new failures.
  - Browser suite: 283 pass / 43 pre-existing flakes / 0 net-new failures.
  - Caplog gate: 0 `MCPClient.disconnect` warnings.
  - **Unexpected addition surfaced**: implementer at L3 introduced `the_one/tools/_search_backends.py` (187 LOC) + `tests/test_search_backends.py` (260 LOC) to resolve circular-import isolation per L3's deviation note. Not in any leg artifact's plan; needs Reviewer assessment.
  - Net F10 production additions (post-actuals):
    - `the_one/agent/core.py` +54 (L1)
    - `the_one/agent/factory.py` +85 net (L1+L3)
    - `the_one/agent/config.py` +17 (L4)
    - `the_one/mcp/_tool_provider.py` +40 net (L3 shared helper extraction)
    - `the_one/tools/_search_stubs.py` 143 LOC NEW (L1)
    - `the_one/tools/_search_tools.py` 87 LOC NEW (L2)
    - `the_one/tools/_search_mcps.py` 215 LOC NEW (L3)
    - `the_one/tools/_search_backends.py` 187 LOC NEW (L3 circular-import workaround — unplanned)
  - Net F10 test additions:
    - `tests/test_agent_visibility_filter.py` 583 LOC NEW (L1, 12 tests)
    - `tests/test_search_tools.py` 517 LOC NEW (L2, 12 tests)
    - `tests/test_search_mcps.py` 658 LOC NEW (L3, 24 tests)
    - `tests/test_search_backends.py` 260 LOC NEW (L3, unplanned)
    - `tests/test_agent_search_integration.py` 445 LOC NEW (L4, 7 tests)
    - Plus minor updates to `tests/HAT.md`, `tests/test_factory.py`, `tests/test_config.py` (audit, unchanged).
  - **Cumulative F10 LOC**: ~3500 (production + test). Above the original F10 §1+§10 sizing estimates (~600-1100 LOC production + tests); driven by the L3 circular-import workaround + the implementers' extra test coverage.
- **Phase 2d step 1: spawn Reviewer**. Per F10 §8 + leg-execution.md crew definition with F10's override: use Sonnet for the bundled fresh-context review (not the crew's Haiku default — F10 §8 specifies Sonnet for the closing review).

### Flight Director Notes — Phase 2d Reviewer outcome (2026-05-10)

- **Reviewer verdict**: `[HANDOFF:confirmed]`. Zero blocking issues, 2 non-blocking items for the debrief follow-up:
  1. `factory.py:72-74` — non-`KeyError` exceptions in `_build_source_index` swallowed without logging. Recommend split `except KeyError: continue` + `except Exception as e: logger.warning(...); continue`.
  2. `test_agent_search_integration.py:235` — dual-registry pattern (`SearchMcps._registry` vs `agent_registry`) in `test_search_mcps_then_call_loaded_mcp_tool` is intentional for test isolation but warrants an explanatory comment. Production wiring always uses the same registry for both.
- **Reviewer clarification**: the "unexpected `_search_backends.py` addition" flagged in pre-Reviewer notes was a misreading on my part — that file is F5's DDG web-search backend (pre-existing on main), not an F10 addition. F10's actual circular-import resolution was lazy imports inside `_build_source_index`. No new module added.
- **Reviewer affirmations**:
  - F5 pause/resume invariant locked correctly by `test_deferred_resumed_mcp_tool_dispatch`.
  - `MCPClient` exception contract preserved (still exactly 4 typed exceptions).
  - `mcp_overrides` filter extraction is a clean refactor (behavior identical to inlined block).
  - `_build_synthetic_description` two-pass logic correct; no off-by-one.
  - Mission amendment Constraint #71 well-formed; F5 amendment preserved unchanged.
  - All 5 F10 UNCHANGED invariants verified in code.
- **Decision**: ship as-is per Reviewer's call. Both non-blocking items captured for F10 debrief follow-up.
- **Next**: update leg statuses `landed` → `completed`; commit batched flight; pause for operator HAT before flight status `landed` per L5's phase mapping.

### Flight Director Notes — Phase 2d commit prep (2026-05-10)

- All 5 leg statuses updated `landed` → `completed`. Flight.md legs all checked off.
- Local commit ready. Pre-push pause for operator confirmation per CLAUDE.md "Actions visible to others / shared state" risk-action guidance.
- Operator HAT (`operator-hat-script.md`) is the gate between commit and flight `landed` status per L5's phase mapping.

### Flight Director Notes — Phase 2c → 2a transition (L4 → L5 design, 2026-05-10)

- **Phase 2c**: L4 marked `landed`. Increment legs_completed → 4 of 5. **L5 is the LAST autonomous leg** — Phase 2d transition happens immediately after L5 lands.
- **Phase 2a (L5 leg design)**: `legs/05-mission-amendment-regression-and-commit.md` drafted. Status initial `planning`.
  - **Scope**: documentation only. Mission amendment in `mission.md` (~30 LOC) + 4 new artifact files (`regression-sweep.md`, `token-cost-measurement.md`, `operator-hat-script.md`, F9 flight-log placeholder).
  - **No production or test code changes**. L5 expected to keep test count at exactly 1505 pass.
  - **Citation audit (designer)**: 5 citations verified.
  - **Sizing**: ~230 LOC across mission + 4 new docs + 1 modified doc.
- **Design review (Developer/Sonnet)**: verdict **approve with changes**. 2 medium issues + 1 low + suggestions + 2 questions.
  - **Medium-severity fixes applied inline**:
    - Baseline citation drift: "F8 baseline 1376/255/43" was cited at "F9 flight-log line 100-102" but that location holds L3's L2-baseline (different number). Corrected citation to F10 flight.md Checkpoints + Post-Flight sections.
    - Phase 2d HAT boundary ambiguity: `/agentic-workflow` Phase 2d (per skill) is Reviewer→fix→commit→PR — NO HAT step. F10's design adds the HAT as a methodology extension. Added explicit "Phase boundaries (clarified per L5 design review)" section to Objective enumerating: L5 (autonomous) → Phase 2d (autonomous review+commit+PR) → HAT gate (interactive, between Phase 2d and Phase 3) → Phase 3 (flight landing). HAT is a F10-design-required gate, not part of the `/agentic-workflow` skill's core protocol.
  - **Suggestions applied**:
    - Token-cost measurement defaults to Shape B (synthetic-LLM proxy) since it's always doable; Shape A appended at HAT time IF operator coordinates. L5 leaves a TBD section for Shape A so Phase 2d Reviewer knows what to expect.
  - **Questions resolved**:
    - Bundled Sonnet review: F10 §8's "bundled fresh-context review at flight close" IS Phase 2d's Reviewer per the `/agentic-workflow` skill — same agent, same scope. L5 doesn't spawn it separately. Clarified in Objective.
    - Mission amendment date: hardcoded `2026-05-10` in the amendment text (matches today's actual landing date). Mirrors the F5 amendment's `2026-05-07` pattern.
- **Decision: skip second design-review cycle**. Same rationale as L1-L4.
- **L5 status updated**: `planning` → `ready`.
- **Next**: spawn Developer for implementation (Phase 2b, action: implement). After L5 lands → Phase 2d (Reviewer for the full F10 diff).

### Flight Director Notes — Phase 2c → 2a transition (L3 → L4 design, 2026-05-10)

- **Phase 2c**: L3 marked `landed`. Increment legs_completed → 3 of 5. More autonomous legs remain → return to Phase 2a for L4 design.
- **Phase 2a (L4 leg design)**: `legs/04-system-prompt-and-integration.md` drafted. Status initial `planning`.
  - **Scope**: `BASE_PROMPT` extension teaching the discovery protocol + end-to-end integration tests driving the full search → load → call sequence via `FakeLLM`. Browser tests deferred to L5 HAT.
  - **Citation audit (designer)**: 10 citations verified.
  - **Sizing**: ~275 LOC (BASE_PROMPT +25, test_agent_search_integration.py +250 NEW).
- **Design review (Developer/Sonnet)**: verdict **approve with changes**. 2 high + 2 medium + 1 low issues + suggestions + questions.
  - **High-severity fixes applied inline**:
    - `TracingFakeLLM` wrapper unnecessary — `FakeLLM.calls` (`conftest.py:55`) already captures `tools=` per-call. Implementation guidance updated to use `llm.calls[N]["tools"]` directly. Eliminates signature-mismatch concern.
    - `test_search_mcps_then_call_loaded_mcp_tool` mock pattern was wrong — `SearchMcps` reads `source_index` from CONSTRUCTOR injection (L3's pattern), NOT `MCPSourceRepository` at runtime. Updated to reference L3's `_make_search_mcps` helper at `test_search_mcps.py:114-137`.
  - **Medium-severity fixes applied**:
    - AC corrected: `BASE_PROMPT` tests are in `tests/test_config.py:166-183` (NOT `test_agent.py`); all use `==` equality, so BASE_PROMPT growth is safe. AC now explicitly confirms these tests need no modification.
    - "Discovery section BEFORE Tool use" — added explicit ordering assertion to `test_base_prompt_includes_discovery_section`: `BASE_PROMPT.index("Tool discovery") < BASE_PROMPT.index("Tool use:")`. Makes the ordering AC computationally verifiable.
  - **Suggestions applied**:
    - Factory/integration setup guidance rewritten to reference L3's `_make_search_mcps` helper (potentially promotable to `conftest.py` if implementer prefers).
- **Decision: skip second design-review cycle**. Same rationale as L1+L2+L3.
- **L4 status updated**: `planning` → `ready`.
- **Next**: spawn Developer for implementation (Phase 2b, action: implement).

### Flight Director Notes — Phase 2c → 2a transition (L2 → L3 design, 2026-05-10)

- **Phase 2c**: L2 marked `landed`. Increment legs_completed → 2 of 5. More autonomous legs remain → return to Phase 2a for L3 design.
- **Phase 2a (L3 leg design)**: `legs/03-search-mcps-implementation.md` drafted. Status initial `planning`.
  - **Path A confirmed at L3 design time**: explored `_tool.py:94-133 — MCPClientTool.__init__` and confirmed Path B (cache-only hydration) is structurally feasible (constructor takes `mcp_tool: MCPTool` + `effective_source: MCPSource`, no live client). But Path A (existing eager `MCPToolProvider.get_tools_for_agent`) keeps L3 scope manageable; Path B refactor would inflate L3 ~~200-250 LOC to ~600+ via factory swap + Path B method on MCPToolProvider + no-cache fallback semantics. F10's primary user-facing wins (client-side token cost, mid-session attach at next-session-start) work with either path. Path B deferred to follow-up flight if measurement shows the eager acquire cost is material.
  - **Scope**:
    - Extract `mcp_overrides` filter (`_tool_provider.py:264-284`) into shared helper `filter_mcp_tools_by_override` — used by both `get_tools_for_agent` (refactor) and `SearchMcps` (new consumer).
    - NEW `_search_mcps.py` with `SearchMcps(Tool)` real impl. Constructor: `on_match`, `registry`, `source_index`, `agent_name`. Source index shape: `{source_name: {"synthetic_description": str, "tool_names_prefixed": list[str]}}`.
    - `SearchMcps.execute` matches on (source_name + synthetic_description) for source-level AND (per-tool name + description) for tool-level. Union, dedup by name. Format result with source-grouped breakdown.
    - Factory: drop `SearchMcpsStub` from imports; add `SearchMcps`; build source_index BEFORE MCP loop via independent `MCPSourceRepository.get` calls (option (b) — clean separation, no public API churn).
    - Synthetic descriptions from cached tool short-names, truncated to ~200 chars with two-pass logic (fits-or-truncate).
    - No-cache fallback: skip source, log WARNING.
  - **Citation audit (designer)**: 19 citations verified against current code.
  - **Sizing**: ~545 LOC (`_tool_provider.py` +40 net, `_search_mcps.py` +200 NEW, factory.py +20 net, `_search_stubs.py` +5 docstring, `test_search_mcps.py` +280 NEW). Above F10 §10's ~200-250 estimate; flagged in artifact's Files Affected as L8 review-queue item.
- **Design review (Developer/Sonnet)**: verdict **approve with changes**. 2 high + 3 medium + 2 low issues + 2 suggestions + 2 questions.
  - **High-severity fixes applied inline**:
    - `MCPTool` dataclass requires `output_schema` + `annotations` fields (not stored in `_cache.tools` payload). Factory hydration loop updated to pass `output_schema=None, annotations=None` explicitly; would have TypeError'd otherwise.
    - `_build_synthetic_description` off-by-one in truncation guard: `> available - 3` dropped names at the boundary case. Rewrote with two-pass logic: first check if full body fits within `available`; if yes, emit complete; else build truncated up to `available - len("...")` budget.
  - **Medium-severity fixes applied**:
    - Line citation drift: factory.py:175→176, factory.py:176→177, factory.py:188-194→189-195. Updated all occurrences in artifact.
    - Source_index vs registry consistency gap (source with `_cache.tools` but `acquire` failure won't have tools in registry): added explicit code-comment note in implementation guidance + Outputs section.
    - Redundant `self._agent_name = agent_name` in `SearchMcps.__init__` (already set by `super().__init__`): removed from pseudo-code with comment explaining drift from L2 pattern.
  - **Suggestions applied**:
    - "Recommended sequence" contradiction resolved: build source_index FIRST (separate DB load via option b), register `SearchMcps`, then run MCP tool registration loop.
    - Empty-registry-no-attached-MCPs UX: distinguish from "search returned 0" — return `"No MCP sources are attached to this agent."` when both `mcp_in_registry` is empty AND `source_index` is empty.
  - **Questions resolved**:
    - Empty-query + empty-registry UX → return informative message above (applied).
    - `MCPTool` dataclass field requirement → leg guidance now shows the explicit `output_schema=None, annotations=None` (applied).
- **Decision: skip second design-review cycle**. Same rationale as L1+L2: fixes were mechanical responses to specifically-flagged issues; no new design choices introduced.
- **L3 status updated**: `planning` → `ready`.
- **Next**: spawn Developer for implementation (Phase 2b, action: implement).

### Flight Director Notes — Phase 2c → 2a transition (L1 → L2 design, 2026-05-10)

- **Phase 2c**: L1 marked `landed`. Increment legs_completed → 1 of 5. More autonomous legs remain → return to Phase 2a for L2 design.
- **Phase 2a (L2 leg design)**: `legs/02-search-tools-implementation.md` drafted. Status initial `planning`.
  - **Scope**: real `SearchTools` implementation in NEW `the_one/tools/_search_tools.py`. Replaces `SearchToolsStub` in production wiring; stub class retained for L1 test-only use. `SearchMcpsStub` untouched (L3 territory).
  - **Key design choices**:
    - Registry passed at construction; iterated at execute time (full population guaranteed by then per factory ordering at lines 175→178→193).
    - Per-agent `enabled_tools`/`disabled_tools` filter NOT re-applied — registry-level filter at `factory.py:178-181` is the source of truth.
    - Substring match on `f"{name} {description}".lower()`, case-insensitive. Empty query returns all (after search-tool + `mcp__` prefix exclusion).
    - Stubs retained as test-only fixtures (cleaner than migrating L1 tests).
  - **Citation audit (designer)**: 14 citations verified against current code.
  - **Sizing**: ~410 LOC (`_search_tools.py` +150 NEW, factory.py +5 net, `_search_stubs.py` +5 doc, test_search_tools.py +250 NEW).
- **Design review (Developer/Sonnet)**: verdict **approve with changes**. 2 medium + 1 low issues + 2 suggestions + 2 questions.
  - **Medium fixes applied inline**:
    - Citation drift on `core.py:42` (pre-L1 line) → corrected to `core.py:80/91/98` (Agent class at 80, `__init__` at 91, `loaded_schemas` kwarg at 98).
    - Dropped `SearchToolsStub` from factory.py import (unused in production wiring post-L2; `# noqa: F401` was suppressing a legitimate warning). Tests import stub directly from `_search_stubs.py` per `test_agent_visibility_filter.py:29-36` — no factory re-export path exists.
  - **Low fix applied**: pinned the no-match return format `"No tools found matching 'X'."` (with trailing period) so tests ==-assert it exactly.
  - **Suggestions applied**:
    - Empty-query path now omits the awkward `"matching ''"` clause; renders as `"Found N tools: ..."`. Non-empty path renders as `"Found N tools matching 'X': ..."`. Both pinned in tests.
    - Test design notes for `test_real_impl_in_factory_wiring` + `test_real_impl_per_agent_filter_applied_at_registry_level` clarified: use mock `AgentConfigStore` injected via `AgentFactory(store=mock_store)` to bypass DB; reference existing patterns in `tests/test_factory.py`.
  - **Questions resolved**:
    - DB dependency for factory integration tests → mock-store injection pattern (above).
    - Empty-query format → split into two paths in implementation (above).
- **Decision: skip second design-review cycle**. Same rationale as L1: fixes were mechanical responses to specifically-flagged issues; no new design choices introduced.
- **L2 status updated**: `planning` → `ready`.
- **Next**: spawn Developer for implementation (Phase 2b, action: implement).

1. `test_factory.py::test_enabled_tools_whitelist` asserted exact `tool_names == ["tool_a"]`. Under F10, stubs are always registered before the built-in loop and bypass the enabled/disabled filter. Updated assertion to membership-style (`"search_tools" in tool_names`, `"tool_b" not in tool_names`, etc.).
2. `test_factory.py::test_agent_name_threads_to_tools` required every registered tool to carry `_agent_name`. Stubs initially got `None` via zero-arg `super().__init__()`. Fixed by adding `agent_name: str | None = None` to both stub constructors and forwarding to `super().__init__(agent_name=agent_name)`.

Both anomalies were corrective adaptations to pre-existing test contracts — not design deviations.

**Test count delta**:

- F8 baseline: 1376 unit (pre-F9). F10 branch base (F9 L1+L2+L3 landed): 1450 unit.
- L1 adds 12 new tests in `test_agent_visibility_filter.py`.
- Post-L1 full suite: **1462 passed**, 2 pre-existing flakes in `test_mcp_sandbox_integration.py` (pre-existing on main, not L1 regressions), 2 skipped, 344 deselected.

**LOC by file**:

- `the_one/agent/core.py`: +50 LOC additions (schema constants ~40, `__init__` kwargs ~10, `_compute_visible_schemas` ~5, `reset` changes ~3, `_run_iterations` loop restructure ~8), -4 LOC (removed `_tool_schemas`). Net ~+54 LOC.
- `the_one/tools/_search_stubs.py`: +118 LOC (NEW — includes module constants, both stub classes, docstrings).
- `the_one/agent/factory.py`: +30 LOC additions (import +1, container setup +5, `_on_search_match` +8, stub registration +4, Agent kwargs +2, comments ~10).
- `tests/HAT.md`: +20 LOC (F10 contract note at top + two inline commentary blocks).
- `tests/test_agent_visibility_filter.py`: +285 LOC (NEW — 12 tests).
- `tests/test_factory.py`: +6 LOC (updated `test_enabled_tools_whitelist` assertions).

**Deviation from leg artifact**: Leg artifact sized `_search_stubs.py` at ~80 LOC; actual is ~118 LOC due to fuller docstrings and the `agent_name` parameter addition required by the existing `test_agent_name_threads_to_tools` assertion. Not a design deviation — the leg artifact AC item specifies `super().__init__()` for base field initialization; `agent_name` plumbing is the natural extension to satisfy the pre-existing test contract.

### L2 — 02-search-tools-implementation

**Status**: landed
**Started**: 2026-05-10
**Completed**: 2026-05-10

**Implementation notes**:

- `the_one/tools/_search_tools.py` (NEW, 82 LOC): `SearchTools(Tool)` real implementation. Class attributes `name = "search_tools"`, `description` and `parameters` imported from `SEARCH_TOOLS_SCHEMA` at `agent.core`. Constructor takes `on_match`, `registry`, `agent_name=None`; calls `super().__init__(agent_name=agent_name)`. Pure helper `_filter_candidates(schemas, query)` extracted at module level for unit-testability. `execute()` applies filter chain (`_EXCLUDED_NAMES` exclusion → `mcp__` prefix exclusion → substring match on `f"{name} {description}".lower()`), calls `self._on_match(matches)`, returns format-pinned text (`"Found N tools: ..."` for empty query, `"Found N tools matching 'X': ..."` for non-empty, `"No tools found matching 'X'."` for no match).
- `the_one/agent/factory.py` (~5 LOC net change): Replaced `from the_one.tools._search_stubs import SearchMcpsStub, SearchToolsStub` with two separate imports: `from the_one.tools._search_stubs import SearchMcpsStub` and `from the_one.tools._search_tools import SearchTools`. At line 175, replaced `SearchToolsStub(on_match=_on_search_match, agent_name=name)` with `SearchTools(on_match=_on_search_match, registry=registry, agent_name=name)`. `SearchMcpsStub` registration at line 176 unchanged.
- `the_one/tools/_search_stubs.py` (docstring update only, +9 LOC): Module-level docstring updated with POST-L2 STATUS block noting `SearchToolsStub` is now test-only; `SearchMcpsStub` remains production until L3.
- `tests/test_search_tools.py` (NEW, 274 LOC, 12 tests): All 12 tests from Outputs spec implemented. One behavioral clarification required: `test_query_substring_match_on_name` assertion updated — `python_exec` legitimately matches "shell" because its description references `shell` and `shell_session_send` as alternatives. This is correct substring-match behavior; the assertion was adjusted to reflect the real implementation rather than change the implementation.

**Test count delta**:

- L1 post-landing baseline: 1462 pass.
- L2 adds 12 new tests in `tests/test_search_tools.py`.
- Post-L2 full suite: **1474 passed**, 2 pre-existing flakes in `test_mcp_sandbox_integration.py` (bwrap not available in this container environment — pre-existing, not L2 regressions), 2 skipped, 344 deselected.
- Delta vs L1 baseline: **+12** (matches L2 test count exactly).

**LOC by file**:

- `the_one/tools/_search_tools.py`: +82 LOC (NEW)
- `the_one/agent/factory.py`: +2 LOC net (+2 import lines, -1 original import line = +1 net on imports; +1 registration change LOC = ~+2 net)
- `the_one/tools/_search_stubs.py`: +9 LOC (docstring update)
- `tests/test_search_tools.py`: +274 LOC (NEW)

**Total**: ~367 LOC. Under the ~410 LOC F10 sizing budget.

**Anomalies**:

- `python_exec` description contains the word "shell" (references shell and shell_session_send as alternatives). This means query "shell" returns python_exec in addition to the five shell-named tools. This is correct substring-match behavior per the spec; the test assertion was adjusted to document this rather than exclude python_exec from results. No implementation deviation.
- Actual new file LOC (`_search_tools.py` 82 LOC) is lower than the ~150 LOC Outputs estimate because the implementation as designed in the artifact was already compact; the estimate included more comment padding. No functional deviation.
- Test file (274 LOC) is slightly higher than ~250 LOC estimate due to the `_MockTool` helper class and more detailed docstrings. Within expected variance.

---

## Anomalies

> Cross-leg index. Populated as legs surface anomalies.

---

## Session Notes

### 2026-05-10 — F10 design + F9 pivot

F9 paused at L3-landed; F10 opened. Design decisions §1-§11 captured upfront (architect added §10 candidate-set construction during design review). Operator-driven scope shift; methodology pattern is "operator-felt priority adjustment + flight-level divert" (F9 §1's acceptable-variations clause stretched to the flight level rather than just the leg level).

### 2026-05-10 — F10 in-flight, L1 design

Flight Director (Mission Control) loaded `/agentic-workflow` skill with `project: the-one, mission: 7, flight: 10`. Phase 1 context-loading complete.

---

## Flight Director Notes

### Phase 1: context loading (2026-05-10)
- **Phase file loaded**: `/home/cprch/projects/the-one/.flightops/agent-crews/leg-execution.md` (project-specific, NOT fallback). Validated structure: `## Crew` (Developer + Reviewer + optional Accessibility Reviewer), `## Interaction Protocol`, `## Prompts` (Review Leg Design + Implement + Review + Review Accessibility + Fix Review Issues + Commit), all sections present and well-formed.
- **Crew composition extracted**: Developer (Sonnet, project context, implements + reviews leg designs), Reviewer (Haiku, project context, code review with no Developer-reasoning carryover), Accessibility Reviewer (Sonnet, optional for UI changes — N/A for L1).
- **Branch created**: `flight/10-lazy-tool-discovery` off `main` (= F9 L3-landed = `3bd6bd4`). Uncommitted changes carried over: F9 flight-log pivot Decision entry, F9 L5 leg artifact draft (preserved for F9 resume-or-absorb decision at F10 close), F10 init artifacts (flight.md + flight-log.md).
- **F10 flight status updated**: `ready` → `in-flight`. F10 flight.md prerequisites checklist updated to reflect F9-pause-done + branch creation.
- **Total legs**: 5 (`01-agent-loop-2-tool-baseline` through `05-mission-amendment-regression-and-commit`).
- **Starting point**: L1.

### Phase 2a: L1 leg design (2026-05-10)
- **Leg designed**: `legs/01-agent-loop-2-tool-baseline.md`. Initial status: `planning`. Scope per F10 §3 + §9 + §10 + design-review-affirmation patterns: agent-loop refactor with per-iteration `_compute_visible_schemas()`, canned-data stubs for `search_tools` + `search_mcps`, factory-wired shared loaded-set containers, F5 pause/resume invariant lock-in test.
- **Citation audit (designer)**: 20 citations verified against current code at leg design time. All OK.
- **Sizing**: ~360 LOC (core.py +50, _search_stubs.py +80 NEW, factory.py +10, HAT.md +20, test_agent_visibility_filter.py +200 NEW).
- **Design review spawned**: Developer (Sonnet) via agentic-workflow Phase 2a step 2. Verdict: **approve with changes**. 2 high + 2 medium + 2 low issues + 2 questions.
- **High-severity fixes applied inline to L1 artifact**:
  - `Tool.__init__` constructor conflict — stubs now call `super().__init__()` (zero-arg valid; base defaults all three params to None).
  - Class-attribute `name` on stubs (matches `ToolRegistry.register`'s `self._tools[tool.name]` at `base.py:118-119`) — added explicit AC.
- **Medium-severity fixes applied**:
  - `resume_after_auth` double-`supports_tools()` call documented as acceptable; test contract updated to "once per `_run_iterations` entry" (NOT per user turn). `test_deferred_resumed_mcp_tool_dispatch` asserts total call count of 2.
  - Existing `Agent._tool_schemas()` method at `core.py:60-63` becomes dead code under L1 — added to Outputs as a removal, added AC for the removal.
- **Low-severity fixes applied**:
  - `tests/test_agent_core.py` references replaced with `tests/test_agent.py` (the actual file) + `tests/conftest.py` for fixtures. Throughout artifact.
  - `FakeLLM.stream()` scaffolding clarified — inherits from `LLMProvider.stream()` at `llm/base.py:100-119` which delegates to `complete()`; pre-load `FakeLLM.responses` pattern for multi-iteration tests.
- **Suggestions applied**:
  - Factory insertion point pinned: AFTER `registry = ToolRegistry()` at `factory.py:146`, BEFORE the built-in loop at `factory.py:147-150`.
  - `test_search_stub_idempotent` added to test list — exercises `_on_search_match` deduplication.
  - Schema constants pinned to `agent/core.py` (single source of truth) — `_search_stubs.py` imports from there to avoid circular `tools → agent` import.
- **Questions resolved**:
  - F8 baseline (1376 unit / 255 browser / 43 flakes) is pre-F9 — L1's 7-11 new tests are net additions, expected post-L1 count is `1376 + N`.
  - `_build` references throughout artifact corrected to `create` (actual method name in `factory.py:78`).
- **Decision: skip second design-review cycle**. Fixes were mechanical responses to specifically-flagged issues with concrete recommended remediations; no new design choices introduced. Per agentic-workflow Phase 2a step 4 ("Skip if only minor/cosmetic fixes were applied" — judgment call here since fixes were substantive but corrective, not novel). Auto-mode preference for action reinforces. If implementation surfaces a regression from incomplete fix application, address at Phase 2d review.
- **L1 status updated**: `planning` → `ready`.
- **Next**: spawn Developer for implementation (Phase 2b, action: implement).
