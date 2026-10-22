# Leg: tools-tab

**Status**: completed
**Flight**: [Agents on the library](../flight.md)

## Objective
Rebuild the agent editor's Built-in Tools tab from library controls:
- `App.ui.groupTile` per category, with the tristate master;
- `App.ui.toolRow` per tool, with the "Overrides" disclosure;
- override fields from a new studio module, `tool-override-fields.js`, which composes `App.ui.field`, `chipList`, `infoButton` and the inputs.

The tab mounts once and is patched through `setAgent`. `tools-tab.js` and the new module end with zero sinks and zero allowance rows. `tools-form-helpers.js` stays byte-identical for the admin editor (Flight 3).

## Context
- **Flight decisions:** DD3, DD4 (the switch; the chip "×"), DD6, DD7, DD8 (corrected below), DD10, DD11.
- **The leg-08 design review** (2026-10-21) split leg 08 into 08a (the `main` merge and override port, landed before this leg) and this leg.
- **Legs 01-08a have landed.** That includes 05 (`infoButton` toggletip), 06a/06b, 07a/07b (the `groupTile` `master.dataset` and the `toolRow` `inputDataset` options; the Knowledge and MCPs tabs no longer use `.tool-toggle`/`.tool-switch`) and 08a (the 0223 rule ported). Read the flight log and the actual `js/ui/tile.js`/`chip-list.js`/`choice.js` APIs.
- **Today** (re-locate by symbol):
  - `tools-tab.js`: category tiles (`[data-category]`, a master `input[data-category-master]` with `aria-label "Enable all {Category} tools"`, indeterminate; `aria-expanded` on the tile root); count chips "N / M enabled"; per-tool `details.tool-tile[data-tool]` with an `input[data-tool]` checkbox; the Overrides affordance; lazy override bodies through `adminFormHelpers.renderField` (string plus `innerHTML`); the `time-tool-note`; disabled-tool rows.
  - Seeding (about `:395-420`) pre-fills NarrowSuperset lists with the operator's items as **locked chips**.

## Decisions (binding)
- **`renderFieldNode` goes in a new module,** `js/areas/studio/tool-override-fields.js`, not `tools-form-helpers.js`. That file's class literals are frozen by the ownership ratchet, and the admin editor must stay byte-identical. The DD8 text that names `tools-form-helpers.js` is superseded.
  - It emits `data-tool-override-tool`, `data-tool-override-field`, `data-field-type` and `data-marker` **on the control element itself**, so 08a's ported `loadedTools` rule and `readFieldValue` keep working unchanged.
  - Field kinds:
    - boolean: checkbox;
    - integer: number input, with min/max from the Narrow rule (`value <= operatorValue`);
    - integer dropdown: select over `ui_choices`, filtered to `<=` the operator value, with a "(custom)" option for an unknown current value;
    - string dropdown: select;
    - string: text input;
    - password: `secretInput`;
    - array: `chipList` with `data-marker`; its `validate` reproduces NarrowPrefix and Narrow-subset exactly, each rule listed and tested;
    - unknown: JSON text input;
    - the info button is `App.ui.infoButton` (the toggletip).
- **Locked chips** are not removable and **are sent as part of the union** (`chipList.values()` and the DOM read include them), as today.
- **No node versions of `renderFieldErrors`/`applyShowIf`.** Nothing in `studio/` calls them, agent-mode fields have no `show_if`, and no agent-editor PUT-422 path paints per-override errors (confirm by grep). Record "none needed" in the flight log.
- **Locator mapping:**
  - tile root `dataset {category}`;
  - master `dataset {categoryMaster: <Category>}`, `aria-label` kept;
  - row `inputDataset {tool: <name>}`;
  - `aria-expanded` lives on the expand button;
  - the count chip through `setCount`, never hidden when there are tools.
- **Patch-only and Cancel:** the tab exposes `{setAgent(agent), destroy}`.
  - **After Save** (same identity), `setAgent` updates the rows' checked and disabled states, the masters and the counts, and **keeps loaded override bodies**: their values now equal the stored ones.
  - **Cancel** drops every loaded override body (clears it, closes the disclosure, re-arms `onFirstOpen`), so the next open re-renders from the stored agent.
  - A rename is a new identity, so the tab fully remounts (06a).
  - The tab is removed from 06a's interim list.
  - A master `setMaster` is silent. A row click calls `setMaster('mixed'|'on'|'off')` and `setCount`.

