# Leg: tool-config-fields

**Status**: completed
**Flight**: [Settings on the library](../flight.md)

## Objective
Grow `static/js/areas/studio/tool-override-fields.js` into one shared tool-settings field module, `static/js/areas/tool-config-fields.js` (`App.toolConfigFields`), with an admin mode for Settings › Built-in tools and an agent mode for the agent Tools tab, per DD13. Then move the agent Tools tab and `agent-form-data.js` onto it, with A8 and A10 in both modes.

## Context
- **Flight decisions:** DD13 (the module's contract, as amended at Architect cycle 2), DD5, DD7 (ledger rows 8 and 10, and the agent-tab rows), DD11.
- **Split at planning** from the original leg 05: the backend text is 05a. This leg is client-only.
- **Today:**
  - `tool-override-fields.js` (291 lines) renders agent-mode fields from library controls. Its header documents every field kind.
  - `tools-form-helpers.js` `renderField` (`:59-315`) renders admin-mode fields as HTML strings, with the error painters, `show_if` and `readFieldValue` (`:382-400`, `parseInt`).
  - `agent-form-data.js:211-220` reads override values through `App.adminFormHelpers.readFieldValue`, and builds the "loaded tools" set from `data-tool-override-tool` (squawk 0223).
  - `tools-tab.js:155` calls `App.studio.toolOverrideFields`.
- **This leg builds the module and moves the agent side.** The admin editor moves onto the module in leg 07a, which then deletes `renderField` and the error painters from `tools-form-helpers.js`. Until 07a, the admin editor keeps using `tools-form-helpers.js`.
- **The DD13 contract, restated:**
  - `render(name, prop, value, opts)` with `opts.mode` (`'admin'|'agent'`), `toolName`, `operatorValue` (agent mode) and `onChange` returns `{el, control, field, value(), setValue(v), setError(msg|null), setVisible(bool)}`, or `null` when agent mode hides the field.
  - `showIf(properties, handles)` wires `show_if` visibility (admin mode).
  - `readValue(el)` dispatches on `data-field-type`; arrays go through `App.ui.chipList.valuesOf` (leg 04e); the checkbox branch is kept.
  - **Admin DOM ids and hooks kept:** `data-field="{name}"` on the control, `data-field-name` and `.tools-editor-field` on the row, ids `tef-{name}`.
  - **Agent DOM hooks kept:** `data-tool-override-tool`, `data-tool-override-field`, `data-field-type` (`data-marker` for arrays) on the value node.
  - **Number parsing:**
    - blank → `''` (skipped);
    - an integer string → the number;
    - anything else: admin mode sends the raw value (the tools PUT's 422 lands on the field in 07a); agent mode shows a client-side field error and the agent Save is refused. `agent-form-data.js` reports a blocking error through the editor's existing error path.
  - **Presentation:** booleans are the library checkbox with the label **inline** in both modes (A10; on the agent tab the label was stacked: ledger row 10). Custom preset values are humanised in both modes (A8, "4MB (custom)", "45s (custom)"; ledger row 8), from the field's unit, read from the field name suffix (`_bytes`, `_seconds`) or a schema hint. Pick one and say which.
  - **Labels and descriptions** come from the schema (05a), so the agent tab shows the written titles and info buttons.
- **`App.studio.toolOverrideFields`** stays as an alias until `tools-tab.js` moves, inside this leg. The alias is then deleted.
- `tests/browser/test_flow_studio_tool_override_fields.py:44` reads the module's file path: retarget it to the new path.
- The dead `mcp_overrides` walk in `agent-form-data.js` is deleted, keeping `var mcpOverrides = {}` (the per-tool toggles fill it).
- **Lane:** the new admin-mode test file `tests/browser/test_flow_admin_tool_config_fields.py` matches the `settings` glob (`test_flow_admin_*`). The agent-mode tests stay in `agent-tabs`.

## Inputs
- Legs 04e (`chipList.valuesOf`, `data-value`) and 05a (titles, descriptions, `config_fields`) landed.

## Outputs
- `static/js/areas/tool-config-fields.js` (new), with its `index.html` tag before `tools-tab.js` and the admin scripts. `tool-override-fields.js` is deleted.
- `tools-tab.js` and `agent-form-data.js` on the new module; `readFieldValue` no longer used by them.
- The admin mode built and contract-tested on a harness page, though not yet used by the Settings editor (07a).
- Tests:
  - the agent-mode tests retargeted;
  - a new admin-mode test file exercising every field kind on a scratch tool schema;
  - a test for agent-mode number validation;
  - a test that squawk 0223's rule still holds (a description-only Save sends no `tool_overrides`; opening one tool's panel keeps the others' stored overrides).
- `the_one/agents.md` ("Tool config fields"); `docs/ui-control-inventory.md` (the note on area composites); CLAUDE.md's control library paragraph (one sentence); ledger rows 8 and 10 confirmed with captures.

## Acceptance Criteria
1. `git grep -n "toolOverrideFields\|tool-override-fields" the_one/ tests/` finds only historical comments or nothing. `App.adminFormHelpers.readFieldValue` has no caller outside `tools-form-helpers.js`.
2. **Agent mode behaves as before**, apart from ledger rows 8 and 10 and the 05a text:
   - the `agent-tabs` lane passes, with assertions retargeted only for the label placement and the humanised custom labels;
   - squawk 0223's tests pass;
   - the NarrowSuperset locked chips (now showing the defaults since 0248) are unchanged.
3. **Admin mode** is tested for every field kind: the ids and hooks, `setError` (`aria-invalid`, `aria-describedby`), `setVisible`, `showIf`, `value()`, and number parsing.
4. **Agent-mode number validation:** "1.5" or "12abc" shows a field error, and the agent Save is refused with no PUT; blank is skipped; "12" sends 12.
5. **The module is ≤ 800 lines** (the line guard), and has no HTML-string sink and no ownership-allowance row.
6. The unit tier, the static guards, and the `agent-tabs`, `agents` and `settings` lanes pass.

## Verification Steps
- `.venv/bin/python -m pytest tests/test_ui_guards.py tests/test_ui_ownership.py tests/test_area_module_size.py tests/test_index_asset_cache_busting.py -q -x --timeout 120`.
- Lanes `agent-tabs`, `agents` and `settings` under `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1`.
- Captures of `agent-tools`, compared with the before set (rows 8, 10 and the 05a rows).
- `make test-unit` once.

## Implementation Guidance
1. Copy `tool-override-fields.js` to the new path and rename the namespace. Keep the alias. Agent tests green.
2. Add `readValue`, then switch `agent-form-data.js`. Delete the dead MCP walk.
3. Add the inline boolean and the humanised custom labels (with captures).
4. Add the agent number validation, test-first.
5. Build admin mode and `showIf`, with their tests.
6. Switch `tools-tab.js`, delete the alias and the old file, and retarget the path test.

## Edge Cases
- **A field that 05a's `config_fields` hides** never reaches `render`. A stale agent override on it stays stored. The existing console warning path in `tools-tab.js:167-171` may fire; leave it, or soften it. Record which.
- **A `show_if` that targets a hidden field:** treat the target as absent (the field stays shown).

## Files Affected
- `static/js/areas/tool-config-fields.js` (new); `static/js/areas/studio/tool-override-fields.js` (deleted); `static/js/areas/studio/tools-tab.js`; `static/js/areas/studio/agent-form-data.js`; `static/index.html`.
- Tests: `test_flow_studio_tool_override_fields.py`, `test_flow_studio_tools_overrides.py`, `test_flow_studio_tool_overrides_preserved.py`, `test_flow_admin_tool_config_fields.py` (new), plus any other `agent-tabs` file that reads labels.
- `the_one/agents.md`, `docs/ui-control-inventory.md`, CLAUDE.md, the flight log.

## Citation Audit
- `tool-override-fields.js` header (field kinds, `data-tool-override-*` on the control; `agent-form-data.js` reads through `readFieldValue`): verified (FD read).
- `agent-form-data.js` about `:211-245` (the walk, the 0223 loaded-tools rule, the MCP walk): verified (FD read).
- `tools-tab.js:155`, `:167-171`: verified (FD grep).
- `tools-form-helpers.js:59-315`, `:382-400`: from the survey.

## Design Review Amendments (cycle 1, 2026-10-23)
These override the body where they conflict.

**Split at its design review.** This leg builds the module only. The agent side moves in the new leg **05c** (`agent-tools-on-fields`).
- **This leg (05b):**
  - **`static/js/areas/shared/tool-config-fields.js`**: `areas/shared/` is a deliberate new folder for area code shared across areas (no precedent at the top level of `areas/`). Its script tag goes before `tools-tab.js` and the admin scripts. The cache-busting order rule (`js/ui/*` before `areas/**`) holds.
  - **Both modes, `showIf` and `readValue`,** tested on a harness page (admin and agent schemas); a new test file in the `settings` lane (`test_flow_admin_tool_config_fields.py`).
  - **The old `tool-override-fields.js` and `readFieldValue` stay**, and nothing switches yet.
- **Leg 05c** moves `tools-tab.js` and `agent-form-data.js`, adds the inline checkbox, A8, the agent number validation, the hidden-override carry-over and the squawk 0223 tests, and deletes the alias and the old file.

**Contract details settled at review:**
- **Booleans** use `App.ui.checkbox` (`label`, `id`, `info`, `dataset`): `cb.el` is the row (with `data-field-name`, `tools-editor-field`/`tool-override-field`) and `cb.control` the control (`tef-{name}` through `id`, the dataset on the input). There is no more detaching the input into `ui.field`.
- **A8, units by field-name suffix:** `_bytes` → B/KB/MB (÷1024, matching the existing `ui_choices` labels); `_seconds` → s/m/h. Applied only when the value divides evenly; otherwise the raw number plus its unit ("1500000 B (custom)"). Only on the dropdown "(custom)" path. A unit test walks every served schema and asserts that each integer property with `ui_choices` either has a known suffix or is listed as unitless.
- **Numbers in agent mode:** use a text input with `inputmode="numeric"` instead of `type=number`. A `type=number` input returns `''` for "12abc" (`validity.badInput`), so the field would be silently skipped. Validation states one message for every invalid input: "Enter a whole number." Min and max are not checked client-side (the server and resolver do); record that.
- **Admin mode hooks for 07a:** the chip list carries `data-field` and `data-field-type` on `chips.el`, and `tef-{name}` on its inner input (`test_flow_chiplist_label_resolver.py` reads it). `showIf(properties, handles)` keys by field name. A harness test covers a `show_if` that targets a hidden field (the field stays shown).
- **AC1 is reworded:** no caller of `readFieldValue` in `areas/studio/` after 05c. `tools-editor.js` (`:255`, `:279`) and `test_flow_admin_tools_editor.py:608` keep it until 07a. `readFieldValue`'s `parseInt` behaviour stays for the admin editor until 07a.

Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
