# Leg: re-style-connector-form-controls

**Status**: completed
**Flight**: [Connector UX Cleanup](../flight.md)

## Objective

Re-class the connector editor's typed Discord form (`connector-form-discord.js:renderConnectionFields`) and two specific sites on the new-connector page (`connector-account-editor.js`) to consume canonical sdcon design-language primitives — `.checkbox-primary` for Intents (multi-select set), `.field-input` for text inputs, `.field-input.field-select` for selects, `tool-enable-switch` for the single-boolean Auto-relay, and a hidden-when-real-type-picked treatment for the Type-dropdown placeholder option. Verify each change via Chrome MCP visually against the Design Language page (`#admin/design-language`) and the MCP editor (`#studio/mcp-sources/{id}`).

## Context

- F5 L1 is the primitives-first leg per the flight's "primitives-first then section-shape" sequencing rationale. L2 (Test Connection fold) and L3 (Move Config + Labels) rely on L1's classes being in place — L1 prepares the surface; L2-L3 reshape it.
- F5 flight Design Decisions pin three specific re-classings: Intents → `.checkbox-primary` multi-select (NOT iOS toggle), Auto-relay → `tool-enable-switch` (iOS toggle, mirroring MCP `Allow network access`), Type-placeholder → suppress from rendered list post-selection.
- The Design Language page's `fields-section.js:7-44` is the canonical primitive catalog. The MCP editor's `mcp-server-editor.js:529-535` is the working reference for the `tool-enable-switch` markup inside a 2-column `.field-row.admin-pf-row` wrapper.
- F4 L1 codified `pool-warming-entrypoints-are-finite-and-named` and three other conventions — none directly applicable to this leg (no pool primitives touched here). The L1-codification-first ordering precedent does not apply to F5 (no NEW conventions surfaced at planning; the convention applied here is the "use existing primitives, don't invent new ones" operator constraint).
- F4 L3 closure-scoped helper precedent (`_labelCache`, `_ensureLabelCache`, `_applyLabelsToCheckboxes` in `connectors-tab.js:_renderAccountTile`) is NOT touched by this leg. L4 will touch `connectors-tab.js` later.
- Touched-surface UX-debt folding (F4 L1 convention): the F4 debrief listed no outstanding UX-debt items against `connector-form-discord.js` or against the Auto-relay/Type-placeholder sites in `connector-account-editor.js` beyond the items already in this flight's scope. Nothing to fold in beyond the leg's own scope.

## Inputs

- `the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` exists with `renderConnectionFields(account, isCreate)` at line 163 (verified at F5 recon). The function emits raw `<input type="checkbox">` (Intents fieldset, lines 174-188), raw `<input type="text">` (Guilds row at line 198-200), raw `<input type="text">` (Presence name at line 210-211), raw `<select>` (Presence type at line 212-220), raw `<small class="form-hint">` text blocks (Intents at 189-191, Guilds at 201, Presence at 221-222), raw `<fieldset>/<legend>` (Intents container at 172-173) and raw `<details>/<summary>` (Advanced disclosure at 226-228).
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` exists with:
  - Type-select rendering at lines 612-630 (create-mode). The placeholder option at line 623 is `<option value="" disabled selected>` (selected only when no real type is picked) but ALWAYS rendered.
  - Auto-relay checkbox rendering at lines 381-394. The `<input type="checkbox" id="cf-auto-relay">` at line 383-386 has no canonical class. The 2-sentence verbose `<small class="form-hint">` follows at line 390-393.
- `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js` exists as the working reference. The `tool-enable-switch` pattern at lines 529-535 is the exact analog for Auto-relay.
- `the_one/interfaces/web/static/js/areas/admin/design-language/fields-section.js` exists as the primitive catalog. `.checkbox-primary` usage at lines 26-43 (single + multi-select examples).
- Canonical CSS classes exist in `the_one/interfaces/web/static/css/components.css`:
  - `.field-input` at line 142
  - `.field-select` at line 184
  - `.field-info-icon` at line 226 (not used in L1; deferred to L3)
  - `.checkbox-primary` at line 252
- `.tool-enable-switch` + `.tool-enable-switch-track` exist in `the_one/interfaces/web/static/css/admin.css:197-263`.
- Chrome MCP available (verified throughout F4 + F5 planning).
- The-one container running at `http://localhost:8484/`.

