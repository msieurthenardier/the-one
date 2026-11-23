# Leg: 03b-library-kinds-editors

**Status**: completed
**Flight**: [The remaining kinds](../flight.md)

## Objective

The knowledge-base create and edit forms and the secret editor gain a GleepGlorp controller,
built on Leg 2's shared fill and follow cores, and the two kinds register in
`App.gleepglorpKinds`. As a result:
- a fill from the drawer opens the right editor and fills it as unsaved edits;
- an approved proposal updates an open editor without silently overwriting unsaved edits;
- the notes appear in the operator-approved placements.

## Context

- **Flight decisions:** DD4 (the cores), DD5 and DD6 (the fields), DD9 (follow), DD13 (pins and
  UI test patterns) and DD14 (layouts).
  - **The DD14 choices that apply:**
    - **Choice 1:** one note under the allowed-tools chips, "Filled by GleepGlorp: added X,
      Y.";
    - **Choice 4:** the key-value note under the secret's values table, "Enter the value for
      {key}, then Create.";
    - **Per-field notes** for name and description;
    - **Follow notes** use the per-field placement, as the agent editor's follow does.
- **Designed after Leg 3a landed** (the server kinds `knowledge_base` and `secret`; fills record
  `values` = the stored changes, see `fill/store.py::fill_view`). Batch B is still uncommitted.
- **What each editor lacks** (FD survey, file:line under `static/js/areas/studio/`):
  - **`knowledge-create.js`** (172 lines):
    - it has no controller, no `saving` flag (only `shell.setBusy`) and no idle waiters;
    - dirty means "either field non-empty", with no baseline;
    - the fields are `nameField` / `descField` (`App.ui.field`, `.el` for a note);
    - it returns `{focus, destroy}`;
    - **opening `#library/knowledge/~new` always focuses the name input**
      (`studio-route.js:221-231/:378` → `library-pane.js:421-425`), which would take focus from
      the drawer composer on a fill navigation.
  - **`knowledge-detail.js`** (353 lines):
    - it has no controller;
    - `readValues()` and a snapshot object; `stored` is the saved row; Save is `busy`, then a
      PUT, then a patch in place;
    - the mount is async, after `/status` and `/items` (`knowledge-glue.js:234-262`);
    - it has no idle waiters.
  - **`knowledge-glue.js`:**
    - the handle key is `'create'` or `'kb:'+id`;
    - the handle is held in `state.knowledgeDetailHandle`;
    - there is no current-controller accessor.
  - **`secret-editor.js`** (418 lines):
    - it has no controller, no `saving` flag and no idle waiters;
    - dirty is the JSON of `readValues()` against the snapshot;
    - **row 0's key follows the name's slug only on an `input` event while `!keyTouched`**
      (`:67-77`), so a silent fill must repeat that;
    - `kv` is a `keyValueTable` (`setRow` silent); `chips` is a `chipList` (`setValues`
      silent); `toolsField.el` hosts the chips note; `values.el` hosts the table note;
    - Save is labelled "Create" or "Save" (`save-secret-btn`).
  - **`secret-glue.js`:**
    - its form key is `'add'` or `'edit:'+id`, which differs from the core's `'create'` /
      `'edit:{id}'`;
    - `state.editingSecret`;
    - `onSaveSuccess` syncs the router with `{name}`.
  - **Neither kind is registered client-side.** `App.approvals.record` returns false for an
    unregistered kind (`approvals.js:57-59`), so an approval invalidates nothing and emits
    nothing, and the drawer reports `editor_unavailable`.
- **The controller contract** the cores and per-kind modules use (`gleepglorp-fill-core.js`,
  `gleepglorp-follow-core.js`; the provider controller `provider-editor-controller.js` is the
  model):
  - **identity and state:** `key`, `isCreate`, `id`, `el`, `alive()`, `ready()`, `saving()`;
  - **saves and dirty:** `onIdle(fn)`, `checkDirty()`, `isDirty()`;
  - **values:** `values()`, `baseline()`, `setField(k, v)`;
  - **notes:** `placeNote(field, el) -> [controls]`, `placeTableNote(el) -> [controls]`,
    `placeFollowNote(el)`, `clearNotes()`;
  - **follow and lifetime:** `rebase(row)`, `fill`, `destroy()`.
