# Flight: Knowledge and connectors on the library

**Status**: in-flight
**Mission**: [Every control comes from one library](../../mission.md)

## Contributing to Criteria
- [ ] **Every kind of control is defined once in the library** (partial). This flight adds:
  - the disclosure;
  - the key-value table (its core; Flight 5 adds the masked column for the MCP editor);
  - the clearable input, and options on `chip`, `editorShell`, `status`, `copyField` and the icon set.

  The knowledge-base editor's item menu moves onto `App.ui.menu`. The knowledge-base and connector editors are then built only from library controls.
- [ ] **A change to one control reaches every place it appears** (partial). `knowledge-section.js` (and its split modules) and `connector-editor.js` reach zero reuse-allowance rows. That is about 102 of the 409 uses left at Flight 2's close.
- [ ] **No UI markup is built from HTML strings** (partial). `knowledge-glue.js` (3), `connector-editor.js` (3), `connector-glue.js` (1) and `mcp-glue.js` (1) reach zero sinks.
- [ ] **Each control's styles are owned by that control** (partial). The knowledge and connector rules in `studio.css` that restyle library controls are folded into their owners or removed; an unused-selector report is reviewed.
- [ ] **Every migrated surface looks as it did before, apart from approved differences.** Before and after captures of the knowledge-base and connector editors in both themes; the operator approves them at the HAT.
- [ ] **Every library control works by keyboard and by role in both engines.** The new controls, plus the knowledge-base item menu moved into the accessible menu pattern (a gap the mission names).
- [ ] **The area code is organised by surface** (partial). `knowledge-section.js` (1493 lines) is split into modules of ≤ 800 lines.
- [ ] **Existing behaviour holds.** The live defects found in planning are fixed, each with a test that reproduces it first (DD8).

---

## Pre-Flight

### Objective
This flight moves the Library destination's knowledge-base and connector editors onto the library. Model providers moved in Flight 1; the MCP server editor is Flight 5's.
1. Do the groundwork the Flight 2 debrief asked for first:
   - split the `contracts` browser lane (1010 tests);
   - replace the exact script-count pin (squawk 0233);
   - write the editor contracts down (squawk 0235);
   - add an unused-selector report script;
   - take the before captures.
2. Split `knowledge-section.js` with no change in behaviour.
3. Build the disclosure, the key-value table core and the small options the editors need.
4. Rebuild the knowledge-base create form and detail editor, and the connector editor, on the library. Each editor mounts once and patches in place.
5. Clean up the Library glue and pane: the sinks, squawks 0191 and 0192.

When it lands, every knowledge, connector and Library-glue file has zero sinks and zero allowance rows. Squawks 0100, 0191, 0192, 0233 and 0235 are closed.

### Open Questions
- [x] One flight for Library and Settings, or two? → DD1 (two; operator, 2026-10-22)
- [x] The legacy iOS switch on the connector's Enabled row? → DD7 (the library switch; operator, 2026-10-22)
- [x] Squawk 0100: which clear control? → DD4 (an explicit × button; operator, 2026-10-22)
- [x] Squawk 0192: which label? → DD9 ("Knowledge bases" everywhere; operator, 2026-10-22)
- [x] Patch in place or re-mount on Save? → DD5 (patch, Flight 2 DD6)
- [x] Which dirty-tracking model? → DD5 (a value model from control handles, not DOM queries; Flight 2 debrief recommendation 3)
- [x] Who builds the key-value table: this flight or the MCP flight? → DD4 (its core here, with the channel map as first consumer; the masked column in Flight 5)
- [x] Squawk 0093 (same-named knowledge bases)? → DD9 (stays open: it needs an API change)

### Design Decisions

