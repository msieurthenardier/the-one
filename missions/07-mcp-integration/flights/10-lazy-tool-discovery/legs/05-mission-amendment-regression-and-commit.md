# Leg: 05-mission-amendment-regression-and-commit

**Status**: completed
**Flight**: [Lazy tool discovery](../flight.md)

## Objective

Close F10 by landing the formal mission constraint amendment in `mission.md` (per F10 §7), running the final regression sweep against the F8 baseline (1376 unit / 255 browser / 43 pre-existing flakes), and capturing the token-cost baseline-vs-after measurement deferred to L5 per F10's architect review. L5 also drafts the operator HAT script that will be walked through interactively.

**Phase boundaries (clarified per L5 design review)**:
- **L5 (this leg, autonomous)**: lands the mission amendment + regression sweep + token-cost measurement (Shape B by default; Shape A added if operator is present at HAT time) + HAT script draft + F9 placeholder.
- **Phase 2d (autonomous per `/agentic-workflow` skill)**: spawns a fresh-context Sonnet Reviewer over the full F10 diff (this IS F10 §8's "bundled fresh-context review at flight close" — same agent, same scope). Fixes any issues via Developer loop. Commits. Opens draft PR.
- **HAT gate (interactive, BETWEEN Phase 2d PR draft and Phase 3 flight landing)**: Flight Director walks the operator through `operator-hat-script.md` AFTER the autonomous commit but BEFORE marking the flight `landed`. This is a Flight-Control-methodology addition not formally specified in the `/agentic-workflow` skill's Phase 2d/3 sequence — F10's design includes the HAT as a required acceptance gate. If the HAT surfaces a defect, the Flight Director iterates (potentially un-merging the PR or appending a follow-up commit) before flight landing.
- **Phase 3 (autonomous)**: verifies all legs `completed`, updates flight status to `landed`, checks off flight in mission, signals `[COMPLETE:flight]`. Operates only if HAT passes.

This phase mapping keeps L5 lightweight (mostly documentation) while preserving the operator-felt acceptance gate F10's design requires.

## Context

- **F10 §7 (mission constraint amendment)** — `mission.md`'s Constraint #71 ("Agent-loop semantic changes are limited to a documented pause/resume primitive (F5 amendment)") currently sanctions ONE loop-level extension (F5's pause/resume). F10 introduces a SECOND: session-scoped mutable loaded-schema set + 2-tool baseline catalog + per-iteration recompute. L5 amends the constraint with explicit "UNCHANGED" enumeration of the existing invariants AND the new F10 clause.
- **F10 §8 (single bundled fresh-context review at flight close)** — the F6.6 + F8 precedent: a clean-context Sonnet reviewer catches blind spots the iterative implementers miss. F10's bundled review happens at Phase 2d; L5's role is to make sure the diff is REVIEWABLE (regression sweep clean, no half-finished work, all artifacts in sync).
- **F10 architect review carry-forward (L5 medium-priority)** — capture iteration count + total prompt-tokens for a representative HAT scenario before-and-after F10 (run scenario against pre-F10 `main` then post-F10 branch). Report deltas in debrief. L5 captures the post-F10 measurement; the pre-F10 number is in F9 L3's landing state on main (or can be reconstructed by re-running against main).
- **F10 architect review carry-forward (L5 HAT prose)** — the operator-felt HAT scenario explicitly calls out the new model: operator should see the agent SEARCH after attach, NOT immediate tool availability. This is consistent with F10's design but operators trained on F1-F9's eager-load model may read it as a regression on first encounter. L5 drafts the HAT prose; Phase 2d walks the operator through it.
- **F9 resume-or-absorb decision** — F9 paused at L3-landed per F10 §11. Decision at F10 close (Phase 2d-adjacent): does F9 resume with L5/L6/L7 reframed under the new architecture, or absorb the remaining vibing into a successor flight (or M08)? L5 captures the operator's stated preference but does NOT execute the F9 resume — that's a separate flight.
- **Studio UI relabel deferral** — F10 §8 defers Studio UI semantics changes ("Allowed tools" / "Allowed MCPs" + chat-time loaded indicator). L5 confirms the deferral remains acceptable post-implementation (no UI test failures masking semantic-mismatch issues).
- **L1+L2+L3+L4 outcome carry-forward**:
  - All four implementation legs `landed` (uncommitted in working tree).
  - Full unit suite at 1505 pass post-L4 (1498 L3 baseline + 7 L4 integration tests).
  - F10 net additions: ~1640 LOC across `agent/core.py` (+54), `tools/_search_stubs.py` (+118 NEW), `tools/_search_tools.py` (+82 NEW), `tools/_search_mcps.py` (+205 NEW), `agent/factory.py` (+85 net), `agent/config.py` (+17), `mcp/_tool_provider.py` (+40 net), `tests/test_agent_visibility_filter.py` (+285 NEW), `tests/test_search_tools.py` (+274 NEW), `tests/test_search_mcps.py` (+305 NEW), `tests/test_agent_search_integration.py` (+255 NEW), plus smaller updates to `tests/HAT.md`, `tests/test_factory.py`, `tests/test_config.py` (via L4 audit, unchanged).