- **Leg-design decisions,** recorded by the FD in the log:
  1. **One controller module per editor family.** Small `knowledge-editor-controller.js` and
     `secret-editor-controller.js`, built from each editor's internals the way
     `provider-editor-controller.js` is built from `provider-editor.js`. A controller can
     instead live inside its editor file if that file stays under 800 lines. The KB
     create and edit forms share one controller factory, with a `create` / `edit` mode.
  2. **Keys follow the core:** `'create'` and `'edit:{id}'`. The secret glue's own `'add'` /
     `'edit:'` form key is unchanged; only the controller's `key` uses the core's names.
  3. **Focus on a fill navigation** (design review: the router does not use `opener` for
     focus).
     - **The agent kind's seam:** `agents-list.js:32-38/514`, called by `agent-kinds.js:61-64`
       as `suppressNextCreateFocus()` / `clearCreateFocusSuppression()`.
     - **The only KB autofocus:** `studio-route.js:378` calls `self._focusKbCreate`, which is
       `knowledge-glue.js:178` (`pane.focusCreate('knowledge')`).
     - **The flag's home:** module level on `App.studio.knowledgeEditorFill`
       (`suppressNextCreateFocus()`, `clearCreateFocusSuppression()`,
       `consumeCreateFocusSuppression()`).
     - **The callers:** `knowledge-kinds.js` sets it in `beforeNavigate` and clears it in
       `afterNavigate`. The glue's `_focusKbCreate` wrapper consumes it and skips the focus when
       set.
     - **Not in `library-pane.focusLibraryCreate`:** that is also the Add menu's refocus path.
     - **Already covered by the drawer:** it calls `afterNavigate` on Stay, error and success
       (`gleepglorp-drawer/fill.js:76-79`).
     - **The other editors don't autofocus on mount:** the secret editor, the KB detail and the
       secret glue.
     - **Kept:** the existing Add-menu autofocus pins (`test_flow_studio_knowledge_inventory.py:166`,
       `test_flow_studio_library_list.py:425`) must keep passing, and a new test checks Add-menu
       autofocus still works after a fill.
  4. **A failed KB detail load** (the `/status` or `/items` fetch fails) leaves no controller.
     The fill then times out after 10 s and reports `editor_unavailable`. That rare path is
     accepted, as for the agent editor.
  5. **Follow notes are per-field and event-only** (as for MCP and provider; no redraw from
     `App.approvals.forTarget` at mount).
     - **Where:** `App.gleepglorpFollow.buildNote(detail, {testid, field})`, placed by `placeNote`
       for each field in `detail.fields` that the editor shows. `fields` are stored keys
       (`proposals/apply.py:235-237`): `name`, `description`, `allowed_tools`. Any other field
       is ignored, and the header gets none (DD14).
     - **Linked for screen readers:** each follow note gets an id and is linked on its controls'
       `aria-describedby` (appended, never replacing), exactly as fill notes are.
     - **The link helpers:** the fill core exposes its internal link and unlink helpers
       (`App.gleepglorpFill.link(el, controls)`, `unlink(entry)`) so the follow modules reuse
       them.
     - **Clearing:** `clearNotes()` (Save, Cancel) removes **both** families, fill and follow,
       and unlinks their ids. `placeFollowNote` is not used by these two kinds.
  6. **The secret follow uses its own glue method,** `followed(row)`, never `onSaveSuccess`.
     - **Why:** `onSaveSuccess` clears `state.dirty` (the shared dirty mirror the leave guard
       reads), calls `syncLibrarySelection` and re-mounts on create.
     - **What `followed(row)` does:** sets `state.editingSecret = row`, `reloadLibrary('secrets')`,
       `App.router.sync('studio', 'secrets/' + id, {name})` and `syncLibrarySelection`. It leaves
       `state.dirty`, the form mode and the mount alone, and is gated on the glue's `secGen !==
       state.editorGen` check.
     - **The KB follow** reloads `knowledge-bases` and updates the title or subtitle through the
       controller. The KB glue does no router sync on a rename today; the URL is id-based.
  7. **The secret handoff note** (DD14 choice 4) tracks row 0 live.
     - **It reads** "Enter the value for {key}, then Create." while row 0 exists with a key and
       an empty value. With no row 0, or an empty key (a name with no slug characters), it reads
       "Enter a key and value, then Create.".
     - **It is redrawn on the editor's input and change events,** as the MCP fill's notes are,
       so it goes away once the operator types a value.
     - **It is linked to row 0's value input,** recomputed at each redraw because rows are
       rebuilt by `setValues` and Add, rather than to the whole table.

## Inputs

- The tree after Leg 3a (landed, uncommitted).
- **The editors and glues:** `static/js/areas/studio/{knowledge-create,knowledge-detail,knowledge-glue,secret-editor,secret-glue,studio-route,library-pane}.js`.
- **The templates:** `provider-editor-controller.js`, `provider-editor-fill.js`,
  `provider-editor-follow.js`, `provider-kinds.js`, `gleepglorp-kinds.js`
  (`registerLibraryKind`), `agent-kinds.js` (the focus hooks), the two shared cores, and
  `static/index.html`.

## Outputs

- **New:** `static/js/areas/studio/knowledge-editor-controller.js`,
  `knowledge-editor-fill.js`, `knowledge-editor-follow.js`, `knowledge-kinds.js`,
  `secret-editor-controller.js`, `secret-editor-fill.js`, `secret-editor-follow.js` and
  `secret-kinds.js`. Names are indicative; a controller may live inside its editor file
  (decision 1).
- **Edited:**
  - `knowledge-create.js`, `knowledge-detail.js` and `secret-editor.js`: a `saving` flag, idle
    waiters flushed when a Save ends (both success and failure), and the controller built and
    handed to the glue;
  - `knowledge-glue.js` and `secret-glue.js`: a current-controller accessor, plus
    `attach(...)` of the fill and follow modules;
  - `studio-route.js` or `library-pane.js`: the one-shot focus suppression;
  - `gleepglorp-kinds.js`: optional nav hooks in `registerLibraryKind`;
  - `static/index.html`: the script tags, the kinds after `provider-kinds.js`.
- **Tests:**
  - `tests/browser/test_flow_gleepglorp_fill_knowledge.py`,
    `test_flow_gleepglorp_follow_knowledge.py`, `test_flow_gleepglorp_fill_secret.py` and
    `test_flow_gleepglorp_follow_secret.py`, which join `gleepglorp-kinds` by glob;
  - `tests/browser/test_flow_gleepglorp_kinds.py`: the registered names, the shape table and
    the script-order pins updated (`:32-42` `_SCRIPT_ORDER_JS` gains `knowledgeKinds` /
    `secretKinds`; `:118`, `:122-123`, `:126-160`, `:179`);
  - `tests/test_gleepglorp_client_helpers.py:45-56`: the hard-coded kind and follow file tuples
    gain the new files;
  - a test that a fill during an in-flight Save waits for it, using a delayed PUT;
  - **lane budget:** `gleepglorp-kinds` grows by four files, and its provisional 210 s budget is
    re-measured at the closing gate (Leg 7).
- **`docs/ui-testid-registry.md`:** the new note testids (`kb-filled-note`,
  `secret-filled-note`, `kb-approved-change-note`, `secret-approved-change-note`, or
  whichever names are chosen).
- **Docs:** `the_one/agents.md` ("GleepGlorp client kinds registry" / "Shared fill and follow
  helpers" gain the two kinds) and the guide topics only if their wording must change.

## Acceptance Criteria

- [ ] **AC1. Registration.**
  - `App.gleepglorpKinds.names()` is `['agent', 'rule', 'routine', 'mcp_server', 'provider',
    'knowledge_base', 'secret']`, the same order as the server `REGISTRY`.
  - Both kinds register through `registerLibraryKind`: `section` `knowledge` / `secrets`,
    `store` `knowledge-bases` / `secrets`, and the nouns.
  - The `test_flow_gleepglorp_kinds.py` pins are updated.
  - A unit test (`tests/test_gleepglorp_client_helpers.py`) asserts that the client
    registration order in `index.html` matches `kinds.KINDS` (DD13).
- [ ] **AC2. Knowledge-base fill, create.** From the drawer, a `knowledge_base` create fill:
  - navigates to `#library/knowledge/~new`, and **focus stays in the drawer composer**;
  - writes the name and description as unsaved edits, with a per-field note under each that
    links through `aria-describedby`;
  - leaves the form dirty with its unsaved caption, and nothing is stored until Create;
  - the receipt reads "filled".
