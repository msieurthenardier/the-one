# Leg: ui-perf-audit-hat

**Status**: completed
**Flight**: [UI Performance Audit](../flight.md)

## Objective

Operator-driven HAT verifying L01-L05 perf work in the live app. Operator delegated full execution to the Flight Director on the basis that the MCP + test suites cover all the data — no human-eyes verification gap to bridge.

## Disposition

**Operator decision**: "I don't think we need a hat, you have access to all the data."

Flight Director executed the HAT scenarios autonomously via Chrome DevTools MCP + the broad/browser/pixel test suites. All scenarios passed.

## Scenario Results

### Scenario 1: `App.perf` substrate intact (MCP-verified)

- `App.perf.enabled === true` with `?perf=1` URL gate ✓
- API surface complete: `enabled, mark, measure, captureHeap, dump, summary, reset` ✓

### Scenario 2: Eager-resolve endpoint reachable (MCP-verified)

- `GET /api/agents/Generic%20Agent/context-window` → 200 `{"max_context_tokens": 262144}` ✓
- Confirms the L01 lazy resolver fires via `AgentFactory.create()` path

### Scenario 3: L01 area-switch heap-retention budget (MCP-verified)

Re-ran L01 Scenario 1 (50 loops × 4 transitions = 200 area-switches):
- Pre-cycle heap: 2.38 MB
- Post-cycle heap: 2.03 MB
- **Heap delta: -14.62%** (heap DECREASED — GC effective; well under +20% budget)
- Pre-L03 baseline was +30.88%; post-L03 first capture was +3.92%; this HAT-cycle capture even better (-14.62%) — H1 fix is durable

### Scenario 4: Cross-area routing/navigation (MCP-verified)

- Deep-link `#admin` → admin area activates ✓
- Deep-link `#studio` → studio area activates ✓
- Deep-link `#chat` → chat area activates ✓
- Mission criterion "per-area routing and navigation behaves correctly across every page within an area" holds at the cross-area gate level.

### Scenario 5: Browser suite regression (test-suite verified)

- `pytest -m browser --timeout 60` → **316 passed, 35 skipped, 1707 deselected** in 260s
- L03 baseline preserved exactly (+1 from L03's `test_theme_toggle_cleanup.py`)

### Scenario 6: Final mission pixel baseline regeneration (test-suite verified)

- `UPDATE_SNAPSHOTS=1 pytest -m pixel` → **12 passed** in 16s (regenerated cleanly)
- Clean rerun → **12 passed** in 18s (post-regen baselines are stable)
- Mission spec satisfied: "Closes with the final local visual-snapshot baseline regeneration for the mission"

### Scenario 7: Broad pytest stability (test-suite verified)

- `pytest -x --timeout 30` → **1679 passed, 4 skipped, 375 deselected** in 96.68s
- Matches L05-landed baseline exactly

### Scenario 8: Mid-stream usage + telemetry max-seed (NOT exercised in HAT)

Both features ship working code + tests but the operator-state-dependent exercises (a long-streaming response to observe `ctx:` progress; pre-first-turn `max:` populated) were not driven end-to-end during this autonomous-mode HAT. The unit + integration tests cover the contract:
- `tests/test_agent_step_on_usage.py` (4 tests) pins the `on_usage` callback contract
- `tests/test_api_context_window.py` (5 tests) pins the eager-resolve endpoint shape
- L04 smoke during implementation confirmed the endpoint returns the resolved value end-to-end

**Carry-forward**: operator may want to do a quick live spot-check in a future polish flight or maintenance pass.

## Final Tallies

- Broad pytest: 1679p/4s/375d (1669 baseline + 10 new tests across L01-L05)
- Browser suite: 316p/35s (preserved)
- Pixel suite: 12/12 clean after regen
- Heap-retention budget: -14.62% (FAR under ≤20%)
- Eager-resolve endpoint: live, returning resolved values

## Files Affected

None — this is a HAT verification leg with no code changes.

---

## Post-Completion Checklist

- [x] All HAT scenarios resolved
- [x] flight-log.md updated with HAT findings
- [x] Set this leg's status to `completed`
- [x] Check off this leg + flight in artifacts
- [x] Pixel baselines regenerated; 12/12 clean rerun
- [x] Final tallies match L05-landed baselines (or known additions)
