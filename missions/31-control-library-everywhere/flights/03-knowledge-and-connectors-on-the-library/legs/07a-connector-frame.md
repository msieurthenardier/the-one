# Leg: connector-frame

**Status**: completed
**Flight**: [Knowledge and connectors on the library](../flight.md)

## Objective
Move the connector editor's frame and fields onto the library:
- the `editorShell` through `mountSlot`;
- the Identity, Setup steps, Binding and Admission sections;
- the token as `secretInput`, keeping the masked round-trip;
- the Enabled `toggle`;
- the header status line;
- the value-model dirty state, with Save busy during its request;
- in-place Cancel and Save;
- doctor results on non-OK responses;
- a handle with `destroy`.

This leg owns `connector-glue.js`'s mount path and its sink. Leg 07b does the Pairing, Channel map and Danger zone sections.

**Tier high:** a security surface (the token).

## Context
- **Flight DD5** (mount once; patch on Save and Cancel; the value-model dirty state; `setBusy`; the glue's mount path; the host clear becomes `replaceChildren()` on an identity change after `destroy`; the token's masked round-trip). **DD6** (the canonical connector form, the testid changes, sentence-case untouched). **DD7** items 1, 4, 6 and 10. **DD8-2** and **DD8-3**. **DD10** (lanes: `library`, `mcp`, `routing`, `shared`). **DD11.**
- **Provider editor precedent** (Flight 1, `js/areas/studio/provider-editor.js`): `editorShell` through `App.ui.util.mountSlot()`, `field`/`textInput`/`select`, `secretInput` with the key re-masked after Save, `App.focusAfter`, `App.api.fetchJson` (which flattens a 422 detail list). Read it first; this leg copies its shape.
- **The connector editor today** (`connector-editor.js`, 724 lines; `renderConnectorEditor(container, connector, connectorTypes, agents, callbacks)` at `:220`):
  - **header** (`:236-300`): the hand-built breadcrumb "Library / Connectors" (`editor-breadcrumb-link`); `h1.editor-title` ("New Connector" or the name, `tabindex=-1`); in edit mode a status row with `connector-status-led` (an `indicator-led`, aria-label) and `connector-status-label` (visible text "Checking connection…"); the caption `editor-unsaved`; Cancel `cancel-connector-btn` (enabled at once on create); Save/Create `save-connector-btn`; `span.editor-error`;
  - **Identity** (`:302-314`): name (`data-field="name"`), type select (`type`), token (`password`, `data-field="token"`, value `cfg.secrets.token`, which the server masks), and Enabled through `_toggleRow` (`:100-121`, the legacy `.tool-enable-switch`, `data-field="enabled"`, `id=conn-enabled`, checked when `config.enabled !== false`);
  - **Setup steps** (`:321-360`): `connector-setup-steps`, `connector-setup-steps-list-{type}` (live on the type change), `connector-setup-steps-doc-ref` (not an `<a>`, pinned by a test);
  - **Binding** (`:361-369`): the `default_agent` select;
  - **Admission** (`:371-384`): three one-per-line textareas, `allowlist_peers`, `allowlist_channels` and `always_listen`;
  - **dirty** (`:586-600`): sticky `markDirty` on every `[data-field]` input or change;
  - **Save** (`:612-720`):
    - `collectPayload` reads the DOM `[data-field]` values and the channel-map rows (`:612-652`);
    - the request is plain `fetch` with no busy state;
    - on OK: `App.store.invalidate('connectors')`, `App.showFlash(…'Connector saved'/'created')`, then `onSaveSuccess`;
    - edit mode then clears the caption and disables the buttons, sets the title, and restores focus;
    - create re-mounts through the glue;
  - **the doctor auto-probe** (`:556-565`) and the manual doctor (`:535-550`) both call `r.json()` with no `r.ok` check (DD8-3). `applyDoctorStatusToLed` is at `:503-512`; `_connectorLedState`/`_connectorLedLabel` at `:150-200`.
- **The glue** (`connector-glue.js`):
  - `renderConnectorsSection` clears `sectionContentEl.innerHTML = ''` (`:47`; the sink);
  - edit `onCancel` re-renders the section (`:75-80`);
  - `onSaveSuccess` sets state, `reloadLibrary`, `router.sync`, and re-renders on create (`:88-103`).

  The host is shared with the provider and MCP editors. `setActiveSection` relies on each glue's clear (`studio.js` about `:521-537`).