- [ ] **AC3. Knowledge-base fill, change.** On an existing base:
  - a change fill writes only the named fields, as unsaved edits, with notes;
  - a field the operator changed and hasn't saved is kept and reported as `kept`;
  - **same-route-with-dirty-state:** the drawer fill on the same base while it is dirty keeps
    the operator's field;
  - **other-route-with-dirty-state:** a fill for another base while this one is dirty raises
    the leave guard, and Stay gives `not_filled` with "you kept your unsaved edits".
- [ ] **AC4. Knowledge-base follow.** An approved `knowledge_base` change, recorded through
  `App.approvals.record`, as the follow tests' `_signal` does:
  - **a clean editor:** the stored values and the title or subtitle update, with a follow note
    under each changed field;
  - **a dirty editor:** the operator's values are kept, their baseline moves, the notes show,
    and Save then writes the operator's values;
  - **store:** `knowledge-bases` is invalidated, and the Library list shows a rename;
  - **another base, or a create form open:** ignored.
- [ ] **AC5. Secret fill, create.** A `secret` create fill navigates to
  `#library/secrets/~new` and writes:
  - **name and description,** each with a per-field note;
  - **row 0's key,** which follows the filled name's slug as typing does (unless the operator
    already typed a key);
  - **the allowed-tools chips,** with one note under them, "Filled by GleepGlorp: added X, Y."
    (DD14 choice 1).

  Under the values table, the note reads "Enter the value for {key}, then Create." (DD14
  choice 4), where `{key}` is row 0's actual key. **No value input is ever written by the
  fill:** the test asserts it is still empty. Nothing is stored until Create.