## Outputs

- `connector-form-discord.js:renderConnectionFields` renders:
  - **Intents**: `<fieldset class="discord-intents-fieldset">` + `<legend>Intents</legend>` SHAPE PRESERVED (the existing fieldset provides the visual grouping and there is no `.discord-intents-set` CSS rule that would substitute; design-review cycle-1 caught this). Only the inner `<input type="checkbox">` markup gains `class="checkbox-primary"`. Each axis's `<label class="discord-intent-row">` wrapper, the `<span>` for the axis label, and the data-testid surface are preserved byte-identical. Verbose help-text `<small class="form-hint">` STAYS in place for L1 (L3 replaces it with `.field-info-icon` tooltip).
  - **Guilds** input as `<input class="field-input" type="text" data-field="guilds-list" ...>`. The `<small class="form-hint">` STAYS for L1 (L3 reshapes).
  - **Presence name** input as `<input class="field-input" type="text" data-field="presence-name" ...>`.
  - **Presence type** select as `<select class="field-input field-select" data-field="presence-type" ...>`. The 5 option entries unchanged. The `<small class="form-hint">` STAYS for L1.
  - **Advanced (kv-table) disclosure** uses the same `<details>/<summary>` shape but with classes that match the MCP editor's disclosure styling IF the MCP editor exposes a disclosure pattern; otherwise styles accurately and notes for L5 sweep. (Inspect at implementation time.)
- `connector-account-editor.js`:
  - **Auto-relay row** at lines 381-394 rewrites to mirror MCP's `Allow network access` shape EXACTLY (siblings inside the field-row, NOT nested): the outer text `<label for="cf-auto-relay">` and the inner `<label class="tool-enable-switch">` are SIBLINGS inside `<div class="field-row admin-pf-row cf-auto-relay-row">`. The inner toggle-label wraps the input + the `<span class="tool-enable-switch-track" aria-hidden="true">`. The input gains `class="field-input"`. The row's new `cf-auto-relay-row` class lets a targeted CSS unpin override `.tool-enable-switch`'s default `position: absolute; bottom: 12px; right: 12px;` (matches the precedents at `admin.css:278-279` for `tools-editor-enabled-row` and `mf-sandbox-network-row`). The verbose `<small class="form-hint">` STAYS for L1.
  - **Type-dropdown placeholder option** at line 623 changes: when `createType !== ''` (a real type has been picked), the placeholder option is suppressed from the rendered list — emit it ONLY when `createType === ''`. The post-selection dropdown shows only the real type options. The closed-state display continues to show "Select a connector type" before any pick because the select's initial selected option is the placeholder when `createType === ''`; once picked, the matching real-type option's `selected` attribute drives the display.
- No changes to data-testids, no changes to `data-field` attributes, no changes to `id` attributes. All form-data collection paths continue to round-trip.
- CSS changes limited to ONE narrowly-scoped addition: a `cf-auto-relay-row` unpin override in `admin.css`, mirroring the `tools-editor-enabled-row` + `mf-sandbox-network-row` precedents at lines 278-279. ~3 LOC.
- Explicit Auto-relay handler at `connector-account-editor.js:943-945` (`autoRelayToggle.addEventListener('change', checkDirty)`) is REMOVED — once the Auto-relay input gains `.field-input`, `attachStaticListeners` at lines 931-934 registers the same change handler, making the explicit block dead code. Remove the 3-line block + its F8-L11 comment to keep the source minimal.
- Sibling artifact bookkeeping (explicit scope): F5 `flight.md`'s L1 Checkpoints entry + L1 Legs checklist item checked off; F5 `flight-log.md`'s Leg Progress section grows an L1 entry; this leg artifact's Status header progresses through its lifecycle.

## Acceptance Criteria

