# Leg: routing-rules-editor-browser-test

**Status**: completed
**Flight**: [First Real Connector — Discord](../flight.md)

## Objective

Land the F7 debrief Important #5 carry-forward: a Playwright test in `tests/browser/test_flow_studio_connector_account_editor.py` exercising the routing-rules editor UI that F7 L7 introduced. Previously HAT-only-validated; this leg pins the contract against regression. Test cases: add a routing rule, fill chip-list with multiple match values, drag-reorder rules, set default agent, save, reload page, assert baseline-not-dirty (no spurious "unsaved changes" prompt). Uses the existing `_activate_access_and_routing_tab` helper from F7 HAT1 at `tests/browser/test_flow_studio_connector_account_editor.py:40`.

## Context

L10 of F8. NOT Discord-specific — pure F7 debrief carry-forward. Per the flight Design Decisions, L10 ships in F8 because the F7 routing-rules editor's drag-reorder + chip-list + default-agent + dirty-tracking behaviors were only HAT-validated and warrant Playwright regression coverage before the F8 HAT (L11) runs the operator through them again.

The routing-rules editor lives in the Access and Routing tab of the connector-account editor (Studio Edit mode only). Renders rows with: drag handle, scope select, match chip-list, agent select, remove button. Below: "Add rule" button + default-agent dropdown.

Key learnings from L1-L9:
- F7 HAT1 added `_activate_access_and_routing_tab` helper for tab activation in edit-mode flows.
- F7 HAT2 redesigned the routing-rules editor with HTML5 drag-and-drop (replacing chevron move buttons).
- L8 added guilds + roles allowlist chip-list rows in the same editor — but separate section from routing-rules. The L10 test exercises ONLY the routing-rules section.
- Playwright snapshot baselines are gitignored per user-global rule — L10 test does NOT introduce snapshot baselines (use DOM-shape assertions).

## Inputs

