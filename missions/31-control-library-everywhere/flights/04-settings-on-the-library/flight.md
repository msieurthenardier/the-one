# Flight: Settings on the library

**Status**: in-flight
**Mission**: [Every control comes from one library](../../mission.md)

## Contributing to Criteria
- [ ] **Every kind of control is defined once in the library** (partial). This flight adds:
  - the page header, the `editorShell` page variant, the banner, the code block, the facts list, the Built-in tools tile, the searchList inline variant, and options on `textInput`, `section`, `tabs`, `editorShell` and `radioGroup`;
  - a shared schema-field module (one renderer for tool settings in Settings and on the agent Tools tab);
  - small library helpers: "latest request wins", the keyed child reconcile and the error reader.

  Every Settings page is then built only from library controls. The legacy `App.tabs` and the legacy iOS switch leave Settings.
- [ ] **A change to one control reaches every place it appears** (partial). The Settings files reach zero reuse-allowance rows: `tools-grid.js`, `tools-editor.js`, `system-page.js`, `date-time-page.js`, `knowledge-settings-page.js`, the non-tools half of `admin.js`, the new tools-page module and `admin.css`. `tools-form-helpers.js` keeps only the rows of the chip-list string path that Flight 5's MCP editor still uses, and the `.area-studio` chip and switch rules move from `admin.css` to `studio.css` as a recorded move of their rows. That is about 120 of the 315 uses left at Flight 3's close. No leg raises the allowance (DD12).
- [ ] **No UI markup is built from HTML strings** (partial). `tools-editor.js` (8), `tools-grid.js` (3), `admin.js` (1), `knowledge-settings-page.js` (1) and `theme.js` (1) reach zero sinks: 14 of the 37 left.
- [ ] **Each control's styles are owned by that control** (partial). `admin.css` becomes Settings-only: the dead blocks go, the rules that restyle library controls are folded into their owners or removed, and the Flight 5 halves (`.area-studio` switch and chip rules) move to `studio.css`. The unused-selector report is reviewed.
- [ ] **Every migrated surface looks as it did before, apart from approved differences.** Before and after captures of every Settings page in both themes, on one realistic seed. The approved visible changes are the presentation-debt items the operator approved at planning (DD7), not ones found at the HAT.
- [ ] **Every library control works by keyboard and by role in both engines.** The new controls; the tile and Enabled switches become `role=switch` with honest names; the theme picker becomes native radios.
- [ ] **The area code is organised by surface** (partial). `admin.js` splits (the tools-page controller out), `knowledge-folders.js` splits (repaying Flight 3's 897 lines), and a static guard enforces the 800-line rule for every area module from now on.
- [ ] **Existing behaviour holds.** The defects found in planning are fixed, each with a test that reproduces it first (DD8). The squawks in DD9 are closed.

---

## Pre-Flight

### Objective
This flight moves the Settings destination onto the library: Built-in tools (grid and editor), Appearance, Prompts, Encryption, Date and time and Knowledge indexing.

1. Do the groundwork the Flight 3 debrief asked for:
   - a guard for the 800-line rule;
   - Settings capture surfaces on a realistic seed, with masks by shape;
   - the lane and flake fixes (squawks 0230, 0247);
   - test and doc debt (squawks 0240, 0246);
   - dead `admin.css` blocks.
2. Split `admin.js` and `knowledge-folders.js`, with no change in behaviour.
3. Settle three mission-wide patterns in the library before Flights 5 and 6 multiply them:
   - error placement and a single error reader;
   - one "latest request wins" helper;
   - a vertical rhythm for `App.ui.section`.
4. Build the new controls.
5. Build the shared schema-field module.
6. Rebuild the tools grid and editor, then the five other pages, on the library. Each page mounts once and patches in place. The planned presentation fixes land as approved visible changes.
7. Close `admin.css`, the counts and the docs, then the HAT.

When it lands, every Settings file is at zero sinks and zero allowance rows (apart from the Flight 5 chip-list path), `App.tabs` and `js/tabs.js` are gone, and squawks 0230, 0231, 0236, 0237, 0238, 0240, 0245, 0246 and 0247 are closed.

### Open Questions
- [x] One flight for Settings, or split tools from the pages? → DD1 (one; the operator had no preference, and the page header, banner, `admin.js` split and `admin.css` close-out cut across both)
- [x] The tool editor wipes default denylists on Save → **squawk 0248, hotfixed on `main` before this flight** (operator, 2026-10-23). This flight builds on the fixed schema contract (DD6).
- [x] The theme picker: keep the segmented look, or take the library radio card look? → DD7 (the card look; operator, 2026-10-23)
- [x] Which presentation-debt items are approved? → DD7 (operator, 2026-10-23): all of A; B1-B3, B5-B12, B14, B15; B4 changed; B13 skipped. The ledger in the flight log has rows 1-41.
- [x] When does a new control own its classes, given the allowance only shrinks? → DD12 (in the leg that migrates its last outside user)
- [x] Is the section stack a default or an option? → DD3 (an opt-in `layout: 'stack'`)
- [x] Are a code block and a read-only facts list controls? → DD4 (yes: `App.ui.codeBlock` and `App.ui.facts`)
- [x] Patch in place or remount on Save/Cancel? → DD5 (patch, as in Flights 2 and 3, now with a side-effect inventory)
- [x] Where do errors go? → DD3 (validation errors on the field; request errors at editor or page level; one reader)
- [x] Knowledge indexing: a page with a mid-page Save, or an editor? → DD6 (editor actions in the page header: Cancel and Save, top right)
- [x] Where does the shared tool-field renderer live? → DD4 (`js/areas/shared/tool-config-fields.js`, grown from `tool-override-fields.js`)

### Design Decisions

**DD1: One flight, Settings only.** (FD call; the operator had no preference, 2026-10-23.)
- The Settings work divides into two clusters, Built-in tools and the other five pages, but the shared pieces cut across both:
  - the page header and banner;
  - the `admin.js` split;
  - the `admin.css` close-out;
  - the error and "latest request" patterns.
- Flight 3 showed that a flight of this size (15 legs) runs well when its legs are split at planning.
- **Out of scope:**
  - the MCP server editor (Flight 5), including the chip-list string path in `tools-form-helpers.js` (`renderChipListEditor`, `wireChipListEditor`, `readChipListValue`, `chipExists`) and the `.area-studio` halves of the switch and chip rules;
  - Chats (Flight 6);
  - the provider editor beyond its banner and squawk 0236's busy Save (leg 04f);
  - the knowledge backend squawks 0243 and 0244, and Known Issues "search score floor" and "Add file".

**DD2: Groundwork first (leg 01).** No product behaviour change. The deleted CSS has no live consumer, which the capture compare proves.
- **The 800-line guard** (Flight 3 debrief recommendation 3). A unit test over `static/js/areas/**/*.js` fails on any file over 800 lines, with a shrink-only allowance of today's offenders: `chat.js` 2399, `mcp-server-editor.js` 2153, `provider-models.js` 1014, `knowledge-folders.js` 897 (until leg 02b) and `provider-editor.js` 896. Each allowance entry is a ceiling, not an exact count, so ordinary edits to `chat.js` don't break it: a listed file fails when it grows past its recorded count, and a listed file that drops to 800 lines or fewer fails until its entry is removed (shrink-only). *(Amended at leg 01 design, 2026-10-23: the spec first said "fails on any count change", which would break on every edit of those files.)* The `studio.js` pin in `tests/test_store_static.py:450` stays.
- **Capture surfaces for every Settings page** (`scripts/ui_capture.py`), on **one realistic seed** reused by the HAT (Flight 3 debrief recommendation 1). The seed includes:
  - a 97-character allowlist path and long hosts;
  - a custom byte size;
  - tools disabled globally;
  - a Test result, both ok and refused;
  - a validation error;
  - the Date and time mismatch (browser zone ≠ effective zone);
  - the Encryption armed state and its staged warning;
  - the Knowledge indexing invalid and saved states.

  Masks are **by shape** (a timestamp, a duration, the preview clock), never by label, so problem text stays visible.
  - **Environment pins** (Architect E1, E2): the instance gets an explicit `TZ=`, and the seed sets the time zone in `mode: zone`, so the server's system zone (tzlocal) cannot vary between runs. The "ok" Test result is stubbed with `page.route` (the `provider-test-ok` precedent), because a real fetch cannot succeed under netns.
  - **Widths:** 1280 and 1024.
  - **Surfaces outside Settings** that this flight changes visibly are captured too (Architect M8):
    - the connector editor and the `kb-*` surfaces (section rhythm, leg 03b);
    - the provider editor's plan sign-in and the self-configuration tab (banner and code block, leg 04f);
    - the agent Tools tab with a Filesystem tool's overrides open (labels, descriptions and default denylists, legs 05 and 0248).
  - **The before set is taken after squawk 0248 merges.** The agent Tools tab and the tool editor then already show the default denylists, so that change does not read as this flight's.
- **Squawk 0230:** `test_filter_keystroke_cost_ratio_60_vs_10_throttled` gets an absolute floor (`m60 <= max(3*m10, 0.25)`) and more work per sample.
- **Squawk 0247:** `knowledge` budget 360 s, with the CLAUDE.md lane table.
- **Squawk 0240:** the toggle tests use role locators, not `label.ui-toggle-label`.
- **Squawk 0246:** the docs and comments left stale by the Flight 3 HAT, plus the recon's extra rows (inventory `:46` self-configuration, `:98` agent editor and knowledge-shared, the duplicate `.connector-setup-steps-doc-ref`).
- **Dead `admin.css`:**
  - `.admin-note`, `.admin-section*`, `.admin-placeholder*`, `.mcp-source-tile-subtitle*`, `.tools-editor-test-help`, `.date-time-mismatch .btn`;
  - the `.area-admin .editor-section` gutter trap (`admin.css:17-22`), which is inert today but would indent any Settings page moved onto `App.ui.section`.
- **The visible-differences ledger** opens in the flight log, pre-filled with the DD7 approved items.

**DD3: Mission-wide patterns, settled in the library before the surfaces (legs 03a and 03b).** (Flight 3 debrief recommendation 4.)
- **Error placement** (the rule from now on, recorded in `agents.md` and the catalogue):
  - **On the field:** a validation error, whether from the client or a server 422 whose `loc` names a field.
  - **At editor or page level** (`editorShell.setError`, or a page banner): a request error, a 422 that names no rendered field, and a load failure.
  - One live announcement per error. No error is shown twice (a field error is not repeated at editor level).
- **One error reader (leg 03a).** `App.api.fetchJson` keeps its message unchanged (two tests pin "Server error 500"), and the thrown error also carries `status` and the raw `detail`.
  - A new `App.api.fieldErrors(err, names)` maps a 422 `detail` array to `{field: message}` plus the unmatched rest. **The `loc` rule:** drop a leading `"body"` segment, then take the first segment that names a field in `names`. Examples: the tools PUT `["path_denylist", 0]` → `path_denylist`; Knowledge indexing (its handler calls `ChunkingSettings.model_validate` by hand) `["size_chars"]` → `size_chars`, while its overlap check is a model validator with `loc` `[]`, which goes to the editor level. A string `detail` (a shape error) is unmatched. The humaniser also strips Pydantic's "Value error, " prefix. When a field matches, the editor-level text is built from the unmatched rest only, never from `err.message`.
  - **One place humanises Pydantic messages** (A11): "Input should be greater than or equal to 0" → "Must be 0 or more", and the same for less-than, length and type errors. The tools editor's two `humanizeValidationMsg` copies go.
  - **Unmatched and model-level errors go to the editor level.** Today's `applyModelLevelHighlights` (a substring match that paints `field-error-highlight` on a row) retires. The pinned test is retargeted, and a ledger row records the change.
  - `_errorMessageFromResponse` (`knowledge-shared.js:26`, 4 callers) is deleted, and its callers move to `fetchJson`. **This is not behaviour-free** (Architect M3):
    - `knowledge-folders.js` `removeFile` keeps treating a 404 as success, through `err.status`;
    - the fallback texts ("HTTP N", "Remove failed", "Folder registration failed") become `fetchJson`'s "Server error N …";
    - both get a ledger row and a test.
  - Raw `fetch` with "HTTP N" text is not added anywhere new. The Settings files move to `fetchJson` in their own legs.
- **One "latest request wins" helper (leg 03a).** `App.ui.util.latest()` returns `{next() -> token, isCurrent(token), invalidate()}`, beside `mountSlot`, with contract tests. Settings pilots it:
  - the tools editor's Save and Test;
  - the tools-page detail fetch;
  - Knowledge indexing load and save;
  - Date and time's module `GEN`.

  Library editors keep their working counters; converting them is Flight 5's and 6's job (recorded, not done here).
- **`syncChildren` is promoted (leg 03b)** to `App.ui.util.syncChildren(parent, nodes, {after})`, which never re-appends a node already in place.
  - `after` is an anchor node: the managed nodes follow it, as `provider-models.js:placeNodes` needs (it reconciles after `nextSibling`). With no anchor, the managed nodes start at the first child.
  - `knowledge-folders.js` uses it from there, and `placeNodes` switches to it.
  - A test that fails on `placeNodes` today proves the blur hazard: removing an earlier row must not re-insert a later, focused row.
- **Section rhythm (leg 03b), opt-in** (Architect H2). `App.ui.section({layout: 'stack'})` is a column with a token gap. Inside a stack the library neutralises its children's own vertical margins (`.field-group`, `.section-title`), because flex margins do not collapse. Hidden children take no space.
  - The default layout does not change, so the 26 existing `App.ui.section` calls, the MCP editor's hand-built `.editor-section` blocks and `dangerZone`'s side-by-side buttons are untouched.
  - Opted in, with the area spacing rules retired:
    - the connector's doctor section, which retires `.doctor-btn + :not([hidden])` (`studio.css:784`);
    - the pairing section. Its `.connector-pairing-result:has(> :not([hidden]))` rule (`:774`) exists for a visible wrapper whose children are all hidden, so the editor hides the wrapper itself when it is empty;
    - the knowledge folders section, which retires `.kb-folders-list { margin-top }` (`:846`).
  - `studio.css:1017` (`.kb-item-row` padding) is row padding, not section rhythm, and stays.
  - Settings pages opt in as they migrate.
  - Captures of `connector-edit` and the `kb-*` surfaces, before and after, prove nothing moved, or the movement is a ledger row.
- **Library a11y squawks (leg 03b):**
  - 0237: `confirm` `lapse()` skips the announcement for a detached node;
  - 0238: `keyValueTable` errors get `role="alert"`.

**DD4: New library controls and options, each built and contract-tested (Chromium and WebKit) before its consumer migrates (legs 04a-04e; split at their design reviews).**
- **`App.ui.pageHeader({title, headingId, intro, testid})`.** It carries `page-header` and `page-title`, with the Settings geometry from `admin.css:24-33`. It replaces two copies: `system-page.js:21` (`App.admin.renderPage`, which delegates to it from leg 08a and serves 08a, 08b and 09) and `admin.js:253` (the tools page's scaffold, leg 06). Knowledge indexing (`knowledge-settings-page.js:32`) uses the `editorShell` page variant, which composes `pageHeader`, so `page-header` and `page-title` have one owner. It keeps the `.page-title` class that about 15 test lines select, and adds a testid.
- **`editorShell` page variant** (`variant: 'page'`), for Knowledge indexing (Architect M7). It composes a `pageHeader` and passes the shell's own actions cluster into `pageHeader`'s actions slot. The dirty and busy logic stays in the shell; the slot only places the cluster. The `h1` is `h1.editor-title.page-title[tabindex=-1]`, so `focusAfter` and both sets of test selectors keep working. It has no breadcrumb. *(Refined at leg 04a's design review, 2026-10-23.)*
- **`App.ui.banner({tone: 'info'|'warning'|'error', text|children, role, actions, hidden, testid})`.** It returns `{el, set(text), show(), hide()}` and carries `banner*`.
  - A **persistent live mode** (`live: 'alert'|'status'`, kept rendered while empty) so it can carry `dangerZone`'s notice, which is a `role=alert` region kept in the DOM while empty (`.action-blocked-message:empty`), not hidden.
  - Its Library consumers move in leg 04f: `provider-editor.js:220`, `self-config-revisions.js:218`, `self-config-external.js:120`, and `dangerZone`'s notice (`editor.js:283`).
  - The tools editor's error banner (`.editor-error-banner`) retires in leg 07b: request errors go to `editorShell.setError` (DD3), so the tool editor has no banner.
  - The Settings uses move with their pages (legs 08b, 09, 10).
- **`App.ui.codeBlock({text, trim, testid})`.** A read-only `pre` with the existing `code-block` look. `trim` strips leading and trailing blank lines for display (A1).
  - A `maxHeight` option (`'tall'` 24rem, `'short'` 18rem) replaces the area max-height rules.
  - Consumers: the self-configuration tab (7 uses, leg 04f), the tool prompt block (leg 07a) and the Prompts page (3 uses, leg 08b).
  - Flight 3 left `pre.code-block` with no catalogue row; this gives it one.
- **`App.ui.facts({rows: [{label, value, mono, testid}], testid})`.** A read-only `dl` of label and value pairs. Three hand-built copies exist today: `admin-kv-*` (Knowledge indexing), `dl.date-time-preview` (Date and time) and `dl.chat-drawer-facts` (the chat drawer).
  - Settings uses it in legs 09 and 10. The chat drawer moves in Flight 6 (recorded, not done here).
  - `code.date-time-chip` becomes a `mono` value. It is not a chip.
- **Declared not controls** (catalogue note in leg 11): `p.admin-system-text` (body typography), the Settings nav host `div.admin-settings-nav` and `.admin-content` (layout), and `platform-section` (a `section` plus a `codeBlock`). Loading lines use `App.ui.status` (`pending`).
- **`App.ui.searchList` inline variant** (`inline: true`). It carries today's date-time CSS (`admin.css:650-681`):
  - a capped scrolling listbox;
  - no active-row paint while unfocused, plus the forced-colours twin;
  - the lead size and the mono description.

  It also adds:
  - scroll position kept across `refresh()` when the active id survives;
  - a `describedBy` option;
  - an item `selected` flag that the library draws as the check lead, with a fixed spacer and visually hidden "(selected)" text.

  The modal defaults (agent picker, Jump to) do not change.
- **`textInput` options** `min`, `max`, `step` and `inputMode`.
- **`App.ui.section` options:** `info` (a title-row info button, for the tools Test section). The DD3 stack layout lands in leg 03b.
- **The Built-in tools tile:** `App.ui.toolTile({name, href, selected, badge, description, toggle:{label, checked, disabled, onChange, testid, dataset}, testid, dataset})`. It returns `{el, link, toggle, setSelected, setChecked, setDisabled, setDescription}` and carries `entity-tile*`, `tool-tile*` and `tile-title-row`. The legacy tile and switch CSS is frozen as a test fixture so the contract can compare the look (Flight 2 precedent `_legacy_tool_css.py`). Flight 2's `groupTile` and `toolRow` do not fit: this is a card with a linked name, a badge, a description and a selected state.
- **Layout options, so `admin.css` reaches zero allowance rows** (Architect cycle 2, M2). Each one is built in a control leg, never discovered in a surface leg:
  - `editorShell` and `section` `inset: 'none'`, replacing `.settings-item .editor-header`/`.editor-section` (`admin.css:132-133`) (04a);
  - `tabs` `panelPadding: 'none'`, replacing `.settings-list .tablist`/`.tabpanel` (`:136-137`) (04d);
  - `emptyState` `variant: 'flush'` (it exists) for `.settings-list .empty-state` (`:139`);
  - a `radioGroup` slot option for the date-time slot indent (`.date-time-page .ui-radio-slot`, `:643`) (04d);
  - `codeBlock` `maxHeight` (04b);
  - the category badges use `App.ui.badge` kinds, which already include every tool category, so `.admin-tool-badge--*` is deleted (06).

  A surface leg that finds another need re-tiers high (DD11).
- **`chipList.valuesOf(el)`** (static), so area code reads a chip list's values without naming an owned class.
- **The shared schema-field module** (`js/areas/shared/tool-config-fields.js`, leg 05b) is area code, not a library control. It composes `field`, `checkbox`, `select`, `textInput`, `chipList` and `secretInput`, so it needs no catalogue row. Its contract is in DD13.
- **The theme picker** uses the existing `App.ui.radioGroup` card look (operator). No new variant.
- **No consumer CSS on library internals.** A needed look becomes an option in legs 04a-04e. A surface leg that finds it needs one is re-tiered high (DD11).

**DD5: The mount, save and dirty model.** (Flights 2 and 3 DD5, plus the Flight 3 debrief recommendation 2.)
- **Mount once, patch in place, a value model from control handles.**
  - Save and Cancel patch; nothing remounts on Save, Cancel, a store notification or a list toggle.
  - Dirty is computed by comparing a snapshot of values read from the handles, never from `querySelector`.
  - `editorShell.setBusy(true)` disables Save, Cancel and Test while a request is in flight (`editor.js:62`). The fields stay live (the connector precedent), so a change typed during the request is kept and stays dirty.
- **Every async write is keyed on identity and latest-ness** (DD3 `latest()` plus `mountSlot`). A response for tool A never writes into tool B's editor, even though every tool editor mounts into the same `.settings-item` node.
- **Secrets are re-masked from the response after Save** (the connector precedent), but only when the field still holds the value that was submitted. A secret typed again during the request is kept.
- **Remount side-effect inventory.** Every patch-in-place leg lists each effect a remount used to have, and gives each one a decision with a test:
  - **re-run on Save** (with a test of the post-Save state);
  - **dropped** (a ledger row);
  - **accepted in writing**.

  The effects to cover are probes, refetches, cleared result lines, timers, re-masking, focus and scroll, `show_if` visibility, the list tile's state, and the leave-guard mirror (`admin.js` `dirty`).
- **Snapshot from the submitted values.** A Save's success re-baselines from what was sent. A change typed during the request stays dirty.
- **Focus after a Save, Cancel or Test** goes through `App.focusAfter` (title on success, the control on failure; the Flight 2 rule).

**DD6: The canonical form of each page.**
- **Built-in tools grid:**
  - `App.ui.tabs` (testids `tab-{cid}` kept) and one `toolTile` per tool;
  - mounted once and reconciled by tool name (`syncChildren`), so a toggle never rebuilds the list and needs no hand-made focus restore;
  - the tile switch is an `App.ui.toggle` named "Enabled for all agents" with the tool name as context (`aria-label` "{name}: enabled for all agents", visible state through `role=switch`; the exact words go in leg 06 and the ledger);
  - a non-ok list response shows a load error, not "Loading tools…".
- **Built-in tools editor:**
  - `editorShell` (the breadcrumb "Settings / Built-in tools", title, `editor-unsaved`, Cancel and Save, `errorRole`);
  - the tool's prompt in its own section below the header (A14), Configuration, then Test;
  - the Enabled row is an `App.ui.toggle` with the static label "Enabled for all agents" (defect b);
  - fields come from the shared module (DD4); 422 errors go on fields, everything else to `editorShell.setError` (DD3);
  - the Test section has a `field` input, an `App.ui.button` and an `App.ui.status` result. The raw output sits under a collapsed "Technical details" (`App.ui.disclosure`), and the head of the output is shown, not the tail (A15, A16; the DD19 MCP-error pattern).
    - The headline is **fixed per outcome** ("Returned a result", "Blocked by this tool's settings", "Request failed"). The client never parses the tool's model-facing error string to build it (Architect L9). The detail stays in Technical details.
  - **Yes/no settings** (A10): the shared field module renders every boolean as the library checkbox with its label inline, in both admin and agent modes. On the agent Tools tab the label is stacked above the checkbox today (`tool-override-fields.js:158-172`), so inline there is a visible change and a ledger row. The Enabled row stays a switch, because it turns the tool itself on or off.
- **The schema contract** (from squawk 0248's fix): every property in the served schema carries a materialised `default`, so an unsaved tool shows its real defaults. The shared field module trusts `prop.default` and never treats a missing default as empty for a list.
- **Appearance:** the theme picker is an `App.ui.radioGroup` (card look; operator) built in `system-page.js`.
  - `App.theme.renderToggle`, its `theme.js` sink and the module-level listener retire. `theme.js` keeps `set`/`get`/the desktop signal, since it loads before `js/ui/`.
  - New testids `theme-option-{light|dark|auto}`.
- **Prompts:** `pageHeader`, one `App.ui.section` per layer (no stacked eyebrows, A3), code blocks trimmed for display (A1), caption spacing (A2), and `fetchJson`.
- **Encryption:**
  - `pageHeader` and a `banner` (warning, A5 wording);
  - the rotate button through `App.ui.confirm` (the retired `App.confirmDelete` alias goes);
  - the result in an `App.ui.status`. A **staged** result stays until the next attempt, and every new attempt clears the old timer (the race fix);
  - focus returns to the button through `App.focusAfter`;
  - `fetchJson`;
  - sentence-case labels (A4).
- **Date and time:**
  - the mismatch hint is a `banner` (info) with its "Use {zone}" button;
  - the status and error lines are `App.ui.status`, and the section titles are `App.ui.section`;
  - the zone list is the inline `searchList`;
  - after "Use {zone}" hides its hint, focus moves to the chosen-zone line;
  - module `GEN` becomes `latest()` with the same semantics: latest wins, and an unmounted instance only updates `App.time`;
  - the preview is `App.ui.facts` with `mono` values.
- **Focus target for "Use {zone}"**: the chosen-zone line gets `tabindex=-1` so it can take focus.
- **Knowledge indexing:**
  - The `editorShell` page variant (DD4): the `h1.page-title`, Cancel and Save top right, the unsaved caption, and busy and dirty from the shell (A19).
  - `App.ui.section` for each section, with one rule (A18).
  - `field` and number `textInput` for the three numbers, with linked hints (defect a). The error replaces the hint (A21), and the overlap is checked against its own limit.
  - `App.ui.toggle` for watching (A20).
  - The read-only rows use `App.ui.facts` (DD4), with humanised values (A23) and plain wording (A24).
  - The page CSS and its owned-class uses move as the page migrates. `.area-admin .field-error` (`admin.css:454`, a restyle of library error text) goes in this leg, the last Settings page to move onto `App.ui.field`.
- **Pages that change nothing on activate** (Appearance, Prompts) still re-render on `_refresh` today. They keep doing so only if their state is fully re-derivable. This is recorded in each page leg's side-effect inventory.

**DD7: Visible changes, and the ledger.**
- **Presentation debt was surveyed at planning** (operator decision at the Flight 3 debrief). It covered every Settings page on realistic data, at 1280 and 1024, in both themes: 24 obvious items (A1-A24) and 15 taste items (B1-B15). Evidence: the review page (https://claude.ai/artifact/FxJaiyiM6byDP81iaeLsr7) and `f4-presentation-debt.md` (FD scratchpad; the summary is copied to the flight log).
- **Approved by the operator** (2026-10-23):
  - **all of A1-A24**;
  - **B1-B3, B5-B12, B14 and B15**;
  - **B4 changed:** a long chip shows on one line with a middle ellipsis, with the full value in its tooltip and accessible name;
  - **B2 clarified:** the breadcrumb keeps "Built-in tools" as the link back to the list, and the tool title takes the Library editors' size;
  - **B13 skipped:** disabled tool tiles are not dimmed.

  The ledger (flight log, rows 1-41) names each item's leg. The B items add work beyond the page rebuilds:
  - **B1:** a short human `summary` per tool, a new class attribute served by `GET /api/tools/configs` and the detail route. It is not model-facing; leg 05a writes them and leg 06 shows them.
  - **B3:** one field width, matching the Library editors (the full form column), plus a `textInput` `width: 'short'` option for numbers (leg 04a).
  - **B4:** the middle ellipsis is a `chipList` change (leg 04e). The agent Tools tab gets it too; the MCP editor's string-built chips are Flight 5's.
  - **B5:** plain `ui_choices` labels.
  - **B6:** a per-tool field list, so a tool's schema omits settings that don't apply to it (for example the read size cap on `delete_file`). It is served per tool, and the agent Tools tab reads the same schema (leg 05a).
  - **B7:** squawk 0231.
  - **B8:** a `searchList` inline option that centres the active row (leg 04d); one font for zone ids and offsets (leg 09).
  - **B12:** a new read-only `GET /api/encryption/status` route returning `{last_rotated_at, credential_count}`. The rotate route records the time in `app_metadata`, and it is `null` before the first rotation (leg 08b, which becomes tier high).
  - **B14:** the button's disabled tokens in the dark theme, a library token change pinned by the contrast test (leg 04c; every editor).
- **Other approved changes:**
  - the theme picker's card look (operator);
  - the library switch for every Settings switch (operator, 2026-10-22);
  - the toggletip info button replaces the hover `title` tooltip on tool fields (a library behaviour);
  - DD3's section rhythm, if it moves anything.
- **A17** (the stale "F6 admin will surface the picker." sentence in `web_search`'s description) is prompt text the model reads. If approved, it lands with a `make eval` run compared against `evals/baselines/m30-platform.json` (the CLAUDE.md convention), in leg 05a.
  - **Re-verify at the start of leg 05a** (Architect E3): the plan token at `~/.config/the-one-evals/plan-token`, a local Ollama serving `gpt-oss:20b`, and the `[evals]` extra with its tiktoken cache. All four were present at planning.
  - The run burns plan quota, so the FD confirms with the operator before starting it.
  - It runs outside any concurrent browser lanes.
- **Squawk 0245** (the pairing expiry) is a visible change, landed in leg 02b, which is otherwise behaviour-free. It is a ledger row.
- **A7** (written field titles) and **squawk 0231** (field descriptions) change `Field(title=…, description=…)` on the tool Config classes. Neither reaches the model: only `GET /api/tools/configs/{name}` reads `model_json_schema()`. Leg 05a re-verifies this with a grep and a unit test that no model-facing text changed.
- Every leg appends its visible differences to the ledger. The HAT walks the ledger.

**DD8: The defects found in planning are fixed, test first.** Each gets a test that fails on today's code, then the fix.
- **Tools grid (leg 06):**
  1. The tile switch's name hides "for all agents", and it has no `role=switch` (defect a).
  2. A non-ok `GET /api/tools/configs` leaves "Loading tools…" for good (`admin.js:448-461`).
  3. A non-404 detail failure leaves `pendingToolName` set, with the URL on `tools/{name}` and no editor (`admin.js:443`).
- **Tools editor (legs 07a-07c):**
  4. The Enabled row reads "Disabled for all agents, not checked" (defect b). (07a)
  5. Cancel during an in-flight Save shows values the server no longer holds. (07c)
  6. An edit typed during a Save is marked saved but was never sent (`tools-editor.js:516`). (07c)
  7. A Save response for tool A writes into tool B's editor and clears B's leave guard (`admin.js:387` `onDirtyChange` unguarded). (07c)
  8. The secret is not re-masked after Save. (07c)
  9. Errors are announced twice (`.editor-error` `role=alert`, then the banner). (07b)
- **Encryption (leg 08b):**
  10. A second rotation within 3 or 4 s has its staged warning wiped by the first timer (`system-page.js:236`, `:244`).
  11. A non-JSON error body shows "Error: Unexpected token…".
  12. Focus is lost after Rotate.
- **Date and time (leg 09):**
  13. "Use {zone}" hides its own focused button.
- **Knowledge indexing (leg 10):**
  14. The hints are not linked to their inputs (defect a).
  15. Typing during a save re-enables Save (a double submit), and the response overwrites the newer typing (`:210`, `:289`).
  16. The "Saved." timer wipes a later error (`:291`).
  17. Focus is lost after Save.
  18. A server 422 does not name its field.
- **Appearance (leg 08a):**
  19. The theme listener outlives the page (`theme.js:174`, `:282`).

**DD9: Squawks.**
- **Absorbed:**
  - 0230, 0240, 0246 and 0247 (leg 01);
  - 0237 and 0238 (leg 03b);
  - 0231 (leg 05a);
  - 0245 (leg 02b: the pairing expiry through the knowledge stamp formatter, promoted to `App.time.formatStamp` if two consumers need it);
  - 0236 (leg 04f: the provider editor's Save calls `setBusy`. That leg already touches the provider editor for its banner, and the fix is the DD5 busy rule).
- **Not absorbed, stay open:**
  - 0228, 0229, 0232 (agent editor);
  - 0239 (knowledge inspect announcement);
  - 0243, 0244 (knowledge backend);
  - 0222 and 0234 (unit-tier profiling).
- **Hotfixed before this flight:** 0248 (on `main`). Leg 05b's shared field module builds on its schema contract.

**DD10: Tests, lanes and specs.**
- **Lanes:**
  - `settings` (263/360 s) carries most of the new tests; `agent-tabs` carries the shared field module; `shared` the theme tests and the chip-list label test; `routing` the `admin.js` split (`test_router_core.py:493` spies `admin.serializeState`/`hydrateState`, so the area object keeps its API); `knowledge` the `knowledge-folders.js` split; both contracts lanes the new controls.
  - Re-budget by the 15% and 1.3x rules at leg 11. `settings` may need a split, as `agents` and `library` did.
- **Pins to retarget, never relax** (DD11). The main ones:
  - the four `tests/test_tools_*_assets.py` string pins;
  - `test_settings_pages_static.py` (the `ROUTE_SECTION` literal and `App.settingsPages` stay in `admin.js`);
  - `test_makefile_verify_serving.py` (served page names);
  - `test_design_tokens_a11y.py`. Its pins read `admin.css` by file name, so each moves in the leg that moves its rule:
    - `.admin-theme-option.active`: leg 08a;
    - `.editor-error-banner`: leg 07b;
    - `.settings-intro` (dead): leg 06;
    - the switch tracks: the `.area-admin` pins go in leg 10 (the switch's last Settings user, after the grid in 06 and the editor in 07a-07b), and the `.area-studio` pins become `studio.css` pins in leg 11;
    - the library toggle is already pinned;
  - `test_ui_tabs_contract.py`'s legacy parity test, which loads `js/tabs.js`. Freeze it as a fixture in leg 06 or drop the parity test with a reason;
  - `test_flow_admin_rotate_flash.py` (`.admin-system-flash` classes, moved to a testid or `data-state`).
- **The library field removes a cleared error node** where today's pages keep it `[hidden]`. Tests asserting a count of 1 move to `to_be_hidden`.
- **Behavior specs:**
  - `windows-window-chrome.md` step 4 and `windows-native-frame-splash.md` steps 11-14 and 19 (both drive Appearance) are amended in leg 08a;
  - `agent-governance-and-search.md` steps 1-5 (the `web_search` editor: dropdown, `show_if`, the password eye, the masked round-trip) are re-read in leg 07b and amended if needed;
  - the route-only specs (`jump-to-palette`, `list-and-detail`, `workbench-navigation`, `shell-navigation-smoke`, `start-a-chat`) are checked in leg 11.
- **Fixed waits.** No new test uses a fixed `wait_for_timeout` to prove "nothing changed after a late response". It waits for the released request to finish, then asserts. The 27 existing ones in the knowledge and connector tests are not this flight's.

**DD11: Standing leg rules** (Flights 2 and 3, plus the Flight 3 debrief). Every leg spec carries these:
- **No consumer CSS on library internals and no `[data-testid]` style hooks.** A needed look becomes a library option in a control leg. A surface leg that needs one is re-tiered high, and the option gets its catalogue row and contract test in that leg.
- **Mind the cascade layers.** A rule moved from an area stylesheet into a control deletes or narrows the area rule in the same change. A computed-style check under an area ancestor (`host.className = 'area-admin'`) proves the owner's rule applies.
- **Append to the ledger,** with an in-progress log line at each internal checkpoint.
- **Retarget pins, never relax them.**
- **Remount side-effect inventory** in every patch-in-place leg (DD5).
- **Re-run the line guard and `git grep` the moved paths** across `tests/`, `scripts/`, `Makefile`, `docs/` and `tests/behavior/`, and paste the hits into the leg.
- **A new browser test file gets its lane glob** in `scripts/run-tests.sh` (`settings` has a glob; `agent_tabs_pat`, `knowledge_pat` and `library_pat` are explicit lists), or it lands in `shared`.

**DD12: When a new control owns its classes.** (Architect cycles 1 and 2.) The ownership allowance only shrinks; Flight 3 paid +12 rows for breaking that.
- **Why a marker class.** `test_inventory_rows_are_classified` needs every `library:` row to list at least one owned class. `test_ui_ownership.py` counts each listed class wherever it appears outside `js/ui/`. A control built before its legacy classes' last outside user moves can therefore neither list those classes (new allowance rows) nor list nothing.
- **The rule:**
  - from its build leg, each new control owns a new marker class (`ui-page-header`, `ui-banner`, `ui-code-block`, `ui-facts`, `ui-tool-tile`) and emits its legacy classes beside it;
  - the legacy class names join the owned list in the leg that migrates their last outside user;
  - no leg raises `OWNERSHIP_ALLOWANCE`.
- **DD11 exception, recorded:** between a control's build leg and its handover leg, area CSS may keep styling the legacy class names on both the area's own markup and the control's. The handover leg deletes or moves those rules.
- **Handover leg per control:**
  - **`banner`** (`banner`, `banner-*`): leg 10. The last outside users are:
    - `system-page.js:196` and its `admin.css:49` rule (Encryption, 08b);
    - `date-time-page.js:425` (09);
    - `knowledge-settings-page.js:36` (10);
    - the Library users move in 04f.
  - **`pageHeader`** (`page-header`, `page-title`): leg 10. `App.admin.renderPage` delegates to it from 08a. The tools scaffold header moves in 06. The Knowledge indexing header moves through the `editorShell` page variant, which composes `pageHeader`, in 10, along with the `admin.css:24-33` rules.
  - **`toolTile`** (`entity-tile*`, `tool-tile*`, `tile-title-row`, and `entity-tile-grid` through a `toolTile.grid()` container): leg 06. That covers the `tools-grid.js` strings, `admin.js:552` `a.tool-tile-link` (in the tools-page module after 02a) and the tile rules in `admin.css`.
  - **`codeBlock`** (`code-block`): leg 08b. The self-configuration users move in 04f, the tool prompt in 07a, and Prompts last in 08b.
  - **The `searchList` inline variant:** built in 04d, with its CSS under the variant class. Until leg 09 that CSS duplicates `admin.css:650-681` (a recorded DD11 exception). Leg 09 deletes the overrides and switches the page to `inline: true`.
  - **`facts`:** new classes only.
- **An emitted-class guard (leg 04c):** a static test that every class a `js/ui` factory emits is owned by some catalogue row or listed as an exemption. Leg 11's owned-list check becomes mechanical, and the DD12 handovers cannot be forgotten.

**DD13: The shared field module's contract** (`js/areas/shared/tool-config-fields.js`, leg 05b; Architect M9).
- **Grown from `tool-override-fields.js`**, with `mode: 'admin' | 'agent'`. `App.studio.toolOverrideFields` stays as an alias for `tools-tab.js:155` until that caller moves, inside leg 05c.
- **`render(name, prop, value, opts)`** returns `{el, control, field, value(), setValue(v), setError(msg|null), setVisible(bool)}`, plus `showIf(properties, handles)`.
- **The DOM contract tests depend on is kept:**
  - admin mode: `data-field="{name}"` on the control, `data-field-name` and `.tools-editor-field` on the row, ids `tef-{name}` (used by the shared-lane chip-list label test and about 60 Settings selectors);
  - agent mode: `data-tool-override-tool` and `data-tool-override-field` on the value node. Squawk 0223's rule ("send `tool_overrides` only for tools whose override body loaded") depends on that attribute being present.
- **`readValue(el)` replaces `App.adminFormHelpers.readFieldValue`** in `agent-form-data.js`. It dispatches on `data-field-type`, and arrays go through `chipList.valuesOf`.
  - **Number parsing changes** (no more silent `parseInt` truncation; a ledger row in both modes):
    - blank → `''`, which is skipped as today (never `Number('') === 0`);
    - an integer string → the number;
    - anything else: **admin mode** sends the raw value, and the tools-PUT 422 lands on the field; **agent mode** shows a client-side field error and refuses the Save. The agent PUT does not validate `tool_overrides` (it is stored as `dict[str, Any]`, and the resolver only runs when the agent is built), so a server error would surface only at the next chat.
  - `readValue` keeps `readFieldValue`'s checkbox branch.
  - The dead `mcp_overrides` walk in `agent-form-data.js` (no producer left in `js/`) is deleted, with a note. `var mcpOverrides = {}` stays, because the per-tool toggles still fill it.
- **Shared presentation:**
  - booleans are the inline-label checkbox in both modes (A10; a ledger row on the agent Tools tab);
  - custom preset values are humanised in both modes (A8);
  - labels and descriptions come from the schema (A7, squawk 0231), so the agent Tools tab shows them too. That is a ledger row, and its capture is in leg 01's before set.
- **Tests:** `tests/browser/test_flow_studio_tool_override_fields.py:44` reads the module's file path. It is retargeted to the new path, with no alias left in the test. A new test file for admin mode goes in the `settings` lane.

### Citation Audit
Verified at `bfeb3f6` (planning surveys, 2026-10-23, and Flight Director spot-checks):

| Citation | Status |
|---|---|
| `tools-editor.js:146` `saved = (fname in config) ? config[fname] : prop['default']`; `filesystem.py:87-89` `path_denylist` `default_factory`; schema has no `default` (squawk 0248) | verified (FD read + run) |
| `tools-grid.js:59-68` tile input `aria-label="Enable {name}"` overrides the label; state span never in the name (DD8-1) | verified (FD read) |
| `tools-editor.js:235-242` Enabled row `aria-label` = state text, visible label "Enabled for all agents" (DD8-4) | verified (FD read) |
| `admin.js:214` `content.innerHTML = '<div class="admin-content"></div>'` (sink) | verified (FD read) |
| `system-page.js:236`, `:244` `setTimeout(...)` with no stored handle (DD8-10) | verified (FD read) |
| `knowledge-settings-page.js:208-211` Save re-enabled from `revalidateAndUpdate`; `:289-291` `applyLoadedSettings` then a 3 s `setTimeout` clearing the flash (DD8-15, -16) | verified (FD read) |
| `admin.css:17-22` `.area-admin .editor-section { padding-left/right: 20px }` (DD2 trap) | verified (FD read) |
| `tests/test_store_static.py:450` `assert len(src.splitlines()) <= 800` is the only line-budget pin (DD2) | verified (FD read; recon grep) |
| `js/api.js:26-40` `fetchJson` flattens a `detail` array to `loc: msg` text and drops `status` (DD3) | verified (FD read) |
| `ui/core.js:83` `App.ui.util.mountSlot` is the only lifetime helper; no "latest" helper exists (DD3) | verified (FD read; recon) |
| `ui/editor.js:188-200` `App.ui.section` is a plain `div.editor-section` with no gap rule (DD3) | verified (FD read) |
| `knowledge-shared.js:26` `_errorMessageFromResponse`, 4 callers (DD3) | verified (recon grep) |
| `HTML_SINK_ALLOWANCE` (`tests/test_ui_guards.py:148-156`): admin.js 1, knowledge-settings-page 1, tools-editor 8, tools-grid 3, theme.js 1 | verified (FD read) |
| `OWNERSHIP_ALLOWANCE` per file: tools-editor 21/38, admin.css 19/52, tools-form-helpers 14/34, knowledge-settings-page 6/18, admin.js 5/6, tools-grid 5/10, date-time-page 3/6, system-page 3/7, tabs.js 1/1; total 135/315 | verified (FD tally) |
| `mcp-server-editor.js` uses only `renderChipListEditor`, `wireChipListEditor`, `readChipListValue` from `App.adminFormHelpers`; `agent-form-data.js:211-220` uses `readFieldValue` (DD1, DD4) | verified (survey grep) |
| `test_ui_tabs_contract.py:152-215` loads `js/tabs.js` for keyboard parity (DD10) | verified (survey read) |
| `test_router_core.py:487-510` spies `admin.serializeState`/`hydrateState` (DD10) | verified (survey read) |
| Banner consumers: `provider-editor.js:220`, `self-config-revisions.js:218`, `self-config-external.js:120`, `editor.js:283` (DD4) | verified (survey grep) |

### Prerequisites
- [x] Squawk 0248 is merged to `main` (the denylist schema defaults): `8a52a39` (#304). The flight branch is cut from it.
- [x] The operator's DD7 decisions are recorded in the ledger (2026-10-23).
- [x] The branch `flight/04-settings-on-the-library` is created from `main` (`8a52a39`) at flight start (2026-10-23).
- [ ] WebKit userland and `THE_ONE_TEST_NETNS=1` work. Re-verify at the start of every leg that runs browser tests.
- [ ] The before captures are taken in leg 01, before any Settings file changes.

### Pre-Flight Checklist
- [x] All open questions resolved
- [x] Design decisions documented
- [x] Citation Audit complete
- [ ] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach
The order Flights 1-3 proved: groundwork, restructure, patterns and controls, surfaces, close. Legs were split at planning (Architect cycle 1: 03, 07 and 08), never mid-flight.
- **Leg 01:** the guard, the captures and before set (after squawk 0248 merges), the lane, flake, test and doc squawks, then the dead CSS deletion and a compare against the before set.
- **Legs 02a and 02b:** split `admin.js` and `knowledge-folders.js` with no behaviour change. 02b also carries squawk 0245, its one ledger row.
- **Legs 03a and 03b:** settle the patterns in the library:
  - 03a: the error reader, `fieldErrors` and `latest()`, with the knowledge callers moved off `_errorMessageFromResponse`;
  - 03b: `syncChildren` with `provider-models.js`, the opt-in section stack with the connector and knowledge opt-ins, and the two library a11y squawks.
- **Legs 04a-04e:** build the controls and options in the library only, each owning a marker class (DD12): the page header, shell page variant and banner (04a); the code block, facts list and input options (04b); readable disabled buttons and the emitted-class guard (04c); the list controls (04d); the tool tile and chips (04e). Split at leg design reviews.
- **Leg 04f:** moves the Agents and Library consumers of `banner` and `codeBlock`, and lands squawk 0236.
- **Legs 05a-05c:** the backend tool-settings text and per-tool schema shaping, including a PUT that never resets a hidden field (05a); the shared field module (05b); the agent Tools tab moved onto it (05c). Split at planning and at 05b's design review.
- **Legs 06 and 07a-07d:** rebuild the tools grid; then the editor frame and fields (07a), its errors and purges (07b), its Save/Cancel model (07c) and its Test section (07d). 07a was split at its design review.
- **Legs 08a-10:** rebuild Appearance, then Prompts with Encryption, then Date and time, then Knowledge indexing.
- **Leg 11:** closes `admin.css`, the counts, the captures, the lanes and the docs.
- **Leg 12:** the HAT.

### Checkpoints
- [ ] The line guard is in, the Settings before set is taken, and squawks 0230, 0240, 0246 and 0247 are closed; the gate is green.
- [ ] `admin.js` and `knowledge-folders.js` are split, with no behaviour change; full gate green.
- [ ] One error reader with `fieldErrors`, and `latest()`, are in the library; the knowledge callers use them.
- [ ] `syncChildren` and the opt-in section stack are in the library; the connector and knowledge captures match or have ledger rows.
- [ ] The new controls and options are contract-tested in both engines, the emitted-class guard is in, and no allowance row was added.
- [ ] The shared field module serves both editors; the agent Tools tab is unchanged except for its ledger rows.
- [ ] The tools grid and editor are on the library; DD8 1-9 fixed; `App.tabs` and `js/tabs.js` gone.
- [ ] Appearance, Prompts, Encryption, Date and time and Knowledge indexing are on the library; DD8 10-19 fixed.
- [ ] Every Settings file is at zero sinks and zero allowance rows (apart from the Flight 5 chip-list path); budgets re-measured; full gate green.
- [ ] HAT passed, and the close checks re-run after any HAT code change.

### Adaptation Criteria

**Divert if**:
- A split cannot stay behaviour-free (a test changes behaviour, not just a path pin): stop and re-plan the boundary.
- The shared field module cannot serve the agent Tools tab without a behaviour change there: keep the two renderers and raise it.
- A server change beyond the approved ones turns out to be needed: raise it as its own question. The approved server changes are the Config titles, descriptions, `ui_choices` labels, per-tool summaries and per-tool field lists, with a PUT that keeps hidden fields (leg 05a); the encryption status route (leg 08b); and the Test route's additive `outcome` field (leg 07d, an FD call at its design review, needed so A15's headlines never parse model-facing text).
- A17's eval run fails its gate: drop A17, and leave the description unchanged.

**Acceptable variations**:
- Module boundaries and names inside DD3, DD4 and DD6.
- Option names on the new controls.
- Splitting a leg further at its design review (never merging legs).
- A `settings` lane split.


### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `groundwork-and-before-set` (01), in this order:
  1. the capture surfaces (Settings, plus the Agents and Library surfaces this flight changes) on the realistic seed, at 1280 and 1024, with pinned `TZ`, a stubbed ok Test result and masks by shape;
  2. the before set, taken after squawk 0248 merges;
  3. the 800-line guard with its allowance;
  4. squawks 0230, 0240, 0246 and 0247;
  5. the opened ledger;
  6. last, the dead `admin.css` blocks and the `.editor-section` trap, followed by a capture compare that shows no difference.

  No product behaviour change (DD2). If its design review finds it too large, it splits into 01a (captures and before set) and 01b (the rest).
- [x] `admin-split` (02a): `admin.js` → `areas/admin/tools-page.js` (`App.admin.toolsPage.create(ctx)`), behaviour-free.
  - The area object keeps its seams as delegates; `ROUTE_SECTION` and `App.settingsPages` stay in `admin.js`.
  - The label-literal pin in `test_settings_pages_static.py` extends to `areas/admin/*.js`.
  - The cache-busting test gains a shell-before rule for `admin.js`.
  - The content shell becomes DOM-built (sink 1 → 0).
  - Lanes: `routing` and `settings`.
- [x] `knowledge-rows-split` (02b): `knowledge-folders.js` → `knowledge-rows.js` (rows and Individual files), behaviour-free; the stale invariant comments fixed; the duplicate `baseName` unified; squawk 0245 (one ledger row). Lanes: `knowledge` and `library`.
- [x] `error-reader-and-latest` (03a), **tier high, a shared interface**: the `fetchJson` error with `status` and `detail`; `App.api.fieldErrors` with the `loc` rule and the one humaniser; `App.ui.util.latest()`; `_errorMessageFromResponse` gone (404 tolerance kept, fallback texts as ledger rows); the error-placement rule written down (DD3). Lanes: `knowledge` and `contracts-controls`, plus every lane whose tests read `fetchJson` messages (grep at leg design).
- [x] `reconcile-and-rhythm` (03b), **tier high, a shared interface**: `App.ui.util.syncChildren(parent, nodes, {after})` with the `placeNodes` blur test; the opt-in `section` stack with child margins neutralised; the connector doctor, pairing and knowledge folders opt-ins, with their area rules retired; squawks 0237 and 0238. Lanes: `providers`, `library`, `knowledge`, both contracts lanes.
- [x] `header-and-banner` (04a), library only: `pageHeader` (with an actions slot); the `editorShell` page variant composing it (`h1.editor-title.page-title`); `inset: 'none'`; `banner` with a collapsing persistent live mode. Marker classes (DD12), catalogue rows, contract tests.
- [x] `code-facts-inputs` (04b), library only: `codeBlock` (trim, `maxHeight`, a keyboard-scrollable region when it overflows); `facts`; the `section` `info` option; the `textInput` number options and `width: 'short'` (B3).
- [x] `disabled-buttons-and-guard` (04c): every disabled button moved from opacity to opaque disabled tokens, at least 3:1 in both themes (B14), with mirror and consumption pins; the emitted-class guard (a `scan_js`-based ratchet, exact in both directions).
- [x] `list-controls` (04d), library only: the `searchList` inline variant (`keepScroll`, `describedBy`, the selected mark, a centred programmatic activation for B8); `tabs` `panelPadding`; the `radioGroup` slot option.
- [x] `tile-and-chips` (04e), library only: `toolTile` and `toolTile.grid` against a frozen `LEGACY_ADMIN_TILE_CSS`; `chipList` `data-value`, `valuesOf` and the middle ellipsis (B4, a 40-character budget through `App.ui.util.middleEllipsis`).
- [x] `library-consumers` (04f): `banner` for the provider editor and the self-configuration tab; `dangerZone`'s notice through the banner's persistent live mode; `codeBlock` for the self-configuration tab's 7 uses; squawk 0236 (provider Save `setBusy`). Lanes: `providers`, `agent-tabs`, plus every lane with a `dangerZone` host.
- [x] `tool-config-text` (05a), **tier high (served schema shape, plus one model-facing sentence)**: written Config titles and descriptions (A7, squawk 0231), plain `ui_choices` labels (B5), a per-tool `summary` (B1) and `config_fields` (B6), with a unit test that the model-facing tool schemas are byte-identical apart from A17; A17 with its eval run, after re-verifying its prerequisites and getting the operator's consent for the quota.
- [x] `tool-config-fields` (05b): `js/areas/shared/tool-config-fields.js` per DD13 (admin and agent modes, `showIf`, `setError`, `readValue`, a text input with `inputmode=numeric` for agent numbers, A8 units by field-name suffix), tested on a harness page; nothing switches yet.
- [x] `agent-tools-on-fields` (05c), **tier high, shared with the agent Tools tab**: the Tools tab and `agent-form-data.js` moved onto the module; the hidden-override carry-over (a stored override on a field 05a hid is never dropped); agent number validation that blocks the Save through `formData.blockingError()`; A8 and A10 on the tab; squawk 0223's rule kept; `tool-override-fields.js` deleted.
- [x] `tools-grid` (06): `App.ui.tabs` and `toolTile`, mounted once and reconciled, with the per-tool summary on each tile (B1); DD8 1-3; `App.tabs`, `js/tabs.js` and its `index.html` tag retired (the `test_ui_tabs_contract.py` parity test frozen as a fixture or dropped with a reason); `toolTile` takes ownership (DD12); A6.
- [x] `tools-editor-frame` (07a), **tier high, a security-adjacent surface (tool safety settings and secrets)**: `editorShell` (`titleLevel: 2`, Library title size, B2), the prompt as a `codeBlock` (A14), the Enabled switch (DD8-4, A9), fields from the module's admin mode (A10, A12, A13, B3), the handle-based snapshot with interim Save/Cancel, `showIf`, `setEnabled` kept, and the Test section moved to DOM unchanged; no sinks and no `App.icon` left.
- [x] `tools-editor-errors-and-purge` (07b): the DD3 error path through `fieldErrors` (DD8-9; the banner retired); `tools-form-helpers.js` reduced to the Flight 5 chip path; the `admin.css` editor rules removed; the a11y pin moved; the bulk test retargeting; the behavior spec checked.
- [x] `tools-editor-save-model` (07c), **tier high**: patch-in-place Save and Cancel; the baseline from the response; per-field re-masking; busy covering Test; `latest()` and identity guards with a split `onSaveSuccess`; the Enabled race rule; the side-effect inventory; DD8 5-8; `App.ui.flash` replacing `App.showFlash`.
- [x] `tools-editor-test` (07d): the route's additive `outcome` field (server-side); the Test result on `status` and `disclosure` with fixed headlines; the head of the output; the "Tests the saved settings." hint when dirty; A15 and A16.
- [x] `appearance` (08a): the theme radio group (card look) built in `system-page.js`; `renderToggle`, its sink and its listener retired (DD8-19); testids `theme-option-*`; the a11y pin moved; `windows-window-chrome.md` and `windows-native-frame-splash.md` amended.
- [x] `prompts-and-encryption` (08b), **tier high (a new backend route on the encryption surface)**: Prompts on `section` and `codeBlock` (A1-A3, B11) with `fetchJson`; Encryption on `banner`, `confirm` and `status`, with A4 and A5; the read-only `GET /api/encryption/status` (last rotation time, recorded by the rotate route, and the credential count; B12), with unit tests and a SECURITY-MODEL.md check; DD8 10-12; `codeBlock` takes ownership.
- [x] `date-and-time` (09): `banner`, `status`, `section`, `facts`, the inline `searchList` with the `admin.css` overrides deleted; DD8 13; `GEN` → `latest()`; B8-B10.
- [x] `knowledge-indexing` (10): the page on the `editorShell` page variant per DD6; DD8 14-18; A18-A24, B3 and B15; the library switch; `.area-admin .field-error` and the `.area-admin` switch rules and their pins gone, including the `test_deep_violet_computed_styles.py:47-49` fixture; `banner` and `pageHeader` take ownership (DD12).
- [x] `settings-close` (11):
  - the `admin.css` close-out, with the Flight 5 halves moved to `studio.css` as a recorded row move;
  - zero counts on every Settings file;
  - the unused-selector report and the single-consumer option recheck;
  - the owned-list check (DD12), and the dead `components.css:1245` header-action rule deleted;
  - after captures;
  - lane re-budget (a possible `settings` split);
  - catalogue (including the "declared not controls" note), registry, CLAUDE.md and `agents.md`;
  - the behavior-spec amendments check;
  - the line guard re-run.
- [ ] `flight-hat` *(the operator wants one per flight)*: the operator walks every Settings page, plus the changed Agents and Library surfaces, in both themes on the leg 01 seed. The steps come from the ledger, and the FD dry-runs each one on the seeded instance; destructive steps use their own disposable, clearly named items. If the HAT changes code, the leg 11 close checks re-run before landing, and a HAT feature gets the Accessibility Reviewer too.

> Leg design greps every moved path, renamed class and retired selector across `tests/`, `scripts/`, `Makefile`, `docs/ui-testid-registry.md` and `tests/behavior/`, and pastes the hits into the leg.

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing
- [ ] Documentation updated

### Verification
- The line guard passes, and every module it allows is at or under its recorded count; `admin.js`, the new tools-page module and every knowledge module are ≤ 800 lines.
- `HTML_SINK_ALLOWANCE` has no row for `tools-editor.js`, `tools-grid.js`, `admin.js`, `knowledge-settings-page.js` or `theme.js`.
- `OWNERSHIP_ALLOWANCE` has no row for the Settings page files, `admin.js`, the tools-page module, `tools-grid.js`, `tools-editor.js`, `tabs.js` or `admin.css`.
  - `tools-form-helpers.js` keeps only chip-list rows.
  - `studio.css` gains exactly the `.area-studio` chip and switch rows moved from `admin.css`.
  - Each kept row names Flight 5.
  - The total is lower than at the start of the flight, and no leg raised it.
- Every control built in this flight owns its legacy class names in the catalogue, and the emitted-class guard passes with no exemption added for them (DD12).
- `js/tabs.js` does not exist. `git grep "App.tabs"` finds no caller.
- `make test-unit` passes, and `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 TEST_TIMEOUT=3600 make gate` is green with the re-measured budgets.
- HAT: the operator approves the after captures and the ledger.
