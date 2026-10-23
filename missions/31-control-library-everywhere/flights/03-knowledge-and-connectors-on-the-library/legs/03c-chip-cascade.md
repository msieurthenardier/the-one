# Leg: chip-cascade

**Status**: completed
**Flight**: [Knowledge and connectors on the library](../flight.md)

## Objective
Fix the chip-list cascade defect (flight DD8-6), test-first. A library `App.ui.chipList` must render with its own owned rules (the locked-chip fill, the invalid border, the muted remove ×) under any area ancestor. The string-built chip lists keep their current look: the Settings tools editor (Flight 4) and the MCP editor (Flight 5).

## Context
- **The cause** (flight DD4's layer rule; confirmed at Architect cycles 1 and 2):
  - `index.html:12` declares `@layer tokens, base, components, areas, utilities`.
  - `css/admin.css` is `@layer areas`, and `css/components.css` is `@layer components`. So **any** `areas` rule beats **any** `components` rule, whatever its specificity.
  - `admin.css` about `:375-440` styles `.area-admin .chip-list-editor` / `.area-studio .chip-list-editor` and their `.chip`, `.chip-remove`, `:focus-within` and `.chip-list-input` descendants. On a library chip list under `.area-studio` they override `components.css` about `:2219-2260` (`.chip-list-editor.is-invalid`, `.chip-list-editor .chip[data-locked]`, `.ui-chip-remove`).
  - **Visible today:** the agent Tools tab's locked (NarrowSuperset) chips get the accent-translucent fill instead of `--surface-elevated` with opacity 0.7.
  - **Latent:** the area `border` cancels `.is-invalid`'s red border.
- `App.ui.chipList` (`js/ui/chip-list.js` about `:38-41`) emits `chip-list-editor` plus the caller's `className`, so there is no library-only class to target. Its input also uses `chip-list-input`. Confirm by reading the file.
- **Consumers:**
  - library: `studio/tool-override-fields.js` (about `:238`, the agent Tools tab overrides), the only one today;
  - string-built: `admin/tools-form-helpers.js` `renderChipListEditor` (Settings tools editor) and `studio/mcp-server-editor.js` (about `:958`, `:985`, `:998`, `:1634`, `:1729`).
- **Also in `admin.css`, string path only, left alone:** `.area-admin .tools-editor-field … .chip-list-editor` (about `:342-348`, the max-width) and `.field-error-highlight .chip-list-editor` (about `:367-370`). They match string-built lists inside `.tools-editor-field`. Check whether a library chip list can ever sit inside `.tools-editor-field` (today it cannot) and record that.
- **DD11:** computed-style checks mount under an area ancestor (`host.className = 'area-studio'` and `'area-admin'`). The precedent is `tests/browser/test_ui_chip_list_contract.py` about `:290-292`, which already has a legacy fixture (`LEGACY_LOCKED_CHIP_CSS`).

## Inputs
- **Requires leg 01 to have landed** (the lane names).
- `js/ui/chip-list.js`, `css/components.css` (the `App.ui.chipList` section), `css/admin.css` (`:340-445`), `tests/browser/test_ui_chip_list_contract.py`, `docs/ui-control-inventory.md` (the chipList row and its owned classes), `tests/_ui_ownership_allowance.py` (the `css/admin.css` `chip-list-editor: 12`, `chip-list-input: 2` and `chip: 2` rows).

## Outputs
- **`App.ui.chipList`** adds an owned marker class to its root (for example `ui-chip-list`) and to its input (for example `ui-chip-list-input`) while keeping `chip-list-editor`/`chip-list-input`, which tests and the shared helpers may read. Grep tests for `.chip-list-editor` before choosing whether to keep them, and keep them if any test or helper reads them.
- **`admin.css`'s area chip rules** are narrowed with `:not(.ui-chip-list)` on the root selector (and the equivalent for the input), so they match only string-built lists:
  - the root, `:focus-within`, `.chip`, `.chip-remove` and its `:hover`;
  - `.chip-list-input`.

  No declaration changes.
- **The ownership allowance** for the `admin.css` chip rows is re-counted. The narrowing keeps the same class names in `admin.css`, so the counts may not change. Record the new numbers, never raising one without a flight-log reason.
- **The catalogue row** for chipList lists the marker classes.
- **The contract test** first reproduces the defect, then pins the fix.

## Acceptance Criteria
- [ ] **A new contract test reproduces the defect first** (it fails before the fix, recorded in the flight log with the failing assertion). With a library chip list mounted under an `area-studio` ancestor, and again under `area-admin`, in light and dark themes and both engines:
  - a locked chip's computed `background-color` is `--surface-elevated`'s resolved value and its `opacity` is `0.7`;
  - after `setError(true)`, the root's `border-color` is `--status-danger`'s value;
  - the remove ×'s colour at rest is `--fg-secondary`.
- [ ] **After the fix** that test passes, and a legacy string-built fixture under the same ancestors keeps today's look: the chip fill is accent-translucent, and the remove × is `--accent`. The string-built lists are unchanged.
- [ ] **The agent Tools tab's locked chips** (a NarrowSuperset override) show the library look in a browser test on the real surface (the `agent-tabs` lane). Extend an existing tools-override test with a computed-style assertion.
- [ ] The Settings tools editor's chip list and the MCP editor's string chips look unchanged: the `settings` and `mcp` lanes pass, plus a computed-style assertion in one existing test of each if none exists.
- [ ] `tests/test_ui_ownership.py`, `tests/test_ui_guards.py`, `tests/test_token_definitions.py`, `tests/test_design_tokens_a11y.py` and `tests/test_ui_control_inventory.py` pass, and no allowance grows.
- [ ] `contracts-controls`, `contracts-overlay`, `agent-tabs`, `settings` and `mcp` pass with `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1`, and `make test-unit` passes.
- [ ] **Ledger row:** "agent Tools tab | locked chips get the library fill back; an invalid chip list shows its red border | DD7 item 9, DD8-6".

## Verification Steps
- The new contract test, run alone, before and after the fix.
- `--lane agent-tabs`, `--lane settings`, `--lane mcp`, `--lane contracts-controls` and `--lane contracts-overlay` under netns and WebKit; `make test-unit`.

## Implementation Guidance
1. **Log a start line.** Write the failing test and run it; record the failure.
2. **Add the marker classes** in `chip-list.js`. Narrow the `admin.css` selectors. Run the test.
3. **Add the real-surface assertions** (agent Tools tab, Settings tools editor, MCP editor).
4. **Catalogue row, allowance re-count, guards, lanes. Flight log:** the entry and the ledger row.

## Edge Cases
- **`:not()` and specificity:** the narrowed area rules stay in `@layer areas`, so specificity does not matter. The layer decides, and the narrowing is what makes the area rules stop matching.
- **The chip-list label resolver test** (`test_flow_chiplist_label_resolver.py`, about `:60-90`) reads `tef-*` ids and `.chip-list-input` on the Settings string path. It must pass unchanged in `shared`; run it.
- **Focus ring:** `:focus-within` is narrowed too, so a library chip list's focus border comes from `components.css` (the same `--accent`; no visible change).

## Files Affected
- `js/ui/chip-list.js`, `css/admin.css`, `docs/ui-control-inventory.md`, `tests/_ui_ownership_allowance.py` (if the counts change)
- `tests/browser/test_ui_chip_list_contract.py`, and one test each in the agent-tabs, settings and mcp lanes (computed-style assertions)
- The flight log

## Citation Audit
Checked at `332496d` on 2026-10-22 (FD read):
- `admin.css:340-445`;
- `components.css:2214-2260`;
- `chip-list.js:30-45`;
- `index.html:12` (the layer order), verified at Architect cycle 2.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