- [ ] **AC6. Secret fill, change.** On an existing secret:
  - a change fill writes `name`, `description` and `allowed_tools`;
  - the chips note names only the tools added against the baseline;
  - masked values and the key table are untouched (the test asserts each row still shows its
    masked value);
  - an operator-changed field is kept;
  - the two dirty-state navigation tests pass, as in AC3.
- [ ] **AC7. Secret follow.** An approved `secret` change:
  - **a clean editor:** the name, description and chips update, with per-field follow notes;
  - **a dirty editor:** the operator's edits are kept;
  - **the values table** is never rebased or re-read;
  - **store and route:** `secrets` is invalidated, and the router's name is synced on a rename,
    as the glue's `onSaveSuccess` does.
- [ ] **AC8. No regression.** These lanes pass with their assertion lines unedited, each run
  alone:
  - `knowledge` and `library` (the existing KB and secret editor tests, including the leave
    guard tests at `test_flow_studio_secrets.py:411-502`);
  - `agents` (the KB attach tests);
  - `gleepglorp-chat`, `gleepglorp-fill` (apart from the `test_flow_gleepglorp_kinds.py` pins)
    and `gleepglorp-kinds`.
- [ ] **AC9. Guards.**
  - The static guards pass: `tests/test_ui_guards.py` (the testid registry, both directions),
    `tests/test_token_definitions.py`, `tests/test_design_tokens_a11y.py`,
    `tests/test_ui_ownership.py`, `tests/test_area_module_size.py` (every file ≤ 800 lines, with
    no `ALLOWANCE` entry) and `tests/test_store_static.py`.
  - `THE_ONE_TEST_NETNS=1 make test-unit` passes.
