# Leg: editor-controller

**Status**: ready
**Flight**: [The MCP server editor on the library](../flight.md)

## Objective
Rebuild the MCP editor's controller on `App.ui.editorShell`, `App.ui.section` and `App.ui.dangerZone`, with the sections in B1's order. Edit-mode Save and Cancel patch in place from the field handles, and the controller's `source` is replaced from Save's response (defect 3). Save, Cancel, Create and Test are busy while a request is in flight (defect 5). Field errors go on the field (A2, defect 10), and the copy (A3) and subtitle (A4, defect 12) are fixed. Every MCP file reaches zero HTML-string sinks and zero ownership-allowance rows.

## Context
- **Flight decisions:**
  - DD4: one controller with a teardown; patch in place; Save re-baselines from the response after the re-mask; `setBusy`; errors per Flight 4 DD3; focus through `App.focusAfter`; the remount side-effect inventory; the stable DOM contract;
  - DD7: A2, A3, A4, B1 and B7; ledger rows 2, 3, 4, 22, 28 (the MCP half), 29 and 33;
  - DD9: defects 3, 5, 10 and 12;
  - DD10: the standing leg rules;
  - DD11: the allowance only shrinks;
  - DD12: `list-and-detail.md` step 13.
- **The controller today** (`js/areas/studio/mcp-server-editor.js`, 573 lines, after leg 09; FD read, 2026-10-25):
  - **`renderMcpSourceEditor` (`:48-230`)** string-builds the header, the Connection section with hosts, the sandbox host, the info and tools hosts, the env/headers host and the danger zone, then sets `container.innerHTML = html` (`:143`, the last MCP sink).
    - **The header:**
      - `h1.editor-title` "New MCP Server" or the name;
      - `p.editor-subtitle`, the raw type slug plus the command or URL (A4);
      - `div.form-actions` with `editor-unsaved`, Cancel, Save and `span.editor-error`.
    - **The breadcrumb** is inserted with DOM APIs (`:152-162`).
    - **The danger zone** is a string with `App.icon('trash')`, "Delete MCP Server" and `data-name`.
    - **The order today** is Connection, Sandbox, Server, Tools, Env/Headers, Danger zone. B1 wants Connection, Env vars or Headers, Sandbox, Server, Tools, Danger zone.
  - **Test** (`:206-211`) is an `App.ui.button` (`mcp-test-connection`) inserted before Cancel and stored as `handles.testBtn`.
    - The consent session hold (`mcp-editor-lifecycle.js` `setSession` / `endSession`, `:68-87`) drives its label ("Waiting for sign-in…") and `disabled` directly.
    - `wireEditorEvents`' `setBusy` (`:462-471`) leaves Test alone while a Test or a session runs.
  - **Save** (`:323-403`):
    - It uses a raw `fetch` with its own error parsing, where it should use `App.api.fetchJson`, and it has no busy state (defect 5).
    - It shows the flashes "MCP Server saved" and "MCP Server created" through `App.showFlash`.
    - An edit Save re-masks (`envHeaders.remaskAfterSave`), retakes the fields' snapshot and sets the title (squawk 0126). It does not set the subtitle (defect 12), and it does not replace `source`.
  - **Cancel** (`:309-321`) reverts to the MOUNT-TIME `source` through `revertEditorToSource` (`:480-496`), which is defect 3. `current` (`:195`, which `connStatus` reads) is never replaced either.
  - **Delete** (`:437-459`) runs `App.confirmDelete` with "Confirm Delete?"; on error it shows an error toast through `App.showFlash`, where row 29 wants the editor error.
  - **`collectFormData` (`:503-570`)** writes "Name is required.", "Type is required.", "Command is required for stdio servers." and "URL is required for streamable-http servers." into `.editor-error`. With `{silent: true}` it returns `{error}` instead (leg 08b, defect 9).
- **The module handles** (legs 06-09):
  - `connectionFields.create` → `{el, values, setValues, setError(field, msg|null), focus(field), setType, destroy}` (fields `name`, `type`, `runtime`, `command`, `cwd`, `args`, `url`);
  - `sandboxFields.create` → `{el, values, setValues, setType, destroy}`;
  - `envHeaders.create` → `{el, values, isDirty, revert, setType, partition, remaskAfterSave, destroy}`;
  - `connectionStatus.create({container, mount, callbacks, getSource, testBtn, serverInfo, setError, titleEl})` → `{el, render, runTest, showInvalid, isTesting}`. It reads `getSource()` for every refetch and render;
  - `serverInfo.create({cache})` → `{serverEl, toolsEl, update, setTools, destroy}`.
