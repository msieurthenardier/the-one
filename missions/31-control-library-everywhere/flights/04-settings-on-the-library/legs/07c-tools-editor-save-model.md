# Leg: tools-editor-save-model

**Status**: completed
**Flight**: [Settings on the library](../flight.md)

## Objective
Give the Built-in tools editor a correct Save and Cancel model: patch in place, a value model from the field handles, busy while saving, every async write guarded by identity and `latest()`, secrets re-masked, and a remount side-effect inventory. This fixes DD8-5 to DD8-8.

## Context
- **Flight decisions:** DD5 (all of it), DD8 5-8, DD3 (`latest()`), DD11.
- **Tier HIGH:** this is the state model of an editor for safety settings, and the bugs it fixes include one that drops a leave guard.
- **Today** (from the survey, re-checked after 07a):
  - Cancel remounts the whole editor from `originalToolDetail`;
  - Save patches in place and re-snapshots from the current DOM (`:516`), so an edit typed during the PUT is marked saved but never sent (DD8-6);
  - Cancel is not disabled during the PUT, so a Cancel then a successful PUT leaves a clean form showing values the server no longer holds (DD8-5);
  - every tool editor mounts into the same `.settings-item`, and the closure queries `container` live, so a Save for tool A can resolve after the operator has opened tool B and write into B's editor (DD8-7): the flash, the disabled Cancel, the cleared caption, and the unguarded `onDirtyChange(false)` (`admin.js:387`, now `tools-page.js`) that drops B's leave guard;
  - the secret field keeps the typed plaintext after Save (DD8-8).
- **The model after this leg:**
  - **One mount per tool identity.** The editor handle is created per open, through a `mountSlot` in `tools-page.js`. Every async continuation checks `slot.isCurrent(token)` **and** a `latest()` token for that request. A stale response writes nothing: no flash, no caption, no `onDirtyChange`, no errors.
  - **The value model:** `snapshot()` reads `{enabled, config}` from the handles (`value()`), never from the DOM. Dirty is `stringify(snapshot()) !== stringify(baseline)`.
  - **Save:**
    - `editorShell.setBusy(true)` (Save, Cancel and Test disabled; fields stay live);
    - the request body is captured as `submitted`;
    - on success, `baseline = submitted` with the response's masked secrets applied, then dirty is recomputed, so a change typed during the request stays dirty (DD8-6);
    - secrets are re-masked only if the field still holds the submitted value (DD5);
    - `setBusy(false)`.
  - **Cancel patches:** each handle gets `setValue(baseline…)`, the Enabled switch is reset, field errors and the shell error are cleared, then the `show_if` visibility is re-applied. No remount. Cancel is disabled during a Save, so DD8-5 cannot occur.
  - **Focus after** Save, Cancel and Test through `App.focusAfter` (title on success, the control on failure), unchanged.
  - **The flash** after a successful Save is `App.ui.flash` ("Tool saved"), inside the item section, gated by the identity check. `rescueFlashes` and the `App.showFlash` calls in `tools-page.js` are replaced (`App.showFlash` 2 uses and `app-flash` 1, gone from the allowance).
- **The remount side-effect inventory (DD5)**, recorded in this leg's flight-log entry, each one re-run on Save or Cancel (with a test), dropped (a ledger row) or accepted in writing:
  - the `show_if` visibility;
  - field errors and the shell error cleared;
  - the Test section's result line and output (cleared on Cancel? kept on Save? decide and test);
  - the secret fields' masked state;
  - the tile's enabled state in the list (Save updates it through `onSaveSuccess`, identity-gated);
  - the leave-guard mirror (`dirty` in `admin.js` through `ctx.setDirty`, identity-gated);
  - focus and scroll;
  - the unsaved caption.

## Inputs
- Leg 07a landed (the new frame and the module handles).

## Outputs
- `tools-editor.js`: the Save and Cancel model above; `tools-page.js`: the mount slot, identity-gated `onSaveSuccess`/`onDirtyChange`/`onMount`, and the flash moved to `App.ui.flash`.
- Tests, each failing on the code before this leg:
  - DD8-5 (hold the PUT, Cancel is disabled; after a success the form shows the saved values);
  - DD8-6 (type during a held PUT; after success the editor is still dirty with the new value);
  - DD8-7 (Save A, hold it, open B with an unsaved edit after the leave guard, release A: B's editor, caption, leave guard and errors are untouched, and A's tile reflects the save);
  - DD8-8 (after Save the secret field shows the mask, unless it was retyped during the request).
- The side-effect inventory in the flight log, with a test for each "re-run" item.
- `agents.md` "Settings item pages": the tools editor's save model.