- [x] `connector-form-discord.js:renderConnectionFields` Intents rendering: the existing `<fieldset class="discord-intents-fieldset">` + `<legend>Intents</legend>` container shape is PRESERVED. Only the inner `<input type="checkbox">` markup at lines 184-185 gains `class="checkbox-primary"`. Each axis's `<label class="discord-intent-row">` wrapper, the `<span>` for the axis label, the `data-field="intent-{key}"`, and the `data-testid="discord-intent-{key}"` attributes are preserved byte-identical. Rationale: cycle-1 design review caught that no `.discord-intents-set` CSS exists; substituting the fieldset removes visual grouping with no replacement. Keep fieldset; class only the inputs.
- [x] `connector-form-discord.js:renderConnectionFields` Guilds input: `<input class="field-input" type="text" id="cf-discord-guilds" data-field="guilds-list" data-testid="discord-guilds-list" value="..." placeholder="">`. The `<label for="cf-discord-guilds">Guilds</label>` is unchanged.
- [x] `connector-form-discord.js:renderConnectionFields` Presence name input: `<input class="field-input" type="text" data-field="presence-name" data-testid="discord-presence-name" value="..." placeholder="Activity name">`. The `<label>Presence</label>` is unchanged.
- [x] `connector-form-discord.js:renderConnectionFields` Presence type select: `<select class="field-input field-select" data-field="presence-type" data-testid="discord-presence-type">` with the 5 PRESENCE_TYPES option entries unchanged.
- [x] `connector-form-discord.js:renderConnectionFields` Advanced (kv-table) disclosure: inspect the MCP editor for any disclosure pattern (`<details>/<summary>` or other). If MCP exposes a disclosure shape, mirror it. If not, keep the `<details>/<summary>` markup but use any styling-class precedent from the connector-account-editor (e.g., the section-title pattern). Note for L5 sweep if no canonical primitive exists.
- [x] `connector-form-discord.js:renderConnectionFields` `<small class="form-hint">` text blocks STAY in place for L1. L3 replaces them with `.field-info-icon` tooltips.
- [x] `connector-account-editor.js` Auto-relay row at lines 381-387 rewrites to mirror MCP's `Allow network access` shape EXACTLY (`mcp-server-editor.js:529-535`). The outer text `<label for="cf-auto-relay">` and the inner `<label class="tool-enable-switch">` are SIBLINGS inside `<div class="field-row admin-pf-row cf-auto-relay-row">`, NOT nested. (Nested labels around the same input cause two click events on a single click that cancel each other; the MCP precedent uses siblings precisely to avoid this.) The inner toggle-label wraps the input + `<span class="tool-enable-switch-track" aria-hidden="true">`.
- [x] `connector-account-editor.js` Auto-relay input gains `class="field-input"` and `aria-label="Auto-relay peer replies to platform"` (defensive; inner label has no visible text). The `id="cf-auto-relay"`, `data-field="auto_relay_platform_replies"`, `data-testid="connector-account-auto-relay-toggle"`, and checked-state are preserved.
- [x] `connector-account-editor.js` Auto-relay row wrapper gains `class="field-row admin-pf-row cf-auto-relay-row"` — adds `cf-auto-relay-row` to the existing class list. The new class is the CSS-unpin hook.
- [x] `admin.css` grows a 2-3 LOC CSS rule unpinning `.tool-enable-switch` for the new row class, mirroring the precedents at `admin.css:278-279`: e.g., `.area-studio .field-row.cf-auto-relay-row .tool-enable-switch { position: relative; bottom: auto; right: auto; }`. The rule lives near the existing precedents (find an appropriate insertion point near lines 278-281).
- [x] `connector-account-editor.js` explicit Auto-relay handler at lines 943-945 is REMOVED — once the input carries `.field-input`, `attachStaticListeners` registers the same change handler. The 3-line `var autoRelayToggle = ...; if (autoRelayToggle) { autoRelayToggle.addEventListener('change', checkDirty); }` block and its M10-F8-L11-Fix-#4 comment are deleted.
- [x] Visual: Auto-relay toggle flips on a SINGLE click (defensive AC against the nested-label bug — if the bug were present, the toggle would appear not to flip). Verified via Chrome MCP click + snapshot showing the data-state change.
- [x] `connector-account-editor.js` Type-dropdown rendering at lines 612-630 (create-mode block): the `<option value="" disabled>Select a connector type</option>` placeholder is emitted ONLY when `createType === ''`. When `createType !== ''`, the placeholder option is NOT emitted in the rendered list. The closed-state display continues to read "Select a connector type" before any pick (because the placeholder is the only selected option at that point); after a pick, the dropdown shows ONLY the real type options.
- [x] `connector-account-editor.js` Type-dropdown `typesEmpty` branch (line 615-617) is unchanged — when no connector types are registered, the "No connector types registered yet" placeholder still emits.
- [x] No changes to `data-testid` attributes, `data-field` attributes, or `id` attributes on any of the affected inputs/labels/selects.
- [x] No changes to JS event-wiring logic — `attachStaticListeners` continues to find the new-class inputs (the `.field-input` class is the key selector at lines 932-933 in connector-account-editor.js).
- [x] CSS changes limited to ONE narrowly-scoped addition in `admin.css` (`.area-studio .field-row.cf-auto-relay-row .tool-enable-switch` unpin override; ~3 LOC). No edits to `components.css` or `studio.css`. No other rules added or modified.
- [x] No changes to `mcp-server-editor.js` or to any design-language section module.
- [x] In-flight Chrome MCP verification:
  - Navigate to `http://localhost:8484/#studio/connectors/{discord-account-id}` on the General tab; take a snapshot + screenshot; visually compare Intent checkboxes against the design-language page's `.checkbox-primary` multi-select example (`fields-section.js:30-43`). The checkboxes render with the canonical dark-theme purple-accent border treatment, NOT browser-default grey squares.
  - On the same page, the Guilds + Presence inputs render with the canonical dark `.field-input` border + focus treatment, NOT browser-default text-input styling.
  - The Presence type select renders with the canonical `.field-select` chevron + dark surface, NOT browser-default `<select>` styling.
  - Navigate to `http://localhost:8484/#studio/connectors/new`; take a snapshot + screenshot; visually verify the Auto-relay row renders as an iOS toggle (`tool-enable-switch` track + ball) matching the MCP editor's `Allow network access` toggle at `#studio/mcp-sources/{id}`.
  - On the same page, open the Type dropdown without selecting a real type; verify "Select a connector type" appears as the placeholder option. Pick `Discord`. Re-open the dropdown; verify "Select a connector type" no longer appears in the list — only Discord (and any future types).
