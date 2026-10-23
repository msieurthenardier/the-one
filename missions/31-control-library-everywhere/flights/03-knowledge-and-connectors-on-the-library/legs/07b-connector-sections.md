# Leg: connector-sections

**Status**: completed
**Flight**: [Knowledge and connectors on the library](../flight.md)

## Objective
Finish the connector editor on the library:
- Pairing: the code in `copyField`, with "Copy pairing code";
- the Channel → agent map on `App.ui.keyValueTable`, fixing DD8-1 and DD8-8 test-first;
- the Danger zone through `App.ui.dangerZone`.

This retires the last `App.showFlash`/`App.confirmDelete` calls and the hand-built nodes in `connector-editor.js`, so that file reaches zero sinks and zero ownership-allowance rows.

## Context
- **Flight DD4** (`keyValueTable`), **DD6** (the canonical connector form; `connector-pairing-code` on `copyField`'s input with two test changes; `copyField` `buttonLabel`), **DD7** items 5, 7 and 8, **DD8-1** (both sequences), **DD8-8**, **DD10**, **DD11**.
- **Leg 07a** built the frame, the value model (with a `channel_map_rows` adapter over the old DOM, which this leg replaces), Save and Cancel patching and the doctor. Read its flight-log entry first for the actual shape it landed.
- **Today's code** (`connector-editor.js`; line numbers from `332496d`, which leg 07a moved, so re-locate by text):
  - **Pairing** (edit only, about `:386-450`):
    - a section-description paragraph;
    - "Generate pairing code" `connector-pairing-btn`;
    - `connector-pairing-result` (`role=status`, `aria-live=polite`);
    - on success, `code.connector-pairing-code` (testid `connector-pairing-code`) plus a Copy button (`connector-pairing-copy-btn`, text "Copy", `aria-label` "Copy pairing code", a hand-rolled clipboard call with `App.showFlash` ×3), then a `span.connector-pairing-expiry` "Expires {iso}";
    - on failure, the error text.
  - **Channel map** (about `:452-498`): the rows (`connector-channel-map-row`, `data-row-idx`, two `field-input` inputs `.channel-map-channel`/`.channel-map-agent`, "✕" `connector-channel-map-remove-btn` "Remove row"), Add `connector-channel-map-add-btn` "+ Add row", and the stale-`rowEntries` bug (DD8-1).
  - **Danger zone** (about `:524-534`, `:568-581`): hand-built `.editor-section.danger-zone`, the "Danger Zone" title, `button.btn-muted-destructive.delete-btn` (testid `delete-connector-btn`) with the span "Delete Connector" carrying `data-confirm-title`, and `App.confirmDelete(deleteBtn, …)`. On failure: `revertFn()` and the header error.
- **The library danger zone** (`js/ui/editor.js`, `App.ui.dangerZone`; Flight 1 DD8 and Flight 2's `actions` form): trash icons and the armed style. The precedent is the agent editor (`general-tab.js` about `:215-230`) and the provider editor (`provider-editor.js` about `:250`).
- **Tests:**
  - `test_studio_connector_editor.py`:
    - pairing `:205-220`, `:222-245` (`code_el.text_content()`, `code_text in result.text_content()`, the copy button's aria-label non-empty);
    - lapse `:286-306`: `delete-connector-btn` takes the `confirm-delete` class, then `confirm-lapsed`, and keeps the text "Delete Connector". Check that `dangerZone`'s button behaves the same, since it arms through `App.ui.confirm`;
  - `test_flow_studio_library_list.py` about `:1370-1410`: the channel map through `.channel-map-channel`/`.channel-map-agent` (class selectors; these move to the new input testids, per leg 04's "Consumer selectors"), save, then values present after the in-place save, then pairing;
  - `tests/behavior/stub-connector-round-trip.md` step 2 (`connector-pairing-result`, already out of date per Architect cycle 1; amend it if this leg changes what it reads).

## Inputs
- Legs 03b (`copyField` `buttonLabel`), 04 (`keyValueTable`) and 07a landed.
- `js/ui/{copy,editor,feedback,key-value-table}.js`.

## Outputs
- **Pairing:**
  - a library `section` with the description;
  - a library button `connector-pairing-btn`;
  - `connector-pairing-result` as a `status` line (polite) for "Generating…" and for failure text;
  - on success, `App.ui.copyField({value: code, label: 'Pairing code', testid: 'connector-pairing-code', copyTestid: 'connector-pairing-copy-btn', buttonLabel: 'Copy pairing code'})` plus the expiry line ("Expires {iso}", unchanged text), inside the pairing result region.

  No `App.showFlash` and no hand-rolled clipboard remain.
- **The channel map:** `App.ui.keyValueTable({columns: [{key: 'channel', label: 'Channel id', placeholder: 'channel id', inputTestid: 'connector-channel-map-channel'}, {key: 'agent', label: 'Agent', placeholder: 'agent name', inputTestid: 'connector-channel-map-agent'}], rows, rowTestid: 'connector-channel-map-row', removeTestid: 'connector-channel-map-remove-btn', addTestid: 'connector-channel-map-add-btn', label: 'Channel to agent map', onChange})`.
  - Rows come from `config.channel_map`.
  - 07a's `channel_map_rows` adapter becomes `kv.values()`: raw rows for dirty, normalised (channel non-empty, trimmed) for the payload, exactly as today.
  - After an edit Save, `kv.setValues(rowsFrom(updated.config.channel_map))` resets the model, so the stale-entries class is gone. On Cancel, the same from the stored record.
- **Danger zone:** `App.ui.dangerZone` with one action, `{label: 'Delete Connector', testid: 'delete-connector-btn', confirmLabel: …, onConfirm}`.
  - On a failed DELETE it reverts the arm and puts the error in the header (`shell.setError`, DD6); on success, `invalidate` and `onDeleteSuccess` as today.
  - The confirm label is "Confirm delete?", the library default.
- **Tests:**
  - `test_flow_studio_library_list.py` moves the two class locators to `[data-testid="connector-channel-map-channel"]`/`-agent`;
  - `test_studio_connector_editor.py` `:234-243` changes `text_content()` to `input_value()`, and `code_text in result.text_content()` to an assertion on the input's value. The copy button's accessible name is "Copy pairing code";
  - **new DD8-1 tests, test-first** (record the failures before the fix):
    - (1) type into rows 1 and 2, add a row, and both keep their typed values;
    - (2) type into a row, remove another row, and the typed value survives;
    - (3) the post-Save sequence: Save with rows A and B, edit row A to A′ without saving, add a row, Save, and the stored map has A′ and B (no stale value returns);
  - **DD8-8:** every channel-map input has an accessible name, and the remove buttons' names differ per row;
  - **dangerZone:** the existing lapse test passes unchanged, or moves to the danger zone's actual classes with the same meaning (armed, then lapsed, then the text restored).
- **Allowances:**
  - `HTML_SINK_ALLOWANCE` has no `connector-editor.js` row (0);
  - `OWNERSHIP_ALLOWANCE` has no `connector-editor.js` rows;
  - `App.showFlash`/`App.confirmDelete` have no calls in `connector-*.js`.
- **CSS:** remove the rules this leg's old markup used, after a grep: `.connector-pairing-code-row`, `.connector-pairing-code`, `.connector-channel-map-*` if any, `.connector-pairing-copy-btn` if any. Run `scripts/unused_selectors.py css/studio.css` and act on the connector entries.
- **Registry:** the `docs/ui-testid-registry.md` rows for these buttons move from the manual-exceptions table to the literal table. Add the new input testids `connector-channel-map-channel`/`-agent`. Any retired id gets a retired-table row plus a `RETIRED_SELECTORS` entry.
- **The catalogue:** the `keyValueTable` row names its first consumer.

## Design review amendments (binding; they supersede earlier text where they differ)
Design review cycle 1 (Sonnet Developer): approve with changes.
1. **The pairing result's structure.**
   - `connector-pairing-result` is a plain container `div`, with no `role` and no `aria-live`.
   - It holds one `App.ui.status` (polite) for "Generating…" (pending) and for failure text (danger).
   - On success the status is cleared and hidden, and the container holds the `copyField`, then the expiry line. That line keeps the `connector-pairing-expiry` class and its `studio.css` rule as area layout (the Flight Director's call: no visible change).
   - Remove only `.connector-pairing-code-row` and `.connector-pairing-code`.
2. **Pairing test changes**, all named:
   - `code_el.text_content()` becomes `expect(code_el).to_have_value(…)`;
   - `code_text in result.text_content()` becomes the input's value check;
   - the copy-button assertion at `:243` (`get_attribute("aria-label")` non-empty) becomes `get_by_role("button", name="Copy pairing code")`;
   - add: there is no `code.connector-pairing-code`; the input is `readOnly` with the name "Pairing code".
3. **The `test_store_static.py` delete pin** (about `:336-340`): keep the literal `encodeURIComponent(cfg.id), { method: 'DELETE' })` and the order DELETE, then `App.store.invalidate('connectors')`, then `callbacks.onDeleteSuccess()`, or retarget the pin deliberately. It is added to Files Affected.
4. **Value-model wiring.**
   - The kv `onChange(values, {type})` calls 07a's `recomputeDirty()`, replacing the old DOM's input, add and remove wiring.
   - **Edit-Save order:** `stored = updated`, then `kv.setValues(rowsFrom(updated.config.channel_map))`, then (07a) `secret` re-mask, then `snapshot = readValues()`, then `setDirty(false)`.
   - **Cancel:** `kv.setValues(rowsFrom(stored.config.channel_map))` before the snapshot reset.
   - Test that after an edit Save the focus restore still lands on the title.
   - **Duplicate channel ids:** the last row wins in the payload, as today, and the re-seed shows one row. Document it beside the empty-channel case.
   - `keyValueTable.setError` is deliberately not used: no behaviour change.
5. **The DD8-1 tests are taken against the post-07a tip,** and recorded as failing there before the fix.
   - **Test (3), exactly:** open an existing connector (edit mode); add rows A and B; Save; edit A to A′ without saving; add a row; Save. Then `GET /api/connectors/{id}` has `config.channel_map` with A′ and B and without A.
   - **Add test (4):** edit a row, Cancel, and the rows are restored.
   - **The DD8-8 test** uses role names: `get_by_role("textbox", name="Channel id, row 1")`, and every `get_by_role("button", name=/^Remove row/)` name is distinct.
6. **The danger zone.**
   - `App.ui.confirm` arms the button itself, and the lapse test (`:286-306`) must pass unchanged.
   - `onConfirm(revert)` receives only `revert` (a signature change from `App.confirmDelete`'s `(el, revertFn)`).
   - **The commit fires one DELETE:** a local `deleting` flag (or disabling the action) until the request settles. On failure: `revert()`, `setDisabled(false)` and the `dangerZone` notice (`role=alert`, testid `connector-delete-error`) with `fetchJson`'s error text (flight DD6 as amended at the leg 05b review; this supersedes 07a's interim `shell.setError`).
   - The DELETE `.then` checks `slot.isCurrent(token)` before any DOM write. `invalidate` and `onDeleteSuccess` always run.
   - Add a test: double-confirm sends one DELETE.
7. **`tests/behavior/stub-connector-round-trip.md` step 2 is amended (mandatory):** the code is `connector-pairing-code`'s value, and the expiry is in `connector-pairing-result`.
8. **Registry.** Move these to the literal table:
   - `connector-channel-map-add-btn`, `-remove-btn`, `connector-pairing-btn` and `connector-pairing-copy-btn` (about `:419-423`);
   - `connector-doctor-btn`, `cancel-connector-btn` and `save-connector-btn`, if 07a has not moved them already.

   Add rows for `connector-channel-map-channel`/`-agent`. Reword the `connector-pairing-code` row to "read-only input".
9. **Static clears:** 07a owns `:233` and `:346` (they become `replaceChildren()`); this leg's `:465` disappears with the kv table. The final grep AC covers both files.
10. **CSS:** there are no `.connector-channel-map-*`, `.channel-map-*` or `.connector-pairing-copy-btn` rules today. The DD7-8 ledger row names the table header, the hover-red trash icon and the input widths.

## Acceptance Criteria
- [ ] Amendments 1-10 are implemented, with their named tests.
- [ ] Pairing, the channel map and the danger zone are library controls (Diagnostics landed in 07a); `connector-editor.js` builds no hand-made section, button, clipboard or confirm markup.
- [ ] The DD8-1 tests (1)-(3) are recorded failing before the fix and pass after. The DD8-8 names hold.
- [ ] `connector-pairing-code` is the read-only input holding the code, the copy button's name is "Copy pairing code", and a copy shows "Copied" (the `copyButton` contract).
- [ ] The delete flow arms, lapses and commits as before, and a failed DELETE shows the header error.
- [ ] `HTML_SINK_ALLOWANCE` and `OWNERSHIP_ALLOWANCE` have no `connector-editor.js` or `connector-glue.js` rows, and `git grep -n "App.showFlash\|App.confirmDelete\|innerHTML" -- the_one/interfaces/web/static/js/areas/studio/connector-*.js` is empty.
- [ ] The `library`, `mcp`, `routing` and `shared` lanes pass under `THE_ONE_TEST_NETNS=1`. So do `make test-unit` and the static guards. `tests/test_ui_guards.py`'s registry checks pass.
- [ ] **Ledger rows:**
  - the pairing code in a read-only field with Copy (DD7-7);
  - the channel map's key-value look (DD7-8);
  - the danger-zone trash icon and armed style (DD7-5);
  - any other difference, with a reason.
- [ ] The `library` lane's time is reported against its budget.

## Verification Steps
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser tests/browser/test_studio_connector_editor.py tests/browser/test_flow_studio_library_list.py -x --timeout 60`
- The four lanes, `make test-unit`, and the grep above.

## Implementation Guidance
1. **Log a start line.** Write the DD8-1 tests against today's code and record their failures.
2. **Channel map onto `keyValueTable`;** wire it into 07a's value model and payload; reset on Save and Cancel.
3. **Pairing onto `copyField`.**
4. **Danger zone onto `dangerZone`.** Check the lapse test against its classes.
5. **Tests, CSS removal, registry, allowances, ledger, flight log.**

## Edge Cases
- **A channel row with an empty channel** is dirty (raw rows) but dropped from the payload, as today. After Save, `setValues` from the response therefore removes that empty row. Document it as the expected result.
- **Pairing generated twice:** the second result replaces the first `copyField` (the region is cleared with `replaceChildren()`).
- **Pairing on a non-OK response:** keep today's message "pairing-code request failed: HTTP {status}" in the status line (danger).

## Files Affected
- `js/areas/studio/connector-editor.js`, `css/studio.css`
- `tests/browser/test_studio_connector_editor.py`, `tests/browser/test_flow_studio_library_list.py`
- `tests/test_store_static.py`, `tests/test_ui_guards.py`, `tests/_ui_ownership_allowance.py`, `docs/ui-testid-registry.md`, `docs/ui-control-inventory.md`
- `tests/behavior/stub-connector-round-trip.md` (if a step reads what changed)
- The flight log

## Citation Audit
Checked at `332496d` on 2026-10-22 (FD read):
- `connector-editor.js:386-498,524-534,568-581`;
- `test_studio_connector_editor.py:205-245,286-306`;
- `test_flow_studio_library_list.py:1370-1410`.

These are re-located by text after leg 07a.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