**DD1: Flight 3 is the Library half; Settings becomes Flight 4.** (Operator, 2026-10-22.)
- The mission's Flight 3 bundled two independent clusters of decisions: Library (knowledge, connectors) and Settings (Built-in tools, Appearance, Prompts, Encryption, Date and time, Knowledge indexing). Together they would have been about 20 legs.
- This flight is the Library half. Settings is Flight 4. The MCP server editor becomes Flight 5, Chats and the close to zero Flight 6, and Alignment Flight 7.
- **Groundwork shared by both halves lands here** (DD2), so Flight 4 starts on it.
- **Settings findings carried to Flight 4** (recorded in the mission's flight list, not fixed here):
  - the Built-in tools tile, editor and field-module design;
  - the banner and page-header controls;
  - the `searchList` inline variant;
  - the Settings defects found in planning (the tile toggle name, the Enabled row's double negative, unlinked hints on Knowledge indexing, the Encryption flash timer race);
  - `App.tabs` / `js/tabs.js`, whose last consumer is `tools-grid.js`.
- **The `.tool-enable-switch` rules in `admin.css` stay** while `tools-grid.js`, `tools-editor.js`, `knowledge-settings-page.js` (Flight 4) and `mcp-server-editor.js` (Flight 5) use them. This flight removes only the connector's use.

**DD2: Groundwork first, in one leg with no product-code change.**
- **Split the `contracts` lane.** It holds 1010 tests in 27 files (collect-only, 2026-10-22), past the ~1000 threshold Flight 1 set.
  - `contracts-overlay` is an explicit list: modal, menu, rail, list_pane_chats, search_list, drawer, nav_groups, confirm, focus_after, dialog_rule, modal_dialog_rule, dialog_scroll (about 484 tests).
  - `contracts-controls` is `test_ui_*` minus that list (about 526), so a new contract file never falls into `shared`.
  - `contracts` stays an alias for both. `THE_ONE_REQUIRE_WEBKIT=1` applies to both.
  - **Budgets.** Each lane's wall time plus 25%, rounded to 30 s, measured in a full `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1` `--parallel 3` run (the table's existing basis). A solo lane run would set the budget too low.
  - Update `tests/test_run_tests_lanes.py`, CLAUDE.md's lane table and descriptions, the `--help` text, and the `contracts` mention in `ci/tasks/browser.yml`'s comment.
- **Squawk 0233.** `tests/test_index_asset_cache_busting.py:99` (`assert len(refs) == 93`) becomes an existence-and-order check:
  - every script that `index.html` references exists;
  - each carries one `?v=`;
  - the dependency order holds (core before the factories, factories before the areas).

  A file split no longer edits this test.
- **Squawk 0235.** Write down the editor contracts in `the_one/agents.md`:
  - the tab-handle contract (`destroy` required; `setAgent`, `deactivate`, `setSources` optional; Rules and notes deliberately has no `setAgent`);
  - the `mountSlot` lifecycle;
  - the studio `state` object's fields;
  - the hidden-editor patch on Chats and Settings.

  A unit test pins the `state` key set. A frame-level check asserts that every mounted agent-tab handle has `destroy` (Flight 2 debrief recommendation 2). This flight's editors adopt these contracts, so the documentation comes first. The knowledge-base and connector editor handles gain `destroy` under the same contract in legs 05a and 07a.
- **Unused-selector report.** `scripts/unused_selectors.py` automates Flight 2 leg 11's hand grep:
  - each class token in a given stylesheet;
  - searched across `static/js` (comments stripped), `index.html`, the other stylesheets and `tests/`;
  - it prints the tokens with no user.

  It is a developer tool with no gate. It gets a smoke unit test. Class names built at runtime (`indicator-led--`+state, `connector-setup-steps-list-`+type, `ui-menu-align-`+align, `chip--`, `badge--`) are matched as known prefixes or listed separately as "dynamic, check by hand", never reported as unused.
- **Captures and the ledger.** `scripts/ui_capture.py` gains these surfaces:
  - the Library start page;
  - the knowledge-base `~new` form;
  - the knowledge-base detail with a registered folder:
    - the folder panel expanded with items;
    - the item menu open;
    - the chunks panel;
    - the source panel;
    - search hits;
    - status with a re-index;
    - the danger zone armed;
  - the connector create form (stub type), and the connector edit form with the pairing result, the doctor result and two channel-map rows.

  The seeder registers a scratch folder of a few text files under the capture's scratch home, beside its scratch data directory and never inside it: a folder inside the data directory is refused with 422. The embedding model is bundled, so indexing works under netns. Text that changes from run to run is frozen or masked before capture, so the before and after sets are comparable: `Indexed:` timestamps, search scores, the watch state and the pairing code. The before set is taken before any knowledge or connector file changes. The flight log opens a **visible-differences ledger** (DD7).

**DD3: Split `knowledge-section.js` first, with no change in behaviour.**

It is 1493 lines and moves into modules under `static/js/areas/studio/`. They follow the `providers-section.js` ctx precedent: `App.studio.<module>.create(ctx)` returns a handle, and the module reaches the editor only through `ctx`.

| Module | Contents | Approx. lines |
|---|---|---|
| `knowledge-shared.js` | `_containingFolder`, `_relativeItemPath`, `STATUS_LABELS`, the element helpers | ~90 |
| `knowledge-create.js` | the create form | ~130 |
| `knowledge-detail.js` | the frame: header, fields, dirty tracking, Save/Cancel, the danger zone and the composition. It owns `refreshStatus`/`refreshItems` and returns `{updateStatus, updateItems}` (unchanged) | ~330 |
| `knowledge-folders.js` | add folder, folder panels, Other items, file rows, the item menu, folder delete | ~560 |
| `knowledge-inspect.js` | the chunks and source panels, `{openChunks, openSource}` | ~110 |
| `knowledge-status.js` | the status summary and re-index, `{update}` | ~120 |
| `knowledge-search.js` | search | ~100 |

- **What stays the same.** The public entry points `App.studio.renderKnowledgeCreate` / `App.studio.renderKnowledgeDetail` (returning `{updateStatus, updateItems}`), which `knowledge-glue.js` calls, and the DOM stay byte-identical. Any visible or test change is a defect.
- **Retarget static pins deliberately, never relax them:**
  - the sink allowance;
  - the ownership allowance (rows move to the new files);
  - the asset tests;
  - `verify-serving`;
  - the `index.html` script order;
  - **`tests/test_store_static.py`:**
    - `test_cross_collection_mutations_invalidate_agents` (about `:265`);
    - the three `INVALIDATION_ROWS` entries anchored on `knowledge-section.js` literals (`fetch('/api/knowledge-bases', {`, `method: 'PUT',`, `callbacks.onSaveSuccess(updated)`, about `:281-297`);
    - the `connector-editor.js` rows (about `:331-337`).

    They move again when DD6 changes those calls to `App.api.fetchJson`, so that leg retargets them too;
  - the `docs/ui-control-inventory.md` rows that name `knowledge-section.js` (about `:55`, `:101`, `:118`);
  - the `agents.md` references.
- **Shared state** is `kb` plus `currentFolders`, which the folders module owns. The ctx carries `refreshStatus`, `refreshItems`, `openChunks`/`openSource` and `flash`.
- `renderStatusSummary` is used at `:1222` and declared at `:1295`. It is a hoisted function declaration, documented at `:1285-1289`; only its `summaryEl` variable is a latent ordering hazard, and the status module owns it after the split.
- **Module boundaries and names may vary.** The ≤ 800-line rule and the ctx-only reach may not.

**DD4: New library controls and options, each built and contract-tested before its consumer migrates.**
- **`App.ui.disclosure(opts)`**: a native `<details>`/`<summary>`.
  - Options: `summary` (text or node), `actions` (nodes in the summary whose clicks do not toggle), `open`, `onToggle(open)`, `onFirstOpen(body)` (a lazy body), `testid`, `dataset`, `className`.
  - Returns `{el, summary, body, setOpen, isOpen, setSummary, destroy}`.
  - It owns a new `ui-disclosure-*` class family and never reuses `mcp-tool-*` (the folder panels borrow `.mcp-tool-item`/`-summary`/`-chevron`/`-body` today, `knowledge-section.js` about `:947-1015`). The folder delete's borrowed `kv-remove-row-btn` (about `:984`) becomes a library icon-only button.
  - It owns the chevron, and the rule that summary SVGs take `pointer-events: none` (load-bearing, `studio.css` about `:969`).
  - It also owns the armed-confirm look *on a summary* (today the three `confirm-delete` rows at `studio.css` about `:988-996`), so `App.ui.confirm` arming an action inside a summary styles it through the control.
  - **The node is long-lived:** a caller that rebuilds the body must not rebuild the disclosure. That keeps the open state across polls.
  - **Two looks, both kept:** a `bordered` variant (today's folder-panel look, borrowed from `.mcp-tool-item*` with the ▸ chevron) and a plain variant (today's `.advanced-collapsible` look, used by the self-configuration history). No look changes. `mcp-server-editor.js` keeps the `.mcp-tool-*` rules until Flight 5.
  - **Actions stay inside `<summary>`.** That is today's structure and the `toolRow` precedent, and it is where 0088's armed-on-summary state lives. It is accepted as a library pattern, and the contract tests assert that an action's click and key presses never toggle the disclosure. The VoiceOver check of nested controls in a summary stays the open manual item from Flight 2 (HAT item 11).
  - **Consumers in this flight:**
    - the knowledge-base folder panels and the "Other items" panel (leg 06a);
    - the self-configuration history (`self-config-history.js:80`, a small move). This adds a third consumer, per Flight 2 debrief recommendation 5.
  - `toolRow`'s Overrides may use it internally (leg design decides). `mcp-error.js` and `trace-shell.js` stay for Flights 5-6.
- **`App.ui.keyValueTable(opts)`**: the key-value table's core.
  - Options:
    - `columns: [{key, label, placeholder}]`;
    - `rows: [{...}]`;
    - `addLabel`, `addTestid`;
    - `rowTestid`, `inputTestid(colKey)`, `removeTestid`;
    - `onChange(values)`.
  - Returns `{el, values(), setValues(rows), setError(rowIndex, colKey, text|null), focusRow(i), destroy}`.
  - **The model is keyed and updated on input**, so adding or removing a row never resets another row's typed value. This class of bug is DD8-1.
  - **Accessible names.** Every input is named from its column and row ("Channel id, row 2"). The remove control is an icon-only library button with an accessible name ("Remove row 2").
  - **Owned classes are a new `ui-kv-*` family.** The MCP editor's `.kv-*` rules (`studio.css` about `:433-446` and its own) stay until Flight 5 migrates that editor onto this control. Flight 5 adds the masked/secret column.
- **`App.ui.chip`** gains `dataset` and `tone: 'warning'`. The warning tone is checked by the contrast gate; it replaces `.kb-item-standalone-badge`'s recolour.
- **A new `App.ui.clearableInput(opts)`** (squawk 0100; operator, 2026-10-22), a separate factory so `textInput`'s return type never depends on an option (`copyField` and `secretInput` call `textInput` internally). With it:
  - a small × library button sits inside the field's end, shown only while the field has text;
  - it is named "Clear" plus the field's label;
  - pressing it or Escape clears the field, fires `input` and the `onClear` callback, and keeps focus in the field.

  It behaves the same in Chromium and WebKit; native `type=search` is not used.
  - **Return shape.** It returns `{el, input, clear(), setValue(v), destroy}`, used as `field({control: c.input, host: c.el})` (the `secretInput` host precedent). `setValue` keeps the × visibility in step with a programmatic write.
  - **Escape** clears and stops propagation only while the field has text. On an empty field it passes through, so a surrounding Escape handler still works.
  - **Knowledge-base search:** clearing also clears the results list and the degraded line, the same as today's empty-query path (`knowledge-section.js` about `:1397-1399`).
- **`App.ui.editorShell` gains `save.enabledWhenClean`.** Today the option exists only on `cancel`, and Save is disabled until `setDirty(true)`, a flag that also shows the unsaved caption. Knowledge-base Create is enabled from the first render (`knowledge-section.js` about `:354`), so the create form needs Save enabled while clean without the caption. Contract test: Save is enabled and the caption hidden on a clean create form.
- **`App.ui.editorShell` gains an error `role` option** (`role=alert` on the error span), because DD6 moves the Delete and folder-delete failures there.
- **`App.ui.status` gains `ledTestid`** for the connector's header line. That line keeps its visible text ("Checking connection…", "Not connected"; `connector-editor.js` about `:265-276`), so it does not change visibly (Architect cycle 2).
  - The line is a `status` with text, placed through `afterTitle`:
    - its root carries `connector-status-label`;
    - its LED carries `connector-status-led` through `ledTestid`;
    - the root carries the state as `data-state`.
  - By the existing contract the LED is `aria-hidden` when there is text (`feedback.js` about `:173-185`). So `test_studio_connector_editor.py` (about `:148-153`) moves from the LED's class and aria-label to the line's text and `data-state`.
- **A `more` icon** (horizontal ellipsis) joins `icons.js` for the item-menu trigger.
- **`App.ui.menu`** gets whatever the knowledge-base item menu needs that it lacks. Leg 03b's design compares `buildItemMenu` (`knowledge-section.js:679-762`) with `menu.js` and lists the gaps, for example an icon-only trigger. The menu keeps no permanent document listeners: the knowledge-base menu's capture-phase `click`/`keydown` listeners (`:732-733`) go.
- **The chip-list cascade defect** (DD8-6) is fixed in leg 03c.
- **The cascade-layer rule.** `components.css` is in `@layer components`. `studio.css` and `admin.css` are in `@layer areas`, which is declared after it, so **any** `areas` rule beats **any** `components` rule, whatever its specificity.
  - A rule moved from `studio.css` into a control's owned section loses to any `areas` rule still left on the same element.
  - Every fold-into-owner move in this flight therefore deletes or narrows the area rule in the same change, and a computed-style test confirms the owner's rule now applies.

**DD5: The mount, save and dirty model.**
- **Mount once.** Each editor mounts through `App.ui.util.mountSlot()` (Flight 2 DD2). Identity is (knowledge-base id or connector id, create or edit). A create that succeeds is a new identity and remounts (today's "creating opens the new item", squawk 0101). An async result checks `isCurrent()` before it writes.
- **Save patches in place.** The knowledge-base Save no longer remounts the detail (`knowledge-glue.js` `onSaveSuccess` → `mountKnowledgeDetail`, about `:233-237`). It patches:
  - the shell (title, subtitle, unsaved caption);
  - the fields' stored snapshot;
  - the list row (through `reloadLibrary`).

  Expanded folders, an open chunks or source panel, search results and scroll survive a Save. The connector's edit Save already patches the title. It now also re-masks the token (`secretInput`, like the provider editor) and resets the snapshot.
- **Cancel in edit mode** restores the fields from the stored record by patching. It no longer remounts (`connector-glue.js` about `:75-80`).
- **The glue changes belong to the editor legs, not leg 08.** Mount-once is impossible while the glue clears and remounts. So:
  - **Leg 05a owns `knowledge-glue.js`'s mount path:**
    - `renderKnowledgeSection`'s host clear (`:72`);
    - `reset()` and `renderKnowledgeDetailView` dropping the handle without destroying it;
    - `onSaveSuccess`'s remount (`:233-237`);
    - the Save focus restore through `focusAfter.defer`/`flush` (`:254`, `knowledge-section.js` about `:597`), which becomes a direct restore once there is no remount;
    - the loading and failure sinks (`:189`, `:263`), which become `status` lines.
  - **Leg 07a owns `connector-glue.js`'s:** the host clear (`:47`), the edit Cancel remount (`:75-80`) and the create remount (about `:103`, kept as an identity change).
  - **The host clears stay, but change form.** `knowledge-glue.js:72` and `connector-glue.js:47` become `replaceChildren()`. They run only on an identity change, after the previous handle's `destroy`. The host element is shared with the provider and MCP editors, and `setActiveSection` relies on the glue's clear (`studio.js` about `:521-537`), so it is not simply deleted.
  - **Both editor handles gain `destroy`,** which releases the menu, disclosure and key-value table listeners and the `mountSlot`. The glue calls it on reset, on a section leave and on a new identity: the handle contract leg 01 documents.
- **The connector token keeps its masked round-trip** (security surface). The edit form receives the token masked (`_connector_response` / `_mask_secrets`). An untouched token is sent back masked, so `_looks_masked` keeps the stored secret, and a create with a masked value is refused with 422 (`api.py` about `:4115-4130`). The value model and the payload keep this exactly. Leg 07a pins it with browser tests:
  - an untouched edit Save keeps the stored token;
  - a typed token replaces it;
  - the reveal eye never shows plaintext that the server did not send;
  - after Save the field shows the response's masked value again.
- **Dirty state comes from a value model, not the DOM.** Each editor reads its values from its control handles (`field`/`textInput`/`toggle`/`keyValueTable.values()`) into one plain object and compares it with the stored snapshot object.
  - No `querySelector` reads of form values.
  - **The channel map's dirty state compares its raw rows** (an added empty row is dirty, as today), not the normalized payload.
  - **The connector moves from sticky dirty to snapshot dirty** (`markDirty` on any input, `connector-editor.js:591`): typing a change and reverting it is clean again. This is a behaviour change, recorded in the ledger (DD7).
  - This is Flight 2 debrief recommendation 3, applied to these editors. The agent editor's DOM-string snapshot and squawks 0228/0229 stay as they are.
- **Save is busy during its request.** It calls `editorShell.setBusy(true)` until the response settles. That fixes DD8-2.

**DD6: The canonical form of each surface.**
- **Knowledge-base create** uses `editorShell` with the breadcrumb "Library / Knowledge bases", Cancel and Create (the new `save.enabledWhenClean`, DD4: as today, an empty Create shows "Name is required."). Its fields are `field` and `textInput`/`textarea`, with the length hint as the field hint.
- **Knowledge-base detail** uses:
  - `editorShell`, and `section` for Folders, Status, Search and the danger zone;
  - `field` for Name and Description;
  - `status` for the status summary, the indexer state and the degraded line. These are rewritten by the 5 s poll, so they take `live: 'off'` (the `provider-models.js` about `:749` precedent) and `led: false` where today's line has no LED. They are set only when their text changes. A test pins that a poll tick does not rewrite an unchanged line;
  - `chip` (dataset, warning tone) for the status counts and the standalone badge;
  - `button` for re-index, register folder, view chunks/source and search;
  - `clearableInput` for search;
  - `emptyState` for empty lists;
  - `dangerZone` for Delete.
  - The folder panels and Other items are `disclosure`, and each file row's menu is `App.ui.menu` with the `more` icon trigger.
- **The connector editor** uses:
  - `editorShell`, with the status LED through `afterTitle`;
  - `section` per group;
  - `field` with `textInput`/`select`/`textarea` (the admission lists stay one-per-line textareas);
  - `secretInput` for the token;
  - `toggle` for Enabled;
  - `status` for the doctor and pairing results;
  - `copyField`/`copyButton` for the pairing code (the hand-rolled clipboard code and its `showFlash` go);
  - `keyValueTable` for the channel map (the agent column stays free text);
  - `dangerZone` for Delete.
- **Kept in every editor:**
  - all testids, apart from the changes below, and the `data-field` datasets (66 `[data-field=…]` locators in tests);
  - the router ids;
  - the 0088 armed-confirm invariant on folder summaries;
  - the existing label text, including the title-case danger-zone labels "Delete Knowledge Base" and "Delete Connector". They match "Delete Agent" and "Delete Provider" in the other editors. Create titles ("New Connector", "New knowledge base") are left as they are; any casing change is a HAT question, not a leg's call.
- **Where a library control's shape changes a pinned testid or assertion:**
  - **`connector-status-led` and `connector-status-label`** both stay as testids. They sit on the header status line's LED (through `ledTestid`) and on its root (DD4). `test_studio_connector_editor.py` (about `:148-153`) moves from the LED's class and aria-label to the line's text and `data-state`.
  - **`connector-pairing-code`** moves onto `copyField`'s read-only input, named "Pairing code" through `copyField`'s existing `label`. Two assertions in `test_studio_connector_editor.py` change:
    - about `:234-242`: `text_content()` becomes `input_value()`;
    - about `:243`: `code_text in result.text_content()` becomes a check of the input's value.
  - **The copy button keeps the accessible name "Copy pairing code".** `copyField` gains a `buttonLabel` option for the button's visible text and name. The "Copied" feedback swaps the visible text, and the accessible name follows it as today (no stale aria-label). Added in leg 03b.
  - Any testid that cannot survive gets a retired-table row and a `RETIRED_SELECTORS` entry in the leg that retires it (DD10).
- **0192's scope** is the Library's knowledge group: the router's spoken label, and any Library heading or menu item that says "Knowledge". The agent editor's "Knowledge" *tab* (`agent-editor.js` about `:43`) names an agent's attachments and stays as it is. The HAT asks the operator whether it should change too.
- **Aliases retired in these files:** `App.confirmDelete` (knowledge 2, connector 1), `App.showFlash` (connector 4, knowledge 1) and `App.icon(` (knowledge 1). `_errorMessageFromResponse` and the knowledge copy give way to `App.api.fetchJson`'s error text, where its shape fits.
- **Error feedback is one surface per editor.** Editor-level failures go to the header error (`editorShell.setError`): Save, Delete and folder delete. The knowledge-base **create** form is the exception, and keeps its body error `kb-create-error` (role=alert) as its one surface. It is pinned at `test_flow_studio_library_list.py` (about `:481`) and `test_flow_studio_knowledge_inventory.py` (about `:192`). The knowledge-base detail delete no longer reverts silently. The folder delete keeps its revert and also states the error there rather than flashing.

**DD7: Visible changes, and the ledger.**
- **Approved now:**
  1. The connector's Enabled row becomes the library switch with its label beside it (operator, 2026-10-22).
  2. The knowledge-base search gains its × clear button (0100, operator 2026-10-22).
  3. The router announces "Knowledge bases" for the knowledge group (0192, operator 2026-10-22).
  4. The connector token becomes the masked field with the reveal eye, re-masked after Save.
  5. The danger zones take the canonical trash icons and armed style (Flight 1 DD8).
  6. The doctor and pairing results become status lines (Flight 1 DD8).
  7. The pairing code is shown in a read-only field with its Copy button (`copyField`), where today it is a `<code>` element with a hand-built Copy.
  8. The channel map gains the key-value table's look: column labels and an icon remove button, where today it has a bare "✕" button and no styles.
  9. The agent Tools tab's locked chips get their library fill back, and an invalid chip list gets its red border (DD8-6).
  10. The connector header is a library status line, with the same text and colour states. On a failed automatic probe it reads "Connection check failed" instead of being left blank or wrong (DD8-3).
- **Everything else visible goes in the ledger.** Every leg appends each visible difference it causes to the flight log's **Visible-differences ledger**, with its reason and the DD that allows it. Anything not allowed by a DD is either a defect to fix or an item for the operator at the HAT. The HAT steps are derived from this ledger and from the DD and leg text, with citations, not from memory (Flight 2 debrief).

**DD8: The defects found in planning are fixed, test first.**
1. **The channel map loses typed values.** `renderRows` rebuilds from `rowEntries`, which input never updates (`connector-editor.js` about `:460-498`).
   - Adding or removing a row resets every other row to its stale value.
   - An edit Save does not itself revert the rows. But the stale `rowEntries` survive it, so the next add or remove after a Save brings the old values back, and a second Save stores them.
   - The test-first reproduction covers both sequences.
   - Fixed by `keyValueTable`'s keyed model (leg 07b).
2. **Create can run twice.** Connector Save is not busy during its request (`:673-720`), so a double-click creates two connectors on the same token. Fixed by DD5's `setBusy` (leg 07a). The provider editor has the same gap; it is logged as a squawk and not fixed here (outside the surface).
3. **The doctor ignores `r.ok`.** `:537-538` and `:557` parse any response, so a 404 or 500 shows "undefined: undefined".
   - On the manual "Run doctor", a non-OK response becomes a danger status line with the response's error text.
   - On the automatic header probe (`:556-565`), it sets the header line to danger, "Connection check failed" (a ledger row).
   - Leg 07a.
4. **The poll steals keyboard focus.** `renderAllItems` rebuilds every file row (`:1168`) and deliberately closes any open menu (`closeAnyOpenItemMenu()`, about `:1188`) whenever the items signature changes. The signature changes when the status counts, the chunk count or `content_freshness` move, which happens on many ticks while files index, though not on every tick. That drops focus on a row's menu trigger and closes an open menu.
   - Rows become keyed and patched; a row is rebuilt only when its item is new.
   - The `closeAnyOpenItemMenu()` call on refresh is removed, and a menu closes only when its own row goes away (leg 06a).
5. **Chunks, source and search fetches race.** They have no generation guard (`:783-853`, `:1395-1437`), so a late response can paint the wrong item.
   - Each panel takes a `mountSlot` or generation check.
   - "View chunks/source" moves focus to the opened panel's heading instead of leaving it on a hidden menu item (`returnFocus:false`, `:753,757`).
   - Search is in leg 05b; chunks and source in leg 06b.
6. **The chip-list cascade.** `admin.css` is in `@layer areas`, which outranks `@layer components` (DD4's layer rule). So its `.area-studio .chip-list-editor*` rules (about `:386-440`) beat the library's `.chip-list-editor .chip[data-locked]` and `.chip-list-editor.is-invalid` (`components.css` about `:2244`), whatever their specificity:
   - the agent Tools tab's locked chips get the accent fill;
   - the area `border:` (about `:387`) cancels the invalid border colour.

   `chipList` emits `chip-list-editor` today (`chip-list.js:39`), so there is no library-only class to target.
   - **The fix:** `chipList` gains an owned marker class, and the `admin.css` rules are narrowed with `:not(<marker>)`, so they keep styling only the string-built chips (the MCP editor, Flight 5; the Settings tools editor, Flight 4).
   - The narrowing covers `.area-* .chip-list-input` too, since the library's input uses that class.
   - A computed-style test, in both themes and under both `area-studio` and `area-admin` ancestors, pins the locked fill and the invalid border on a library chip list. It fails on unfixed code (leg 03c).
7. **Suspected: the knowledge-base menu hijacks keys while open.** Its capture-phase `keydown` listener (`:732-733`) may take arrows and Escape away from Ctrl K Jump to. Leg 06b reproduces it first. Either way, `App.ui.menu` replaces the listener.
8. **The channel-map inputs have no accessible names,** and every remove button is "Remove row". Fixed by `keyValueTable` (DD4).

**DD9: Squawks.**
- **Closed in this flight:**
  - **0100** (DD4, leg 05b);
  - **0191** (leg 08): `isLibrarySection` (`library-pane.js:114-117`) and `studio-route.js` (about `:186`) derive from `LIBRARY_GROUPS` (`:60`), the one table.
    - `LIBRARY_GROUPS` is declared inside `libraryPane`'s `create(ctx)` closure, and `studio-route.js` loads before `library-pane.js` (`index.html` about `:104` against `:106`).
    - So the table is hoisted to module scope and exposed (for example `App.studio.libraryGroups`), and `studio-route.js` reads it lazily at call time, never at load.
  - **0192** (leg 08): "Knowledge bases" in `router.js` `LIBRARY_LABELS` (`:440`), plus the pins at `tests/browser/test_router_announce.py` (about `:201`) and `test_flow_studio_library_list.py` (about `:507`, `:1276`);
  - **0233** and **0235** (DD2, leg 01).
- **Stays open:** **0093.** The knowledge-base list rows show the name and the agent count, and `GET /api/knowledge-bases` returns no folder path. Telling same-named bases apart needs an API change, which belongs in a squawk on `main`, not this flight.
- **Logged at planning:** squawk 0236, the provider editor's Save is not busy during its request (DD8-2's twin).
- **Not in this flight's path:** 0228, 0229, 0230, 0232, 0222/0234.

**DD10: Tests, lanes and specs.**
- **Keep every testid.** When a `_btn(…)` button becomes `App.ui.button({testid})`, its row moves from the registry's manual-exceptions table (`docs/ui-testid-registry.md` about `:413`) to the literal table. Any retired id gets a row in the retired table plus a `RETIRED_SELECTORS` entry (`tests/test_nav_helper.py`).
- **Selectors.** Tests that select retired classes move to role, testid or label locators. Each leg pastes, at design time, its grep of class selectors and text pins across `tests/`, `scripts/`, the Makefile, `docs/ui-testid-registry.md` and `tests/behavior/`. Known ones:
  - `.kb-folder-path`, `.kb-folder-summary`, `.kb-item-path`, `.kb-folder-watch`, `.kb-chunk-seq`, `.kb-search-hit-score` and summary clicks (`test_flow_studio_knowledge_inventory.py`). `.kv-remove-row-btn` selectors are only in `test_flow_studio_mcp_editor.py` (about `:663`, `:710`), which is untouched;
  - `.channel-map-channel/-agent` (`test_flow_studio_library_list.py:1386-1402`);
  - `.editor-title` (connector tests).
- **Lanes.** A new knowledge or connector test file is added to `library_pat` in `scripts/run-tests.sh`. The `library` lane (270 s of 300 at the Flight 2 debrief) is re-measured at leg 09. Past 1.3× its budget, it splits into `library` and `knowledge` by the same rule as Flight 2's `agents` split.
- **Lanes each leg runs.** The pins these surfaces touch live in more than the `library` lane:
  - **`mcp`:** `test_flow_studio_library_list.py` (the channel-map test about `:1384-1402`, the 0192 announcer pins at `:507` and `:1276`, the knowledge-base create pins about `:481`);
  - **`routing`:** `test_router_announce.py` (0192);
  - **`agent-tabs`:** the self-configuration history (the disclosure, leg 03a); `tool-override-fields.js`, the only library `chipList` consumer (leg 03c);
  - **`routing`** for legs 05a, 05b, 06a, 07a and 07b: the mount and dirty-guard pins in `test_router_items.py`, `test_router_guard.py`, `test_nav_guard.py` and `test_store_library.py`;
  - **`shared`** for the same legs: `test_flow_studio_navigation.py`, `test_agents_library_isolation.py` (the knowledge poll stops), `test_flow_jump_to.py`, `test_flow_studio_loadall_error.py`;
  - **`settings`** and **`mcp`** for leg 03c: the narrowed area chip rules must keep styling the string-built chips;
  - **`contracts-*`:** every control leg.

  Each leg spec lists the lanes it runs, and a leg that changes a control also runs both contracts lanes with `THE_ONE_REQUIRE_WEBKIT=1`. Each surface leg also reports the `library` lane's time against its budget. It starts at 90%, so a split may come before leg 09.
- **Behavior specs.**
  - `list-and-detail.md` (steps 10-18), `kb-studio-round-trip.md` and `stub-connector-round-trip.md` are amended in the leg that breaks a step's selector or text.
  - They run on a dev instance at mission close (the mission criterion). The HAT walks the same flows.
  - `jump-to-palette.md` step 7 keeps `knowledge-base-card` and `connector-card`.
- **Contract additions** (the Flight 2 DD11 rule): each new size-bearing control gets computed-size assertions against its canonical neighbours. Each composite-role control gets a role-structure assertion.

**DD11: Standing leg rules** (Flight 2 debrief recommendation 4). Every leg spec carries these:
- **No consumer CSS on library internals and no `[data-testid]` style hooks.** A needed look becomes a library variant option, added in a control leg (03a, 03b or 04). A surface or close-out leg that finds it needs a library option is re-tiered high, and the option gets its own catalogue row and contract test in that leg.
- **Mind the cascade layers.** Moving a rule from an area stylesheet into a control's owned section deletes or narrows the area rule in the same change, and a computed-style check proves the owner's rule applies (DD4).
  - The check mounts the control under an area ancestor (`host.className = 'area-studio'`, and `'area-admin'` where an admin rule applies; precedent `test_ui_chip_list_contract.py` about `:290-292`), or tests on the real surface.
  - The plain harness root has no area ancestor, so a check there passes even on unfixed code.
- **Append to the ledger.** Each leg appends its visible differences to the ledger (DD7), and a short in-progress log line at each internal checkpoint, so an interrupted Developer can be resumed (Flight 2 leg 11).
- **Retarget pins, never relax them.** A static pin is retargeted deliberately and never loosened. Each leg retargets the pins its own moved calls break (for example the `test_store_static.py` rows: the knowledge-base save in 05a, the delete in 05b, the connector rows in 07a and 07b). A leg that adds a key to the studio `state` updates leg 01's key-set pin.

### Citation Audit
Verified at `08562ec` (planning surveys and Flight Director spot-checks, 2026-10-22):

| Citation | Status |
|---|---|
| `connector-editor.js:460-498` `renderRows` rebuilds from `rowEntries`; input only calls `markDirty` (DD8-1) | verified (FD read) |
| `connector-editor.js:537-560` doctor `.then(r => r.json())` with no `r.ok` check, twice (DD8-3) | verified (FD read) |
| `connector-editor.js:673-690` Save: no busy state; `_errorMessageFromResponse` at `:656` (DD8-2, DD6) | verified (FD read) |
| `connector-editor.js:431-437,697` `App.showFlash` ×4; `:569` `App.confirmDelete`; `:591` `markDirty` (DD5, DD6) | verified (grep) |
| `knowledge-section.js:679` `buildItemMenu`; `:732-733` capture-phase `document.addEventListener('click'/'keydown', …, true)` (DD4, DD8-7) | verified (grep) |
| `knowledge-glue.js:233-237` `onSaveSuccess` → `mountKnowledgeDetail(updatedKb)` (DD5) | verified (FD read) |
| `ui/editor.js:51-63` `cancel.enabledWhenClean`, `setBusy`, `setError` exist; **`save.enabledWhenClean` does not** (Save disabled until `setDirty(true)`) (DD4, DD5, DD6) | verified (grep); corrected at Architect review: `save.enabledWhenClean` is a new option (DD4) |
| `knowledge-glue.js:72,189,254,263`; `connector-glue.js:47,75-80,103` host clears, remounts, sinks (DD5) | verified (Architect review) |
| `api.py` about `:4115-4130` masked-token create refusal; `_looks_masked` preserve (DD5) | verified (Architect review) |
| `tests/test_store_static.py` about `:265,281-297,331-337` pin `knowledge-section.js` and `connector-editor.js` literals (DD3) | verified (Architect review) |
| `ui/feedback.js:145,195-210` `status` states include `pending`; `chip` tones only `neutral`/`danger`, no `dataset` (DD4) | verified (grep) |
| `icons.js` has no `more`/ellipsis icon (DD4) | verified (grep) |
| `self-config-history.js:80` native `<details>` (DD4) | verified (grep) |
| `router.js:440` `LIBRARY_LABELS.knowledge: 'Knowledge'` (DD9) | verified (FD read) |
| `library-pane.js:60` `LIBRARY_GROUPS`; `:114-117` hand-listed `isLibrarySection` (DD9) | verified (FD read) |
| `tests/test_index_asset_cache_busting.py:99` `assert len(refs) == 93` (DD2) | verified (grep) |
| `HTML_SINK_ALLOWANCE` (`tests/test_ui_guards.py:149-159`): connector-editor 3, connector-glue 1, knowledge-glue 3, mcp-glue 1 (Objective) | verified (FD read) |
| `OWNERSHIP_ALLOWANCE`: knowledge-section 27 rows / 62 uses, connector-editor 26 / 40; total 187 / 409 (Criteria) | verified (FD tally) |
| `admin.css` about `:386-440` against `components.css` about `:2244` chip-list cascade (DD8-6) | effect verified; **mechanism corrected** at Architect review: `@layer areas` outranks `@layer components`, not a specificity tie. `chip-list.js:39` emits `chip-list-editor` (no library-only class) |
| `contracts` lane: 1010 tests in 27 files (DD2) | verified (survey collect-only) |

### Prerequisites
- [x] Flight 2 is completed and merged (`main` at `08562ec`).
- [ ] The branch `flight/03-knowledge-and-connectors-on-the-library` is created from `main` at flight start.
- [x] The operator's decisions (DD1, DD4, DD7, DD9) were taken on 2026-10-22.
- [ ] WebKit userland and `THE_ONE_TEST_NETNS=1` work. Re-verify at the start of **every** leg that runs browser tests.
- [ ] The before captures are taken in leg 01, before any knowledge or connector file changes.

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
Groundwork, restructure, controls, surfaces, then close: the order Flights 1 and 2 proved.
- **Leg 01:** splits the contracts lane, fixes the script-count pin, writes the editor contracts down, adds the unused-selector report, extends the capture tool and takes the before set. No product code changes.
- **Leg 02:** splits `knowledge-section.js` with no behaviour change.
- **Legs 03a-04:** build the controls in the harness, and fix the chip cascade (03c).
- **Legs 05a-07b:** move the knowledge-base create and detail editor, its folders, and the connector editor onto them, together with each editor's glue mount path. They fix the DD8 defects test-first and remove each file's allowance rows and sinks.
- **Leg 08:** cleans the pane and the `mcp-glue.js` clear, and closes 0191 and 0192.
- **Leg 09:** closes the counts, takes the after captures, re-budgets the lanes and updates the docs.
- **Leg 10:** the HAT.

### Checkpoints
- [ ] The contracts lane is split and the script pin is fixed; editor contracts are documented; before captures taken; the gate is green.
- [ ] `knowledge-section.js` is split into modules of ≤ 800 lines with no test-behaviour change; full gate green.
- [ ] The disclosure, the key-value table and the options are contract-tested in both engines; the chip cascade is fixed.
- [ ] The knowledge-base frame is mounted once through its glue and patches in place on Save.
- [ ] The knowledge-base folders are on the library; the 0088 invariant holds; DD8-4/5/7 fixed.
- [ ] The connector frame is on the library and its token keeps the masked round-trip; DD8-2/3 fixed.
- [ ] The connector sections are on the library; DD8-1/8 fixed.
- [ ] Every knowledge, connector and glue file is at zero sinks and zero allowance rows; budgets re-measured; full gate green.
- [ ] HAT passed.

### Adaptation Criteria

**Divert if**:
- The `knowledge-section.js` split cannot stay behaviour-free (a test changes behaviour, not just a path pin): stop and re-plan the boundary.
- Patching in place on Save breaks the 0088 armed-confirm invariant or the folder poll in a way that is not a local fix: raise it before choosing a remount.
- A server-side change turns out to be needed (for example for DD8-3's error text): raise it as its own question, as Flight 2 did with squawk 0223 on `main`.

**Acceptable variations**:
- Module boundaries and names inside the DD3 table.
- Option names on the new controls.
- Splitting a leg further at its design review (never merging legs: the Flight 2 debrief's lesson runs the other way).
- A `library` lane split.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [ ] `groundwork-and-before-set` (01): the contracts lane split, squawk 0233, squawk 0235 docs and the `state` key pin, `scripts/unused_selectors.py`, the Library capture surfaces, the before set, and the opened ledger. No product code changes (DD2).
- [ ] `knowledge-split` (02): `knowledge-section.js` into the DD3 modules, behaviour-free; pins retargeted; full gate.
- [ ] `disclosure` (03a): `App.ui.disclosure` with the bordered and plain variants, summary actions and the armed-on-summary look; the self-configuration history as a consumer (runs `agent-tabs`, which is at 94% of its budget); catalogue row and contract tests (DD4).
- [ ] `control-options` (03b): `chip` `dataset`/`warning`, `App.ui.clearableInput`, the `more` icon, the menu gaps, `editorShell` `save.enabledWhenClean` and error `role`, `status` `ledTestid` and `data-state`, `copyField` `buttonLabel`; catalogue rows and contract tests (DD4).
- [ ] `chip-cascade` (03c): the `chipList` marker class and the narrowed `admin.css` area rules, test-first under area ancestors in both themes. Runs `agent-tabs`, `settings`, `mcp` and both contracts lanes (DD8-6). Split from 03b at Architect cycle 2: CSS across three lanes.
- [ ] `key-value-table` (04): `App.ui.keyValueTable` core with the keyed model and accessible names; catalogue row; contract tests with size and role assertions (DD4).
- [ ] `knowledge-frame` (05a): the create and detail frames on `editorShell` through `mountSlot`, the fields, the value-model dirty state, Save patches in place, and the handle's `destroy`. Owns `knowledge-glue.js`'s mount path and its three sinks (DD5). Retargets the pins its moved calls break (DD11).
- [ ] `knowledge-status-search-danger` (05b): Status and re-index on `status`/`chip`/`button`; Search with `clearableInput` (0100) and its generation guard (DD8-5); the danger zone and the header error surface (DD6); alias calls retired.
- [ ] `knowledge-folder-panels` (06a): `disclosure` panels and Other items; keyed, focus-preserving rows with no menu close on refresh (DD8-4); chips patched through their own nodes; the 0088 invariant kept (summaries are never rewritten while a delete is armed); the folder delete error.
- [ ] `knowledge-item-menu-and-inspect` (06b): the item menu on `App.ui.menu` (DD8-7 test first, the capture listeners gone); chunks and source with generation guards and focus on the opened panel (DD8-5).
- [ ] `connector-frame` (07a), **tier high, a security surface**: `editorShell` through `mountSlot`; fields; the `secretInput` masked round-trip pinned by tests (DD5); the Enabled `toggle`; the header status line (`ledTestid`, visible text kept); value-model dirty state; `setBusy` (DD8-2); doctor non-OK (DD8-3); the handle's `destroy`. Owns `connector-glue.js`'s mount path and its sink.
- [ ] `connector-sections` (07b): pairing with `copyField`, the channel map on `keyValueTable` (DD8-1 for both sequences, DD8-8), admission fields, the danger zone; alias calls retired.
- [ ] `library-pane-and-labels` (08): the `mcp-glue.js` clear; squawk 0191 (the hoisted `LIBRARY_GROUPS`); squawk 0192 ("Knowledge bases", with the `routing` and `mcp` lane pins).
- [ ] `library-close` (09): zero counts on every Library-half file, the unused-selector report for `studio.css`, the single-consumer option recheck, after captures, the `library` lane re-budget, catalogue/registry/docs (CLAUDE.md, `agents.md`), and the behavior-spec amendments check.
- [ ] `flight-hat` *(optional; the operator wants one per flight)*: the operator walks the knowledge-base and connector editors in both themes. The steps come from the ledger and the DD7 list, and the operator approves the capture set.

> Leg design greps every moved path, renamed class and retired selector across `tests/`, `scripts/`, `Makefile`, `docs/ui-testid-registry.md` and `tests/behavior/`, and pastes the hits into the leg.

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing
- [ ] Documentation updated

### Verification
- `wc -l` shows every knowledge module at ≤ 800 lines.
- In `tests/_ui_ownership_allowance.py` and `HTML_SINK_ALLOWANCE`, these files have no rows: the knowledge modules, `knowledge-glue.js`, `connector-editor.js`, `connector-glue.js`, `mcp-glue.js` and `library-pane.js`.
- `make test-unit` passes, and `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 TEST_TIMEOUT=3600 make gate` is green with the new lanes and budgets.
- HAT: the operator approves the capture set and the ledger's differences.
