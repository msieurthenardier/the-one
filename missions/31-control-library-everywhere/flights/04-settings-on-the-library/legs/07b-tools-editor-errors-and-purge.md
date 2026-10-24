# Leg: tools-editor-errors-and-purge

**Status**: ready
**Flight**: [Settings on the library](../flight.md)

## Objective
Finish moving the tools editor onto the library:
- errors through `App.api.fieldErrors`: field messages on fields, the rest through `editorShell.setError`, one announcement each (DD8-9);
- the `.editor-error-banner` retired;
- `tools-form-helpers.js` reduced to what other callers still need;
- the dead editor rules removed from `admin.css`;
- the a11y pin, the bulk of the editor tests and the behavior spec brought in line.

Split from leg 07a at its design review (2026-10-23).

## Context
- **Flight decisions:** DD3 (error placement, `fieldErrors`), DD8-9, DD10, DD11. Ledger rows 11 and 41, and DD3's retired model-level highlight.
- **After 07a,** Save shows every error as plain text through `editorShell.setError`.
- **This leg's error path:**
  - a 422 detail goes through `App.api.fieldErrors(err, fieldNames)`: each matched field gets `handle.setError(message)`, and the rest goes to `editorShell.setError(result.text)`;
  - any other failure goes to `editorShell.setError`;
  - only the shell's error has `role=alert` (`errorRole: 'alert'`); confirm it is the only one;
  - a field error is never repeated at editor level.
  - `applyModelLevelHighlights` and both `humanizeValidationMsg` copies are deleted. The pinned `field-error-highlight` test is retargeted to the field's error and `aria-invalid`.
- **`tools-form-helpers.js` after this leg:**
  - **deleted:** `renderField`, `renderFieldErrors`, `clearFieldErrors`, `clearFieldErrorA11y`, `humanizeValidationMsg` (no other callers);
  - **kept:** the chip-list path (`renderChipListEditor`, `wireChipListEditor`, `readChipListValue`, `chipExists`) and `cssEscape` for the MCP editor (Flight 5); `readFieldValue` only if `agent-form-data.js` still uses it (after 05c it should not; then delete it, together with its admin-editor uses, which 07a removed).
  - Measure the final line count (about 711 lines today).
- **`admin.css`:** remove the rules 07a and this leg make dead: `.tools-editor-enabled-row`, `.editor-prompt-block`/`.editor-prompt-text`, `.editor-subtitle-meta`, `.editor-error-banner*`, `.field-unknown-type`, the `.tools-editor-field` width rules, and the editor's `.area-admin .tool-enable-switch` uses (the switch rules themselves stay for leg 10).
- **The a11y pin:** `test_design_tokens_a11y.py:469-492` pins the `.editor-error-banner` contrast in `admin.css`. It moves to the shell's error style (`.editor-error` in the library). Name the class in the test.
- **Behavior spec:** `tests/behavior/agent-governance-and-search.md` steps 1-5 (the `web_search` editor) are re-read and amended if a selector or wording changed.

## Inputs
- Legs 03a (`fieldErrors`) and 07a landed.

## Outputs
- `tools-editor.js` with the DD3 error path; `tools-form-helpers.js` reduced; `admin.css` cleaned.
- Tests:
  - DD8-9, test-first: a non-field 422 and a 500 each produce one `role=alert` change, and a field 422 shows on its field with no editor-level repeat;
  - a field 422 on `redirect_cap` shows "Must be 0 or more" with `aria-invalid`;
  - a model-level 422 shows at editor level;
  - `test_flow_admin_tools_editor.py`, `test_flow_settings_visible_fixes.py`, `test_flow_settings_focus_after.py`, `test_flow_chiplist_label_resolver.py`, the asset tests (`test_tools_admin_editor_assets.py`, `test_tools_form_helpers_assets.py`) and `test_design_tokens_a11y.py` retargeted; the info icon's `title` is now a toggletip (ledger row 41).
- The allowance tables:
  - `tools-editor.js` has no sink or ownership rows;
  - `tools-form-helpers.js` keeps only chip-list rows;
  - `admin.css` loses its editor rows.
- The behavior spec checked or amended; the registry and catalogue updated; `agents.md` "Settings item pages".

## Acceptance Criteria
1. The DD8-9 tests fail before and pass after.
2. The field-error, model-level and humanised-message tests pass.
3. `tools-form-helpers.js` has none of the deleted functions. `git grep -n "renderField\|humanizeValidationMsg\|applyModelLevelHighlights" the_one/` finds nothing.
4. The `admin.css` rules above are gone; the unused-selector report shows no new dead rule; the a11y pin targets the shell's error class.
5. The behavior spec is checked (and amended if needed).
6. The captures of every tool editor surface match the before set, apart from ledger rows 7-14, 26, 27 and 41.
7. The unit tier, the static guards, the emitted-class guard, and the `settings`, `shared` and `routing` lanes pass.

## Verification Steps
- `.venv/bin/python -m pytest tests/test_ui_guards.py tests/test_ui_ownership.py tests/test_design_tokens_a11y.py tests/test_tools_admin_editor_assets.py tests/test_tools_form_helpers_assets.py -q -x --timeout 120`.
- Lanes `settings`, `shared` and `routing` under netns; the capture compare; `make test-unit` once.

## Files Affected
- `static/js/areas/admin/tools-editor.js`, `tools-form-helpers.js`, `static/css/admin.css`.
- The tests listed above, `tests/_ui_ownership_allowance.py`, `tests/test_ui_guards.py`.
- `tests/behavior/agent-governance-and-search.md` (if amended), `docs/ui-testid-registry.md`, `docs/ui-control-inventory.md`, `the_one/agents.md`, the flight log.

## Citation Audit
- From the 07a design review: `readFieldValue` callers `agent-form-data.js:220`, `:261` (before 05c); the a11y pin `test_design_tokens_a11y.py:469-492`; the helper functions' callers.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