- `tests/browser/test_flow_studio_connector_account_editor.py:40` — `_activate_access_and_routing_tab` helper.
- `tests/browser/test_flow_studio_connector_account_editor.py` — existing browser test patterns + `seed_connector_account` helper.
- `interfaces/web/static/js/areas/studio/connector-account-editor.js:1548+` — `_renderRoutingRow` shape, `data-routing-rule`, `data-routing-scope`, `data-routing-match`, `data-routing-agent`, `data-routing-drag-handle` data-testids.
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js:1597+` — `renderRoutingRulesSection` with the "Add rule" button + default-agent dropdown.
- L1-L9 test suite green (2384 passed).

## Outputs

- `tests/browser/test_flow_studio_connector_account_editor.py` extended with at least 4 new Playwright tests:
  1. **`test_routing_rules_add_rule_with_chip_list`**: open edit mode on a seeded account, activate Access and Routing tab, click "Add rule", select scope (e.g. "channel"), fill chip-list with multiple values (e.g. "ch1", "ch2"), select agent, click save; reload page and assert the row is persisted with correct scope/match/agent.
  2. **`test_routing_rules_drag_reorder`**: seed an account with 3 existing rules, activate tab, drag rule-0's handle onto rule-2's position, click save, reload; assert the new order is persisted. Uses Playwright's `drag_to` primitive.
  3. **`test_routing_rules_default_agent_persists`**: select a default agent from the dropdown, save, reload; assert the default-agent select shows the chosen value.
  4. **`test_routing_rules_baseline_not_dirty`**: seed an account with 1 existing rule, open edit mode, activate tab, do nothing else; assert the save button is NOT marked dirty (no spurious "unsaved changes" state). This pins the "load → no-op interaction → baseline-not-dirty" contract that F7 HAT2 surfaced.

- `tests/browser/test_flow_studio_connector_account_editor.py` module docstring — add an L10 cross-reference noting the F7 debrief Important #5 closure.

- F1-F9 + L1-L9 regression: 2384 → ~2388 (4 new browser tests). The browser tests are marker-deselected by default (`-m browser` to opt in); L10's tests need to be explicitly invoked via the `make test-browser` chain.

## Acceptance Criteria

- [ ] **`test_routing_rules_add_rule_with_chip_list`** passes — adds a rule, fills the chip-list with 2+ match values, selects scope + agent, saves, reloads, assertions confirm persistence.

- [ ] **`test_routing_rules_drag_reorder`** passes — drags a rule's handle to reorder, saves, reloads, assertions confirm new order. Uses Playwright's drag-and-drop API.

- [ ] **`test_routing_rules_default_agent_persists`** passes — selects default agent, saves, reloads, assertion confirms persistence.

- [ ] **`test_routing_rules_baseline_not_dirty`** passes — loads page, activates tab, no other interaction; assertion confirms save button is not in dirty/unsaved state.

- [ ] **No snapshot baselines committed**. Tests use DOM-shape assertions (locator + expect), not Playwright `expect(page).to_have_screenshot()`.

- [ ] **Tests run under the browser marker** (`@pytest.mark.browser`) — opt-in via `make test-browser` chain. Default `pytest` run does NOT execute them (regression: 411 deselected stays 411-N → 411 minus the new browser tests).

- [ ] **F1-F9 + L1-L9 regression**: full suite count unchanged at 2384 passed (browser tests are deselected by default); `make test-browser` shows 4 new browser tests pass.

- [ ] **`tests/browser/test_flow_studio_connector_account_editor.py` module docstring** — adds an L10 cross-reference noting F7 debrief Important #5 closure.

## Verification Steps

- `grep -c "test_routing_rules_" tests/browser/test_flow_studio_connector_account_editor.py` — at least 4.
- `docker exec the-one pytest tests/browser/test_flow_studio_connector_account_editor.py -m browser -x --timeout 60 -k "routing_rules"` — 4 passed.
- `docker exec the-one pytest tests/ -x --timeout 30` — full default suite still 2384 passed (no change).
- `make test-browser` — full browser-marker test run passes (excluding any pre-existing flake; new 4 tests pass).

## Implementation Guidance

1. Read the existing test patterns in `tests/browser/test_flow_studio_connector_account_editor.py` (lines 50+ have F7 L9 HAT tests; mirror the structure).
2. Identify the relevant data-testids in `connector-account-editor.js`:
   - `[data-testid="tab-access-and-routing"]` — tab activation (already in helper).
   - `[data-routing-rule]` / `[data-routing-rule-idx]` — rule rows.
   - `[data-routing-scope]` / `[data-routing-match]` / `[data-routing-agent]` — per-row controls.
   - `[data-routing-drag-handle]` — drag source.
   - Search for "Add rule" button — likely `[data-testid="add-routing-rule-btn"]` or similar.
   - Search for default-agent dropdown — likely `[data-testid="connector-routing-default"]` or similar.
3. Seed a connector account with at least one configured agent + multiple rules (for the reorder test). The `seed_connector_account` helper at the top of the file is the precedent.
4. Implement the 4 tests in order; use Playwright's `expect(...).to_have_value(...)` / `to_have_attribute(...)` / `to_have_count(...)` for assertions.
5. For drag-reorder: Playwright's `page.locator(handle).drag_to(page.locator(target))` is the standard primitive. Verify it works against the HTML5 native drag-and-drop the editor uses; if not, may need lower-level mouse events.
6. Run with `make test-browser` (chained ensures playwright is installed).

### Code patterns to follow

- **`_activate_access_and_routing_tab(page)`** — F7 HAT1 helper. Always call before interacting with routing/lifecycle/allowlist sections.
- **`seed_connector_account(app_clean, name=...)`** — file-top helper for pre-existing accounts.
- **F7 L9 HAT tests in the same file** — structural mirror (load page → tab activate → interact → assert).

## Edge Cases

- **Drag-and-drop in headless Chromium**: HTML5 native drag events sometimes don't fire reliably with Playwright's `drag_to`. Fall back to manual mouse-down + mouse-move + mouse-up sequence if needed.
- **Save button dirty-state detection**: the editor likely uses a CSS class like `dirty` or `is-dirty` on the save button, OR a data attribute. Inspect the editor's source for the exact selector.
- **Reload-after-save**: Playwright's `page.reload()` may need `page.wait_for_load_state("networkidle")` afterward to ensure the new state is rendered before assertions.
- **Account-without-agents**: if the seeded account has no agents available for the routing-rules agent dropdown, the rule's agent select will be empty — seed at least one agent + attach it before testing.

## Files Affected

- `tests/browser/test_flow_studio_connector_account_editor.py` — 4 new tests + module docstring update

---

## Post-Completion Checklist

- [ ] All acceptance criteria verified
- [ ] Tests passing (`make test-browser`)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set leg status to `landed`
- [ ] Check off L10 in flight.md
- [ ] Do NOT commit — wait for flight-level review

## Citation Audit

- `tests/browser/test_flow_studio_connector_account_editor.py:40` — `_activate_access_and_routing_tab` helper — **OK**
- `interfaces/web/static/js/areas/studio/connector-account-editor.js:1548-1595` — `_renderRoutingRow` shape — **OK**
- `interfaces/web/static/js/areas/studio/connector-account-editor.js:1597+` — `renderRoutingRulesSection` — **OK**
- F7 debrief Important #5 — Playwright test carry-forward — **OK** (per F8 flight spec)

4 citations verified.