- [ ] **AC10. Docs** (Outputs) are updated.

## Verification Steps

- **AC1-AC7:** the new browser files, run with `-m browser`, then the whole
  `gleepglorp-kinds` lane. Report, for each safety-relevant test, whether it was falsified:
  - the value input stays empty;
  - the masked rows are untouched;
  - the kept-field case;
  - the dirty follow;
  - the leave-guard Stay.
- **AC8:** each lane alone, one at a time. `git diff -- tests/browser/` shows only the new
  files and the `test_flow_gleepglorp_kinds.py` pins.
- **AC9:** run the guards, then the unit tier in the background.
- **AC10:** quote the docs.

## Implementation Guidance

1. **Read the templates:**
   - `provider-editor-controller.js` (how a controller is built from an editor's closure and
     handed to `providerEditorFill.create(ctl)`);
   - `provider-editor-fill.js` / `-follow.js` on the cores;
   - `provider-kinds.js` and `registerLibraryKind`;
   - `agent-kinds.js` `beforeNavigate` / `afterNavigate` (the focus);
   - the four MCP and provider fill and follow browser test files and their helpers
     (`test_flow_gleepglorp_fill.py` `_bworld`, `_seed_b`, `_deliver`, `_wait_status`;
     `seeders.seed_gleepglorp_fill` / `seed_gleepglorp_proposal`; the follow tests' `_signal`
     and `_approve_proposal`).

2. **Saving and idle waiters** in all three editors.
   - A `saving` flag is set where `shell.setBusy(true)` starts a Save, and cleared on both
     paths.
   - Idle waiters run when the flag clears.
   - On a KB create success, the shell stays busy and the glue navigates away. The controller
     then dies with the mount; flush or drop its waiters on destroy.

3. **Knowledge-base controller** (create and edit modes).
   - `values()` / `baseline()` are `{name, description}`; a create's baseline is
     `{name: '', description: ''}`.
   - `setField` sets the input's value silently, then does what the input handler does: clears
     `nameField.setError(null)` and `shell.setError('')`, refreshes the create hint, and calls
     `checkDirty`.
   - `placeNote` uses `nameField.el` / `descField.el` and returns `[input]`.
   - `rebase(row)` (edit): updates `stored`, the snapshot and the title or subtitle. Clean
     fields take the row's value; dirty ones keep theirs. Then `checkDirty`.
   - `ready()` is true once mounted. `el` is the shell root.
   - Build it in both forms and report it to `knowledge-glue.js`, which keeps `current` for the
     fill and follow `attach`. The detail mount is async: report the controller when it
     actually mounts.

4. **Secret controller.**
   - `values()` / `baseline()` are `{name, description, allowed_tools}`, read from the editor
     (`tools` is `allowed_tools`).
   - **`setField('name', v)`** sets the input and clears `nameField.setError(null)`. Then, on a
     create while `!keyTouched()` and row 0 exists, it runs `kv.setRow(0, {key: slug(v)})`, as
     the input handler does. The editor's env exposes `keyTouched()` (or the slug rule as one
     function), so the rule is not re-implemented. Then `recomputeDirty()`.
   - `setField('description', v)`: the input, then `descField.setError(null)`, then
     `recomputeDirty()`.
   - **`setField('allowed_tools', list)`:**
     - `chips.setValues(list)`, then `toolsField.setError(null)`, `chips.setError(false)` and
       `recomputeDirty()`;
     - `setValues` and `kv.setRow` fire no `onChange`, so the explicit recompute is required.
   - **`rebase(row)` needs the editor's internals exposed by its env:** a snapshot getter and
     setter (a JSON string holding rows and tools) and a `stored` setter.
     - It parses the snapshot and replaces `name`, `description` and `tools` only.
     - It updates `stored.name`, `.description` and `.allowed_tools`, keeping `stored.values`,
       so Cancel never rewrites the key table from the fetched row.
     - Then `shell.setTitle`.
   - **Notes:**
     - `placeNote` hosts name and description in their field elements, and `allowed_tools` in
       `toolsField.el` with controls `[chips.input]`;
     - `placeTableNote` uses `values.el` with controls `[kv table]`;
     - a `firstKey()` helper reads row 0's key for the handoff note.
   - `rebase(row)` covers metadata only, never `kv`.