- [x] Browser test suite (mechanical): `docker exec the-one pytest tests/browser/test_flow_studio_connector_account_editor.py tests/browser/test_flow_studio_connector_account_create_and_test.py tests/browser/test_flow_studio_connector_discord_form.py tests/browser/test_flow_studio_connector_discord_vocabulary.py -m browser -x --timeout 60` passes (no regressions on the editor surfaces L1 touched).
- [x] No source files beyond `connector-form-discord.js` and `connector-account-editor.js` modified.

## Verification Steps

- `grep -n "checkbox-primary" the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` returns at least 3 hits (one per intent axis).
- `grep -n "field-input" the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` returns at least 3 hits (Guilds + Presence name + Presence type — last one is paired with `field-select`).
- `grep -n "field-select" the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` returns exactly 1 hit (Presence type select).
- `grep -n "tool-enable-switch" the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` returns at least 2 hits (label class + track span). Before L1: zero hits.
- `grep -nE 'Select a connector type|placeholderSelected' the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` returns exactly the placeholder-option emission + the suppression guard.
- Visual: Chrome MCP snapshot + screenshot of both `#studio/connectors/{id}` General tab and `#studio/connectors/new` confirming the rendering criteria above.
- `docker exec the-one pytest tests/browser/test_flow_studio_connector_account_editor.py tests/browser/test_flow_studio_connector_account_create_and_test.py tests/browser/test_flow_studio_connector_discord_form.py tests/browser/test_flow_studio_connector_discord_vocabulary.py -m browser -x --timeout 60 -v` shows 100% pass.
- `git diff --stat` shows changes ONLY in `connector-form-discord.js` + `connector-account-editor.js` + `admin.css` (the narrowly-scoped Auto-relay unpin rule) + F5 sibling artifacts (`flight.md`, `flight-log.md`, this leg). No edits to `components.css` or `studio.css`.