## Acceptance Criteria
1. The four DD8 tests fail before this leg and pass after it, in Chromium, and also in WebKit if the `settings` lane runs WebKit for editor tests (follow the lane's existing engine choice).
2. **No remount on Save or Cancel:** a `MutationObserver` on `.settings-item` records no removal of the editor root during Save and Cancel, and a focused field keeps focus through a Cancel triggered by keyboard (focus then goes to the title per the focus-after rule).
3. **Busy:** during a held PUT, Save, Cancel and Test are disabled, the fields are enabled, and a second Save click sends nothing.
4. **The side-effect inventory** is complete in the flight log, and each "re-run" item has a passing test.
5. **The leave guard:** with B dirty and A's stale response arriving, `App.nav`'s dirty source for Settings still reports dirty (the router guard asks on leave).
6. `tools-page.js` has no `App.showFlash` and no `app-flash`, and its ownership rows are gone.
7. The unit tier, the static guards, and the `settings` and `routing` lanes pass.

## Verification Steps
- The new tests alone, twice, under netns (the timing-sensitive ones wait on released requests, never fixed timeouts: DD10).
- The `settings` and `routing` lanes under `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1`.
- `.venv/bin/python -m pytest tests/test_ui_guards.py tests/test_ui_ownership.py tests/test_area_module_size.py -q -x --timeout 120`; `make test-unit` once.

## Edge Cases
- **A Save failure** after the operator moved to another tool: nothing is shown anywhere. The failed tool's draft is gone with its editor (as today when leaving after the guard's Continue).
- **The list toggle for the open tool during a held Save:** the toggle's PUT and the Save's PUT race. The editor's Enabled switch follows the server state of whichever finished last. Test it: toggle off in the list while a Save holds `enabled: true`, release both in either order, and the editor and the tile agree with the final server value.
- **Cancel with no changes:** disabled (the shell's rule), as today.

## Files Affected
- `static/js/areas/admin/tools-editor.js`, `tools-page.js`.
- `tests/browser/test_flow_admin_tools_editor.py` (or a new `test_flow_admin_tools_editor_save.py` in the `settings` glob), `test_flow_settings_focus_after.py`, `test_router_items.py` (if a seam changes).
- `tests/_ui_ownership_allowance.py`, `the_one/agents.md`, the flight log.

## Citation Audit
- `tools-editor.js:516` (the success re-snapshot from the DOM), `:425-447` (Cancel remounts), `admin.js:387` (`onDirtyChange` unguarded): from the survey. Re-locate them after 02a and 07a.

## Design Review Amendments (cycle 1, 2026-10-23)
These override the body where they conflict.
- **This is now leg 07c**, after the 07a split: 07a builds the handle snapshot and the interim Save/Cancel, and 07b the errors.
- **Split `onSaveSuccess`:**
  - the list cache (`toolConfigs[i]`) and the list re-render run whenever a Save response arrives while the tools page is mounted, so A's tile reflects A's save;
  - the `editingTool`, `dirty` and editor-handle writes are identity-gated, because a stale A response must never put B's schema or state under A's data.
- **The baseline comes from the response, not the request:** after a successful Save, the baseline is `response.config` plus `response.enabled`.
  - It is set (`setValue`) into each handle whose value still equals what was submitted.
  - A field changed during the request keeps its value and stays dirty.
  - A secret field takes the response's masked value only if it still equals the submitted plaintext (per-field re-masking).
  - A field absent from the response is treated as its Config default.
- **The Enabled race:** every response sets `baseline.enabled` from that response's `enabled`, the same rule the list toggle's `setEnabled` follows. The Enabled control follows the new baseline only if the operator hasn't touched it (its value equals the previous baseline).
  - The test holds both routes (the list toggle's PUT and the Save's PUT) and releases them in each order. The oracle is a final `GET /api/tools/configs/{name}`: the server applies writes in the order the routes are continued, so the editor and the tile must agree with that GET.
  - Write the order-of-arrival caveat into `agents.md`.
- **Busy covers the Test button too.** The Test button belongs to the section, not the shell's `actions.test`, so `setBusy` doesn't disable it. One editor-level `setBusy(on)` disables the shell's buttons and the Test button, and re-applies on release. **Save is blocked while a Test is in flight** (the Test reads the saved row; the decision is recorded).
- **`onDirtyChange`, `onCancel` and `reportDirty`** are all gated by `slot.isCurrent(token)`. Cancel calls `onDirtyChange(false)` only after the handles are reset.
- **The probe for AC5:** `page.evaluate('App.nav.isDirty()')` (or `App.nav.dirtySources()`, read-only, `nav.js` about `:146-152`).
- **The ordering:** `setDirty(recomputed)` before `setBusy(false)`.
- **The Test result on Save and Cancel** (inventory item): kept on Save; cleared on Cancel only if Cancel changed a value. Tested.
- **DD8-7's test:** open B through its link with A dirty and held. Click Continue in the `App.confirmDialog`, wait for B to mount, type in B, release A. Then assert B's caption, `App.nav.isDirty()` still true, no error on B, and A's tile updated. In Playwright sync mode, keep the `Route` and resolve it from the test body, not from inside the handler. Don't hold the list reload GETs.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