- **Server contract** (`the_one/interfaces/web/api.py`):
  - GET and PUT responses mask `secrets` (`_connector_response` about `:4033`, `_mask_secrets` about `:2767`);
  - a PUT with a masked or sentinel token keeps the stored one (`_looks_masked` about `:2709`, used about `:4160-4175`);
  - a POST with a masked value is refused with 422 (about `:4115-4130`).
- **Tests on this surface** (12 tests in `tests/browser/test_studio_connector_editor.py`; plus `test_flow_studio_library_list.py`, `test_router_items.py`, `test_router_guard.py` about `:311,323,435`, `test_nav_guard.py:290`, `test_store_library.py`, `test_flow_studio_navigation.py`, `test_agents_library_isolation.py`). They select by testid and `[data-field=…]`, except:
  - `.editor-title` (`:315`);
  - the LED's class and aria-label (`:148-153`);
  - the pairing code's `text_content()` (`:234-243`, which is leg 07b's).

## Inputs
- **Requires** legs 01 (lanes), 03b (`editorShell` `errorRole`; `status` `ledTestid`) and 04. The channel map stays the old DOM in this leg; see the Outputs.
- **Behavior spec** `tests/behavior/stub-connector-round-trip.md` names `library-add-btn`, `connector-pairing-btn`, `connector-pairing-result`, `save-connector-btn` and `delete-connector-btn`. All are kept.

## Outputs
- **The frame:** `connector-editor.js` builds the frame with `App.ui.editorShell`:
  - breadcrumb `{lead: 'Library / ', …}` in the shell's breadcrumb shape (match the provider editor), with the link testid `editor-breadcrumb-link`;
  - title "New Connector" or the name (unchanged text), with `tabindex=-1`, focusable for `focusAfter`;
  - `actions.cancel` (`cancel-connector-btn`, `enabledWhenClean: isCreate`) and `actions.save` (`save-connector-btn`, "Create"/"Save");
  - `errorRole: 'alert'`;
  - the caption testid `editor-unsaved`.
- **The status line (edit mode only)** is an `App.ui.status({led: true, ledTestid: 'connector-status-led', testid: 'connector-status-label', state: 'idle', text: 'Checking connection…'})` placed through `afterTitle`. Its root carries `data-state`. Its visible text and states come from `_connectorLedLabel`/`_connectorLedState`, unchanged.
- **The fields:**
  - `App.ui.field` with `textInput` (name), `select` (type, default agent) and `textarea` (the admission lists), each keeping `dataset: {field: …}` and the label text and ids (`conn-name`, `conn-type`, …);
  - the token is `App.ui.secretInput` (the reveal eye) with `data-field="token"` on its input;
  - Enabled is `App.ui.toggle` (the library switch, its label beside it, operator 2026-10-22) with `data-field="enabled"` on its input, checked when `config.enabled !== false`;
  - Setup steps keeps its testids and live update, built with `section` and DOM nodes.
- **The value model:** `readValues()` returns `{name, type, token, enabled, default_agent, allowlist_peers, allowlist_channels, always_listen, channel_map_rows}` from the control handles.
  - `channel_map_rows` reads the old channel-map DOM through one small adapter function in this leg. Leg 07b replaces that function with `keyValueTable.values()`.
  - The snapshot is that object at mount and after each successful Save.
  - Dirty is `JSON.stringify(readValues()) !== JSON.stringify(snapshot)`, recomputed on every input or change event from the controls, fed to `shell.setDirty` and `callbacks.onDirtyChange`. Typing a change and reverting it is clean (a DD5 behaviour change, recorded in the ledger).
  - The payload is built from `readValues()` with exactly today's normalisation:
    - lines become arrays, trimmed, empties dropped;
    - the sparse `config`;
    - `enabled: false` only when it is off;
    - a channel row is kept only when its channel is non-empty;
    - `secrets: {token}`.