## Implementation Guidance

1. **Read the three target file sections** before editing:
   - `connector-form-discord.js:163-238` — current `renderConnectionFields` body.
   - `connector-account-editor.js:381-394` — current Auto-relay row.
   - `connector-account-editor.js:612-630` — current Type-select create-mode block.
   - `mcp-server-editor.js:529-535` — `tool-enable-switch` reference.
   - `the_one/interfaces/web/static/js/areas/admin/design-language/fields-section.js:7-44` — primitive examples.

2. **Add `.checkbox-primary` to Intent checkboxes** (`connector-form-discord.js:174-188`):
   - PRESERVE the existing `<fieldset class="discord-intents-fieldset">` + `<legend>Intents</legend>` shape. (Cycle-1 design review caught that no `.discord-intents-set` CSS rule exists; substituting the fieldset would leave the Intents block visually ungrouped. The primitive ask is "use `.checkbox-primary` on the inputs" — satisfied without container change.)
   - In the per-axis loop, change the input emission from:
     ```javascript
     html += '<input type="checkbox" data-field="intent-' + axis.key +
             '" data-testid="discord-intent-' + axis.key + '"' + checkedAttr + ' />';
     ```
     to:
     ```javascript
     html += '<input type="checkbox" class="checkbox-primary" data-field="intent-' + axis.key +
             '" data-testid="discord-intent-' + axis.key + '"' + checkedAttr + ' />';
     ```
     Only the `class="checkbox-primary"` attribute is added; everything else is byte-identical.
   - Keep the `<small class="form-hint">` block at lines 189-191 unchanged.
   - Keep `<label class="discord-intent-row">` wrapper + `<span>` for axis label unchanged.

3. **Re-class the Guilds input** (`connector-form-discord.js:198-200`):
   - Change `<input type="text" id="cf-discord-guilds" data-field="guilds-list" data-testid="discord-guilds-list" value="..." placeholder="">` to `<input class="field-input" type="text" id="cf-discord-guilds" data-field="guilds-list" data-testid="discord-guilds-list" value="..." placeholder="">`. Adding `class="field-input"` is the entire diff for this row.

4. **Re-class the Presence inputs** (`connector-form-discord.js:208-220`):
   - Presence name input: add `class="field-input"`. Existing `<input type="text" data-field="presence-name" data-testid="discord-presence-name" value="..." placeholder="Activity name">` → `<input class="field-input" type="text" data-field="presence-name" data-testid="discord-presence-name" value="..." placeholder="Activity name">`.
   - Presence type select: add `class="field-input field-select"`. Existing `<select data-field="presence-type" data-testid="discord-presence-type">` → `<select class="field-input field-select" data-field="presence-type" data-testid="discord-presence-type">`. The option entries inside are unchanged.

5. **Advanced disclosure stays as-is** (`connector-form-discord.js:226-237`):
   - MCP editor uses `<details class="mcp-tool-item">` (line 237), `<details class="mcp-server-instructions">` (line 377), `<details class="mcp-server-meta">` (line 391) — single-class-on-`<details>` precedent. The existing `<details class="discord-advanced-kv-disclosure"><summary>Advanced (kv-table)</summary>...</details>` shape already matches this precedent. No change.