- **The library:**
  - `App.ui.editorShell` (`js/ui/editor.js`, the header comment `:41-80`) has:
    - `breadcrumb {label, href, trail}`, `title`, `subtitle`, `subtitleTestid`, `errorRole: 'alert'`;
    - `actions {cancel {testid, onClick, enabledWhenClean}, save {label, testid, onClick}, test {testid, onClick}}`;
    - the methods `setTitle`, `setSubtitle`, `setDirty`, `setBusy`, `setError`, `setTestState({disabled, label})`;
    - the properties `cancelButton`, `saveButton`, `testButton`, `titleEl` and `errorEl`.

    The caption keeps the `editor-unsaved` testid.
  - `App.ui.dangerZone({actions: [{label, testid, confirmLabel, dataset, onConfirm(revert)}]})` (`:369-436`).
  - `App.ui.flash(text, {container})`.
  - `App.api.fetchJson` and `App.api.fieldErrors(err, names)` (`js/api.js:86-127`):
    - a string `detail` goes to `rest`;
    - a pydantic `loc` (`body` dropped) matching a name goes to `fields`.

    The server's MCP 422s are mostly strings from `_validate_mcp_source_config` (`api.py:2932-2990`). Pydantic errors come through `_validation_detail` (`api.py:166`), with a `loc` such as `["name"]` or `["config", "url"]`.
  - **The reference pattern:** `connector-editor.js` `performSave` and Cancel (`:640-733`):
    - busy until a create's remount;
    - on an edit, apply the response, then re-snapshot, `setTitle`, `setBusy(false)`, `setDirty(false)`, and the callback last, inside a try.
- **The glue** (`mcp-glue.js:60-140`): `onSaveSuccess(updated, isCreate)`:
  - sets `state.editingMcpSource`;
  - calls `reloadLibrary('mcp-sources')`;
  - runs the router sync;
  - on a create, remounts, then calls `current.runTest({autoRun: true})` for streamable-HTTP only.

  `onMounted` keeps the controller, and `onCancel` (create) discards and goes to `#library`.
- **The guards that still hold MCP entries** (FD grep, 2026-10-25):
  - `tests/_ui_ownership_allowance.py:32-51` and `:108-127`: about 20 keys for `mcp-server-editor.js`. They cover `api:App.confirmDelete(`, `api:App.icon(`, `api:App.showFlash(`, the `btn-*` classes, `danger-zone*`, `delete-btn`, `editor-*`, `form-actions`, `section-title` and others;
  - `tests/test_ui_guards.py:106` and `:121` (`"areas/studio/mcp-server-editor.js": 1`), plus `SINK_START_FILES` and `SNIPPET_START_FILES` (`:149-150`).

  `MOVES`, `SINK_MOVES` and `SNIPPET_MOVES` are already empty (leg 09).
- **`components.css:1294`, `.form-actions .editor-error`:** the legacy colour rule kept for the hand-built MCP header (DD7, A1). This leg deletes it.
- **`tests/behavior/list-and-detail.md` step 13** (`:111`) says "choose the Streamable HTTP transport". B3's label is "Remote server (HTTP)", and B2 moved Test into the header.

## Inputs
- Legs 06-09 have landed: every field, the env and headers, the status, sign-in and Test flow, and the server info sit on handles. Batch B4 (08b and 09) is reviewed and committed before this leg starts.

