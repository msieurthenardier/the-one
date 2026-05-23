# Leg: connectors-tab-axis-cleanup

**Status**: completed
**Flight**: [Connector UX Cleanup](../flight.md)

## Objective

Close two specific visual bugs on the agent's Connectors tab (the per-agent overlay surface, e.g., Cave Man Bot → Connectors): **(6)** add visual containment for the per-axis body so the expanded editor reads as "this is the {axis} editor for this account" rather than as a free-floating dropdown spanning the full tile width; **(7)** hide the empty "Selected entries" chip container in the `discoverable-dropdown` component when no chips are selected, so the empty container does not render as a confusing blank box. ~50-80 LOC across `connectors-tab.js` (no JS change for item 6 — it's pure CSS), `discoverable-dropdown.js` (item 7 toggles `hidden` attribute), and `studio.css` (item 6 adds the containment rule).

## Context

- F5 L4 is the Connectors-tab leg per the flight's leg ordering. L1 + L2 + L3 landed (form-controls re-styled, Test Connection + Invite folded into Connection section, runtime-config moved to A&R tab with relabels). L4 touches a DIFFERENT file set — `connectors-tab.js` + `discoverable-dropdown.js` + `studio.css` — independent of L1-L3.
- F5 flight Design Decision "Cave Man Bot Peers axis containment + empty-chips hide" pins both fixes. Item 6 is CSS-only (containment around `.connector-acl-axis-body`); item 7 is JS toggle (`hidden` attribute on `.discoverable-dropdown-chips`).
- The Connectors tab is the per-agent overlay (NOT the Studio Connectors grid). It lives at `#studio/agents/{agent-name}` → Connectors tab. The tile is `connectors-tab.js:_renderAccountTile`; the per-axis body is built by `_buildAxisRow` (the same code path F4 L3 touched for `_labelCache`).
- F4 L3's closure-scoped helpers (`_labelCache`, `_ensureLabelCache`, `_applyLabelsToCheckboxes`) live INSIDE `_renderAccountTile`. L4's per-axis-body CSS class is added to the existing `<div class="connector-acl-axis-body">` (already exists at `connectors-tab.js:_buildAxisRow`, just needs a CSS rule).
- F4 L4 fold-in (`connector-account-pool-warmed` event listener in `discoverable-dropdown.js`) is unaffected — listener is on `document`, not on any chips-container DOM ancestor.
- Touched-surface UX-debt folding (F4 L1 convention): F4 debrief listed no outstanding UX-debt against `connectors-tab.js` or `discoverable-dropdown.js` beyond items in F5 scope.

## Inputs

- `the_one/interfaces/web/static/js/areas/studio/connectors-tab.js` exists.
  - `_renderAccountTile(listContainer, account, attachedMap, aclsMap, onChange)` at line 118 — defines the agent-Connectors-tab tile shape, including the F4 L3 `_labelCache` closure.
  - `_buildAxisRow(axis, scopeList, agentAxisValue)` at line 206 — builds the per-axis editor (Peers / Channels) including the `body` element (`<div class="connector-acl-axis-body">`) that toggles `hidden` on expand. The `body` is the container that fills the full tile width today.
  - The `body` element receives chip-mode (dropdown) content OR checkbox-mode content. Both modes emit content that fills `body`'s width.
- `the_one/interfaces/web/static/js/areas/studio/discoverable-dropdown.js` exists.
  - `_buildDOM(opts)` at line ~75 emits the root `<div class="discoverable-dropdown">` with children: input-row, menu, chips container (`<div class="chip-list-editor discoverable-dropdown-chips" role="group" aria-label="Selected entries" data-testid="discoverable-dropdown-chips-{axis}">`), status div.
  - `_renderChips(state)` at line 122 — clears `chipsEl.innerHTML` then iterates `state.currentValues` to populate chip children. Currently does NOT toggle `hidden` based on `currentValues.length`.
- `the_one/interfaces/web/static/css/studio.css` exists.
  - `.connector-acl-axis-body` is the L4 target for the containment rule. Currently no rule (or a minimal one — grep to confirm).
  - `.chip-list-editor.discoverable-dropdown-chips` styling lives in `studio.css` (grep for the selector to find existing rules — the L4 hide is a JS toggle, not CSS).
- Chrome MCP available; `the-one` container at `http://localhost:8484/`.
- Cave Man Bot agent is the operator-realistic test target (has Discord Constellation + Stub HAT Account attached; F4 L4 HAT walked this surface).

## Outputs