6. **Re-style Auto-relay row — siblings, NOT nested** (`connector-account-editor.js:381-394`):
   - Current:
     ```javascript
     lifecycleHtml += '<div class="field-row admin-pf-row">';
     lifecycleHtml += '<label for="cf-auto-relay">Auto-relay peer replies to platform</label>';
     lifecycleHtml += '<input type="checkbox" id="cf-auto-relay" ' +
             'data-field="auto_relay_platform_replies" ' +
             'data-testid="connector-account-auto-relay-toggle"' +
             (autoRelayConfigValue ? ' checked' : '') + ' />';
     lifecycleHtml += '</div>';
     ```
   - New (mirrors `mcp-server-editor.js:529-535` EXACTLY — outer text label + inner toggle-track label are SIBLINGS):
     ```javascript
     lifecycleHtml += '<div class="field-row admin-pf-row cf-auto-relay-row">';
     lifecycleHtml += '<label for="cf-auto-relay">Auto-relay peer replies to platform</label>';
     lifecycleHtml += '<label class="tool-enable-switch">';
     lifecycleHtml += '<input type="checkbox" class="field-input" id="cf-auto-relay" ' +
             'data-field="auto_relay_platform_replies" ' +
             'data-testid="connector-account-auto-relay-toggle"' +
             ' aria-label="Auto-relay peer replies to platform"' +
             (autoRelayConfigValue ? ' checked' : '') + ' />';
     lifecycleHtml += '<span class="tool-enable-switch-track" aria-hidden="true"></span>';
     lifecycleHtml += '</label>';
     lifecycleHtml += '</div>';
     ```
   - **Critical**: the outer `<label for="cf-auto-relay">` and the inner `<label class="tool-enable-switch">` are SIBLINGS inside the `<div>` — NOT nested. (Nested labels around the same input cause two click events on a single click that cancel each other; the toggle would appear not to flip.)
   - `cf-auto-relay-row` is the new CSS-unpin hook (step 7 below).
   - `class="field-input"` on the input is critical for `attachStaticListeners` to pick up the change event (replaces the explicit handler being removed at step 8).
   - `aria-label` on the input is defensive — the inner toggle-label has no text (track-span is `aria-hidden`); the outer text label still associates via `for=id`. Mirrors MCP.
   - Verbose `<small class="form-hint">` block at lines 388-394 STAYS for L1. L3 reshapes.

7. **Add the CSS unpin override in `admin.css`** — insert near the existing precedents at lines 278-281:
   ```css
   .area-studio .field-row.cf-auto-relay-row .tool-enable-switch {
     position: relative;
     bottom: auto;
     right: auto;
   }
   ```
   This matches `tools-editor-enabled-row` + `mf-sandbox-network-row` precedents byte-for-byte. Without it, the toggle would float to `bottom: 12px; right: 12px;` of its nearest positioned ancestor per the default `.tool-enable-switch` rule at admin.css:197.