## Outputs
- **The shell (A3, A4, B2):**
  - **`App.ui.editorShell`** with:
    - the breadcrumb `{label: 'Library', href: App.router.href({destination: 'library'}), trail: ' / MCP servers'}`;
    - the title: the name, or "New MCP server" on create;
    - `errorRole: 'alert'`.
  - **The actions:**
    - `cancel` (`cancel-mcp-source-btn`, `enabledWhenClean` on create);
    - `save` ("Create" or "Save", `save-mcp-source-btn`);
    - `test` (`mcp-test-connection`, which keeps its testid). It calls the existing `runTest({})`. It is built if and only if the MOUNT-TIME source is in edit mode with type stdio or streamable-HTTP (today's `hasConnection`). The shell cannot add or remove it later, and a type switch before Save does not need to (the Test then sends the dirty form).
  - **The title fallback:** `editorShell` throws on a falsy title (`editor.js:82`). The mount and every `setTitle` after Save use `name || 'MCP server'`.
  - **The type labels** come from `mcpTypes`, an array of `{value, label}` (`api.py:3082-3083`: "Local program (stdio)" and "Remote server (HTTP)").
  - **The subtitle (A4, FD decision):** "{type label} · {command or URL}" from the `mcpTypes` labels, for example "Local program (stdio) · /usr/bin/python" or "Remote server (HTTP) · https://…".
    - It is the type label alone when there is no command or URL.
    - It falls back to the raw type for a type with no label (a legacy row).
    - It is set by one helper, used at mount and after every edit Save (defect 12).
    - Add `subtitleTestid: 'mcp-editor-subtitle'` (a new registry row) so tests can read it.
- **The Test hold moves to the shell, with ONE writer** (design review, issue 1). Today three things write Test's `disabled`:
  - `editorShell.apply()`, on every `setDirty` and `setBusy`;
  - `connectionStatus.runTest` and `settle` (`mcp-connection-status.js` about `:311`, `:316`; the focus check about `:282`);
  - the lifecycle's `setSession` / `endSession` (`mcp-editor-lifecycle.js:68-87`), plus `wireEditorEvents`' `setBusy`.

  Under the shell, a keystroke during a running Test would call `apply()` and re-enable Test. So:
  - **One controller-owned `syncTestHold()`:** `hold = connStatus.isTesting() || mount.sessionActive()`, then `shell.setTestState(hold ? {disabled: true, label: mount.sessionActive() ? 'Waiting for sign-in…' : null} : null)`.
    - It is called at Test start, at `settle`, and from ONE `mount.onSessionChange` registration. `setSession` and `endSession` already call `notify()`, so do not also call it from them. On a dead mount it does nothing.
    - Delete the lifecycle's now-dead `heldLabel`, `labelOf` and `setLabel` (`mcp-editor-lifecycle.js:68-87`). Read the focus check at `mcp-connection-status.js` about `:282` as `(testBtn && !testBtn.disabled && testBtn) || titleEl()`.
    - **The creation order:** the shell first, with `actions.test.onClick` a late-bound closure (`function () { runTest({}); }`); then `connStatus` with `shell.testButton`, `shell.titleEl` and `shell.setError`.
    - **Retarget, by name,** the leg 08b test "label restored on a destroyed mount" (`test_flow_studio_mcp_editor.py` about `:3935-3975`). After this leg a dead mount's button is not rewritten, so assert that the NEXT mount's Test reads "Test".
    - Pass it into `connectionStatus.create` and the lifecycle as a callback (for example `onTestHoldChange`), and delete EVERY direct `testBtn.disabled =` write and every direct label write in those files.
  - **The label:** a plain Test keeps "Test" on the button (today's behaviour; "Testing connection…" stays in the result area). Only a sign-in session relabels it.
  - **Busy:** `setBusy` becomes `shell.setBusy`, which already ORs into Test's disabled state.
  - **Unchanged:** during a session only Test is held, and Save and Cancel stay live.
  - **No Test button:** `connectionStatus.create` takes the shell's `testButton`, which is null in create mode and for a type other than stdio or HTTP. It must tolerate `null` everywhere (its focus targets fall back to the title). Today `:311`, `:316` and `:375` dereference it unguarded, as does the editor's `runTest`.
  - **Tests:**
    - typing during a held Test leaves Test disabled (failing first);
    - a create-mode mount and a legacy-type mount have no Test and throw nothing;
    - the leg 08b hold tests (the label, its restore on a destroyed mount, Reset and Forget disabled during a session) pass unchanged or retargeted, never relaxed.
- **The sections in B1's order** (row 22):
  1. Connection: `App.ui.section({title: 'Connection'})` holding `connection.el`, then `connStatus.el` (edit mode);
  2. `envHeaders.el`;
  3. `sandbox.el`;
  4. `serverInfo.serverEl`;
  5. `serverInfo.toolsEl`;
  6. the danger zone (edit mode).

  Create mode keeps leg 06's rule: only Name and Type until a type is chosen. Each module keeps its own visibility rule.
- **The danger zone (B7, A3, row 29):**
  - `App.ui.dangerZone` with one action:
    - the label "Delete MCP server";
    - the testid `delete-mcp-source-btn`;
    - `dataset: {name: source.name}`;
    - the armed label "Confirm delete?", the library default.
  - On success: invalidate `mcp-sources` and `agents`, show `App.ui.flash('MCP server deleted', {container})`, then call `onDeleteSuccess`.
  - **On error (row 29):** `revert()`, then `shell.setError(message)`, with no toast. Focus goes back to the button.
  - **A late Delete after `destroy`** keeps today's rule: invalidate, then `onListStale`, and the dead editor is not touched.
  - **The Reset and Forget errors (row 29)** already go to `setError` (`mcp-connection-status.js` about `:289`, `revert()` then `setError`). Verified at design review, so no change; add a test if none exists.
  - **Tests:** a Delete error (a 500 through `page.route`) shows the editor error, reverts the button and returns focus to it. A Delete released after `destroy` writes nothing to the page and still invalidates.
- **Save (defects 3, 5 and 10; DD4):**
  - **Validation** (design review, issue 7): `collectFormData` validates on the handles and never writes the DOM. It returns `{payload}` or `{error, fields}`, where `error` is the first field's sentence (A2's wording) and `fields` maps a field to its message. Save puts `fields` on the fields. The silent Test path (leg 08b, defect 9) keeps passing `error` to `connStatus.showInvalid`, so the Test result area now reads "Enter a name." and similar. Retarget, by name in the flight log, every leg 08b test that asserts the old "… is required" text there. Each message goes to `connectionFields.setError(field, msg)`, and focus goes to the first field with an error (`connectionFields.focus(field)`). A2's wording:
    - Name: "Enter a name."
    - Command: "Choose or enter a command." (on `runtime` when nothing is chosen, else on `command`)
    - URL: "Enter the server's URL."
    - Type: "Choose how it connects."

    Every field error clears when its field changes, or on the next Save. If `connectionFields`' `onChange` does not already clear its own field's error, add that in `mcp-connection-fields.js`, with a test.
  - **The request:**
    - `shell.setBusy(true)` before the request, so a second click cannot send a second POST (defect 5);
    - `App.api.fetchJson` with the PUT or POST;
    - on error, `App.api.fieldErrors(err, ['name', 'type', 'command', 'url', 'cwd', 'args'])`: field hits go to the field, the rest go to `shell.setError(text)`, then `setBusy(false)` and focus back to Save. A string `detail` (the server's config validator) goes to the editor error.
  - **An edit Save that succeeds,** in this order:
    1. `App.store.invalidate('mcp-sources')`;
    2. if the mount is dead, `onListStale` and return;
    3. `App.ui.flash('MCP server saved', {container})`;
    4. `current = updated`, BEFORE the re-mask, so every `getSource()` reader sees the saved row (defect 3);
    5. `envHeaders.remaskAfterSave(submitted, updated)` (the env and headers rows keep leg 07's per-row rule);
    6. the fields' baseline from `updated` (see "The fields' baseline" below);
    7. `shell.setTitle(updated.name || 'MCP server')`, then the subtitle helper;
    8. `serverInfo.update` and `connStatus.render()`, because a URL or type change drops `last_check` and `auth_posture` server-side (the batch B3 fix);
    9. recompute dirty, `shell.setDirty(dirty)`, then `shell.setBusy(false)` (the shell restores a dirty-derived state, so dirty must already be right), then `syncTestHold()`;
    10. `App.focusAfter.restore`;
    11. `onSaveSuccess` last, inside a try (the connector order).
  - **The fields stay editable during a Save** (DD4, the connector precedent). `shell.setBusy` disables only the buttons.
  - **The fields' baseline** (FD decision on design review issue 2, option b). `connectionFields.setValues` and `sandboxFields.setValues` write the whole form, and `values()` has a different shape from a stored source (runtime, command and args are split), so the controller cannot compare field by field today. Add a pure `baselineFrom(source)` to each of the two modules: it returns exactly the `values()` shape `setValues(source)` would produce, without touching the DOM.
    - **The snapshot** is `JSON.stringify({connection: connectionFields.baselineFrom(current), sandbox: sandboxFields.baselineFrom(current)})`. Dirty compares it with the same shape built from `values()`, or `envHeaders.isDirty()`.
    - **At the Save click,** keep `submittedValues`, the `values()` snapshot string.
    - **On success:**
      - if `values()` still equals `submittedValues` (no field edited during the request), call `setValues(updated)` on both modules, which normalises them, plus the types;
      - otherwise leave the DOM as the operator has it, edits and a type change included.

      Either way the snapshot becomes the baseline from `updated`, so an edit made during the request stays dirty and a clean form is clean.
    - **`baselineFrom` goes through the controls' own normalisation** (cycle 2):
      - de-duplicate and coerce to `String`, as `ui/chip-list.js` `setValues` does (args and writable paths);
      - derive the runtime with the existing pure `deriveStdioRuntimeSelection` (`mcp-editor-shared.js`), never a re-implementation. That includes the `|| 'uvx'` default, which HTTP sources get too;
      - return the network flag `true` for `baselineFrom(null)`, as `setValues(null)` does;
      - build the object in exactly the same key order as `values()`, from one shared key list or normaliser in each module, so the two cannot drift;
      - `current.type` must be among the mount-time Type options (a legacy type is appended at mount), or `typeSelect.value` reads `''`. Note this as a limit in the module comment.

      Test `baselineFrom(src)` against `values()` after `setValues(src)` directly, in a small browser test, BEFORE wiring dirty. `setValues` fires no events, so the controller recomputes dirty itself (step 9).
    - **A clean mount must not read dirty** (`baselineFrom(source)` equals `values()` after `setValues(source)`). Test this for every capture seed: stdio with each runtime (uvx, `npx -y`, `pipx run`, custom), HTTP, legacy, no args, empty cwd, a duplicate arg and a duplicate writable path.
  - **A create Save that succeeds:**
    1. invalidate;
    2. flash "MCP server created";
    3. `App.focusAfter.defer` to the new mount's title;
    4. `onSaveSuccess(updated, true)`.

    The editor STAYS busy until the glue's remount replaces it (the connector rule). The glue's create → edit remount, the `destroy` first and the auto-run for streamable-HTTP are unchanged.
- **Cancel (edit; defect 3):**
  - It reverts to `current`, the last saved row, not the mount-time `source`: `connectionFields.setValues(current)`, `sandboxFields.setValues(current)`, the types, and `envHeaders.revert()`.
  - Then it clears the field errors and the editor error, retakes the snapshot, sets `setDirty(false)` and restores focus to the title.
  - Create-mode Cancel is unchanged (`onCancel`).
- **Dirty:** `checkDirty` drives `shell.setDirty(dirty)` and `onDirtyChange`. The hand-written `applyButtons` and `reportDirty`, and the `.editor-unsaved` lookups, go.
- **Copy (A3, row 3):**
  - "New MCP server", "MCP server saved", "MCP server created", "MCP server deleted", "Confirm delete?";
  - the Name placeholder: if it still reads "My MCP Server", sentence-case it;
  - grep for every remaining Title Case string in the MCP files and list the hits in the flight log.
- **Zero sinks and zero allowance rows in every MCP file** (design review, issue 5):
  - **`tests/test_ui_guards.py`:**
    - delete `DYNAMIC_SINK_BASELINE["areas/studio/mcp-server-editor.js"]` (`:106-108`) and `HTML_SINK_ALLOWANCE["areas/studio/mcp-server-editor.js"]` (`:121`);
    - set `SINK_TOTAL` 6 → 5 (`:144`);
    - for `SINK_START_FILES` and `SNIPPET_START_FILES` (`:149-150`), READ the start-record semantics first (`sink_start` / `sink_stale_errors`, about `:223-250`). If they are the flight-start record that the MOVES rules check against, keep them as they are and say so; delete entries only if the guard requires it;
  - **`tests/_ui_ownership_allowance.py`:** remove every `mcp-server-editor.js` key from the allowance (`:32-51`) and from `START_ROWS` (`:108-138`; the block also holds `api-key-*`, `chip-list-*`, `field-*`, `indicator-led*`, `api:App.consentLink.` and `btn-*` keys), applying the same rule as the start record above;
  - **`TOTAL_USES`:** lower each exact entry by computing it from the live scan, never by hand;
  - no `App.showFlash`, `App.confirmDelete` or `App.icon` calls remain in `areas/studio/mcp-*.js`;
  - `HTML_SINK_ALLOWANCE` then holds only `areas/chat.js: 5`.

  Report the whole-app totals before and after.
- **The legacy CSS:** delete `components.css:1294` (`.form-actions .editor-error`), and any other rule whose only user was the hand-built MCP header. Use `scripts/unused_selectors.py` on `components.css` and `studio.css`, and paste the result. Grep for each deleted class across `tests/`, `scripts/`, `docs/` and `tests/behavior/`.
- **The line guard:** the controller stays at 800 lines or fewer. If `tests/test_area_module_size.py` still has an `ALLOWANCE` entry for an MCP file, remove it (the FD grep found none).
- **`tests/behavior/list-and-detail.md` step 13:** "choose Remote server (HTTP) as the type". Check the step's other wording against B2 (Test in the header; the auto-run still runs on create) and A6 (the status line). Leg 11 owns the row meta "Tools not loaded" → "Not connected" (B6). Amend the spec text only, never its run logs.
- **The store pins** (design review, issue 3). `tests/test_store_static.py` `INVALIDATION_ROWS` (`:315-335`) anchors on literal source strings in `mcp-server-editor.js`: `"var method = isEdit ? 'PUT' : 'POST';"`, `"callbacks.onSaveSuccess(updated, !isEdit)"`, and `"encodeURIComponent(source.id), { method: 'DELETE' })"` … `"callbacks.onDeleteSuccess()"`. The agents-invalidation count `>= 1` (`:290`) depends on the Delete site staying in this file.
  - **Retarget the anchors to the new `fetchJson` form, as TWO rows,** because the create and edit callbacks become separate sites and `_window` ends at the FIRST end marker:
    - one row for create: its anchor is the create branch, its end is that branch's `callbacks.onSaveSuccess(updated, true)` line;
    - one row for edit: its anchor is the edit branch, its end is the edit `onSaveSuccess` call inside the try.

    Each row checks that `App.store.invalidate('mcp-sources')` comes before its own end. Name the exact literals in the test and in the flight log. Keep `var method = isEdit ? 'PUT' : 'POST';` as a literal only if it survives, and say so. The dead-mount `onListStale` return must not be an end marker. The Delete row keeps its own anchor and end (`onDeleteSuccess`).
  - Keep the rule that each invalidation sits between its anchor and the callback's end marker, so the invalidate-before-callback order stays pinned. Never relax it.
- **The tests that read the old copy** (design review, issue 4):
  - `test_flow_studio_library_list.py:795`, `:1159` and `:1217` hard-code "New MCP Server": retarget them to "New MCP server";
  - `test_flow_studio_mcp_editor.py:191` and `:217` match `Confirm Delete\?` case-insensitively, so they pass unchanged;
  - `:3707`'s `.editor-header .form-actions [data-testid="mcp-test-connection"]` still resolves under the shell;
  - `.editor-header-text` (`test_flow_studio_library_list.py:807`, `:871`) is kept by the shell;
  - also grep `scripts/ui_capture.py` for the old copy and selectors.
- **The docs:**
  - `the_one/agents.md`: the MCP editor's structure, the save model and the copy;
  - `docs/ui-testid-registry.md`: `mcp-editor-subtitle`, and check the `.form-actions` notes at `:42` and `:166`.

  `CLAUDE.md` has no mention to change (grep at design review).

## The remount side-effect inventory (DD4)

| Effect | Before (leg 09 tree) | After (this leg) | Test |
|---|---|---|---|
| Edit Save | patch, with the title only; `source` and `current` stale | patch: re-mask, then baseline, title, subtitle, `current`, server info and status line, then focus, then the callback | defect 3, 12 tests; the subtitle after a URL edit |
| Edit Save with an edit in flight | the edited field stays dirty (env rows only) | every field edited during the request stays dirty | held PUT with `page.route`, then type, release, assert dirty |
| Create Save | no busy; a double-click makes 2 sources | busy until the remount | defect 5: a held POST, a second click, then exactly one POST |
| Create → edit remount | `destroy`, mount, auto-run (HTTP) | unchanged | the existing auto-run tests |
| Edit Cancel | reverts to the mount-time `source` | reverts to `current` | defect 3: Save, then edit, then Cancel shows the saved values; Save again keeps the secret the first Save added |
| Delete | an error goes to a toast | an error goes to the editor error, and the button is reverted | row 29: a 500 from `page.route` |
| Test, the session hold | the button is driven directly | `shell.setTestState` | the leg 08b hold tests |
| Busy | Test only | Save, Cancel, Create and Test during Save or Create | row 33 |
| Transport switch | the module rules | unchanged (the sections are reordered only) | the leg 06 and 07 tests |
| `onListStale` and the invalidations | as they are today | unchanged | `test_store_static.py` `INVALIDATION_ROWS` |

## Acceptance Criteria
- [ ] **Built from the library:** `mcp-server-editor.js` builds the editor from `editorShell`, `section` and `dangerZone`, with no `innerHTML` and no HTML string. The sections are in B1's order, which is tested by reading the section titles in DOM order for a stdio source and an HTTP source.
- [ ] **Defect 3:** after an edit Save, Cancel shows the saved values, and a second Save does not drop a secret added by the first (both tested, failing first).
- [ ] **Defect 5:** a double-click on Create, with the POST held, sends one POST. Save, Cancel and Test are disabled while a Save is held (tested, failing first).
- [ ] **A2 and defect 10:** each empty required field shows its message on the field, and focus moves to it. A server 422 with a `loc` reaches its field, and a string `detail` reaches the editor error (`role=alert`) (tested).
- [ ] **A4 and defect 12:** the subtitle uses the type label, and follows a URL or command change after Save (tested, failing first).
- [ ] **Row 29:** a Delete error shows in the editor error, not as a toast (tested). Reset and Forget errors were checked to do the same.
- [ ] **A3:** the copy is sentence case (tested where a test reads it), and the leftover grep is listed.
- [ ] **The Test hold works through `setTestState`, with one writer (`syncTestHold`).** Typing during a running Test keeps Test disabled (tested, failing first). A mount with no Test button throws nothing (tested). Every leg 08b test passes.
- [ ] **A clean mount is never dirty** for every capture seed (`baselineFrom`). A field edited during a Save stays dirty, and an untouched one is clean after it (tested with a held PUT).
- [ ] **`tests/test_store_static.py`'s anchors are retargeted,** with the invalidate-before-callback order still pinned.
- [ ] **No MCP entries left in the guards:**
  - zero HTML sinks and zero ownership-allowance rows for every `areas/studio/mcp-*.js`;
  - `HTML_SINK_ALLOWANCE` holds only `areas/chat.js`;
  - the guard tables are updated exactly, with the totals reported.
- [ ] **`.form-actions .editor-error` is deleted,** with the grep and the unused-selector report pasted into the flight log.
- [ ] **`list-and-detail.md` step 13 is amended.**
- [ ] **Lanes and files pass:**
  - lanes `mcp`, `library`, `agents` and `routing` (store pins);
  - `providers`, `knowledge` and `settings`, if any shared CSS or `js/ui/` file changed;
  - `contracts-controls` with `THE_ONE_REQUIRE_WEBKIT=1`, if `js/ui/` changed;
  - the static guards, then `make test-unit`.
- [ ] **Captures:** each change maps to rows 2, 3, 4, 22, 28, 29 and 33 only (FD-checked).

## Verification Steps
- Tests first: the defect 3, 5, 10 and 12 tests and the B1 order test run on the leg 09 tree, and which fail and why is recorded before any product change.
- `git grep -n "innerHTML\|showFlash\|confirmDelete\|App.icon(" the_one/interfaces/web/static/js/areas/studio/mcp-*.js` finds nothing.
- The lanes above with `THE_ONE_TEST_NETNS=1`, at most 3 at a time host-wide; then the static guards and `make test-unit`.
- Captures into `~/.cache/the-one-ui-capture/m31-f5-l10`, compared with `m31-f5-l09` using PIL `ImageChops`. The status line's date text differs run to run.

## Implementation Guidance
1. **Tests first:**
   - defects 3, 5, 10 and 12, the B1 order, row 29 and the subtitle;
   - Test staying disabled while you type during a Test;
   - the clean-mount, no-dirty seeds, and the field edited during a Save.

   Use `page.route` holds for the in-flight cases (DD12), never fixed waits.
2. **`baselineFrom` on the two field modules,** and the one hold writer (`syncTestHold`, with the direct writes removed).
3. **The shell and sections:** the shell, the section order, the danger zone and the subtitle helper.
4. **The save model:** `fetchJson`, busy, `current`, the baseline, field errors and Cancel to `current`. Retarget the store anchors.
5. **The guards, then the CSS deletion and its grep.**
6. **The docs, the behavior spec text, the captures, the ledger and the flight log.**

## Edge Cases
- **A legacy row whose type has no label** (the `mcp-edit-legacy` capture): the subtitle falls back to the raw type, and it never throws.
- **An empty name in a stored row:** the title falls back to an empty string; the shell requires a title, so pass "MCP server". Check that `editorShell` accepts it.
- **A Save that lands after `destroy`:** nothing is written into the page, and the invalidation and `onListStale` still run.
- **A Save during a consent session:** Test stays held, Save completes, and the session is not cancelled (DD4).
- **A type change, then a Save:** the subtitle, the sections' visibility, the env/headers title and the status line all follow the saved type.
- **A 422 with both a field `loc` and a string:** the field gets its message and the editor error gets the rest.

## Files Affected
- `js/areas/studio/mcp-server-editor.js`, `mcp-editor-lifecycle.js` (the hold), `mcp-connection-status.js` (the one hold writer, a null Test), `mcp-connection-fields.js` and `mcp-sandbox-fields.js` (`baselineFrom`, the error clearing); `mcp-glue.js`, only if the controller's contract changes.
- `tests/test_store_static.py` (the anchors).
- `css/components.css`, and `css/studio.css` if a rule loses its last user.
- `tests/browser/test_flow_studio_mcp_editor.py` (new tests and retargets), `test_mcp_test_connection_button.py`, `test_flow_studio_library_list.py`, `test_flow_studio_library_focus.py` (check each); `tests/test_ui_guards.py`, `tests/_ui_ownership_allowance.py`; `tests/test_area_module_size.py` (if needed).
- `docs/ui-testid-registry.md`, `the_one/agents.md`, `tests/behavior/list-and-detail.md`; the flight log and ledger.

## Citation Audit
- `mcp-server-editor.js`: `:48-230` (`renderMcpSourceEditor`), `:143` (the sink), `:206-211` (Test), `:309-321` (Cancel), `:323-403` (Save), `:437-459` (Delete), `:480-496` (revert), `:503-570` (`collectFormData`). FD read in full on the leg 09 tree (2026-10-25).
- `mcp-editor-lifecycle.js:60-102` (the session hold); `mcp-connection-status.js:1-34` and `:414-421` (`create` and its API), `:289` (Reset and Forget's `setError`). FD read.
- `js/ui/editor.js:41-80` (the shell contract), `:369-436` (`dangerZone`); `js/api.js:86-127` (`fieldErrors`); `connector-editor.js:640-733` (the reference save); `mcp-glue.js:60-140`. FD read.
- `tests/_ui_ownership_allowance.py:32-51` and `:108-127`; `tests/test_ui_guards.py:106`, `:121` and `:149-150`; `components.css:1294`; `tests/behavior/list-and-detail.md:111`. FD grep.
- Batch B4 review fixes may move lines in `mcp-connection-status.js` and `api.py`, so re-locate them at the start.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.

## Design Review
- **Cycle 1 (2026-10-25): approve with changes.** Applied in place:
  - **Test had three writers of its disabled state** (H). Now there is one `syncTestHold()`, and the direct writes are removed. A plain Test keeps the label "Test". A null Test button is tolerated.
  - **There was no per-field baseline** (H). FD decision, option b: add a pure `baselineFrom(source)` to `connectionFields` and `sandboxFields`, compare the whole snapshot, and treat an edit made during a Save as dirty. Clean-mount tests cover every seed.
  - **`test_store_static.py`'s anchors** are added, with their order kept (H).
  - **The tests that read the old copy** are listed (M).
  - **The exact guard entries** are listed, and the start-record semantics must be read first (M).
  - **Shell gaps** (M):
    - Test is built from the mount-time type;
    - the title falls back to "MCP server";
    - the fields stay editable during a Save;
    - `setDirty` runs before `setBusy(false)`.
  - **`collectFormData`** returns `{error, fields}`, and the leg 08b Test-result assertions are retargeted (M).
  - **Delete-error tests** are added, and Reset and Forget errors were verified to go to `setError` (L).
  - **The CLAUDE.md bullet** is dropped (L).

  The changes are substantive (the hold writer, a new module function), so a cycle 2 review was spawned.
- **Cycle 2 (2026-10-25): approve with changes** (2 medium, 3 low; no high). Applied in place:
  - `baselineFrom` goes through the controls' normalisation: de-dup, `deriveStdioRuntimeSelection`, the `uvx` default, `null` → network `true`, one key order, the legacy-type limit, and a direct unit-level test first;
  - the store anchors are two rows, create and edit, each with its own end marker;
  - one `onSessionChange` registration, the dead lifecycle helpers deleted, the null-safe focus check, the creation order;
  - the destroyed-mount label test is retargeted by name.

  These are clarifications within the design: status `ready`, and no third cycle (the 2-cycle limit).