## Acceptance Criteria
- [ ] **The tab** is built as described above, with today's intro text, testids and `data-*` hooks. The `current_time` row carries the `time-tool-note`; disabled rows show the strike-through, `title` and no affordance. The count text "N / M enabled" and the 23 tool rows are still asserted, by `input[data-tool]` or the row `[data-tool]`, not `details.tool-tile`.
- [ ] **`tool-override-fields.js`** renders every field kind above, with tests for each kind and for each Narrow rule (accept and reject).
- [ ] **Patch and Cancel:**
  - an override disclosure that is open, with focus inside, survives a same-identity Save;
  - edit an override, Cancel: the field shows the stored value when reopened;
  - Save with changed `tool_overrides`: the bodies reflect the saved values;
  - an agent with a stored override on a tool the operator has since disabled keeps it (no body, so the 0223 rule preserves it).
- [ ] **Tests:**
  - `test_flow_studio_tools_overrides.py` (about `:72-74`, `:86`, `:105`, `:109`, `:112`, `:125-127`, `:136`, `:153`, `:164`, `:219-229`, `:300`, `:318`, `:362-370`, `:393`);
  - `test_flow_studio_time_tool.py` (`:45-47`, `:66-67`, `:122`, `:141`, `:158`);
  - `test_flow_agent_tabs.py` `:205`, `:234`, `:248` (**this leg owns these lines**; 07a/07b did not touch them).

  Move them to the new locators **without weakening** any assertion. Check the other grep hits (`_lists.py`, `test_flow_admin_tools_grid.py`, `test_flow_settings_items.py`, `test_flow_settings_visible_fixes.py`); they are expected to be admin-scoped and unchanged. The 0223 browser tests keep passing.
- [ ] **CSS:** after confirming by grep that no remaining JS uses them, delete `.tool-toggle`, `.tool-switch` and `.tool-row-disabled .tool-toggle`, the `.tools-category-tile*` and `.tool-tile*` studio rules, `.mcp-source-tile-toggle` and `.mcp-tool-toggle-name` (if unused), and the dead `.tool-actions`.
  - Update `tests/test_design_tokens_a11y.py` (about `:643-680`) and `test_deep_violet_computed_styles.py` (`:54`): retarget the switch pins to the library toggle's rules, keeping the same contrast checks.
  - Keep any legacy rule that `test_ui_tile_contract.py`'s comparison needs (or move it into a test fixture), as 07b decided.
  - `.area-admin .tool-tile*` stays.
- [ ] **Zero:** `tools-tab.js` and `tool-override-fields.js` have no sinks and no allowance rows. `tools-form-helpers.js` is unchanged (`git diff` empty), and its rows are recorded as Flight 3 debt.
- [ ] **Captures:** `agent-tools` and `admin-builtin-tool-editor` to `…/m31-f2-after-08b/`. Agent Tools differs only by DD4 items 1 and 2; the admin editor shows no difference.
- [ ] **Gates:** `make test-unit`; the static guards and ownership checks; the contracts lane if a library option is added; the `agents` and `settings` lanes under netns.
- [ ] **Docs:** `the_one/agents.md` covers the Tools tab, `tool-override-fields.js`, the locked-chip and loaded-set rules, and the Cancel/Save behaviour.

## Files Affected
- `the_one/interfaces/web/static/js/areas/studio/{tools-tab,tool-override-fields,agent-editor-controller}.js` (the interim list), `index.html` (the new script and the pin), `css/studio.css`, `css/components.css` (comment copies).
- `tests/browser/test_flow_studio_tools_overrides.py`, `test_flow_studio_time_tool.py`, `test_flow_agent_tabs.py`, plus new tests; `tests/test_design_tokens_a11y.py`, `test_deep_violet_computed_styles.py`.
- `tests/_ui_ownership_allowance.py`, `tests/test_ui_guards.py`, `tests/test_index_asset_cache_busting.py`.
- `the_one/agents.md`.

## Citation Audit
From the leg 08 design review (2026-10-21; post-split tree and `origin/main` `f6b2ed0`).

## Design Review Addenda (2026-10-21)
- **Dirty tracking (binding).** `wireEditorEvents` only listens to `.field-input`, `.field-textarea`, `.field-select` and `.tool-toggle`, so the new library inputs would not mark the form dirty. Each control's own `onChange` (`toggle`, `toolRow`, `groupTile` `master.onChange`) calls the editor's dirty callback directly, passed in through the tab's ctx. A test checks that clicking a switch or checkbox enables Save and shows `.editor-unsaved`. It uses a real click, not an `evaluate` flip. This applies to both the category masters and the tool rows.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
