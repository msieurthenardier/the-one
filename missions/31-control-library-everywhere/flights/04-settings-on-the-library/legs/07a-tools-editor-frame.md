# Leg: tools-editor-frame

**Status**: landed
**Flight**: [Settings on the library](../flight.md)

## Objective
Rebuild the Built-in tools editor's frame, fields and error handling on the library:
- `editorShell` (default variant, `inset: 'none'`) with the "Settings / Built-in tools" breadcrumb and the Library-size title (B2);
- the tool prompt in its own section as a `codeBlock` (A14);
- a Configuration section with the Enabled switch (DD8-4, A9) and fields from the shared module's admin mode (B3, A10, A12);
- 422 errors on fields through `fieldErrors` and everything else through `editorShell.setError`, announced once (DD8-9).

This leg leaves the Save/Cancel value model (07b) and the Test section (07c) on their current behaviour, wired to the new frame. It deletes `renderField` and the error painters from `tools-form-helpers.js`, and every `App.icon` call in the tools editor.

## Context
- **Flight decisions:** DD3 (errors), DD5 (07b), DD6 (the editor), DD8-4 and DD8-9, DD13 (the module), DD7 (ledger rows 9, 10, 12, 13, 14, 26, 27 and 41), DD11, DD12 (`codeBlock` legacy names until leg 08b).
- **Tier HIGH:** a security-adjacent surface. The editor edits tool safety settings (allowlists and denylists, sandbox network) and secrets (search API keys). Squawk 0248's lesson: the editor must show and send the real defaults. The shared module trusts `prop.default`.
- **Today** (`tools-editor.js`, 749 lines): one HTML string per mount (`:105-197`, 8 sinks). The header is hand-built; the Prompt block sits inside `.editor-header`; the Enabled row is the legacy switch with `aria-label` = the state text (`:235-242`); fields come from `helpers.renderField` (strings). The errors:
  - a raw `fetch`;
  - a 422 puts inline `span.field-error` on matched rows plus `applyModelLevelHighlights` (substring);
  - the rest goes to `.editor-error` (`role=alert`), then is promoted to `.editor-error-banner` (also `role=alert`), which is the double announcement.
- **The frame after this leg:**
  - `editorShell({breadcrumb: {lead: 'Settings / ', label: <the Built-in tools label from App.settingsPages>, href: '#settings/tools'}, title: name, titleLevel: 1 or the Library size (B2: match the Library editors' title size; check the Library editors' level and computed size), subtitle: <the category's display name> (A13), inset: 'none', errorRole: 'alert', actions: {cancel, save}})`;
  - a prompt section: `App.ui.section({title: 'Prompt', …})` with `App.ui.codeBlock({text: description, label: 'Tool prompt', maxHeight: 'short'})`;
  - Configuration: `App.ui.section({title: 'Configuration', layout: 'stack'})` with the Enabled `App.ui.toggle({label: 'Enabled for all agents', dataset: {field: 'enabled'}, testid?})` (the visible label is inline on one line; the name is the static label; A9, DD8-4). Then, for each served property, `App.toolConfigFields.render(name, prop, value, {mode: 'admin', toolName, onChange})`. With no properties: plain muted left-aligned text "No additional configuration." (A12), not `.empty-state`.
  - Field width (B3): the full form column, numbers `width: 'short'`.
  - The Test section stays string-built in this leg only if 07c is next and its tests stay green. Otherwise move it as is into a temporary DOM wrapper. Record which.
