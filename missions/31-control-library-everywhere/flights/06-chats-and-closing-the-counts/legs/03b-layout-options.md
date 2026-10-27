# Leg: layout-options

**Status**: ready
**Flight**: [Chats, and closing every count to zero](../flight.md)

## Objective
Retire the area-CSS restyles of library controls in `chat.css` and `studio.css`, and `agent-picker.js`'s footer class, by giving each look a library home:
- a `searchList` chooser variant;
- the search list's meta truncating before its label (A9);
- the active row kept by identity across a data refresh (D4, squawk 0185);
- a drawer option and a modal option;
- base-rule moves for the list pane, badge and tab panel;
- a section inset and a field-width option.

When the leg ends, `chat.css` and `studio.css` hold no ownership-allowance row.

## Context
- **Flight decisions:** DD6 (the option table), DD7 (A9, D4; ledger rows 9 and 32), DD13 (standing rules) and DD15 (re-author `jump-to-palette` here).
- **The 12 area-CSS rows and their rules** (`tests/_ui_ownership_allowance.py`):

  | Row | Rule today | Library home |
  |---|---|---|
  | `chat.css` `ui-search-list` | `:25` `.agent-picker-body > .ui-search-list { gap: 0; }` | `searchList` `variant: 'chooser'` |
  | `chat.css` `ui-search-list-field` ×2 | `:26` `… .ui-search-list-field { padding: 0 20px 12px; }`; `:27` the field input inside it | the chooser variant |
  | `chat.css` `field-input` | `:27-30` `.agent-picker-body .ui-search-list-field .field-input { height: 40px; font-size: var(--font-size-body-lg); }` | the chooser variant (it owns the large field) |
  | `chat.css` `ui-search-list-listbox` | `:31-34` padding `0 12px 12px`, a top hairline | the chooser variant |
  | `chat.css` `ui-search-list-empty` | `:35` top hairline | the chooser variant |
  | `chat.css` `ui-drawer-header` | `:87` `#chat-drawer.ui-drawer--overlay .ui-drawer-header { padding-right: 56px; }` | `App.ui.drawer` `reserveHeaderEnd: true` (padding only in overlay mode) |
  | `chat.css` `ui-list-pane` | `:9` `.sidebar-panel.area-chat > .ui-list-pane { flex: 1; min-height: 0; }` | the `.ui-list-pane` base rule (`flex: 1 1 0`, basis 0 as today) |
  | `chat.css` `badge` | `:117` `.chat-drawer-head .badge { flex-shrink: 0; }` | the `.badge` base rule, after an audit (below) |
  | `studio.css` `ui-list-pane` ×2 | `:12-13` `.studio-agents-list > .ui-list-pane, .studio-library-list > .ui-list-pane { flex: 1; }` | the `.ui-list-pane` base rule |
  | `studio.css` `tabpanel` | `:24` `.area-studio .tabpanel { padding: 16px 20px 80px; }` | the `.tabpanel` library rule (`components.css:1223`) |
  | `studio.css` `editor-section` | `:32` `.area-studio .editor-section { padding-left: 20px; padding-right: 20px; }`, which `components.css:1457` beats with `!important` for `--flush` | **a default flip:** the base `.editor-section` takes `padding: 12px 20px` (design review). `App.ui.section` and `editorShell` already take `inset: 'none'` (`editor-section--flush`, `ui/editor.js:90`, `:322-327`), which every Settings page and `tools-editor.js` passes. `--flush` then wins by order at equal specificity, so the `!important` goes. No studio call site changes, and `provider-editor.js` is untouched |
  | `studio.css` `field-input` ×2 | `:45` `.field-model-wrap .field-input { flex: 1; }` (**a no-op**: `.field-input` already has `flex: 1`, `components.css:135-137`, and `App.ui.select` carries `field-input`); `:472` `.self-configuration-external-grant .field-input { flex: 1; min-width: 160px; }` (only `min-width` is new) | `:45` is **deleted** with no option. `:472` uses a new `textInput` `minWidth` option (px, set on the element by the library). No `width: 'fill'` (design review) |

  Re-verify each line before editing; leg 03a may have shifted `components.css`.