## Inputs

What exists before this leg runs:

- L1+L2+L3+L4 landed (uncommitted in working tree). Full unit suite at 1505 pass.
- `missions/07-mcp-integration/mission.md:71` — Constraint #71 in the current text, ending: "...further pause/resume primitives need explicit mission-constraint amendment".
- `the_one/agent/config.py:BASE_PROMPT` (post-L4) — includes "Tool discovery" section.
- F8 baseline reference: 1376 unit / 255 browser / 43 pre-existing flakes (per F10 flight.md's Checkpoints + Post-Flight sections; same number reiterated in F10 flight-log around the design-review discussion of cumulative-LOC discipline).
- F10 branch `flight/10-lazy-tool-discovery` checked out off `main`.
- Pre-existing `tests/test_mcp_sandbox_integration.py` 2-test flake (confirmed pre-existing on main; not F10-introduced).

## Outputs

What exists after this leg completes:

- **MODIFIED**: `missions/07-mcp-integration/mission.md` (~30 LOC addition):
  - Constraint #71 amended with the F10 NEW clause. The amendment preserves the existing constraint phrasing as-is and adds F10's extension as a second amendment block (mirroring the F5 amendment format already in place):
    ```
    **F10 amendment (2026-05-10)**: F10 introduces a SECOND sanctioned
    loop-level extension — session-scoped lazy tool discovery. Agents
    may carry a per-instance `_loaded_schemas: list[dict]` +
    `_loaded_tool_names: set[str]` visibility filter; the catalog
    presented to the LLM is `[search_tools, search_mcps, continue] +
    loaded_schemas` per iteration; the `search_*` tools mutate the
    loaded set as a side effect of being called. The following remain
    UNCHANGED from F1-F9:
    - Agent dispatches by tool name via `self.tools.get(name)`.
    - Iteration cap (`max_iterations`) semantics.
    - `continue`-tool turn-keeping signal.
    - Capability-gate fallback (no-tool-support providers run plain chat).
    - F5's pause/resume primitive (`auth_required` → modal → resume).
    Further loop-level extensions still need explicit mission-constraint
    amendment.
    ```
- **NEW** (or MODIFIED if exists): `missions/07-mcp-integration/flights/10-lazy-tool-discovery/regression-sweep.md` (~80 LOC):
  - Captures the regression sweep results in a structured format Phase 2d's Reviewer can read.
  - Unit suite count + delta vs F8 baseline + pre-existing flakes audit.
  - Browser suite count + delta vs F8 baseline + flake audit.
  - Any net-new failures explicitly enumerated (target: zero).
  - Pre-existing `test_mcp_sandbox_integration.py` 2-test flake confirmed unchanged (bwrap unavailable in test container; existed pre-F10).
- **NEW**: `missions/07-mcp-integration/flights/10-lazy-tool-discovery/token-cost-measurement.md` (~50 LOC):
  - **L5 default: Shape B (synthetic-LLM proxy)** — always doable without operator coordination. Use a scripted `FakeLLM` scenario that simulates the same tool-call sequence pre-F10 (full eager-load catalog) and post-F10 (2-tool baseline + `search_mcps`-triggered load). Count schemas in each iteration's `tools=` via `FakeLLM.calls`; multiply by per-schema-token estimate (~50-200 tokens per schema). Report estimated delta.
  - **Shape A (real-LLM, operator-coordinated)** — appended at HAT time IF the operator runs the measurement on real provider + real Cloudflare API MCP. L5 leaves a clearly-marked Shape A section reading "TBD — pending operator coordination at HAT time" so Phase 2d Reviewer knows what to expect.
  - F10 §1 noted that token-cost-worse-than-baseline doesn't gate the flight (the mid-session-attach + architectural-shift wins justify ship); the measurement is signal for follow-up tuning.
- **NEW**: `missions/07-mcp-integration/flights/10-lazy-tool-discovery/operator-hat-script.md` (~60 LOC):
  - Operator-facing HAT script Phase 2d walks through.
  - Step 1: confirm dev container + a default agent + an attached MCP source (or instructions to set one up).
  - Step 2: start chat session; send "what tools do you have available?". Verify: agent calls `search_tools("")` first iteration, then `search_mcps("")`, then synthesizes a list response. **Operator-felt callout**: this is the NEW model — agent searches before listing. NOT a regression.
  - Step 3: from another browser tab, attach a NEW MCP source to the same agent. Start a NEW chat session with that agent. Send the same prompt. Verify: agent's `search_mcps("")` result includes the newly-attached source's tools.
  - Step 4: in the existing (pre-attach) session, repeat the question. Verify: the new source is NOT visible (per F10 design — sessions don't refresh mid-session; new session required). Operator confirms this behavior is expected.
  - Step 5: confirm caplog clean across the HAT (`docker compose logs --tail 200 the-one 2>&1 | grep -c "MCPClient.disconnect"` = 0).
- **MODIFIED**: `missions/07-mcp-integration/flights/09-alignment/flight-log.md` (~10 LOC):
  - Append F9 resume-or-absorb decision capture. The actual decision (resume L5/L6/L7 under the new architecture, or absorb into M08, or abort) is operator-facing at F10 close; L5 records the operator's stated preference at HAT time.

## Acceptance Criteria

- [ ] `mission.md:71` (Constraint #71) amended with the F10 amendment block per Outputs format. Preserves existing F5 amendment phrasing unchanged.
- [ ] The F10 amendment block enumerates ALL 5 "UNCHANGED" invariants (dispatch by tool name, iteration cap, continue-tool, capability-gate fallback, F5 pause/resume) AND the F10 NEW clause.
- [ ] `regression-sweep.md` created with unit + browser counts and delta-to-F8-baseline verified. Net-new failures count = 0.
- [ ] `token-cost-measurement.md` created with pre-F10 vs post-F10 numbers. If operator coordination is unavailable for real-LLM measurement, the file explicitly documents which measurement was substituted and why.
- [ ] `operator-hat-script.md` created with all 5 steps + the operator-felt callout for Step 2 + caplog gate.
- [ ] F9 flight log appended with the F9 resume-or-absorb decision capture (placeholder text; actual decision captured at Phase 2d HAT time).
- [ ] All L1-L4 tests pass UNMODIFIED.
- [ ] Full unit suite passes: `docker exec the-one pytest -q --timeout 120 --ignore=tests/test_mcp_pool.py`. Expected: 1505 pass (+0 from L4; L5 adds documentation artifacts only, no production or test code changes).
- [ ] Full browser suite passes: `docker exec the-one pytest tests/browser/ -q --timeout 120 -m browser`. Expected: 255 pass / 43 pre-existing flakes (matches F8 baseline).
- [ ] Caplog gate clean: `docker compose logs --tail 200 the-one 2>&1 | grep -c "MCPClient.disconnect"` = 0 across the verification run.
- [ ] L5 status updated to `landed`.

## Verification Steps

- Read the amended `mission.md:71` block end-to-end. Confirm: F10 amendment text reads cleanly; preserves F5 amendment unchanged; the 5 UNCHANGED invariants are enumerated; the F10 NEW clause is precise.
- Run unit suite: `docker exec the-one pytest -q --timeout 120 --ignore=tests/test_mcp_pool.py`. Capture pass count + any failures. Diff against F8 baseline (1376) + L4's post-landing count (1505).
- Run browser suite: `docker exec the-one pytest tests/browser/ -q --timeout 120 -m browser`. Capture pass count + flakes. Diff against F8 baseline (255 / 43).
- Caplog check: `docker compose logs --tail 500 the-one 2>&1 | grep -c "MCPClient.disconnect"`. Expect 0.
- For `token-cost-measurement.md`: if the operator has a viable measurement scenario available, run it. If not, document the synthetic-LLM proxy (e.g., a `FakeLLM`-based scenario approximating real model behavior) used as substitute.

## Implementation Guidance

### Mission constraint amendment

Read `mission.md:71` for the current Constraint #71 text. Identify where the existing F5 amendment text ends. Insert the F10 amendment block immediately after F5's amendment, NOT replacing it. The F5 amendment is preserved as-is; F10 is additive.

Suggested layout:

```markdown
- **Agent-loop semantic changes are limited to a documented pause/resume primitive (F5 amendment)**: ...
  [Existing F5 amendment text — preserve as-is]
  
  **F10 amendment (2026-05-10)**: F10 introduces a SECOND sanctioned loop-level extension — session-scoped lazy tool discovery. Agents may carry a per-instance `_loaded_schemas: list[dict]` + `_loaded_tool_names: set[str]` visibility filter; the catalog presented to the LLM is `[search_tools, search_mcps, continue] + loaded_schemas` per iteration; the `search_*` tools mutate the loaded set as a side effect of being called. The following remain UNCHANGED from F1-F9:
  - Agent dispatches by tool name via `self.tools.get(name)`.
  - Iteration cap (`max_iterations`) semantics.
  - `continue`-tool turn-keeping signal.
  - Capability-gate fallback (no-tool-support providers run plain chat).
  - F5's pause/resume primitive (`auth_required` → modal → resume).
  Further loop-level extensions still need explicit mission-constraint amendment.
```

### Regression sweep — automated capture

Run the full unit + browser suites; capture the output into `regression-sweep.md`:

```markdown
# F10 Regression Sweep

**Date**: 2026-05-10
**Flight**: F10 (Lazy tool discovery)
**Baseline**: F8 (1376 unit / 255 browser / 43 pre-existing browser flakes)
**L4 post-landing baseline**: 1505 unit (1376 + 129 net new across F9 L1-L3 + F10 L1-L4)

## Unit suite

Command: `docker exec the-one pytest -q --timeout 120 --ignore=tests/test_mcp_pool.py`

**Result**: {N} pass / {N} fail / {N} skip / {N} deselect
**Delta vs L4 baseline**: {±N}
**Net-new failures since F8 baseline**: {0 or list with file:test_name}
**Pre-existing flakes confirmed unchanged**:
- `tests/test_mcp_sandbox_integration.py::{2 test names}` — bwrap unavailable in test container; pre-existing on main.

## Browser suite

Command: `docker exec the-one pytest tests/browser/ -q --timeout 120 -m browser`

**Result**: {N} pass / {N} fail (flake) / {N} skip
**Delta vs F8 baseline (255 / 43)**: {±N}
**Net-new failures**: {0 or list}

## Caplog gate

Command: `docker compose logs --tail 500 the-one 2>&1 | grep -c "MCPClient.disconnect"`
**Result**: {N}
**Target**: 0
```

### Token-cost measurement

Two viable shapes — pick based on operator availability at HAT time:

**Shape A (real-LLM, operator-coordinated)**:
1. Pre-F10 baseline: check out `main`. Start dev container. With operator: start a chat session, attach cloudflare_api MCP source to a default agent, send `"list my Cloudflare zones"`. Inspect telemetry overlay or backend logs for: iteration count + total input tokens for the user turn.
2. Post-F10: check out `flight/10-lazy-tool-discovery`. Repeat the same scenario. Capture same metrics.
3. Report delta in `token-cost-measurement.md`.

**Shape B (synthetic-LLM proxy)**:
1. Use a scripted `FakeLLM` scenario that simulates the same tool-call sequence:
   - Pre-F10: scripted with full eager-load catalog (mock all `cloudflare_api` tools + built-ins in the initial `tools=`).
   - Post-F10: scripted with the 2-tool baseline + simulated `search_mcps("cloudflare")` call adding the relevant tools.
2. Count the schemas in each iteration's `tools=` (via `FakeLLM.calls`); multiply by per-schema-token estimate (~50-200 tokens per schema for typical MCP tool descriptions).
3. Report estimated delta.

Shape A is higher-signal but requires operator coordination. Shape B is a backup if operator is unavailable. Document which was used.

### Operator HAT script

Draft `operator-hat-script.md` per the 5-step structure in Outputs. Phase 2d walks the operator through the script; L5's job is just authoring the prose.

### F9 flight log update

Append a placeholder entry to `missions/07-mcp-integration/flights/09-alignment/flight-log.md` under Decisions:

```markdown
### F9 resume-or-absorb decision (capture pending at F10 close — 2026-05-10)
**Context**: F9 paused at L3-landed per the F9→F10 pivot Decision above. F10 closes with L5 landing. Operator must decide whether F9's remaining legs (L5/L6/L7/L8) resume under the new lazy-discovery architecture, absorb into a successor mission (M08), or abort with the remaining work captured as M07 known issues.
**Decision**: TBD at F10 close (operator-facing).
**Impact**: tracked here; will be amended with the actual decision at F10 close.
```

The actual decision is captured at Phase 2d HAT time.

## Edge Cases

- **Unit test count delta not exactly +0 vs L4 post-landing**: L5 should add ZERO new code tests (only documentation artifacts). If the count changes, investigate — likely a regression in L1-L4 that surfaced only at full-suite run time.
- **Browser test flake count differs from F8 baseline of 43**: re-run with a delay; flakes are non-deterministic. Three consecutive runs at the same count is the gate. Document if persistent diff.
- **Mission amendment text conflicts with future F11+ amendments**: F10 amendment is final-form for F10's scope. Future flights amend by appending a similar block, preserving F10's amendment unchanged.
- **Pre-existing `test_mcp_sandbox_integration.py` flakes count drops below 2 (i.e., a flake test passes unexpectedly)**: not a regression; just a flake. Note in regression-sweep.md as observation.
- **Token-cost measurement Shape B substituted because operator unavailable**: document explicitly in `token-cost-measurement.md`. Phase 2d's Reviewer should know the measurement is a proxy, not a real-LLM number.

## Files Affected

- `missions/07-mcp-integration/mission.md` — ~30 LOC amendment to Constraint #71
- `missions/07-mcp-integration/flights/10-lazy-tool-discovery/regression-sweep.md` — NEW ~80 LOC
- `missions/07-mcp-integration/flights/10-lazy-tool-discovery/token-cost-measurement.md` — NEW ~50 LOC
- `missions/07-mcp-integration/flights/10-lazy-tool-discovery/operator-hat-script.md` — NEW ~60 LOC
- `missions/07-mcp-integration/flights/09-alignment/flight-log.md` — ~10 LOC placeholder Decision entry

**Total**: ~230 LOC across mission + 4 new docs + 1 modified doc. Pure documentation; no production code, no test code changes.

## Citation Audit

Citations verified against current code at L5 design time (2026-05-10):

- `missions/07-mcp-integration/mission.md:71` — Constraint #71 (Agent-loop semantic changes with F5 amendment) ✓ verified
- `the_one/agent/config.py:BASE_PROMPT` — post-L4 with "Tool discovery" section ✓ verified (L4-landed)
- `the_one/agent/core.py:_compute_visible_schemas` ✓ verified (L1-landed)
- `tests/test_mcp_sandbox_integration.py` — pre-existing flakes (2 tests, bwrap unavailable in container) ✓ verified
- F8 baseline reference (1376 unit / 255 browser / 43 flakes) ✓ verified per F10 flight.md Checkpoints + Post-Flight sections (NOT F9 flight-log line 100-102 — that's L3's L2-baseline statement, different number; corrected at design review time)

**Audit summary**: 5 citations verified against current code at leg design time. 5 OK, 0 drifted, 0 gone, 0 unverifiable.

---

## Post-Completion Checklist

**Complete ALL steps before marking leg `landed`:**

- [ ] All acceptance criteria verified
- [ ] Mission amendment text reviewed; F5 amendment preserved unchanged.
- [ ] Regression sweep results captured in `regression-sweep.md`.
- [ ] Token-cost measurement captured in `token-cost-measurement.md` (Shape A or Shape B documented).
- [ ] Operator HAT script drafted in `operator-hat-script.md`.
- [ ] F9 flight log updated with placeholder for resume-or-absorb decision.
- [ ] Update flight-log.md with L5 leg progress entry under "Leg Progress" section.
- [ ] Set this leg's status to `landed` (NOT `completed` — completion happens at Phase 2d after the bundled review + HAT + commit).
- [ ] Check off this leg in flight.md Legs list.
- [ ] **Do NOT commit yet** — per the Objective's phase mapping: Phase 2d Reviewer runs first (autonomous; bundled Sonnet review per F10 §8), commit + PR draft, THEN HAT gate (interactive, Flight Director + operator), THEN Phase 3 flight landing. L5 stays uncommitted until Phase 2d's autonomous commit batches the whole flight.
- [ ] **Do NOT signal `[HANDOFF:review-needed]`** — Phase 2d transition is handled by the Flight Director observing all 5 legs landed.
