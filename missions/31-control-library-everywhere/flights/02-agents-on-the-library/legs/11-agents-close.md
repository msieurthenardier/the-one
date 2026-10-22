# Leg: agents-close

**Status**: completed
**Flight**: [Agents on the library](../flight.md)

## Objective
Close Flight 2:
- confirm every agent-editor file is at zero sinks and zero allowance rows, and fix any stragglers;
- remove dead agent-tab CSS;
- take the "after" capture set and compare it with the "before" set;
- re-measure and re-budget the browser lanes (squawk 0217);
- run the full gate;
- bring the docs and the catalogue to the flight's final state.

## Context
- **Flight decisions:** DD10 (captures, budgets, the test contract), plus the Verification section of `flight.md`.
- **Legs 01-10c have landed** (01-08a committed in 54112f5 and the main merge 5ad49a1; 08b-10c uncommitted). Read every flight-log entry, especially the allowance deltas, the logged rises with their reasons, each leg's capture-difference list, and the Flight Director Notes.
- **Measured lane times this flight:** `agents` 547-578 s (budget 510), the others within budget. Squawk 0229 (`test_agent_save_never_steals_focus_the_user_moved`) is a known flake that has not recurred since 07b.
- **Run the capture tool with `.venv/bin/python`** (system `python3` lacks `tzlocal`).
- **Squawk 0217's evidence has drifted.** The budget table is `scripts/run-tests.sh` (`[agents]=510`, `[shared]=300`; about 25% headroom, rounded to 30 s). CLAUDE.md's table reads 510/497 and 300/286. `tests/test_run_tests_lanes.py` pins the table and the schedule order.

## Acceptance Criteria
- [ ] **No rows.** These files have no rows in `HTML_SINK_ALLOWANCE`, `DYNAMIC_SINK_BASELINE` or `OWNERSHIP_ALLOWANCE`:
  - `studio.js` and every studio module created in legs 02a, 02b and 03;
  - `agent-editor.js`, `general-tab.js`, `rules-notes-tab.js`, `tools-tab.js`, `mcps-tab.js`, `knowledge-tab.js`;
  - the self-configuration modules.

  Any straggler is fixed in this leg.
- [ ] **No styling through testids.** Leg 10c styles the Rules and notes empty-state roots with `[data-testid="rules-empty"]` and `[data-testid="notes-empty"]` in `css/studio.css`, to avoid naming the library's owned `.empty-state` class. Testids are test hooks, never style hooks. Move that rule onto the library: extend `emptyState`'s `variant: 'plain'` to own the root spacing too, or wrap the notice in a consumer container with its own class. Then grep `static/css` for `[data-testid` and remove every match. The Rules and notes capture stays pixel-identical. (FD ruling, 2026-10-21; no consumer CSS restyles a library control's nodes.)
- [ ] **No sizes over 800.** `studio.js` and every new studio module are ≤ 800 lines (`wc -l`).
- [ ] **Dead CSS.** An unused-selector report for `css/studio.css` (a grep of each class token across `static/js` and `tests/`) is recorded in the flight log, and selectors no built markup uses any more are deleted. Rules with remaining consumers (the admin `.tool-tile*`, the MCP editor's `.mcp-tool-item*`, the chip-list copies used by the admin string path) stay, and each is named in the log as Flight 3/4 debt.
- [ ] **The after set.** `THE_ONE_TEST_NETNS=1 .venv/bin/python scripts/ui_capture.py --out $HOME/.cache/the-one-ui-capture/m31-f2-after` covers all surfaces. Every before/after pair for the agent surfaces and the admin editor guard is read in both themes. Each visible difference is listed in the flight log, with its DD4 item (1 the switch, 2 the chip "×", 3 MCP Refresh, 4 the info toggletip) or its DD8/DD9 line. The admin Built-in tools editor shows no difference. An unexplained difference is fixed before landing. **Two carried differences must be explained or fixed:**
  - the region at about (294,14)-(317,38), the Agents list pane's "New" control and the header strip, which differs from the before set in every agent capture since 06a;
  - the danger-zone button gap and icon spacing from leg 04 (06a, 06b).

  The HAT list (in the Flight Director Notes) gets the final set.
- [ ] **Re-budget (squawk 0217).** `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 TEST_TIMEOUT=3600 make gate` runs in the background with an explicit timeout above its length. Every lane's wall time is recorded, and the budgets of lanes over or near budget are re-set by the script's headroom rule.
  - If `agents` would exceed 1.3× its budget, split it into `agents` and `agent-tabs` (the self-configuration, rules and notes, and tools-override files), updating `scripts/run-tests.sh`, `tests/test_run_tests_lanes.py` and CLAUDE.md's lane table and descriptions.
  - Squawk 0217 is completed.
- [ ] **Toggletip clipping, carried from leg 05 (unverified there):** with the info bubble open, capture the provider editor (thinking or context-window info) and an agent-editor info button. Confirm the bubble is not clipped by the editor pane's scroll container. If it is, fix the positioning (for example a `position: fixed` placement computed from the button's rect) with a contract case.
- [ ] **Docs:**
  - **The catalogue** (`docs/ui-control-inventory.md`): the rows for tabs, the category tile, the chip list, the legacy toggles (iOS switch, studio pill) and the agent tabs reflect this flight. Rows still not on the library name Flight 3/4/5.
  - **`the_one/agents.md`:** the studio modules, the agent editor, the tabs, `mountSlot`, the confirm announcement and the toggletip.
  - **CLAUDE.md:** the lane table, plus any operator-facing line this flight changed: the agent-PUT `tool_overrides` watch-out and the self-configuration notes.
- [ ] **The full gate is green; ruff is clean.**

## Verification Steps
- The grep of the allowance files for the listed paths returns nothing.
- `wc -l` on the listed modules.
- The capture run, with the pairs read.
- The full gate, plus `tests/test_run_tests_lanes.py`.

## Implementation Guidance
1. Stragglers, then the dead-CSS report and deletions.
2. The after captures and comparison.
3. The full gate and re-budget, then squawk 0217.
4. Docs.

## Edge Cases
- **A flaky lane in the gate:** re-run the failure in isolation, and record any known-squawk flake.
- **A capture difference outside DD4:** fix it and recapture. Never relabel it as approved.

## Files Affected
- Any straggler JS or CSS under `the_one/interfaces/web/static/`.
- `scripts/run-tests.sh`, `tests/test_run_tests_lanes.py`.
- `tests/_ui_ownership_allowance.py`, `tests/test_ui_guards.py`.
- `docs/ui-control-inventory.md`, `the_one/agents.md`, `CLAUDE.md`, `squawks/0217-*.md`.

## Citation Audit
Checked at planning: `scripts/run-tests.sh:61,68` (budgets) and CLAUDE.md `:370,375` (the table rows), from the planning survey. Re-verified at leg start.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