- **`agent-picker.js:180`:** `el('span', {className: 'modal-dialog-footer-end', text: 'Enter to start'})`. `ui/modal.js` documents the class as the caller's tool. It becomes an `App.ui.modal` `footerEnd: Node|string` option.
- **The search list** (`js/ui/search-list.js`):
  - `inline` is today's only variant flag (`ui-search-list--inline`);
  - `keepScroll` (inline only) remembers the active id across a refresh with the same query (`:122`, `:227`);
  - otherwise `render()` resets `activeIndex` (`:230`);
  - `.ui-search-list-meta` is `flex-shrink: 0; white-space: nowrap` (`components.css:1046-1051`), so a long meta squeezes the label (A9);
  - Jump to (`js/jump-to.js`) is a shell composition with its own `.jump-to-body` rules in `components.css:1806-1837` (including its own `gap: 0` copy at `:1812`). Its refresh code keeps the active row only when the user has moved off the first row (`jump-to.js:302-312`, M25 DD10).
- **Squawk 0185** (D4 (a), the operator's choice, 2026-10-26: "keep the highlighted row by identity across refreshes" rather than "the first row follows the data"):
  - **The rule:** a data refresh with the query unchanged keeps the active option by identity when it is still present, **whether or not the user moved**, falling back to the first option. A query change still activates the first match.
  - **What this supersedes.** The rule replaces M25 DD10's "the first row follows the data while it is active" (`jump-to.js:304-312`, `lastFirstId`). On a cold Jump to open, the row highlighted before `sessions` lands stays highlighted, and the newest chat no longer takes over. That is the squawk's point: the highlighted row is the one Enter picks.
  - **The pinned tests and spec steps to rewrite deliberately** (a contract change, not a relaxation):
    - `tests/browser/test_flow_jump_to.py:542` ("The first row is active once every collection has arrived (DD10)");
    - `test_ui_search_list_contract.py::test_each_source_call_makes_the_first_option_active` (`:291-303`), which arrow-keys, refreshes and expects index 0;
    - `test_without_keep_scroll_a_refresh_resets` (`:696`);
    - `tests/behavior/jump-to-palette.md` steps 2 and 3.

    `test_keep_scroll_resets_on_a_changed_query_or_a_vanished_id` (`:677`) stays valid.
  - **Identity is `(group index, id)`.** The picker's "Recently used" and "All agents" groups reuse item ids, so an id alone would snap a user on All agents' row 3 up to Recently used.
  - **Scroll after a keep:** `scrollActiveIntoView('nearest')`, not restoring `scrollTop`. Rows inserted above would otherwise push the kept row out of view.
  - The inline variant's `keepScroll` already does this for its own case. **Unify** them, never run two keep rules. Jump to's `lastFirstId` logic is removed.
  - The change reaches every `searchList`: the agent picker, Jump to and the Date and time zone list.
- **The audits this leg needs:**
  - **`.badge` with `flex-shrink: 0`:** list every place a badge sits in a flex container (the Library and Agents list rows, tiles, the drawer and pane, the notes tab, the provider editor's type badge). Confirm that none relies on the badge shrinking. If one does, use a `noShrink` badge option instead of the base rule, and record the choice.
  - **`.ui-list-pane` with `flex: 1 1 auto`:** all three hosts want it. Check that no other host (for example a contract-test harness or a dialog) would grow unexpectedly.
  - **The section inset:** list the `.editor-section`s under `.area-studio` (the agent editor's tabs, the Library editors, the knowledge editors) and those outside it (Settings). Choose the option so the studio editors keep 20px and Settings keeps 0, then delete the `!important` at `components.css:1457` if nothing needs it any more.
- **`App.ui.field` / `textInput`'s `width` option** accepts only `'short'` and throws otherwise (`ui/field.js:16`, `:40`). The new `minWidth` option sits beside it, with the doc comment updated. `components.css:1557` (`.api-key-wrap .field-input { flex: 1 }`) is likewise redundant; delete it only if `api-key-wrap` still has a user.
- **`provider-editor.js` has zero line headroom** (896/896). It is not expected to change here; if the section-inset option touches it, add no net lines.

## Inputs
- Leg 03a landed: the flash contract, `badge.live`, the copy confirmation and the note flag.

## Outputs
- **`App.ui.searchList` `variant: 'chooser'`:**
  - a root modifier class (for example `ui-search-list--chooser`), owned in the catalogue row;
  - its rules in `components.css` carry today's picker look: zero gap, the field band padding, the 40px large field, the list padding and hairline, the empty hairline;
  - the agent picker passes it, and its five `chat.css` child-selector rules are deleted. `.agent-picker-body` itself (flex, the 624px cap) is not a guard-owned class and stays area layout in `chat.css`. The variant owns only the paddings, the field and the hairlines, and depends on no area ancestor;
  - Jump to may adopt it for its `gap: 0` if the result is identical; otherwise it stays a shell composition, recorded either way.
- **A9:** `.ui-search-list-meta` truncates with an ellipsis before the label shrinks. The label is the identifier and keeps its full width until the meta has given up its room. Rows with short meta keep today's layout. **The approach** (design review: the obvious one fails, because `.ui-search-list-text` is `flex: 1` with basis 0):
  - `.ui-search-list-text { flex: 1 0 auto; min-width: 0; }`;
  - `.ui-search-list-description` with `contain: inline-size` (or `width: 0; min-width: 100%`), so a long description adds nothing to the text's intrinsic width;
  - `.ui-search-list-meta { flex: 0 1 auto; min-width: 64px; overflow: hidden; text-overflow: ellipsis; }`, the 64px floor so it never collapses to nothing.

  Check A9 in Jump to's "where" meta too, against its `.jump-to-body .ui-search-list-row` overrides.
- **D4 (squawk 0185):** the keep-by-id rule for every `searchList`, plus Jump to's simplified refresh. The squawk is closed in this leg's flight-log entry, with its corrective action and verification (sign-off at the flight-end review).
- **`App.ui.drawer` `reserveHeaderEnd: true`:** a modifier class on the drawer root (for example `ui-drawer--reserve-end`; the drawer takes a static `opts.el`), with the rule `.ui-drawer--overlay.ui-drawer--reserve-end .ui-drawer-header { padding-right: 56px; }`. The doc comment says the 56px is the room for a 32px toggle placed over the drawer's header (16 + 32 + 8). The agent drawer passes it, and the `chat.css:87` rule is deleted.
- **`App.ui.modal` `footerEnd: Node|string`:** the modal appends a `.modal-dialog-footer-end` span inside `.modal-dialog-footer`, after any `footer` content, and creates the footer row when only `footerEnd` is given. It is allowed in every layout. `agent-picker.js` passes "Enter to start". `modal-dialog-footer-end` stays as a library-internal owned class, so `test_flow_chat_picker.py:147` still resolves. `test_ui_modal_contract.py:451`/`:487`, which build the class by hand, move to the option. `modal.js`'s doc comment (`:43-46`), the catalogue and `jump-to.js:364`'s comment are updated.
- **Base rules:**
  - `.ui-list-pane { flex: 1 1 0; }` (the same as today's `flex: 1`) with `min-height: 0` kept, plus a computed-style check on a contract-harness host;
  - `.badge { flex-shrink: 0; }`. The design review's audit found no badge relying on shrinking: `.badge` is `inline-block; white-space: nowrap`, the tile and list-pane wrappers are already `flex: none` or `flex-shrink: 0`, and dots gain from it. The Developer confirms the audit and records it;
  - `.tabpanel` takes the agent editor's padding (`16px 20px 80px`), while `ui-tabs--flush` stays 0.

  The `chat.css:9`, `chat.css:117`, `studio.css:12-13` and `studio.css:24` rules are deleted.
- **The section inset:** the default flip above. Check first that no `.editor-section` outside `.area-studio` lacks `inset: 'none'`. `App.ui.dangerZone`'s sections are all in studio editors. `studio.css:32` and the `!important` are deleted. `.editor-section + .editor-section` and `--stack` touch no side padding.
- **Field:** `studio.css:45` is deleted; `studio.css:472` becomes `App.ui.textInput({ …, minWidth: 160 })`.
- **The allowance:** every `css/chat.css` and `css/studio.css` row is gone, along with the `agent-picker.js` row. `TOTAL_USES` is lowered to match. `MOVES` keeps leg 02's entries.
- **Catalogue:** the Search list row (the chooser variant, A9, the keep-by-id rule), Drawer, Modal, List pane, Badge, Tabs, Section / Editor shell and Field rows, with the new owned classes.
- **Behavior spec:** `tests/behavior/jump-to-palette.md` is re-read for D4. Any step whose expected result assumed the first row follows the data is re-authored.
- **Ledger rows 9 and 32** confirmed in the flight log.

## Acceptance Criteria
- [ ] `tests/_ui_ownership_allowance.py` has no `css/chat.css`, `css/studio.css` or `js/areas/chat/agent-picker.js` row, and `tests/test_ui_ownership.py` passes.
- [ ] **No visible change outside A9 and D4.** The capture tool's picker, drawer (1280 push and 1024 overlay), Chats list, agent editor tabs, the Library editors and a Settings page are compared against the before set (or against a capture from the leg's start for surfaces outside it) with PIL. Any difference maps to ledger row 9, or is fixed.
- [ ] **A9 (contract test, both engines; it also covers a long description with a short meta):**
  - with a 390px meta and a 30-character label in a 640px chooser, the label's full text is visible (its `scrollWidth` is no more than its `clientWidth`) and the meta shows an ellipsis;
  - with a short meta, the row's layout matches the old one (label and meta widths within 1px).
- [ ] **D4 (contract test, both engines):**
  - after the user arrow-keys to row 3, a `refresh()` with an unchanged query whose new data adds a row above keeps row 3's item active, and in view;
  - **a cold refresh with the user not having moved** also keeps the highlighted item (DD10 superseded);
  - with duplicate ids in two groups, the active row stays in its own group;
  - when the active item disappears, the first option becomes active;
  - a query change activates the first match.

  The pinned tests and `jump-to-palette.md` steps 2 and 3 are rewritten, as listed in Context. The Date and time zone list keeps its behaviour (`settings` lane).
- [ ] **Each option has a contract test in both engines:**
  - `reserveHeaderEnd` adds its padding in overlay mode only, with none in push mode;
  - `footerEnd` places its node at the footer's end, with and without `footer`;
  - `minWidth` sets the input's minimum width;
  - the chooser variant's field is 40px;
  - a default section has 20px side padding and `inset: 'none'` has 0.
- [ ] **The audits** (badge, list pane, section inset) are recorded in the flight log with their call-site lists and choices.
- [ ] **Guards:** `tests/test_ui_emitted_classes.py`, `tests/test_ui_control_inventory.py`, `tests/test_ui_library_source.py`, `tests/test_ui_guards.py`, `tests/test_token_definitions.py`, `tests/test_design_tokens_a11y.py` and `tests/test_area_module_size.py` pass.
- [ ] **Lanes:**
  - `contracts-controls` and `contracts-overlay` (`THE_ONE_REQUIRE_WEBKIT=1`);
  - `chats`, `chats-transcript`, `agents`, `agent-tabs`, `library`, `knowledge`, `mcp`, `mcp-connection`, `providers`, `settings`, `settings-tools`, `routing` and `shared` (Jump to).

  Run them at most three at a time.
- [ ] `make test-unit` passes after the browser runs. `ruff` is clean.

## Verification Steps
1. The unit guards (list above), `-q -x --timeout 120`.
2. The contract lanes with `THE_ONE_REQUIRE_WEBKIT=1 THE_ONE_TEST_NETNS=1`, then the area lanes.
3. **Captures:** `THE_ONE_TEST_NETNS=1 .venv/bin/python scripts/ui_capture.py --out <scratch> --surfaces <picker, drawer, Chats list, agent editor, Library editors, a Settings page>`, compared with the before set (PIL `ImageChops`) for the chat surfaces, and with a leg-start capture for the rest.
4. `make test-unit`; `ruff check`; `ruff format --check`.

## Implementation Guidance
1. **Take a leg-start capture first** of the non-chat surfaces this leg touches (the agent editor, the Library editors, a Settings page), since the before set has only some of them.
2. **The audits,** written into the flight log before any rule moves.
3. **The search list:** the chooser variant, then A9, then D4, each test first, then the picker and Jump to.
4. **The drawer and modal options,** then their consumers.
5. **The base rules and the section inset,** with a capture comparison after each.
6. **Field width:** the two studio inputs.
7. **The allowance, catalogue, the spec re-read,** then the lanes and `make test-unit`.

## Edge Cases
- **The cascade.** Rules moved from `@layer areas` (scoped, for example, by `.agent-picker-body`) into `@layer components` lose a layer and a class of specificity. A computed-style check under the real host proves each owner rule applies (DD13).
- **The picker's `<dialog>` lives under `<body>`,** outside `.area-chat`. The chooser variant must not depend on an area ancestor.
- **The `--flush` `!important` trap** (Flight 4 debrief): if the section inset becomes a library option, `editor-section--flush` must still zero it without `!important`, or keep `!important` with the reason recorded.
- **D4 with grouped results:** the active id must be found across groups (Jump to's empty-query mix has several groups).
- **D4 and `keepScroll`:** the inline variant's existing behaviour is the same rule. Unify them, never run two keep rules.
- **Truncation and accessible names:** an ellipsized meta still exposes its full text to assistive technology (the option's name includes it). Add a `title` with the full meta only if the row's accessible name lacks it.

## Files Affected
- `the_one/interfaces/web/static/js/ui/search-list.js`, `js/ui/drawer.js`, `js/ui/modal.js`, `js/ui/field.js`, `js/ui/page.js` or `js/ui/editor.js` (the section inset), `js/jump-to.js`.
- `js/areas/chat/agent-picker.js`, `js/areas/chat/agent-drawer.js`, the studio editors that set the inset, `js/areas/studio/general-tab.js` and the self-configuration tab (`width: 'fill'`).
- `css/components.css`, `css/chat.css`, `css/studio.css`.
- `tests/browser/test_ui_search_list_contract.py`, `test_ui_drawer_contract.py`, `test_ui_modal_contract.py`, `test_ui_field_contract.py` (or its equivalent), and the section or editor contract test.
- `tests/_ui_ownership_allowance.py`, `docs/ui-control-inventory.md`, `tests/behavior/jump-to-palette.md`, `squawks/0185-jump-to-active-row-moves-under-user.md`, the flight log.

## Citation Audit
- `css/chat.css:9`, `:25-35` (FD read) and `:87`, `:117` (code survey §2.2).
- `css/studio.css:12-13`, `:24`, `:32`, `:45` (FD read) and `:472` (code survey).
- `css/components.css:1046-1051` (meta), `:1223` (`.tabpanel`), `:1451-1458` (`.editor-section`, `--flush` `!important`) and `:1806-1837` (Jump to). FD read.
- `js/ui/search-list.js:122`, `:227`, `:230` (`keepScroll`, `restoreId`, the reset). FD grep.
- `js/ui/field.js:16`, `:40` (the `width` option). FD grep.
- `js/jump-to.js:302-312`, from the code survey §7 and squawk 0185. Re-verify.
- `js/areas/chat/agent-picker.js:180`, from the code survey. Re-verify.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.

## Design Review
- **Developer design review, cycle 1 (Sonnet, 2026-10-27, read-only): approve with changes.** Applied in place:
  - **[high] D4:** the operator's D4 (a) is kept as "keep by identity, moved or not". DD10 is superseded explicitly, and the pinned tests and spec steps are listed for deliberate rewrite (FD answer: the review page's option (a) was "keep the highlighted row by identity across refreshes", so the intent-only variant would undercut it). Scroll uses `nearest`.
  - **[high] identity** is `(group index, id)`.
  - **[high] A9:** the working flex approach and the 64px floor, plus a long-description case.
  - **[medium] field:** `width: 'fill'` dropped; `:45` deleted as a no-op; a `minWidth` option for `:472`.
  - **[medium] list pane:** `flex: 1 1 0`.
  - **[medium] the section inset** becomes a default flip, removing the `!important`.
  - **[medium] `footerEnd`** semantics and its test pins.
  - **[low] the rest:** the picker host stays area (FD answer: the variant does not own the 624px cap); the `reserveHeaderEnd` class and the documented 56px (FD answer: a documented boolean); the badge audit pre-listed and the base rule chosen.
- No second cycle. The changes sharpen the options within the leg's design, and D4's semantics follow the operator's recorded choice.
