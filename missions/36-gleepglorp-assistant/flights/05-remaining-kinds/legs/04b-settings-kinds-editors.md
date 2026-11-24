# Leg: 04b-settings-kinds-editors

**Status**: completed
**Flight**: [The remaining kinds](../flight.md)

## Objective

The Built-in tools editor, the Tools grid, the Knowledge indexing page and the Date and time page
gain their GleepGlorp client side, built on Leg 2's shared fill and follow cores. The two Leg 4a
kinds, `tool_config` and `app_settings`, register in `App.gleepglorpKinds`. As a result:
- a fill from the drawer opens the tool's editor, or Knowledge indexing, and fills it as unsaved
  edits;
- an approved proposal updates an open editor without silently overwriting unsaved edits;
- an approved on/off change flips that tool's toggle on an open Tools grid, with the follow note;
- an approved time-zone change re-renders an open Date and time page with the follow note, and
  moves the app's own clock (`App.time`) in **every** open window, whatever page it shows;
- the notes appear in the operator-approved placements (DD14).

## Context

- **Flight decisions:** DD4 (the cores), DD7 (tool configs), DD8 (app settings), DD9 (follow),
  DD13 (pins and UI test patterns), DD14 (layouts: choice 2 per-field notes, choice 3 Date and
  time follow note, choice 5 Tools grid follow note).
- **Designed after Leg 4a landed** (uncommitted; the server kinds, their views and their
  `config_changed` events). From Leg 4a:
  - `tool_config`: `target_id` = the built-in tool's name, `target_key` `tool_config:{name}`;
    fields are the settable names (`enabled` plus the DD7 allowlist, per tool); a fill's `values`
    use the same names. Built-in tools are never deleted, so the server's `exists` is a fixed
    name check.
  - `app_settings`: `target_id` = the page key `date-and-time` or `knowledge-indexing` (the page
    key is the route section, DD8); one page per proposal. The Date and time fields are
    `fill_refused` on the server, so **no fill view ever targets `date-and-time`**; only
    Knowledge indexing is fillable. A `time_zone` change in `system` mode also stores
    `time_zone_mode: "zone"` (`kinds/app_settings.py:203-205`), so the event's `fields` carry
    both.
  - `config_changed` reaches every open window: `proposals/apply.py:224-241` broadcasts to every
    socket, and each window's socket (opened at load on every page,
    `gleepglorp-drawer/chat.js:3-5`) feeds `App.approvals.record`
    (`areas/chat/window-frames.js:46-51`), de-duplicated by proposal id.
- **What each surface lacks** (FD survey, `static/js/areas/admin/` unless noted):
  - **`tools-editor.js`** (536 lines): `renderToolsEditor` returns only `{setEnabled, destroy}`
    (`:526-534`); everything else is closure-private (`handles[f]`, `enabledToggle` at `:206`,
    `baseline`, `snapshot()` `:152-158`, `checkDirty()` `:160-168`, the `saving` /
    `previewing` / `testing` flags). Field handles (`shared/tool-config-fields.js:11-20,
    258-282`) have `setValue`, which fires no events, so the editor must run `checkDirty()` and
    `showIfCtl.apply()` itself after it. Every allowlisted numeric field renders as a `<select>`
    (`ui_hint: dropdown`); a value outside the choices is appended as "(custom)"
    (`tool-config-fields.js:246-259`). `search_backend` is a string select; `searxng_base_url`
    and `google_pse_cse_id` are text inputs hidden by `show_if` unless their backend is chosen.
  - **`tools-page.js`** (553 lines): mounts the editor after `GET /api/tools/configs/{name}`
    (`selectTool` `:317-352`, `mountToolItem` `:254-312`). Its `refresh()` (`:481-487`)
    **re-mounts the editor** and would lose unsaved edits, so a follow must not use it. It
    holds `toolConfigs` (the grid's list) and `editingTool`; the `onSaved` branch
    (`:262-282`) is the model for updating them after a change.
  - **`tools-grid.js`** (290 lines) over `App.ui.toolTile` (`static/js/ui/tile.js:349-440`): a
    tile has no note slot. Toggles save on choice (`tools-page.js:handleToolToggle`
    `:354-397`, `applyToggle` `:399-440`), with `toolsInFlight[name]` set while a toggle's PUT
    runs.
  - **`knowledge-settings-page.js`** (450 lines): returns only `{destroy}`. Its page field names
    differ from the kind's (`size_chars` / `chunk_size_chars`, `overlap_chars` /
    `chunk_overlap_chars`; `watch_enabled` and `reconcile_interval_seconds` match).
    `revalidate()` (`:250-268`) recomputes validity, dirty and the guard after any write. The
    first `GET` is in flight at mount; a failed load disables the inputs.
  - **`date-time-page.js`** (570 lines): returns nothing; `reload()` (`:340-348`) and the page's
    own `applySettings(r, {external: true})` are closure-private. It saves on choice and has no
    dirty state. `test_flow_settings_date_time.py:346` calls `App.admin.renderDateTimePage(d)`
    directly, so the call shape must keep working.
  - **`App.time.applySettings`** (`static/js/time.js:190-192`) is called only at boot
    (`app.js:216`) and by the Date and time page, so today an approved zone change reaches no
    other window until a reload.