5. **Fill modules** on `App.gleepglorpFill.module({routeIs: libraryRoute('knowledge' |
   'secrets')})`, `prepare` (the allowlists: KB `name`, `description`; secret `name`,
   `description`, `allowed_tools`), `writer` and `notes(ctl, {testid, skipIfUnchanged: true})`.
   - **Secret notes on a create fill:**
     - per-field notes for name and description;
     - the chips note: "Filled by GleepGlorp: added X, Y." with the tools added against the
       baseline, as a per-field note on `allowed_tools`;
     - the table note: "Enter the value for {firstKey}, then Create.", shown while row 0's
       value is empty.
   - **Secret notes on a change fill:** the same, without the table note.
   - **What the operator changed is kept:** use `operatorScalar` for scalars. For
     `allowed_tools`, compare the ordered list (`same()`) against the baseline and against what a
     fill wrote. The "added" note compares as sets, so a reorder isn't reported as an add.
   - **The glue clears `current`** on teardown and on an unmounted or failed detail, so a stale
     controller is never returned.

6. **Follow modules** on `App.gleepglorpFollow.listen('knowledge_base' | 'secret', …)` and
   `refetchThen(ctl, '/api/knowledge-bases/'+id | '/api/secrets/'+id, …)`, then
   `ctl.rebase(row)`.
   - Per-field notes through `buildNote(detail, {testid, field})` for each changed field shown.
   - `reload` of the store; the secret's router sync on a rename (reuse the glue's code path).
   - Ignore a create form, another target, or a controller that isn't alive.

7. **Registration** (`knowledge-kinds.js`, `secret-kinds.js`) via `registerLibraryKind`. Extend
   it with optional `beforeNavigate` / `afterNavigate`, keeping the MCP and provider specs
   byte-identical: their no-op defaults stay.
   - The KB kind's `beforeNavigate` sets a one-shot flag that `_focusKbCreate` (or its caller in
     `studio-route.js`) checks and clears, so a fill navigation to `knowledge/~new` leaves
     focus in the composer.
   - Add the script tags after `provider-kinds.js`, with each controller, fill and follow file
     before its kinds file.

8. **The testid registry** (`docs/ui-testid-registry.md`): add every new testid, written as an
   extractable literal (the Leg 2 lesson).

9. **Tests.** Model the four new files on the MCP and provider ones. Each UI-navigation test
   includes **same-route-with-dirty-state** and **other-route-with-dirty-state**. If any new
   container keyboard handler is added (none is expected), add **click-inside-then-key**.

10. **Run:**
    - the guards;
    - `make test-unit` (in the background);
    - each lane alone: `gleepglorp-kinds`, `gleepglorp-fill`, `gleepglorp-chat`, `knowledge`,
      `library` and `agents`.

    Update the flight log, mark the leg `landed`, and signal `[LAND:leg]`.

## Edge Cases

- **A fill while a Save is in flight:** `whenSettled` waits for `saving()` to clear, through
  the new flag.
- **A KB create fill while the create form is already open and dirty:** this is the same route,
  so the fill writes fields the operator hasn't changed and keeps the rest.
- **A secret create fill whose name slug collides with an existing key:** the server refuses it
  on Create, as for typing, and the fill doesn't check.