- **`the_one/interfaces/web/static/js/areas/studio/discoverable-dropdown.js`** — `_renderChips(state)` at line 122 toggles `hidden` attribute on the chips container based on `state.currentValues.length`. **Critical** (cycle-1 catch): the JS toggle alone is INSUFFICIENT because `.area-studio .chip-list-editor` (admin.css:393-406) sets `display: flex` with specificity (0,0,2,0) which overrides the user-agent `[hidden] { display: none }` (specificity 0,0,1,0). A companion CSS rule MUST land in studio.css with higher specificity so `hidden` actually hides the container — see CSS output below.
  ```javascript
  function _renderChips(state) {
    var chipsEl = state.root.querySelector('.discoverable-dropdown-chips');
    if (!chipsEl) return;
    chipsEl.innerHTML = '';

    // L4 item 7: hide the chip container when empty so it doesn't render
    // as a confusing blank box. The chip-list-editor CSS gives it a
    // minimum visual height; hiding it prevents the empty-state from
    // looking like a stray empty rectangle.
    if (!state.currentValues || state.currentValues.length === 0) {
      chipsEl.setAttribute('hidden', '');
      return;
    }
    chipsEl.removeAttribute('hidden');

    for (var i = 0; i < state.currentValues.length; i++) {
      // ... existing chip-rendering loop ...
    }
  }
  ```
- **`the_one/interfaces/web/static/css/studio.css`** — TWO targeted CSS additions (cycle-1 scoped):
  - **Extend the existing `.area-studio .connector-acl-axis-body` rule at line ~1104** (currently `margin-top: 8px;`). Add the new containment properties while PRESERVING the existing `margin-top: 8px` (operator-deliberate spacing):
    ```css
    /* M11 F5 L4: per-axis body containment — visually scopes the per-axis
       editor (Peers / Channels) so the expanded body reads as "this is
       the {axis} editor" rather than as a free-floating dropdown
       spanning the full tile width. */
    .area-studio .connector-acl-axis-body {
      margin-top: 8px;            /* existing — preserved */
      border-left: 2px solid var(--border);
      padding: 8px 0 8px 12px;
      background: var(--surface-elevated);  /* tonal step-up from tile's --surface */
      border-radius: var(--panel-radius-sm);
    }
    ```
    - `--surface-elevated` (NOT `--surface`) per cycle-1 review: tonal differentiation from the parent tile background. `--surface-elevated` is used at studio.css:1135, 1169 for similar nested-surface treatment.
    - Exact border/padding values tune visually via Chrome MCP iteration; the above are starting points.
  - **Add a new `.area-studio .discoverable-dropdown-chips[hidden]` override rule** so the JS `hidden` attribute actually hides the chip container despite `.area-studio .chip-list-editor`'s `display: flex`:
    ```css
    /* M11 F5 L4: hide empty chip container — specificity 0,0,3,0
       outranks .area-studio .chip-list-editor (0,0,2,0) so the JS
       hidden-attribute toggle in _renderChips actually takes effect. */
    .area-studio .discoverable-dropdown-chips[hidden] {
      display: none;
    }
    ```
  - Both rules use design-language tokens (`--border`, `--surface-elevated`, `--panel-radius-sm`).
- No changes to `connectors-tab.js` source — item 6 is CSS-only (the `<div class="connector-acl-axis-body">` already exists; just needs the new CSS rule).
- No changes to data-testids, no behavior changes beyond the hide-when-empty + the visual containment.
- Sibling artifact bookkeeping: F5 `flight.md`'s L4 Checkpoints + L4 Legs item checked off; F5 `flight-log.md`'s Leg Progress section grows an L4 entry; this leg artifact's Status header progresses through its lifecycle.

## Acceptance Criteria