- **Traps found by the survey:**
  - `App.gleepglorpFollow.listen(kind, fn)` registers **once per kind per page**; a second call
    for the same kind is a silent no-op (`gleepglorp-follow-core.js:60-64`). So the tools editor
    and the Tools grid share one `tool_config` registration, and Knowledge indexing and Date and
    time share one `app_settings` registration.
  - `registerLibraryKind` hard-codes the Library route, so both kinds use plain
    `App.gleepglorpKinds.register(...)`, as `agent-kinds.js` does.
  - `recordKey` returning null drops the event (`approvals.js:60-62`), so both kinds return
    `{scope: 'target', id: detail.target_id}`.
  - `whenSettled` resolves false at once if the active fill's `ctl.ready()` is false
    (`gleepglorp-fill-core.js:81-110`), so a controller is attached only once its editor has
    loaded, and `ready()` is false only after a failed load.
  - `tests/test_gleepglorp_client_helpers.py` reads kind files from `areas/studio/` only, and
    `kinds.KINDS[-0:]` is the whole tuple, so emptying `_PENDING_CLIENT_KINDS` needs the
    assertions rewritten, not just the tuple emptied.

## Design decisions (this leg)

1. **Controllers in their own files,** on the `secret-editor-controller.js` model, so the editor
   files stay small: `tools-editor-controller.js` and `knowledge-settings-controller.js`, built by
   their editors and exposed through a current-controller accessor on the page owner
   (`tools-page.js`; the Knowledge page through `admin.js` or the page's own module). Each has the
   surface the cores use: `key`, `id`, `el`, `alive()`, `ready()`, `saving()`, `onIdle(fn)`,
   `checkDirty()`, `changed()`, `isDirty()`, `values()`, `baseline()`, `setField(k, v)`,
   `placeNote(k, el)`, `addFollowNotes(detail, fields)`, `clearNotes()`, `rebase(row)`, `fill`,
   `destroy()`.
   - **Keys:** `edit:{toolName}` and `edit:knowledge-indexing`, which `core.prepare` forms from
     `view.target_id` unchanged.
   - **`setField`** writes silently, then runs the editor's own recompute: `checkDirty()` and
     `showIfCtl.apply()` for the tools editor, `revalidate()` for Knowledge indexing. It maps the
     kind's names to the page's (`chunk_size_chars` → the size input, and so on) and `enabled` to
     the editor's Enabled switch (not a field handle).
   - **`ready()`:** true once the editor has its data; the Knowledge controller reports false
     after a failed load, so a fill returns `editor_unavailable` at once rather than waiting.
     The accessor returns null while the first load is still in flight.
2. **The tools editor's busy states.** The controller's busy test is
   `saving || previewing || testing || confirming`, where `confirming` is a new local flag set
   just before `App.confirmDialog` ("Saving narrows N agents") and cleared in both its
   `onConfirm` and `onCancel` (both fire from `modal.onClose`, `ui/dialog.js:84-92`, Escape
   included). In `onConfirm` it is cleared and `doSave` runs at once (it sets `saving`
   synchronously, so there is no idle gap); if the editor is no longer alive or current the flag
   is never left set. `onIdle` waiters are flushed at **every** site that ends one of the four
   states (the save, preview and test paths and the dialog's Cancel), not only the save path.
   - **What this reaches:** the drawer refuses a fill outright while any modal is open
     (`gleepglorp-drawer/fill.js` `process`, `App.ui.modal.anyOpen()` → `not_filled` / `stay`).
     So `confirming` matters for a fill already waiting (`whenSettled`) when the dialog opens,
     and for a follow (`refetchThen` waits on `onIdle`).
3. **The tools editor fill.**
   - It writes `search_backend` first, then runs `showIfCtl.apply()`, so a fill that sets the
     backend and its URL or CSE id in one go writes a visible field with its note.
   - **A dependent field whose row stays hidden** (`searxng_base_url` or `google_pse_cse_id`
     while the backend is something else) **is written into its handle anyway, with no note**
     (`placeNote` returns null for a hidden row). This is the honest option the core offers:
     `snapshot()` (`tools-editor.js:143-149`) includes every handle whatever its visibility, so
     the value is part of the unsaved edit and of Save; the receipt's "filled" is then true; and
     switching the backend later reveals the value. `keep()` is **not** used for it, because the
     receipt's partly-filled sentence says the operator changed the field
     (`areas/chat/fill-receipts.js:215-217`). (Design review, cycle 1.)
   - A numeric value outside a select's choices is written as the select's "(custom)" option,
     as an operator-typed custom value is today.
   - `enabled` fills the editor's Enabled switch (DD7); the grid toggle is never a fill target.
4. **One `tool_config` follow module** (`tool-config-follow.js`) registers once and, for an
   event on a tool:
   - re-fetches `GET /api/tools/configs/{name}` once (through `refetchThen` when that tool's
     editor is open, so it waits for an in-flight Save; a plain fetch otherwise);
   - updates the page's `toolConfigs[i]` and `editingTool`, and re-renders the grid, as the
     `onSaved` branch does;
   - **the editor**, when that tool's is open: `controller.rebase(row)` (a clean field takes the
     stored value; a dirty one keeps the operator's value while the baseline moves, the 3b rule),
     then per-field follow notes;
   - **the grid** (DD14 choice 5), when `enabled` is among the fields and the Tools page is
     showing: the tile's toggle shows the stored value, and the follow note sits in that tool's
     tile, linked to the toggle through `aria-describedby`. A tile whose own toggle PUT is in
     flight (`toolsInFlight[name]`) is skipped. The note clears on the operator's next toggle of
     that tile, on a newer approval for that tool, or when the grid is rebuilt.
   - It never calls `tools-page.refresh()`.
   - Off the Tools page it does nothing beyond what `approvals.record` already does
     (invalidating the kind's `store`).
5. **The grid note is a host child of the tile,** not a library change. The grid
   (`tools-grid.js`, through a per-tile setter it exposes to the page) appends the follow core's
   note node as the tile's last child (`tile.el`) and removes it when cleared; its
   `aria-describedby` link to the toggle goes through `App.gleepglorpFill.link` / `unlink`.
   - **Why not `toolTile.setNote`:** host children under a tile's `el` are an existing,
     contracted pattern (`tests/browser/test_ui_tile_contract.py:915-936`, group tiles); the
     ownership guard does not forbid appending a core-built node; and a new method would break
     the exact-API assertion at `test_ui_tile_contract.py:696-705`. (Design review, cycle 1.)
   - The tile is a card in a multi-column grid, so "under that tool's row" in the approved mockup
     is "at the foot of that tool's card". **No new placement:** this is DD14 choice 5 in the
     grid's actual layout.
   - The grid's reconcile keeps tiles it already has (`syncChildren`), so the note survives a
     re-render of the same tile; the follow re-places or clears it as decision 4 says.
5a. **The notes are styled in the admin area.** The fill and follow note rules
   (`.agent-filled-note`, `.agent-approved-change-note`, `css/studio.css:1275-1299`) are scoped to
   `.area-studio`; every surface here mounts under `.area-admin` (`app.js:158-171`). Without a
   change they render as unstyled paragraphs. The Developer either widens those selectors to
   cover `.area-admin` in place (if `studio.css` loads on every page) or adds the same rules to
   `css/admin.css`, plus a small padding rule for the note at the foot of a tool card. No
   duplicated rule set if widening works. (Design review, cycle 1.)
6. **One `app_settings` follow registration** in a small always-loaded module
   (`areas/shared/app-settings-follow.js`, after `gleepglorp-follow-core.js`), dispatching on
   `target_id`:
   - **`date-and-time`, in every window:** `GET /api/time-settings`, then
     `App.time.applySettings(r)`; then, if the Date and time page is mounted, its handle patches
     the page from `r` (the existing `external: true` path, so the list re-centres) and shows the
     follow note (DD14 choice 3). One fetch per event.
   - **`knowledge-indexing`:** hands the event to the Knowledge indexing follow, which re-fetches
     `GET /api/knowledge-settings` through `refetchThen`, rebases (clean fields take the stored
     value; dirty ones keep the operator's value, and the baseline moves) and shows per-field
     follow notes. The read-only facts refresh too.
   - The Knowledge follow and the Date page register handlers with this module; neither calls
     `listen('app_settings', ...)` itself.
7. **The Date and time page handle.** `renderDateTimePage(container)` keeps its call shape and
   returns `{destroy}` as today's General renderer expects (`areas/admin.js:204-232`). On mount
   the page registers a `followed(r, detail)` handler for `date-and-time` with the shared
   dispatcher (decision 6) and deregisters it in `destroy`; the Knowledge indexing follow
   registers for `knowledge-indexing` the same way. One mechanism for both pages. `followed`
   patches the page and places the follow note after the zone radio group, linked to the mode
   radios and the search input. The note clears on the operator's next choice on the page or on
   re-mount.
8. **The kind specs.**
   - **`tool_config`** (`areas/admin/tool-config-kinds.js`): `labels` (item noun "built-in
     tool", `editorUnavailable` "The tool editor could not open.", `targetGone` "That built-in
     tool no longer exists."); `store: 'agents'`, with a comment saying why: the grid and editor
     don't read it, but turning a tool on or off changes what agents can use, and the editor's
     own Save invalidates `agents` for the same reason (`tools-page.js:263/407`); `recordKey` → `{scope: 'target', id: target_id}`; `openLink` →
     `{destination: 'settings', section: 'tools', id: target_id}`; `fill` with
     `routeFor` = that spec, `openKey` = `'edit:' + target_id`, `exists` → `Promise.resolve(true)`
     (built-in tools are never removed), `routeIs` matching `settings/tools/{name}` with the
     segment URI-decoded, `select` and the nav hooks no-ops.
   - **`app_settings`** (`areas/admin/app-settings-kinds.js`): `labels` (item noun "settings
     page", `editorUnavailable` "The settings page could not open.", `targetGone` "That settings
     page no longer exists."); `store: null`; `recordKey` as above; `openLink` →
     `{destination: 'settings', section: target_id}`; `fill` for `knowledge-indexing` only
     (`routeFor` `{destination: 'settings', section: 'knowledge-indexing'}`, `openKey`
     `'edit:knowledge-indexing'`, `exists` → `Promise.resolve(true)`).
   - Both file names end in `-kinds.js`, are loaded after `secret-kinds.js`, `tool_config` first,
     and contain `register('tool_config'` / `register('app_settings'` literally (the order test
     reads them).
9. **Note testids** (indicative; the registry rows follow the names chosen):
   `tool-filled-note`, `tool-approved-change-note`, `tool-grid-approved-change-note`,
   `knowledge-settings-filled-note`, `knowledge-settings-approved-change-note`,
   `date-time-approved-change-note`.
10. **Direct saves still push nothing to other windows** (DD9's known gap, unchanged).

## Inputs

- The tree after Leg 4a (landed, uncommitted).
- **The surfaces:** `static/js/areas/admin/{tools-editor,tools-page,tools-grid,knowledge-settings-page,date-time-page}.js`,
  `static/js/areas/admin.js`, `static/js/areas/shared/tool-config-fields.js` (read only; not
  changed), `static/js/ui/tile.js` (read only), `static/js/time.js`, `static/js/app.js`,
  `static/css/studio.css`, `static/css/admin.css`.
- **The templates:** `areas/studio/secret-editor-{controller,fill,follow}.js`, `secret-glue.js`,
  `agent-kinds.js`, `gleepglorp-kinds.js`, the two shared cores, `approvals.js`,
  `gleepglorp-drawer/fill.js` and `static/index.html`.
- The FD survey: session scratchpad `leg4b-survey.md` (cited sections are summarised above).

## Outputs

- **New** (names indicative): `static/js/areas/admin/tools-editor-controller.js`,
  `tool-config-fill.js`, `tool-config-follow.js`, `tool-config-kinds.js`,
  `knowledge-settings-controller.js`, `knowledge-settings-fill.js`,
  `knowledge-settings-follow.js`, `app-settings-kinds.js`;
  `static/js/areas/shared/app-settings-follow.js`.
- **Edited:**
  - `tools-editor.js`: the `confirming` flag, idle waiters, the controller built and returned;
  - `tools-page.js`: the current-controller accessor, the follow hook that updates
    `toolConfigs` / `editingTool` and the grid, and `attach(...)` of the fill and follow;
  - `tools-grid.js`: a per-tile note setter (append or remove the core's note under `tile.el`);
  - `knowledge-settings-page.js`: the controller, a rebase, the dispatcher registration;
  - `date-time-page.js`: the dispatcher registration and the follow note;
  - `areas/admin.js`: only if the handles need wiring through it;
  - `static/css/studio.css` or `static/css/admin.css`: the note rules for `.area-admin`
    (decision 5a);
  - `static/index.html`: the script tags (fill, follow and controller before each editor; the
    shared app-settings follow right after `gleepglorp-follow-core.js`; the two kinds files
    after `secret-kinds.js`, `tool_config` first).
- **Tests:**
  - `tests/browser/test_flow_gleepglorp_fill_tool_config.py`,
    `test_flow_gleepglorp_follow_tool_config.py`, `test_flow_gleepglorp_fill_app_settings.py`,
    `test_flow_gleepglorp_follow_app_settings.py` (join `gleepglorp-kinds` by glob);
  - `tests/browser/test_flow_gleepglorp_kinds.py`: `_SCRIPT_ORDER_JS` (`:30-42`) and the order
    assert (`:133-136`), the names (`:120-127`), the shape table (`:138-160`) and the stub-kind
    names (`:188-206`);
  - `tests/test_gleepglorp_client_helpers.py`:
    - `_PENDING_CLIENT_KINDS` (`:56`) removed;
    - the `scripts == [...]` pin (`:68-74`) gains `tool-config-kinds`, `app-settings-kinds`;
    - the file read (`:78-79`, `_src(STUDIO / ...)`) finds the kind file under any
      `areas/<area>/`;
    - the assertions (`:81-84`) become `tuple(registered) == kinds.KINDS`;
    - the fill-scaffolding tuple (`:33-47`) gains the two new fill modules, read from
      `areas/admin/`;
    - the follow-listener tuple (`:90-100`) gains only `tool-config-follow.js` and
      `shared/app-settings-follow.js` (the modules that call `listen`); the Knowledge follow and
      the Date page register with the dispatcher instead;
    - the library-builder tuple (`:50-53`) is unchanged: the new kinds use plain `register`;
    - AC10's "exactly one `listen` per kind" scan is a new test.
  - `tests/browser/seeders.py` (`seed_gleepglorp_fill`, `:643`): only if needed, a compatible
    `target_key` override, because the seeder falls back to `f"{kind}:{agent_name}"` for kinds
    without `resolve_target` (both new kinds), so two seeds in one test would share
    `tool_config:plain`. Either that override, or the new tests pass `agent_name=` the tool name
    or page key. Seed `changes` with the kind's field names (the view's `values` come from them).
- **Registries:** `docs/ui-testid-registry.md` (the note testids). No control-inventory change
  (decision 5).
- **Docs:** `the_one/agents.md` (the client kinds registry and shared helpers sections gain the
  two kinds, the shared `app_settings` dispatcher and the "once per kind" trap); the guide only
  if its wording must change.

## Acceptance Criteria

- [ ] **AC1. Registration.**
  - `App.gleepglorpKinds.names()` is `['agent', 'rule', 'routine', 'mcp_server', 'provider',
    'knowledge_base', 'secret', 'tool_config', 'app_settings']`, the server `REGISTRY` order.
  - `_PENDING_CLIENT_KINDS` is gone and the order test asserts the full `kinds.KINDS` against
    the script tags in `index.html`, reading kind files from any area.
  - The `test_flow_gleepglorp_kinds.py` pins are updated; the shape table has rows for both new
    kinds.
  - Both kinds' `recordKey` returns `{scope: 'target', id}`, so `App.approvals.record` returns
    true for a detail of each.
- [ ] **AC2. Tool config fill.** From the drawer, a `tool_config` fill for a tool:
  - navigates to `#settings/tools/{name}` (through `_nav`), and focus stays in the drawer
    composer;
  - writes only the named fields as unsaved edits, each with a per-field note linked through
    `aria-describedby`; `enabled` fills the Enabled switch;
  - a fill that sets `search_backend` to `searxng` and `searxng_base_url` in one go leaves the URL
    row visible and filled, with its note; a URL fill while the backend stays non-SearXNG stores
    the value in the hidden field's handle with no note, the receipt reads "filled", and choosing
    SearXNG afterwards shows the filled URL;
  - a numeric value outside the choices shows as the "(custom)" option;
  - leaves the editor dirty with its unsaved caption; nothing is stored until Save, and Save runs
    the impact dialog as today;
  - the receipt reads "filled" (or "partly filled" with the kept fields).
- [ ] **AC3. Tool config fill, dirty and busy.**
  - **same-route-with-dirty-state:** a fill for the open tool while it is dirty keeps the
    operator's changed field and reports it `kept`;
  - **other-route-with-dirty-state:** a fill for another tool while this editor is dirty raises
    the leave guard, and Stay gives `not_filled` with the kept-edits reason;
  - a fill that arrives while a Save's PUT is in flight waits for it (delayed PUT);
  - a fill that arrives while the "Saving narrows N agents" dialog is already open reports
    `not_filled` / `stay` (the drawer's existing modal rule);
  - a fill already waiting when that dialog opens (delay `/impact` so the fill starts during the
    preview) writes nothing until the operator chooses Save anyway or Cancel.
- [ ] **AC4. Tool config follow, editor.** An approved `tool_config` change for the open tool:
  - on a clean editor, shows the stored values with a follow note under each changed field;
  - on a dirty editor, keeps the operator's edits, moves the baseline (Save stays enabled; Cancel
    shows the approved values), and notes the changed fields;
  - for `enabled`, flips the Enabled switch the same way;
  - leaves an editor for a different tool untouched;
  - does not re-mount the editor (an unrelated unsaved edit in it survives);
  - through a real approval (`POST /api/gleepglorp/proposals/{id}/approve`), the open editor
    follows.
- [ ] **AC5. Tool config follow, grid** (DD14 choice 5). With the Tools grid showing, an
  approved `enabled` change for a tool flips that tile's toggle to the stored value and shows the
  follow note at the foot of that tile, linked to the toggle and styled as a caption (computed
  style, not unstyled body text); the note clears on the operator's next toggle of that tile. A
  non-`enabled` change puts no note on the grid.
- [ ] **AC6. Knowledge indexing fill.** A `knowledge-indexing` fill writes the named fields as
  unsaved edits with per-field notes (all four fields, the toggle included), revalidates (an
  overlap above half the size shows the page's own error and disables Save), and leaves the page
  dirty under the `admin` guard. The dirty and leave-guard cases of AC3 hold here too. A fill
  while the page's first load failed returns `editor_unavailable` without the 10 s wait.
- [ ] **AC7. Knowledge indexing follow.** As AC4 for the Knowledge indexing page: clean fields
  take the stored values with notes; dirty ones are kept with the baseline moved.
- [ ] **AC8. Date and time follow, every window.**
  - With the Date and time page open, an approved zone change re-renders it (radio, chosen zone,
    preview) and shows the follow note linked to the mode radios; the note clears on the
    operator's next choice.
  - **Second window:** with two windows of one browser context open (one on Date and time, one on
    another page), a real approval moves `App.time.zone()` in **both** windows, and
    `App.time.formatClock` of a fixed instant changes in the second. A rendered time in the second
    window that subscribes through `App.time.onChange` re-renders in the new zone: the Developer
    picks one subscriber that a test world can show (for example a chat message time,
    `areas/chat/instance.js:385`, or the System page, `system-page.js:330`) and names it. Times
    that do not subscribe are out of scope (they update on their next render, as today).
  - A `time_zone`-only change in `system` mode shows the page in "Use this zone" with the new
    zone.
- [ ] **AC9. Notes in the admin area.** Every new note (tools editor, Tools grid, Knowledge
  indexing, Date and time) is built by the shared cores, is caption-styled in the admin area
  (a computed-style check in the browser tests), and links through `aria-describedby`.
  `App.ui.toolTile` is unchanged; `tests/test_ui_control_inventory.py` and
  `tests/test_ui_ownership.py` pass, and no area module builds a hand-styled note node.
- [ ] **AC10. Registrations stay single.** Exactly one `App.gleepglorpFollow.listen` call
  exists per kind across `static/js/` (a unit test), and no follow module uses raw
  `addEventListener` (the existing helper test, widened).
- [ ] **AC11. Nothing else moves.**
  - The `settings-tools`, `settings`, `gleepglorp-fill`, `gleepglorp-chat`,
    `gleepglorp-kinds` and `contracts-controls` lanes pass, plus the lane(s) holding
    `tests/browser/test_router_items.py` and `test_lists_helper.py` (they drive the tool tiles;
    find them with `scripts/run-tests.sh --list`), each run alone. Existing test files keep their
    assertions unedited, apart from the pins listed in Outputs. The Studio Tools-tab lanes are
    not affected (`tool-config-fields.js` does not change).
  - Agent, MCP, provider, knowledge-base and secret fills and follows behave as before.
  - Every module stays under the 800-line area guard, with no `ALLOWANCE` entry.
  - `App.admin.renderDateTimePage(container)` still works when called directly.
- [ ] **AC12. Gates and docs.** `ruff check` / `ruff format --check` clean; `make test-unit`
  passes (expected skips 15 under the namespace); the testid registry and `agents.md` updated.

## Verification Steps

- **Run order (one test process at a time, `THE_ONE_TEST_NETNS=1`, through
  `scripts/run-tests.sh` with `PYTHON=.venv/bin/python`):** the new browser files first, then
  each lane in AC11 alone, then `make test-unit`. **Landing waits for all of these to finish;**
  do not land with a run still going. Never kill a slow unit run (about 8 minutes here).
- **Falsify** (edit, run, see it fail, restore by edit) and report each:
  - the dirty follow keeps the operator's value (rebase overwrites dirty fields);
  - the confirm-dialog wait (`confirming` left out of `saving()`);
  - the grid follow note (the note not placed);
  - the second-window clock (the global follow removed, leaving only the Date page's);
  - the single-registration test (a second `listen('app_settings')` added);
  - the backend-then-URL fill (`showIfCtl.apply()` after the `search_backend` write removed: the
    URL row stays hidden);
  - the admin-area note style (the CSS change removed).
- **AC9:** the inventory and ownership tests, and the computed-style checks.
- **AC11:** `git diff --stat -- tests/browser/` shows only the four new files, the
  `test_flow_gleepglorp_kinds.py` pins and, if touched, `seeders.py`.

## Implementation Guidance

- Follow the 3b modules closely; the differences are the decisions above. Read
  `secret-editor-controller.js` (`rebase` at `:127-146`) and `secret-editor-fill.js` before
  writing.
- Seed fills with the `test_flow_gleepglorp_fill.py` helpers (`_bworld`, `_seed_b`, `_deliver`,
  `_wait_status`). `_seed_b` passes `kind`, `action` and `target_id` through to
  `seed_gleepglorp_fill`; mind the `target_key` fallback described under Outputs. Signal follows with `App.approvals.record(...)` and a unique proposal id,
  plus one real approval per kind (`seed_gleepglorp_proposal` and the approve route), as
  `test_flow_gleepglorp_follow_secret.py` does.
- The second window: `other = page.context.new_page()`, as
  `test_flow_gleepglorp_drawer_chat.py:186-199` does. Pin the browser zone with
  `credentialed_context(browser, base, timezone_id=...)` and set the zone mode explicitly
  (`system` mode resolves from the host; DD8).
- Navigate through `tests/browser/_nav.py`; no raw hashes.
- **UI test patterns (DD13):** same-route-with-dirty-state and other-route-with-dirty-state are
  in AC3 and AC6. Click-inside-then-key applies only if the leg adds a container keyboard
  handler; it should not.
- The `gleepglorp-kinds` lane grows by four files; its provisional budget is re-measured at the
  closing gate (Leg 7). Do not change budgets here.

## Edge Cases

- A fill or follow for a tool whose editor is closed but whose grid is showing: the grid follows
  (for `enabled`); nothing else.
- A follow while the Tools page shows another category tab: the tile is updated; the note shows
  when its tab is shown (or is dropped with the rebuild, whichever the grid's reconcile gives;
  record which).
- Two approvals for one tool in quick succession: the second replaces the first's notes.
- An event for `date-and-time` in a window whose Date page is not mounted: only `App.time` moves.
- A failed re-fetch: dropped, as `refetchThen` does; no note.
- A fill view for `date-and-time` cannot occur (server `fill_refused`); no client path is added
  for it.
- A fill that arrives while any modal is open (the impact dialog included) is `not_filled` /
  `stay` by the drawer's existing rule; the leg does not change it.
- `App.time.setZone` returns early for an unchanged zone, so the Date page's own
  `applySettings` call and the dispatcher's are idempotent.
- The tools editor of a tool that shows no config fields (enabled only): the fill and follow
  touch only the Enabled switch.

## Files Affected

- `static/js/areas/admin/{tools-editor,tools-page,tools-grid,knowledge-settings-page,date-time-page}.js`,
  possibly `static/js/areas/admin.js`
- `static/js/areas/admin/{tools-editor-controller,tool-config-fill,tool-config-follow,tool-config-kinds,knowledge-settings-controller,knowledge-settings-fill,knowledge-settings-follow,app-settings-kinds}.js` (new)
- `static/js/areas/shared/app-settings-follow.js` (new)
- `static/css/studio.css` or `static/css/admin.css`
- `static/index.html`
- `tests/browser/test_flow_gleepglorp_{fill,follow}_{tool_config,app_settings}.py` (new);
  `tests/browser/test_flow_gleepglorp_kinds.py`; `tests/browser/seeders.py` (only if the
  `target_key` override is taken); `tests/test_gleepglorp_client_helpers.py`
- `docs/ui-testid-registry.md`, `the_one/agents.md`
- **Registries and pins checked:** the client registry order; the testid registry; the control
  inventory (unchanged); `ALLOWANCE`; the `gleepglorp-kinds` glob.

## Citation Audit

From the FD's survey of the tree after Leg 4a (2026-11-23). Paths under `static/js/`.

- `areas/admin/tools-editor.js:206` Enabled toggle; `:152-168` snapshot and `checkDirty`;
  `:419-446` Save and the impact dialog; `:508-514` `setEnabled`; `:526-534` the return —
  verified (survey; `:206` re-checked against the flight's citation)
- `areas/shared/tool-config-fields.js:246-259` the "(custom)" option; `:258-282` the handle —
  verified (survey)
- `areas/admin/tools-page.js:254-312` `mountToolItem`; `:262-282` `onSaved`; `:317-352`
  `selectTool`; `:354-440` toggle save; `:481-487` `refresh` — verified (survey)
- `ui/tile.js:349-440` `toolTile` (no note slot) — verified (survey)
- `areas/admin/knowledge-settings-page.js:230-268` snapshot and `revalidate`; `:321-338` load —
  verified (survey)
- `areas/admin/date-time-page.js:340-348` `reload`; `:374-411` save on choice; `:514-520` the
  zone section — verified (survey)
- `areas/admin.js:204-232` General renderers; `:301-305` `editorOpen`; `:330-333`
  `registerSource('admin')` — verified (survey; path corrected from `areas/admin/admin.js` at
  design review; the flight's `:301-334` holds)
- `areas/admin/tools-editor.js:143-149` snapshot covers every handle — verified (design review)
- `ui/dialog.js:84-92` `onConfirm` / `onCancel` from `modal.onClose` — verified (design review)
- `areas/chat/fill-receipts.js:215-217` the partly-filled sentence — verified (design review)
- `css/studio.css:1275-1299` note rules scoped to `.area-studio`; `app.js:158-171` area class —
  verified (design review)
- `tests/browser/test_ui_tile_contract.py:696-705` exact tile API; `:915-936` host children —
  verified (design review)
- `tests/browser/seeders.py:643` `seed_gleepglorp_fill` `target_key` fallback — verified (design
  review)
- `time.js:190-192` `applySettings`; `app.js:216` boot call — verified (survey)
- `areas/shared/gleepglorp-follow-core.js:60-64` once-per-kind `listen`;
  `gleepglorp-fill-core.js:81-110` `whenSettled`; `:126-143` `prepare` — verified (survey)
- `approvals.js:57-88` `record` (null `recordKey` drops the event) — verified (survey)
- `gleepglorp-drawer/fill.js:90-121` `process` (null fill spec → `editor_unavailable`) —
  verified (FD read)
- `the_one/gleepglorp/kinds/app_settings.py:203-205` the implicit zone mode — verified (FD read)
- `tests/test_gleepglorp_client_helpers.py:33-47/57/68-83/90-100`;
  `tests/browser/test_flow_gleepglorp_kinds.py:30-42/120-160/188-206` — verified (survey)