8. **Remove the now-redundant explicit Auto-relay handler** (`connector-account-editor.js:943-945`):
   - Once the input carries `.field-input`, `attachStaticListeners` (lines 931-934) registers the same `change` handler. The explicit block becomes dead code.
   - Delete the 3-line block + its M10-F8-L11-Fix-#4 comment:
     ```javascript
     // Existing — remove:
     var autoRelayToggle = container.querySelector('[data-field="auto_relay_platform_replies"]');
     if (autoRelayToggle) {
       autoRelayToggle.addEventListener('change', checkDirty);
     }
     ```
   - Also remove the preceding comment that names this block (the M10 F8 L11 Fix #4 reference) — the dirty-tracking is now uniform with all other field-input handlers; no special-case comment needed.

9. **Suppress Type-dropdown placeholder post-selection** (`connector-account-editor.js:618-623`):
   - Current:
     ```javascript
     var placeholderSelected = createType === '' ? ' selected' : '';
     html += '<option value="" disabled' + placeholderSelected + '>Select a connector type</option>';
     ```
   - New:
     ```javascript
     if (createType === '') {
       html += '<option value="" disabled selected>Select a connector type</option>';
     }
     ```
   - When a real type has already been picked (`createType !== ''`), do NOT emit the placeholder option at all. The select's selected display now drives from the matching real-type option's `selected` attribute (set later in the loop at line 626).

10. **Run Chrome MCP visual verification** after each substantive change. Suggested order:
   - After Intent re-class: take screenshot of `#studio/connectors/{id}` General tab; visually compare with design-language page's multi-select example.
   - After Guilds + Presence re-class: take screenshot; verify text inputs + select all have dark-theme borders.
   - After Auto-relay re-class: take screenshot of `#studio/connectors/new`; verify iOS toggle renders.
   - After Type-placeholder fix: open + close + re-open the Type dropdown; verify placeholder appears once, disappears after Discord pick.

11. **Run targeted browser tests**:
   - `docker exec the-one pytest tests/browser/test_flow_studio_connector_account_editor.py tests/browser/test_flow_studio_connector_account_create_and_test.py tests/browser/test_flow_studio_connector_discord_form.py tests/browser/test_flow_studio_connector_discord_vocabulary.py -m browser -x --timeout 60`

12. **Update F5 `flight.md`** — check off L1 in Checkpoints + Legs sections.

13. **Append L1 leg-progress entry** to F5 `flight-log.md`.

14. **Update this leg artifact's Status header** progressively: `planning` → `ready` → `in-flight` → `landed`.

## Edge Cases

- **Intent fieldset preserved**: cycle-1 design review caught that no `.discord-intents-set` CSS rule exists; substituting the fieldset would have removed visual grouping. The fieldset shape is preserved; only the inputs gain `.checkbox-primary`. Existing browser tests targeting `data-testid="discord-intents-fieldset"` or `<fieldset>` remain immune — verified.
- **`attachStaticListeners` overlap with explicit Auto-relay handler** (`connector-account-editor.js:931-934` static-registry + `:943-945` explicit): once Auto-relay gains `.field-input`, both register a `change → checkDirty` handler. The explicit registration becomes dead code; step 8 of Implementation Guidance removes it to keep the source minimal. If left in place, `checkDirty` runs twice per click — harmless (idempotent snapshot reads) but confusing for future readers.
- **Intent checkbox dirty-tracking**: Intent checkboxes don't go through `attachStaticListeners`'s `.field-input` filter (they're plain `<input type="checkbox">` now with `.checkbox-primary`, not `.field-input`). The existing dirty-tracking path for Intents is via the typed-form-listener registration at `connector-form-discord.js:558-562` (look for `change` event wiring on `[data-field^="intent-"]`). Adding `.checkbox-primary` does NOT change that selector. Verify Intent dirty-tracking still fires by running the editor tests.
- **Type-dropdown placeholder suppression and round-trip**: when the operator picks Discord, then accidentally clicks the select and picks the new "Select…" option (which no longer exists post-pick), they should be stuck at Discord. Verified by the absence of the placeholder option in the list when `createType !== ''`. If they Cancel + reopen the editor, `createType` resets to `''` and the placeholder reappears — natural behavior.
- **Markdown-linter or pre-commit hook on changed JS files**: no such hooks expected per F4 commits. Don't introduce any.
- **CSS specificity for `.checkbox-primary` inside `<label class="discord-intent-row">`**: with the fieldset preserved, the existing `.discord-intent-row` CSS rules (if any) continue to apply. `.checkbox-primary` from `components.css:252` styles the input directly. No conflict expected — verify visually via Chrome MCP.
- **MCP editor disclosure pattern confirmed**: MCP uses `<details class="mcp-tool-item">` / `<details class="mcp-server-instructions">` / `<details class="mcp-server-meta">` — single-class-on-`<details>` precedent. The existing `<details class="discord-advanced-kv-disclosure">` matches; no change required.
- **Browser-cached JS**: the operator may need to hard-reload the browser (Ctrl+Shift+R) to pick up the new JS. The Chrome MCP `navigate_page` with `ignoreCache: true` handles this for agent verification; the operator may need to do it manually if walking the editor in their own browser.

## Files Affected

- `the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` — Intent checkbox inputs gain `.checkbox-primary` (fieldset shape preserved); Guilds input gains `.field-input`; Presence name input gains `.field-input`; Presence type select gains `.field-input.field-select`. Advanced disclosure unchanged (already matches MCP single-class-on-`<details>` precedent).
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — Auto-relay row rewritten with `tool-enable-switch` sibling-label markup + `cf-auto-relay-row` wrapper class (lines 381-394); explicit Auto-relay change-handler at lines 943-945 + its comment REMOVED (now redundant with `attachStaticListeners`); Type-dropdown placeholder option suppressed post-selection (lines 618-623).
- `the_one/interfaces/web/static/css/admin.css` — one new ~3 LOC unpin rule `.area-studio .field-row.cf-auto-relay-row .tool-enable-switch { position: relative; bottom: auto; right: auto; }` inserted near precedents at lines 278-281.
- `missions/11-discord-connector-depth/flights/05-connector-ux-cleanup/flight.md` — L1 checkpoint + L1 leg checklist item checked off.
- `missions/11-discord-connector-depth/flights/05-connector-ux-cleanup/flight-log.md` — L1 leg-progress entry appended.
- `missions/11-discord-connector-depth/flights/05-connector-ux-cleanup/legs/01-re-style-connector-form-controls.md` — this artifact's status header updated through the lifecycle.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified (grep checks pass; Chrome MCP visual verification confirms; browser tests pass)
- [x] `docker exec the-one pytest tests/browser/test_flow_studio_connector_account_editor.py tests/browser/test_flow_studio_connector_account_create_and_test.py tests/browser/test_flow_studio_connector_discord_form.py tests/browser/test_flow_studio_connector_discord_vocabulary.py -m browser -x --timeout 60` passes
- [x] Update `flight-log.md` with L1 leg-progress entry
- [x] Set this leg's status to `landed`
- [x] Check off L1 in `flight.md` (Checkpoints + Legs sections)
- [x] Do NOT commit (F5 batches review + commit at flight end per the agentic-workflow protocol)

---

## Citation Audit

All code-location citations in this leg artifact verified against current code at leg design time (2026-05-23):

- `connector-form-discord.js:renderConnectionFields` — function confirmed at line 163.
- `connector-form-discord.js:172-192` — Intents fieldset rendering confirmed (raw `<fieldset>/<legend>`, raw `<input type="checkbox">`).
- `connector-form-discord.js:198-200` — Guilds input confirmed (raw `<input type="text">`).
- `connector-form-discord.js:208-220` — Presence name + Presence type select confirmed (raw `<input>` + raw `<select>`).
- `connector-form-discord.js:226-237` — Advanced disclosure confirmed (raw `<details>/<summary>`).
- `connector-account-editor.js:381-394` — Auto-relay row confirmed (raw `<input type="checkbox">`).
- `connector-account-editor.js:612-630` — Type-select create-mode block confirmed; placeholder option at line 623 always-emitted.
- `connector-account-editor.js:932-933` — `attachStaticListeners` selector pattern confirmed (`.editor-section .field-input:not(...)`).
- `mcp-server-editor.js:529-535` — `tool-enable-switch` sibling-label pattern confirmed at exact line range; matches the proposed Auto-relay re-style.
- `mcp-server-editor.js:237, 377, 391` — `<details>` single-class-on-element precedent confirmed (`mcp-tool-item`, `mcp-server-instructions`, `mcp-server-meta`).
- `fields-section.js:7-44` — design-language primitive examples confirmed (`.field-input`, `.field-select`, `.checkbox-primary`, `.field-info-icon`).
- `components.css:142` — `.field-input` definition confirmed.
- `components.css:184` — `.field-select` definition confirmed.
- `components.css:252` — `.checkbox-primary` definition confirmed.
- `admin.css:197` — `.tool-enable-switch` default positioning confirmed (`position: absolute; bottom: 12px; right: 12px;`).
- `admin.css:278-281` — unpin-override precedents confirmed (`tools-editor-enabled-row` + `mf-sandbox-network-row`); F5 L1 adds `cf-auto-relay-row` to this set.
- `connector-account-editor.js:943-945` — explicit Auto-relay change-handler block confirmed; F5 L1 removes after granting `.field-input` to the input.

15 citation sites verified clean. No drift repaired. Cycle-1 design review revisions captured inline.