- [x] `discoverable-dropdown.js:_renderChips(state)` toggles `hidden` attribute on `.discoverable-dropdown-chips` container based on `state.currentValues.length` — hidden when empty (0 chips), visible when ≥ 1 chip.
- [x] `discoverable-dropdown.js:_renderChips(state)` still empties the container (`chipsEl.innerHTML = ''`) on each call — the existing clear-and-repopulate pattern is preserved.
- [x] The new hide-when-empty behavior runs on EVERY `_renderChips` call (including the post-fetch render, post-add-chip render, post-remove-chip render). When the operator removes the last chip, the container hides; when they add the first chip, the container shows.
- [x] `studio.css` EXTENDS the existing `.area-studio .connector-acl-axis-body` rule at line ~1104 (currently `margin-top: 8px;`) to add containment properties: `border-left: 2px solid var(--border); padding: 8px 0 8px 12px; background: var(--surface-elevated); border-radius: var(--panel-radius-sm);`. The existing `margin-top: 8px` is PRESERVED. Uses `--surface-elevated` (tonal step-up from `--surface`) per cycle-1 catch — `--surface` matched the chip-list-editor background and read as visually flat.
- [x] `studio.css` ADDS a new `.area-studio .discoverable-dropdown-chips[hidden]` override rule: `display: none;`. Required so the JS `hidden` attribute toggle in `_renderChips` actually hides the chip container (cycle-1 catch: `.area-studio .chip-list-editor`'s `display: flex` at specificity 0,0,2,0 overrides the user-agent `[hidden]` rule at 0,0,1,0; the new rule at 0,0,3,0 outranks).
- [x] The containment rule applies UNIFORMLY to chip-mode (dropdown editor) AND checkbox-mode (checkbox-list editor) bodies — both render inside the same `.connector-acl-axis-body` container per `connectors-tab.js:_buildAxisRow`.
- [x] No changes to `connectors-tab.js` (the `body` element with `connector-acl-axis-body` class already exists; just gets the new CSS rule).
- [x] No changes to data-testids, data-axis, or aria-* attributes on the chip container.
- [x] `discoverable-dropdown.js`'s status div (`.discoverable-dropdown-status`) is unaffected — it stays visible regardless of chip count.
- [x] In-flight Chrome MCP verification:
  - Navigate to `http://localhost:8484/#studio/agents/Cave%20Man%20Bot/connectors`.
  - Expand Discord Constellation Peers axis — visual containment is apparent (border-left + padding); the body reads as "the Peers editor for Discord Constellation."
  - Expand Discord Constellation Channels axis (which has 1 chip from F4 HAT) — visual containment applies; the Selected entries chip container is visible with the `#gleepglorp-text` chip.
  - Remove the chip via the chip's `×` button — verify the Selected entries container hides (no blank box). Add a chip via the dropdown — verify the container reappears.
  - Expand Stub HAT Account Peers axis — same visual containment.
- [x] Browser test suite: `docker exec the-one pytest tests/browser/test_flow_studio_per_agent_overlay_dropdown.py tests/browser/test_flow_studio_per_agent_overlay_label_resolver.py tests/browser/test_flow_studio_connector_allowlist_dropdown.py tests/browser/test_flow_studio_connector_routing_dropdown.py tests/browser/test_flow_studio_connector_discoverable_dropdown.py -m browser -x --timeout 60 -v` passes — no regressions on the dropdown surfaces.
- [x] No source files beyond `discoverable-dropdown.js` and `studio.css` modified.

## Verification Steps

- `grep -n "currentValues.length\|hidden.*chipsEl\|chipsEl.*hidden" the_one/interfaces/web/static/js/areas/studio/discoverable-dropdown.js` returns at least 2 hits (the new length check + the setAttribute/removeAttribute pair).
- `grep -nE "\.connector-acl-axis-body" the_one/interfaces/web/static/css/studio.css` returns 1 hit (the existing rule at ~line 1104, now extended with containment properties — NOT a second new rule).
- `grep -nE "discoverable-dropdown-chips\[hidden\]" the_one/interfaces/web/static/css/studio.css` returns 1 hit (the new `display: none` override).
- **Chrome MCP computed-style check** (cycle-1 catch — visual judgment alone is insufficient given the `hidden` attribute pitfall): after removing the last chip, use `mcp__chrome-devtools__evaluate_script` to confirm `getComputedStyle(document.querySelector('.discoverable-dropdown-chips')).display === 'none'`. Visual screenshot also confirms no blank box.
- Visual (Chrome MCP):
  - Cave Man Bot Connectors tab expanded axes show visual containment (border-left + padding around per-axis body).
  - Empty Selected entries container is hidden (no blank box).
  - Non-empty Selected entries container shows chips normally.
- Persistence + interaction: removing chips → container hides; adding chips → container reappears. Verified via Chrome MCP click + DOM snapshot.
- Browser test suite passes.
- `git diff --stat` shows changes ONLY in `discoverable-dropdown.js`, `studio.css`, + F5 sibling artifacts.

## Implementation Guidance

1. **Read target file sections** before editing:
   - `discoverable-dropdown.js:75-110` — `_buildDOM(opts)` to confirm chips container markup.
   - `discoverable-dropdown.js:122-168` — `_renderChips(state)` current implementation.
   - `connectors-tab.js:262-330` — `_buildAxisRow(axis, scopeList, agentAxisValue)` to confirm `body` element class `connector-acl-axis-body`.
   - `studio.css` — grep for `connector-acl-axis-body` to find existing rules (if any). Grep for `chip-list-editor` and `discoverable-dropdown-chips` for context.
   - `tokens-section.js` (or the design-language tokens page) for the current `--border`, `--surface`, `--panel-radius-sm` token values.

2. **Modify `_renderChips(state)`** in `discoverable-dropdown.js`:
   - Add the hidden-when-empty check at the top of the function (after the `chipsEl.innerHTML = ''` clear).
   - Add inline comment citing L4 item 7.

3. **Add the CSS containment rule** in `studio.css`:
   - Insert near other `.connector-acl-axis-*` rules (grep for existing siblings).
   - Use the canonical Design Language token vars.
   - Add a multi-line comment citing F5 L4 item 6.
   - Initial values: `border-left: 2px solid var(--border); padding: 8px 0 8px 12px; margin: 4px 0 4px 8px; background: var(--surface); border-radius: var(--panel-radius-sm);`. Iterate on the values per Chrome MCP visual verification.

4. **Chrome MCP visual + computed-style verification**:
   - Navigate to `http://localhost:8484/#studio/agents/Cave%20Man%20Bot/connectors` (hard-reload to bust JS+CSS cache).
   - Expand Peers axis on Discord Constellation tile → take screenshot → judge containment visual rhythm. Use `var(--surface-elevated)` as starting background per cycle-1.
   - If border feels too heavy: drop to 1px or change color. If padding feels off: adjust. Iterate until rhythm reads cleanly.
   - Expand Channels axis (has 1 chip from F4 HAT) → verify chip is visible inside the now-contained body.
   - **DO NOT mutate Discord Constellation chip state** (cycle-1 catch — downstream HAT tests rely on persisted seed). Instead, exercise the chip add/remove round-trip on the **Stub HAT Account Peers axis** (operator-safe playground).
   - Stub HAT Account Peers: expand → verify containment. Add a chip via dropdown → verify Selected entries container shows. Remove the chip via `×` → verify container hides.
   - **Critical (cycle-1)**: confirm the hide actually works via `mcp__chrome-devtools__evaluate_script`:
     ```javascript
     getComputedStyle(document.querySelector('[data-testid^="discoverable-dropdown-chips-"]')).display
     ```
     Returns `"none"` when empty; `"flex"` when populated.
   - Expand Stub HAT Account Channels axis → same containment + same hide-when-empty behavior.

5. **Run targeted browser tests**:
   - `docker exec the-one pytest tests/browser/test_flow_studio_per_agent_overlay_dropdown.py tests/browser/test_flow_studio_per_agent_overlay_label_resolver.py tests/browser/test_flow_studio_connector_allowlist_dropdown.py tests/browser/test_flow_studio_connector_routing_dropdown.py tests/browser/test_flow_studio_connector_discoverable_dropdown.py -m browser -x --timeout 60 -v`

6. **Update F5 `flight.md`** — check off L4 in Checkpoints + Legs sections.

7. **Append L4 leg-progress entry** to F5 `flight-log.md`.

8. **Update this leg artifact's Status header** progressively: `planning` → `ready` → `in-flight` → `landed`.

## Edge Cases

- **Tests asserting `.discoverable-dropdown-chips` visibility regardless of chip count**: grep `grep -rn "discoverable-dropdown-chips" tests/browser/`. Any test asserting `to_be_visible()` on the chips container WITHOUT first ensuring at least one chip exists will fail post-L4 — but realistic tests would seed chips first. Document any test that needed updating.
- **The chips container's `aria-label="Selected entries"`**: stays on the `<div>` regardless of `hidden`. Screen readers won't announce a hidden element. Acceptable per accessibility convention.
- **The `data-testid="discoverable-dropdown-chips-{axis}"`** is preserved. Tests can still locate the element via testid (even when hidden); they just need to use `to_be_visible()` carefully.
- **Visual rhythm tuning**: the initial CSS values are starting points. If the operator (or Chrome MCP visual judgment) reads the containment as too heavy/too subtle, iterate inline. Don't punt to L5 sweep — L4's purpose is to land the visual fix; L5 reviews the cumulative result for things L4 missed, not for L4's own tuning.
- **The `.discoverable-dropdown` root** has its own width — the containment is on the PARENT (`.connector-acl-axis-body`), so the dropdown inside it still spans its available width minus the new padding. Acceptable.
- **Checkbox-mode bodies** (from `_buildCheckboxList` in connectors-tab.js) render directly inside `.connector-acl-axis-body` — the containment applies uniformly. Verify by Chrome MCP on the Channels axis of Cave Man Bot (which is in checkbox-mode post-F4 due to the seeded chip).
- **`hidden` vs `display: none`** (cycle-1 catch): the `hidden` attribute alone is INSUFFICIENT for `.discoverable-dropdown-chips` because `.area-studio .chip-list-editor` sets `display: flex` (admin.css:393-406) with specificity 0,0,2,0 that overrides the user-agent `[hidden]` rule at 0,0,1,0. The companion CSS rule `.area-studio .discoverable-dropdown-chips[hidden] { display: none; }` (specificity 0,0,3,0) lands in studio.css to make the hide actually take effect. The `.discoverable-dropdown-menu` precedent (`discoverable-dropdown.js:100`) works without a companion rule because it has no overriding `display:` value — different scenarios.
- **Positive side effect** (cycle-1 noted): the post-fetch `_renderChips` calls in the `pre-probe-404` path (`discoverable-dropdown.js:541`) and the `ok` path (line 557) also go through the new hide-when-empty branch. Cold-pool empty state no longer renders the blank box either. Intentional and worth surfacing in the L5 sweep.

## Files Affected

- `the_one/interfaces/web/static/js/areas/studio/discoverable-dropdown.js` — `_renderChips(state)` toggles `hidden` attribute on `.discoverable-dropdown-chips` based on `state.currentValues.length`. ~5 LOC.
- `the_one/interfaces/web/static/css/studio.css` — TWO targeted edits per cycle-1: (a) EXTEND existing `.area-studio .connector-acl-axis-body` rule at line ~1104 with containment properties (preserve `margin-top: 8px`); (b) ADD new `.area-studio .discoverable-dropdown-chips[hidden] { display: none; }` override rule. Total ~12 LOC including comments.
- `missions/11-discord-connector-depth/flights/05-connector-ux-cleanup/flight.md` — L4 checkpoint + L4 leg checklist item checked off.
- `missions/11-discord-connector-depth/flights/05-connector-ux-cleanup/flight-log.md` — L4 leg-progress entry appended.
- `missions/11-discord-connector-depth/flights/05-connector-ux-cleanup/legs/04-connectors-tab-axis-cleanup.md` — this artifact's status header updated through the lifecycle.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified (grep checks pass; Chrome MCP visual verification confirms containment + hide-when-empty; browser tests pass)
- [x] `docker exec the-one pytest tests/browser/test_flow_studio_per_agent_overlay_dropdown.py tests/browser/test_flow_studio_per_agent_overlay_label_resolver.py tests/browser/test_flow_studio_connector_allowlist_dropdown.py tests/browser/test_flow_studio_connector_routing_dropdown.py tests/browser/test_flow_studio_connector_discoverable_dropdown.py -m browser -x --timeout 60` passes
- [x] Update `flight-log.md` with L4 leg-progress entry
- [x] Set this leg's status to `landed`
- [x] Check off L4 in `flight.md` (Checkpoints + Legs sections)
- [x] Do NOT commit (F5 batches review + commit at flight end per the agentic-workflow protocol)

---

## Citation Audit

All code-location citations in this leg artifact verified against current code at leg design time (2026-05-23, post-L3):

- `discoverable-dropdown.js:75-110` — `_buildDOM` confirmed (chips container at lines 103-105).
- `discoverable-dropdown.js:122-168` — `_renderChips` confirmed.
- `connectors-tab.js:118` — `_renderAccountTile` confirmed.
- `connectors-tab.js:262` — `_buildAxisRow` confirmed (post-F4 L3 closure helpers intact; line repaired from initial 206 at cycle-1).
- `connectors-tab.js:295` — `body.className = 'connector-acl-axis-body'` assignment confirmed.
- `studio.css:1104` — existing `.area-studio .connector-acl-axis-body { margin-top: 8px; }` rule confirmed (cycle-1 surfaced; L4 EXTENDS this rule rather than adding a duplicate).
- `studio.css:1306` — `.discoverable-dropdown-chips` empty rule confirmed (cycle-1 — no existing `[hidden]` override; L4 adds one).
- `admin.css:393-406` — `.area-studio .chip-list-editor { display: flex; ...; min-height: 40px; background: var(--surface); }` confirmed (cycle-1 — this is the rule that overrides `[hidden]` without the new override).
- Design Language tokens (`--border`, `--surface-elevated`, `--panel-radius-sm`) — confirmed; `--surface-elevated` per cycle-1 review for tonal step-up.

9 citation sites verified at design time. Cycle-1 repairs: 1 line drift (`_buildAxisRow` 206 → 262); 4 new sites added (`connectors-tab.js:295`, `studio.css:1104` existing rule, `studio.css:1306` chips rule, `admin.css:393-406` chip-list-editor display:flex).