- **A secret change fill that removes tools:** the chips show the new list, and the note names
  only the added ones. If nothing was added, there is no chips note, but the field still holds
  the written value.
- **A follow for a secret while a value row is being edited:** the values table is untouched,
  and the follow rebases only the metadata.
- **The KB edit form's async mount:** a follow that arrives before the controller exists is
  ignored, and the mount reads fresh data anyway.
- **`afterNavigate` on a failed navigation** (the leave guard's Stay) clears the one-shot focus
  flag. The drawer already calls it on every path.
- **A fill arriving between a KB Create success and the glue's replace-navigation** waits on
  the busy `create` controller and times out as `editor_unavailable`. That is rare and
  accepted. The controller's `saving()` stays true until it is destroyed. No fill assumes the
  create editor survives Create, because the receipt is posted at apply time.
- **The guide.** `guide/knowledge-bases.md` and `secrets.md` changed in Leg 3a. Re-read them
  once the fill lands, and fix any wording about "unsaved edits" that the client now contradicts.

## Files Affected

- `static/js/areas/studio/knowledge-create.js`, `knowledge-detail.js`, `knowledge-glue.js`,
  `secret-editor.js`, `secret-glue.js`, `studio-route.js` (or `library-pane.js`)
- `static/js/areas/studio/{knowledge,secret}-editor-{controller,fill,follow}.js`,
  `{knowledge,secret}-kinds.js` (new)
- `static/js/gleepglorp-kinds.js` (the optional nav hooks)
- `static/index.html`
- `tests/browser/test_flow_gleepglorp_{fill,follow}_{knowledge,secret}.py` (new);
  `tests/browser/test_flow_gleepglorp_kinds.py` (the pins); `tests/test_gleepglorp_client_helpers.py`
  (the order test)
- `docs/ui-testid-registry.md`, `the_one/agents.md`
- **Registries and pins checked:**
  - the client registry order;
  - the testid registry;
  - `ALLOWANCE`;
  - the `gleepglorp-kinds` glob (new files join with no script edit).

## Citation Audit

From the FD's editor survey against the tree after Leg 3a (2026-11-23). File:line are under
`static/js/`.

- `areas/shared/gleepglorp-fill-core.js:61-113` `module`; `:44-53` `libraryRoute`; `:115-132`
  `prepare`; `:134-201` `notes`; `:203-223` `writer` - verified (survey)
- `areas/shared/gleepglorp-follow-core.js:29-79` `buildNote`, `matches`, `listen`, `refetchThen`
  - verified (survey)
- `gleepglorp-kinds.js:58-105` `registerLibraryKind` (no-op nav hooks at `:99-101`) - verified (survey)
- `areas/studio/knowledge-create.js:66-109` fields and error; `:116-123` dirty; `:125-162` submit
  (busy only) - verified (survey)
- `areas/studio/knowledge-detail.js:60` `stored`; `:128-140` `readValues` and snapshot; `:160-214`
  Save - verified (survey)
- `areas/studio/knowledge-glue.js:81-115` handle keys; `:234-262` the async detail mount; `:386`
  `isOpen` - verified (survey)
- `areas/studio/studio-route.js:221-231/:378` and `library-pane.js:421-425`, the create autofocus
  - verified (survey)
- `areas/studio/secret-editor.js:36-45` `slug` and `rowsFrom`; `:67-77` the name-to-key follow;
  `:92-143` the kv table, chips and `toolsField`; `:163-172` `readValues`; `:224-236` the shell;
  `:359-403` `performSave` (busy only) - verified (survey)
- `areas/studio/secret-glue.js:61-65` form keys; `:111-123` `onSaveSuccess` (`router.sync` with
  `{name}`) - verified (survey)
- `approvals.js:55-88` `record` returns false for an unregistered kind - verified (survey)
- `router.js:89/:92` sections `knowledge` and `secrets`; `:513-516` item collections - verified
  (survey)
- `tests/browser/test_flow_gleepglorp_kinds.py:118/:122/:126-160/:179` registry pins - verified
  (survey)