- **Save:**
  - `shell.setBusy(true)` before the request and `setBusy(false)` when it settles (DD8-2);
  - `App.api.fetchJson` for the request, keeping its error text in `shell.setError` and the "Name is required." check;
  - on OK: `App.store.invalidate('connectors')`, then `App.ui.flash` replaces `App.showFlash` ("Connector saved"/"Connector created"), then `onSaveSuccess`;
  - **edit mode patches in place:** the title through `setTitle`; the token re-masked from the response's `secrets.token`, with the reveal turned off; the snapshot reset and `setDirty(false)`; focus restored to the title;
  - **create** stays an identity change: the glue remounts in edit mode.
- **Cancel (edit mode)** patches every control back from the stored record (the token to its stored masked value, with the reveal turned off) and resets the snapshot, with no remount. Cancel on create keeps closing the editor (the glue's discard).
- **The doctor (DD8-3):**
  - the manual "Run doctor": a non-OK response puts `connector-doctor-result` (a `status` line, testid kept) in danger with the response's error text;
  - the automatic probe: a non-OK response sets the header line to danger, "Connection check failed" (a ledger row);
  - a network failure keeps today's behaviour, staying at "Checking…" for the probe and "Doctor request failed: …" for the manual run.
- **The handle:** `renderConnectorEditor` mounts through a `mountSlot` and returns `{destroy}`. `destroy` releases the slot, stops pending async writes through `isCurrent`, and removes listeners.
- **The glue** (`connector-glue.js`):
  - it keeps the handle;
  - `renderConnectorsSection` calls `handle.destroy()`, then `sectionContentEl.replaceChildren()`, only on an identity change (a new connector id, or create↔edit);
  - edit `onCancel` no longer re-renders (the editor patches);
  - `onSaveSuccess` keeps today's rule: it re-renders only on create (`if (isCreate)`);
  - the glue's reset and section-leave paths call `destroy`.

  The `HTML_SINK_ALLOWANCE` row for `connector-glue.js` is removed (1 → 0), and `connector-editor.js`'s sinks are removed where this leg's code held them. The three clears at `:233`, `:346` and `:465` become `replaceChildren()`; `:465` is the channel map's and goes in 07b, so lower the count to match.
- **Pins:** the `test_store_static.py` connector rows (about `:331-337`) retarget to the moved calls. The ownership-allowance rows for every class this leg stops emitting are removed (the ratchet test prints the corrected rows).
- **Tests:**
  - `test_studio_connector_editor.py` `:148-153` moves to the status line's text ("Not connected") and the root's `data-state="danger"`, keeping the LED testid visible check; `.editor-title` (`:315`) moves to a role or testid locator;
  - **new browser tests, test-first where they cover a defect:**
    - (a) a double-click on Create makes one connector (count via `GET /api/connectors`); fails before the fix;
    - (b) the manual doctor on a 500 (route-stubbed) shows a danger line with the error text, not "undefined: undefined"; fails before;
    - (c) the auto-probe on a non-OK response shows "Connection check failed";
    - (d) **an untouched token survives an edit Save:**
      - seed a token of at least 12 characters, so the GET mask is `***...{last4}`;
      - change only the name, and Save;
      - `GET /api/connectors/{id}` shows the same `secrets.token` tail before and after, and the field still shows that masked value;
    - (e) **a typed token replaces it.** After Save:
      - the GET tail is the new one;
      - `input_value()` is the masked string, and the input `type` is `password`;
      - clicking the reveal eye shows the masked string, not the plaintext;
      - no element's attributes (`value`, `title`, `aria-label`, `data-*`; checked with `page.evaluate` over `document.querySelectorAll('*')`) hold the plaintext.
      Repeat the attribute check after Cancel, and after a type-then-revert. This extends `:56-75`, whose `page.content()` check cannot see `.value`;
    - (f) type in Name and revert, and the caption clears and Save disables;
    - (g) edit Save keeps the editor mounted: the same `connector-editor` root node identity before and after, and the title updates;
    - (h) edit Cancel restores the stored values without a remount (the same node identity).

## Design review amendments (binding; they supersede earlier text where they differ)
Design review cycle 1 (Sonnet Developer): approve with changes.
1. **Save ordering (security).**
   - Edit success runs `cfg = config = stored = updated`, then `secret.setValue(updated.secrets.token || '')` with the reveal off, then `snapshot = readValues()` (read back from the controls), then `setDirty(false)`.
   - No variable holds the typed token after the request settles: the payload object is local to the click handler.
   - On create success the shell **stays busy**: there is no `setBusy(false)`, because the remount replaces it.
   - `setBusy(false)` runs on failure and on edit success only.
   - Test (a) clicks twice fast, and once more after the 201 but before the remount.
   - If the glue's remount fetch (`Promise.all([types, fetchAgents])`) fails, the glue's new `.catch` calls the current handle's `setBusy(false)` and `setError("Couldn't reopen the connector: …")`.
2. **Cancel restores from `stored`** (the last saved record): every control, the token back to its stored mask with the reveal off, and the old channel-map DOM (`rowEntries` from `stored.config.channel_map`, then `renderRows()`). The snapshot is then reset. Add a test: edit a channel-map row, Cancel, and the rows are restored; type a token, Cancel, and the field is back to the stored mask with the reveal off.
3. **Dirty wiring.**
   - Each control's own `onInput`/`onChange` calls `recomputeDirty()`: the inputs on `input`, the selects and the toggle on `change`.
   - The `container.querySelectorAll('[data-field]')` wiring and `markDirty` go.
   - The old channel map's inputs, add button and remove buttons call `recomputeDirty()` directly (they fire no `input` event on add or remove).
4. **`focusAfter`.** Edit Cancel uses `begin(cancelBtn)` then `restore(tok, titleEl)` synchronously, with no `defer`, since there is no remount to flush it. Only create keeps `defer`/`flush`.
5. **After `destroy`, nothing writes:** the Save `.then`, the doctor responses and the probe check `slot.isCurrent(token)` before any DOM, flash or focus write. `App.store.invalidate('connectors')` still runs after a successful create or save, because the server state changed. `discardOpen_` and the glue's reset path call `destroy`. The pin is `test_router_guard.py` about `:435` (a save resolving after a breadcrumb go keeps the root).
6. **The glue's identity key.**
   - The glue keeps `handle` and `handleKey` (`'add'` or `'edit:' + id`).
   - Inside the `Promise.all(...).then` (not at the call), it remounts only when the computed key differs from `handleKey` or there is no handle.
   - A same-key render (from `tryConsumePending`, a store notification, or `setActiveSection` re-entering while mounted) keeps the editor and its unsaved edits. It does not refresh the agents or types lists: accepted and documented in `agents.md`.
   - `destroy` and the glue's reset null the handle, so re-entering the section remounts.
7. **Diagnostics belongs to this leg:** a `section`, `App.ui.button` (`connector-doctor-btn`) and `status` (`connector-doctor-result`). Leg 07b keeps Pairing, Channel map and the Danger zone only.
   - **Section order:** the shell's `el` is appended first. Then Identity, Setup steps, Binding, Admission, Pairing (edit), Channel map, Diagnostics (edit) and Danger zone (edit), in today's order, built sequentially into `container`.
   - The old Danger zone's failure path writes `shell.setError` in this leg.
8. **`test_store_static.py` connector pins** (about `:330-338`) stay text-anchored. Keep `var method = isCreate ? 'POST' : 'PUT';`, then `App.store.invalidate('connectors')`, then `callbacks.onSaveSuccess(updated, isCreate)`, in that order. Retarget the anchors only if the literal text must change; the delete pin is unchanged here.
9. **Error text.** `fetchJson`'s plain-text fallback ("Server error 500 …") replaces "Create failed"/"Save failed" for non-JSON errors: a ledger row. A 422 for a masked-looking token on create shows through `shell.setError`, with a test.
10. **Known non-changes, recorded in the flight log:**
    - typing a masked-looking string on edit is kept as "preserve";
    - a stale `default_agent` falls back to the select's first option.
11. **Node-identity tests (g) and (h)** mark the shell header (`.editor-header`, or the shell `el`) with `el.__m = 1` through `page.evaluate`, then check the marker after.
12. **The registry:** `connector-status-led` now sits on a `status`-owned LED span; note it in `docs/ui-testid-registry.md`.

## Acceptance Criteria
- [ ] Every output above is in place. The frame, fields, token, Enabled, the status line, Save, Cancel and the doctor are built from library controls, and `connector-editor.js` has no hand-built header, field group, switch or status markup.
- [ ] New tests (a)-(h) pass. (a) and (b) are recorded as failing before the fix (test-first) in the flight log.
- [ ] **Amendments 1-12** are implemented, each with its test where one is named.
- [ ] **The masked round-trip holds:**
  - no plaintext token in the page after a create or edit Save;
  - an untouched Save keeps the stored token;
  - `tests/test_api_secret_mask_roundtrip.py` passes.
- [ ] `HTML_SINK_ALLOWANCE` has no `connector-glue.js` row, and `connector-editor.js`'s count is lowered by the sinks this leg removed. The ownership allowance shrinks for `connector-editor.js`, with no row added anywhere.
- [ ] The `library`, `mcp`, `routing` and `shared` lanes pass under `THE_ONE_TEST_NETNS=1`, and so does `make test-unit`. The static guards (`test_ui_guards.py`, `test_token_definitions.py`, `test_design_tokens_a11y.py`) pass.
- [ ] **Ledger rows:**
  - the Enabled switch (DD7-1);
  - the token reveal eye (DD7-4);
  - the doctor result as a status line (DD7-6);
  - the header status line with the same text and states, and "Connection check failed" on a failed probe (DD7-10);
  - revert-to-clean dirty (DD5);
  - any other visible difference, with a reason.
- [ ] The `library` lane's time is reported against its budget in the flight log.

## Verification Steps
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser tests/browser/test_studio_connector_editor.py -x --timeout 60`
- `--lane library`, `--lane mcp`, `--lane routing`, `--lane shared`; `make test-unit`.
- `git grep -n "showFlash\|tool-enable-switch\|editor-header\|innerHTML" -- the_one/interfaces/web/static/js/areas/studio/connector-*.js`: only the 07b-owned sites remain (pairing, channel map, danger zone), each listed in the flight log for 07b.

## Implementation Guidance
1. **Log a start line.** Read `provider-editor.js` (the frame, `mountSlot`, `secretInput` re-mask, `fetchJson`, focus) and `general-tab.js` (`toggle` with a label beside it).
2. **Write the defect tests (a) and (b)** and see them fail. Write (d) and (e) against today's code; they may already pass, and they pin the contract before the change.
3. **Build the frame and fields,** then the value model and dirty state, then Save and Cancel, then the doctor and the status line. Run `test_studio_connector_editor.py` after each.
4. **Change the glue,** then run `library`, `mcp`, `routing` and `shared`.
5. **Pins, allowances, ledger, flight log** (with in-progress lines).

## Edge Cases
- **Type change on create:** the setup steps follow the select (keep it), and the type select is part of the value model.
- **Create with an empty token** posts `secrets: {token: ''}` as today; the server accepts it. Do not send a masked value on create (a 422).
- **Save while a probe is in flight:** the probe's late response writes the header line only if the mount is current (`isCurrent`), and only if the identity is unchanged.
- **The guard's dirty source:** the studio nav source reads `state.dirty` through `onDirtyChange`. Keep calling it on every transition, including back to clean, so a revert to clean lets the operator leave with no prompt (the `test_router_guard.py`/`test_nav_guard.py` pins).
- **`focusAfter` on create:** keep `App.focusAfter.defer(saveTok, titleEl)` across the create remount (the glue flushes it), as today.

## Files Affected
- `js/areas/studio/connector-editor.js`, `js/areas/studio/connector-glue.js`
- `css/studio.css`: remove the rules that only the old frame and fields used (`.connector-enabled-row`, `.connector-status-row`/`-label`), after grepping; the cascade-layer rule applies
- `tests/browser/test_studio_connector_editor.py` (new tests; the LED and title locators)
- `tests/test_store_static.py`, `tests/test_ui_guards.py` (the sink allowance), `tests/_ui_ownership_allowance.py`
- `docs/ui-testid-registry.md` (move any `_btn`-indirection manual-exception rows this leg's buttons leave to the literal table)
- The flight log

## Citation Audit
Checked at `332496d` on 2026-10-22 (FD read):
- `connector-editor.js:100-121,150-200,220-320,321-384,500-534,535-565,586-724`;
- `connector-glue.js:30-110`;
- `api.py:2709,2767,4033`;
- `test_studio_connector_editor.py:56-80,140-160,234-245,315`.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