- **Errors (DD3):**
  - a 422 detail through `App.api.fieldErrors(err, fieldNames)` → each field's `setError`, and `editorShell.setError(result.text)` for the rest;
  - every other failure → `editorShell.setError`;
  - the `.editor-error-banner`, `.editor-error` promotion, `applyModelLevelHighlights` and `humanizeValidationMsg` are deleted (ledger row 11 covers the message text; DD3's ledger row covers the retired highlight). The pinned `field-error-highlight` test is retargeted to assert the field's error and `aria-invalid`.
  - Announced once: one `role=alert` region per error; a field error is not repeated at editor level.
- **`tools-form-helpers.js` after this leg:** only the Flight 5 chip-list path (`renderChipListEditor`, `wireChipListEditor`, `readChipListValue`, `chipExists`, `cssEscape` if used) and `readFieldValue` (if still used by the MCP editor, otherwise deleted). Expected about 230 lines. Its 2 `App.icon` calls (`:111`, `:283`) live in `renderField`, so they go.
- **`admin.css`:** the editor rules this leg makes dead (`.tools-editor-enabled-row`, `.editor-prompt-block`/`.editor-prompt-text`, `.editor-subtitle-meta`, `.editor-error-banner*`, `.field-unknown-type`, the `.tools-editor-field` width rules, `.area-admin .tool-enable-switch` uses from the editor; keep the switch rules for leg 10). The a11y pin `.editor-error-banner` (`test_design_tokens_a11y.py:469-492`) moves to the shell's error style.
- **Behavior spec:** `tests/behavior/agent-governance-and-search.md` steps 1-5 walk the `web_search` editor (the dropdown, the `show_if` reveal, the password eye "Show password"/"Hide password", the masked round-trip). Re-read them against the new editor, and amend any step whose selector or wording changed.

## Inputs
- Legs 04a-04f, 05a and 05b landed (the shell page and inset options, `codeBlock`, `fieldErrors`, the module's admin mode).

## Outputs
- `tools-editor.js` rebuilt (target ≤ 600 lines; the line guard is the gate), with zero sinks and no ownership rows. All 6 `App.icon` calls and its `App.showFlash` call gone (the flash moves to `App.ui.flash`, wired properly in 07b).
- `tools-form-helpers.js` reduced to the Flight 5 path; its ownership rows reduced to the chip-list ones.
- `tools-page.js` mounting through the new editor API (`App.admin.renderToolsEditor` kept as the entry, or renamed with its asset test updated).
- Tests:
  - DD8-4 and DD8-9, test-first;
  - the B2, A9, A12, A13 and A14 checks;
  - `test_flow_admin_tools_editor.py` retargeted: the info icon's `title` (it is now a toggletip, ledger row 41), `.tool-enable-switch` → the switch role, `.editor-error-banner` → the shell error, `.save-btn`/`.cancel-btn` kept by the shell.
- `admin.css` cleaned. Allowance and sink tables updated. The registry: `cancel-tool-btn` and `save-tool-btn` kept through the shell's testid options.
- `agents.md` "Settings item pages" and the tools editor section; the catalogue rows for consumers.

## Acceptance Criteria
1. **DD8-4:** the Enabled control is `role=switch`, named "Enabled for all agents", with its label visible on one line, and its state is announced. The test fails today (the name is the state text).
2. **DD8-9:** a non-field 422 and a 500 each produce exactly one `role=alert` announcement (count the alert regions that change), and a field 422 produces the field's error with no editor-level repeat. The tests fail today.
3. **Field errors:** a 422 on `redirect_cap` shows "Must be 0 or more" on that field with `aria-invalid`. A model-level 422 shows at editor level.
4. **The frame:**
   - the breadcrumb "Settings / Built-in tools" with "Built-in tools" linked to `#settings/tools`;
   - the title at the Library editors' computed size (B2);
   - the category subtitle (A13);
   - the prompt as a code block in its own section, with no reflow when the editor becomes dirty (A14: its width is the same clean and dirty);
   - A12's text left-aligned;
   - B3's widths.
5. **The real defaults show** for a never-saved Filesystem and Execution tool (0248's browser tests pass unchanged), and **a Save still round-trips them** (until 07b reworks Save, today's Save path is wired to the module's `value()` handles).
6. **The `show_if` reveal** works (`web_search` SearXNG), with hidden rows' values still submitted as today.
7. **Counts:**
   - `tools-editor.js` has no sink row and no ownership row;
   - `tools-form-helpers.js` keeps only chip-list rows;
   - `git grep -n "App.icon(" the_one/interfaces/web/static/js/areas/admin/` finds nothing.
8. The behavior spec `agent-governance-and-search.md` is checked, and amended where needed.
9. The captures of every tool editor surface match the before set apart from ledger rows 7-14, 26, 27 and 41.
10. The unit tier, the static guards, the emitted-class guard, and the `settings`, `shared` (the chip-list label test) and `routing` lanes pass.

## Verification Steps
- `.venv/bin/python -m pytest tests/test_ui_guards.py tests/test_ui_ownership.py tests/test_design_tokens_a11y.py tests/test_tools_admin_editor_assets.py tests/test_tools_form_helpers_assets.py tests/test_tools_test_button_assets.py tests/test_area_module_size.py -q -x --timeout 120`.
- The lanes under `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1`.
- The capture compare.
- `make test-unit` once.

## Edge Cases
- **Secrets** (`ui_hint: password`): the module's `secretInput` with the masked value. Re-masking after Save is 07b's.
- **A tool with an unknown field type:** the module's JSON input. A test keeps it.
- **Field names repeating across tools** sharing a Config: every lookup is on the current editor's handles, never a document query.

## Files Affected
- `static/js/areas/admin/tools-editor.js`, `tools-form-helpers.js`, `tools-page.js`, `static/css/admin.css`.
- `tests/browser/test_flow_admin_tools_editor.py`, `test_flow_settings_items.py`, `test_flow_settings_visible_fixes.py`, `test_flow_settings_focus_after.py`, `test_flow_chiplist_label_resolver.py`, the asset tests, `test_design_tokens_a11y.py`, the allowance tables.
- `tests/behavior/agent-governance-and-search.md` (if amended), `docs/ui-testid-registry.md`, `docs/ui-control-inventory.md`, `the_one/agents.md`, the flight log.

## Citation Audit
- `tools-editor.js:105-197` (the string mount), `:146` (the defaults read), `:235-242` (the Enabled row): verified (FD read).
- The sinks and icon counts are from the survey (`f4-survey-tools.md` §0) and the recon (all 8 `App.icon` calls in the editor and `renderField`).

## Design Review Amendments (cycle 1, 2026-10-23)
These override the body where they conflict.

**Split at its design review.** This leg keeps the frame, the prompt, the Enabled toggle, the module fields, the handle-based snapshot, Save and Cancel, and the Test section moved to DOM. The new leg **07b** (`tools-editor-errors-and-purge`) takes the error rewiring (DD8-9, `fieldErrors`, the shell error, the banner retirement), the `tools-form-helpers.js` and `admin.css` purges, the a11y pin, the bulk test retargeting and the behavior-spec check. The save-model leg is now **07c** and the Test leg **07d**.

**In this leg (07a):**
- **The handle-based value model, as the minimum Save and Cancel need:** `snapshot()` from the handles' `value()` and the toggle, dirty by snapshot comparison, the Save body from `snapshot()`, and `App.toolConfigFields.showIf(properties, handles)`. `getFormSnapshot`, `applyShowIf` and every `container.querySelector('[data-field=…]')` read are gone. 07c then adds the real behaviour changes: busy, the guards, patch-in-place Cancel, the response baseline, re-masking.
- **Interim wiring until 07b and 07c:**
  - Save is still a raw `fetch` PUT, with errors shown through `editorShell.setError` (plain message; field painting arrives in 07b);
  - Cancel still remounts through `renderToolsEditor` with `originalToolDetail`, which now rebuilds the shell. The old `editor-unsaved` node swap (`:439-445`) is gone; check `test_flow_settings_items.py:178`, which pins the caption node surviving Cancel, and retarget it to the caption's text and state if the node identity changes. It is a ledger row if anything visible moves.
- **`onMount(api).setEnabled`** (the list toggle for the open tool, `:450-470`) is kept, acting on the toggle handle and the baseline. The Settings item tests and `test_router_guard` depend on it.
- **B2:** `titleLevel: 2`. The Settings page header owns the page's single `h1`. The shell's `.editor-header-text .editor-title` gives the Library size (`components.css` about `:1320`), checked as a computed font size, with an `h1` count of 1. The shell sets `tabindex=-1` on the title (verify) for `focusTitle` and focus-after.
- **The Test section** moves to DOM code in this leg, behaviour unchanged:
  - `App.ui.section({title, info})` (04b's option);
  - an `App.ui.button` with the `play` icon option (not `App.icon`);
  - today's input, result span and output `pre` rebuilt with `util.el`.

  So the editor has no sinks and no `App.icon` calls after 07a. 07d redesigns the result.
- **Selectors to keep:**
  - the module keeps `data-field="{name}"` on the `<input>`/`<select>` itself (`input[data-field=…]` and `select_option` are used);
  - the Enabled toggle has `dataset: {field: 'enabled'}` (`test_flow_settings_items.py:131` `.settings-item [data-field="enabled"]`);
  - `[data-field="search_backend"]` is pinned by `test_flow_cross_area_dirty_gate.py:54` and `test_flow_admin_settings_nav.py:481`. Add both files to Files Affected.
- **AC6 has an explicit test:** a `show_if`-hidden row's value is still submitted.
- **Unknown field types:** the module's tests (05b) cover the JSON input and its warning. This leg does not test them twice.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
