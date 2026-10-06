# Leg: controls-and-data

**Status**: completed
**Flight**: [Chats and Jump-to](../flight.md)

## Objective

Land the shared groundwork the Chats surfaces consume:
- the `contracts` browser lane (squawk 0117);
- the control-library additions leg 4 needs: `App.ui.searchList`, the `modal` chooser
  options, and the `listPane` chats rows with row actions;
- the `sessions` store collection, with a `prime` API and the REST `platform` field.

Each control gets a demo, an inventory row and contract tests in Chromium and WebKit.

## Context

The flight's governing decisions are **DD4** (the store), **DD5** (the Chats list and the
row-action contract), **DD11** (lanes), **DD12** (testids), **DD14** (control additions)
and **DD15** (A10, A16, A30).

- **Built where consumed.** This leg builds only what leg 4, `chats-list-and-picker`,
  consumes:
  - `searchList`;
  - the `modal` options `width`, `top`, `initialFocus`, `closeButton`, `footer` and the
    chooser layout;
  - the `listPane` `chats` style, `block`, row actions, `dataset` and the
    `data-confirm-title` label.

  It does **not** build `App.ui.drawer` (leg 6), the rail bottom slot (leg 7),
  `modal.ariaLabel`/`anyOpen` (leg 7) or `listPane.setQuery` (leg 6).
- **Nothing user-visible changes in Chats.** No surface consumes the new controls yet:
  they appear only on the Design language page and in contract tests. The chat area only
  primes the new `sessions` collection.
- **Squawk 0117 first.** The new `test_ui_*` contracts must land in the new `contracts`
  lane, not in the 12m38s `shared` lane.
- **Flight 3 lessons:**
  - every `static/` change runs the UI guard, token-definition and contrast suites;
  - WebKit must actually run (`THE_ONE_REQUIRE_WEBKIT=1`; DD11), because a local skip
    hides failures until CI after merge.
- **Not this leg:** the chat area's rendering, the picker itself, any route, the
  WebSocket protocol.

## Inputs

- The branch `flight/04-chats-and-jump-to` at `af86324` or later, with Flight 3
  completed.
- `scripts/run-tests.sh`: five lanes. `shared` is the complement of `chats_pat`,
  `studio_pat` and `settings_pat`, plus `test_visual_snapshots.py`.
- `tests/browser/test_ui_*.py`: 12 files, all in `shared` today.
- `static/js/ui/list-pane.js`:
  - `ROW_STYLES = ['agents', 'library']`;
  - `buildRow` (link or button, label/meta/badges/count);
  - `setItems` rebuilds every `li`, with `focusedEntry`/`restoreFocus`;
  - `setStop` (the roving tabindex).
- `static/js/ui/modal.js`:
  - the title is always an `h2`, and `aria-describedby` is the body;
  - an actions row;
  - `open()` focuses `autofocusBtn || buttons[0] || first focusable || card`;
  - the card CSS is `.modal-dialog` (`components.css` around 1446–1480), with a `max-width`
    of 480px, centred.
- `static/js/store.js`: `URLS` names five collections. `get`, `peek`, `invalidate` and
  `subscribe` exist, and there is no `prime`.
- `static/js/confirm.js`: `App.confirmDelete(itemEl, onConfirm)` arms by adding
  `confirm-delete` to `itemEl` and swapping the text of `itemEl`'s `[data-confirm-title]`
  child.
- `the_one/interfaces/web/api.py`: `_session_summary` returns `id`, `agent_name`, `title`,
  `created_at` and `updated_at`; `list_chat_sessions` uses it.
- `static/js/areas/chat.js`: the `session_list` handler (around 1196–1224) holds the
  WebSocket rows (with `platform`).

## Outputs

- `scripts/run-tests.sh`:
  - a sixth lane, `contracts` (`test_ui_*`), with `shared` now the complement of all five
    named lanes;
  - a `--list` option that prints the lane's files and exits 0 without running pytest;
  - the usage and error text updated.
- `tests/test_run_tests_lanes.py` (new): a unit test that the six lanes partition the
  browser suite.
- `static/js/ui/search-list.js` (new), `App.ui.searchList`. It gets a CSS block in
  `css/components.css`, a script tag in `index.html` (the asset pin bumped) and a demo
  section on the Design language page.
- `static/js/ui/modal.js`: the chooser options. `static/js/ui/list-pane.js`: the chats
  style, `block`, row actions, `dataset` and `data-confirm-title`. Both with CSS and demos.
- `static/js/store.js`: a `sessions` collection and `App.store.prime`.
- `static/js/areas/chat.js`: `session_list` primes `sessions`.
- `api.py`: `_session_summary` adds `platform`.
- Tests:
  - `tests/browser/test_ui_search_list_contract.py` (new);
  - the modal and `listPane` contract tests extended;
  - `tests/test_store_static.py` (six collections, `LITERAL_LIST`, `prime`);
  - `tests/browser/test_store.py` (prime behaviour);
  - the API test for `platform`;
  - the guard and inventory and the index asset pin.
- Docs:
  - `docs/ui-control-inventory.md` (a `searchList` row; the modal and `listPane` rows
    updated);
  - `docs/ui-testid-registry.md` (demo testids);
  - `CLAUDE.md` (the lane list, and `App.store`'s six collections and `prime`);
  - `the_one/agents.md` (the control library: `searchList`, modal options, `listPane`
    additions; the client data store: `sessions`, `prime` and the invalidation rows).

## Acceptance Criteria

**A. Lanes (squawk 0117).**

- [ ] **AC1. The `contracts` lane exists.** `bash scripts/run-tests.sh --lane contracts`
  selects exactly the `tests/browser/test_ui_*.py` files.
  - `shared` no longer includes them.
  - The usage and error text lists
    `chats|agents|library|settings|contracts|shared`.
- [ ] **AC2. `--list` prints and exits.** `bash scripts/run-tests.sh --lane <lane> --list`
  prints the lane's file paths, one per line, and exits 0 without invoking pytest.
  - `--list` is parsed explicitly (`--list) list=1; shift ;;`), so it never reaches
    pytest.
  - `--list` without `--lane` exits 2 with an error.
- [ ] **AC3. The six lanes partition the suite.** `tests/test_run_tests_lanes.py` (unit,
  in `make test-unit`) runs `--list` for each of the six lanes and asserts:
  - the lanes are pairwise disjoint;
  - their union equals every `tests/browser/test_*.py`, minus `test_visual_snapshots.py`.

  It is falsified once:
  1. Add a scratch `tests/browser/test_zz_probe.py` matching no lane, and confirm it
     appears in `shared`.
  2. Temporarily add a pattern that makes a file match two lanes, and confirm the test
     fails.
  3. **Delete the probe file**, revert the pattern, and record the result in the flight
     log.
- [ ] **AC4. Docs.** `CLAUDE.md` "Per-area browser test lanes" lists the `contracts` lane
  and its membership. It states that `shared` is the complement of the five named lanes.

**B. `App.ui.searchList` (DD14, A10).**

- [ ] **AC5. The API.** `App.ui.searchList(opts)` returns
  `{el, input, refresh(), getActive(), setActive(id), destroy()}`. The options are:
  - `label` (a visually hidden input label, required);
  - `placeholder`;
  - `source(query)`, which synchronously returns the groups
    `[{id, label, items: [{id, label, description, meta, metaMono, lead, testid,
    dataset}]}]`. It is called on every input, and on `refresh()`;
  - `emptyText(query)`;
  - `onPick(item)`;
  - `testid`, `inputTestid` and `rowTestid`.
- [ ] **AC6. ARIA.**
  - The input is `role="combobox"`, with `aria-autocomplete="list"`,
    `aria-expanded="true"`, `aria-controls` pointing at the listbox id, and
    `aria-activedescendant` pointing at the active option (absent when there is none).
  - The listbox is `role="listbox"`. Each group is `role="group"`, labelled by a visible
    group caption that has no `role=option`.
  - Each row is `role="option"`, with a unique id and `aria-selected="true"` only on the
    active row. Rows are not focusable (`tabindex` absent); focus stays in the input.
- [ ] **AC7. Keys and pointer.**
  - After every `source` call the first option is active.
  - ↓ and ↑ move the active option across groups, clamped at the ends (no wrap).
  - **Enter** calls `onPick(activeItem)` and calls `preventDefault`. With no options it
    does nothing.
  - Home and End are **not** intercepted; they move the caret, per the APG combobox
    pattern. This is a deliberate narrowing of the flight's DD10 wording, recorded in the
    flight log.
  - A `pointermove` over a row makes it active, and a click picks it.
  - The active option is scrolled into view (`block: 'nearest'`) inside the listbox only.
  - Escape is **not** handled; the containing modal owns it.
- [ ] **AC8. Rendering and states.**
  - Each row shows its `lead` (`aria-hidden`), the label (weight 600), and the
    `description` on a second muted line with an ellipsis.
  - The `meta` sits right-aligned, in mono when `metaMono` is set.
  - The active row has a visible style in both themes (A10): a wash plus a border.
    `--accent-translucent-hover` (`tokens.css` around 124 and 260) is **not yet audited as
    a background**, so `tests/test_design_tokens_a11y.py` gains these pairs, in both
    themes, composited over the dialog surface:
    - label `--fg` on the wash (4.5:1);
    - description `--fg-muted` on the wash (4.5:1);
    - meta on the wash (4.5:1);
    - the `--accent` border at 3:1 non-text.
  - The Enter and arrow handling ignore `e.isComposing || e.keyCode === 229` (IME).
  - With no options, an `App.ui.emptyState` shows `emptyText(query)`, the listbox is
    hidden, and `aria-activedescendant` is removed.
  - It is built with DOM APIs only (no HTML-string sink), installs no document or window
    listener, and `destroy()` removes its listeners. `tests/browser/test_ui_listener_cleanup.py`
    gains a `searchList` case.
- [ ] **AC9. Contract tests.** `tests/browser/test_ui_search_list_contract.py` covers
  AC5–AC8 in **Chromium and WebKit** (the `engine_page` fixture). It is green with
  `THE_ONE_REQUIRE_WEBKIT=1`, so WebKit runs and does not skip.

**C. `App.ui.modal` chooser options (DD14).**

- [ ] **AC10. The new options.** They are all optional. Existing callers, including
  `App.confirmDialog`, are unchanged: with no new option set, the padding,
  `aria-describedby` and centring are identical.
  - `width`: a pixel number that sets the card width. The card's `max-width` stays within
    the viewport minus 32px.
  - `top`: a pixel number. The card aligns to that offset from the top, not to the centre.
  - `initialFocus`: a Node inside the modal, focused on `open()` instead of the default
    order.
  - `closeButton`: `{label, ariaLabel, testid}`. It adds a `btn-ghost btn-sm` button at the
    end of the header row that closes with `cancelValue`.
  - `footer`: a Node rendered after the body, in `.modal-dialog-footer`.
  - `layout: 'chooser'`:
    - the card has zero padding;
    - the header is a flex row (title and close), with padding `16px 20px 12px`;
    - the body is full-bleed;
    - the footer row is the 11px muted footer from §5.6;
    - **no `aria-describedby`** (the chooser forces it to null), so a screen reader does
      not read the whole list on open;
    - no actions row;
    - the `title` stays an `h2` that the dialog's `aria-labelledby` references;
    - `body` is a Node, placed full-bleed.
  - **Focus on `open()`** is `initialFocus`, if given and connected. Otherwise it is the
    first focusable in the **body** (not the header's close button), and otherwise the
    usual order. A test asserts that the default never lands on the close button when the
    body has an input.
  - The close button takes part in the Tab wrap, and closing through it restores focus to
    the opener.
  - `width` and `top` are inline styles on the opted-in card only, so the existing scroll
    and rule tests' measurements are unchanged.
- [ ] **AC11. The scrim.** The backdrop keeps using the existing `--scrim` token. No token
  is added or changed (DD14; A30 was resolved by Flight 1).
- [ ] **AC12. Contract tests.** `tests/browser/test_ui_modal_contract.py` gains tests for
  each new option, in both engines:
  - `initialFocus` focuses the given node;
  - the close button closes and restores focus to the opener;
  - the chooser layout has no `aria-describedby`;
  - `top` and `width` place the card.

  The existing modal contract tests stay green.

**D. `App.ui.listPane` additions (DD5, DD12).**

- [ ] **AC13. `rowStyle: 'chats'`.** It is added to `ROW_STYLES`.
  - **Line 1:** the label (13px, `--fg`, ellipsis) with the item's new `time` field
    pushed to the end (11px, `--fg-muted`, no shrink).
  - **Line 2:** the `meta` (11px, `--fg-secondary`), then the `badges`.
  - Row padding is `8px 10px` (A8). The selected style follows the existing styled rows.
  - **Contrast.** The `time` (`--fg-muted`) and the `meta` (`--fg-secondary`) at 11px are
    gated at 4.5:1 on the sidebar ground **and** on the selected-row wash, in both themes.
    Add any pair that is not already in `test_design_tokens_a11y.py`. Reference spec A24
    records `--fg-muted` on the light selected wash at 4.43:1, so check how Flight 1 or
    Flight 3 resolved that, and reuse it.
- [ ] **AC14. The `block` option.** It takes a Node, inserted directly after the
  `<header>`, outside it. The `<header>`'s children are unchanged, as
  `test_ui_library_contract.py` pins.
- [ ] **AC15. Row actions.**
  - `item.action = {label, icon, testid, onClick(item, actionEl, li)}` renders a sibling
    `<button type=button class="ui-list-pane-action">` inside the row's `li`, after the
    row:
    - `aria-label` is the action `label`, with the icon only;
    - it does **not** carry `.ui-list-pane-row`;
    - it is hidden with `display:none` until `li:hover` or `li:focus-within` (not
      `visibility` or `opacity`, which would break Tab reach).
  - **Tab policy.** Only the action of the row that is the roving tab stop has
    `tabindex="0"`, and every other action has `"-1"`. `setStop` re-derives the actions'
    tabindex, and so does a `focusin` on the body. So Tab goes from the stop row to its
    action, then out of the list.
  - **Focus restore across `setItems`.**
    - Each entry gains an `action` reference. `focusedEntry` matches
      `entry.li.contains(active)` and reports whether focus was on the row or the action.
    - A focused **action** restores to the same item's action.
    - If that item is gone, focus goes to the **neighbouring row**: the next visible row,
      else the previous one. Then `setStop(thatRow)` runs and the action tabindexes are
      re-derived.
    - **A focused row keeps Flight 3's rule unchanged**: the same id, else selected, else
      first (`test_ui_library_contract.py:1172-1184`). The neighbour rule applies **only**
      when focus was on an action, which is the delete case.
  - **Keys on an action.** ↑ and ↓ move to the previous and next visible row (the roving
    rows). Home and End move to the first and last row. `rovingFocus` must tolerate focus
    on a non-row node inside the body.
  - **Armed state.** When `setItems` rebuilds while an item's `li` carries `confirm-delete`
    (armed by `App.confirmDelete`), that **same `li` node** (row and action) is reused for
    that item id.
    - Its armed title and timer survive.
    - The entry's `item` is updated to the **new** item, so the action's click handler
      reads `entry.item` at click time, never a stale closure.
    - The reused row still goes through `applyView` (`aria-current`, tabindex, hidden).
    - If the armed item is **absent** from the new list, its `li` is dropped. The lapse
      timer in `confirm.js` must not throw on the detached node; verify, and pin it.
    - The next `setItems` after it disarms replaces it normally.
    - The coupling to `confirm.js` (the class, and the `[data-confirm-title]` child) is
      documented in the factory comment.
  - An item with no `action` has no button, so the pending row gets none.
- [ ] **AC16. Row data.**
  - `item.dataset` (a plain object) sets `data-*` attributes on the row element.
  - The row's label span always carries `data-confirm-title`, so `App.confirmDelete(li)`
    swaps the label text.
- [ ] **AC17. Contract tests.** In both engines, extend the `listPane` contract tests in
  `tests/browser/test_ui_library_contract.py`, or add `test_ui_list_pane_chats_contract.py`
  in the `contracts` lane. They cover:
  - the chats row anatomy (line 1 and line 2, the time pushed to the end);
  - `block` placement, with the header children unchanged;
  - the action tab policy (Tab from the stop row reaches its action, then leaves the
    list);
  - ↑ and ↓ while an action is focused move to the neighbouring rows;
  - the action is hidden at rest and revealed on hover and on focus-within;
  - focus restore to the same action, and to the neighbouring row when the action's item
    is gone. A focused **row** whose item is gone keeps Flight 3's same-id, then selected,
    then first rule, so `test_ui_library_contract.py:1172-1184` stays green unchanged;
  - an armed `li` survives a `setItems`, with `entry.item` updated;
  - an armed `li` whose item is gone is dropped without the lapse timer throwing;
  - `dataset` and `data-confirm-title`.

  Every Flight 3 `listPane` contract test stays green.

**E. Data (DD4).**

- [ ] **AC18. The REST field.** `GET /api/chat/sessions` items include `platform`, which
  is `null` for UI sessions and the platform string for connector sessions. A unit test in
  `tests/test_db_api.py` (or a sibling) seeds both kinds through
  `POST /api/chat/sessions` and asserts the field.
  - `_session_summary` is also used by the detail, create and update responses
    (`api.py` around 4302, 4322 and 4347), so they gain `platform` too. That is additive.
  - **`the_one/agents.md` around 658–661** (M11 F13 L5) calls extending `_session_summary`
    an anti-pattern. That note is about rich `session_metadata`. Update the paragraph:
    one scalar `platform` is sanctioned by the Mission 25 scope fence ("exposing a
    session's platform"), and rich metadata stays out.
  - A unit test pins that the REST summary keys are a subset of
    `_session_to_list_payload`'s keys (`app.py` around 1356), so the primed (WebSocket) and
    fetched (REST) rows cannot silently diverge.
- [ ] **AC19. The `sessions` collection.** `App.store` has a sixth collection, `sessions`
  (`GET /api/chat/sessions`).
  - `tests/test_store_static.py::test_store_urls_name_the_five_collections` is
    **renamed** to `..._six_collections` and asserts all six.
  - `LITERAL_LIST` includes `chat/sessions`, and `test_no_literal_list_fetches_outside_store`
    stays green: no client file fetches `/api/chat/sessions` literally.
- [ ] **AC20. `App.store.prime(name, rows)`.** It sets the collection's value to a copy of
  `rows`, with `loaded`, `ok` and `fresh` all true. It bumps `gen` and clears `inflight`,
  so a request started earlier neither populates the cache nor is joined later. It then
  notifies subscribers with a copy.
  - `tests/browser/test_store.py` gains these tests:
    - prime notifies;
    - a racing older `get` resolves without overwriting the primed value;
    - a `get` after `prime` resolves from the cache with no fetch;
    - an unknown collection throws.
- [ ] **AC21. The chat area primes.** Every WebSocket `session_list` reply calls
  `App.store.prime('sessions', rows)`. The rows are mapped to the REST summary shape:
  `id`, `agent_name`, `title`, `created_at`, `updated_at`, `platform`. Nothing else in
  Chats changes. A static pin in `test_store_static.py` asserts the prime call sits in
  the `session_list` handler.
- [ ] **AC22. The invalidation map.** It gains the rows for leg 1 (DD4):
  - **agent rename** (`studio.js` around 3528–3542, beside `invalidate('agents')`)
    invalidates `sessions`, because a rename re-points `chat_sessions.agent_name`;
  - the agent's **Purge now** (`handlePurgeHistory`, `studio.js` around 2889–2906)
    invalidates `sessions` in its success `.then`, after the `deleted` count.

  Each gets a pin in `test_store_static.py`, and `the_one/agents.md` "Client data store"
  lists them.
  - **No other client site needs a row.** The client's only per-session deletion is the
    WebSocket `delete_session`, which comes back through a `session_list` and so a prime.
  - Agent delete leaves sessions in place (`DELETE /api/agents/{name}` does not touch
    them), so it needs no `sessions` invalidation.
  - The `start_session` join row lands in leg 3.

**F. Registry, inventory and gates.**

- [ ] **AC23. Inventory and docs.** `docs/ui-control-inventory.md` gains an
  `App.ui.searchList` row, and the `listPane` and `modal` rows are updated.
  `tests/test_ui_control_inventory.py` is green. Every new demo testid is registered in
  `docs/ui-testid-registry.md`, and `test_registered_testids_exist_in_source` is green.
- [ ] **AC24. The index pin.** `index.html` loads `ui/search-list.js` in the `ui/` group.
  If the design-language sections are loaded through `index.html` script tags (verify how
  `ui-modal-section.js` is loaded), it also loads `ui-search-section.js`.
  - `tests/test_index_asset_cache_busting.py`'s pin (`len(refs) == 71`) becomes **73**
    with both tags, or **72** if the section loads another way.
  - The pin's history comment block is extended.
- [ ] **AC25. Gates.** Run and report:
  - `make lint` and `ruff format --check`: clean.
  - The static guards: `test_ui_guards`, `test_token_definitions`,
    `test_design_tokens_a11y`, `test_ui_control_inventory`, `test_nav_helper`,
    `test_store_static`, `test_index_asset_cache_busting`, `test_ui_library_source` and
    `test_run_tests_lanes`.
  - `make test-unit`.
  - The browser lanes, each through `scripts/run-tests.sh` with
    `THE_ONE_TEST_NETNS=1` and `PYTHON=.venv/bin/python`:
    - `contracts`, with `THE_ONE_REQUIRE_WEBKIT=1`;
    - `shared` (`TEST_TIMEOUT=3600`);
    - `chats`.

## Verification Steps

- **AC1–AC3:**
  - `bash scripts/run-tests.sh --lane contracts --list`, and the same for `shared`;
  - `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_run_tests_lanes.py -x
    --timeout 60`;
  - record the falsification in the flight log.
- **AC5–AC9, AC10–AC12, AC13–AC17.** WebKit needs its host libraries: run
  `bash scripts/setup-webkit-userland.sh` once if `THE_ONE_REQUIRE_WEBKIT=1` reports a
  launch failure. Then:

  ```
  THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python TEST_TIMEOUT=2400 bash scripts/run-tests.sh --lane contracts -x
  ```

  Then view the Design language page demos in a dev instance on 8486 or higher, never
  8484. For one new contract per control, falsify once and record it: for example, drop
  `aria-selected` or the action's tabindex re-derivation and watch a test fail, then
  restore.
- **AC18–AC22:** the unit tests, `tests/test_store_static.py`, and `tests/browser/test_store.py`
  (shared lane).
- **AC23–AC25:** the commands listed in AC25.

## Implementation Guidance

1. **The lanes first.**
   - In `scripts/run-tests.sh` add `contracts_pat=('test_ui_*')` and a `contracts)` case,
     and add `contracts_pat` to `shared`'s `_assigned` expansion.
   - Add `--list` parsing next to `--lane`. After `lane_files` is computed,
     `printf '%s\n' "${lane_files[@]}"; exit 0` when `--list` is set.
   - Update the header comment and the error line.
   - Write `tests/test_run_tests_lanes.py`, which uses `subprocess.run(["bash",
     "scripts/run-tests.sh", "--lane", lane, "--list"], cwd=REPO)`. Then update the lane
     section of `CLAUDE.md`.
2. **`searchList`.**
   - Model the file on `ui/menu.js` and `ui/list-pane.js` for structure (an IIFE, ES5,
     `App.ui.util.el`).
   - The input is an `App.ui.textInput`, with a visually hidden label through
     `App.ui.field({labelHidden:true})`. The listbox is a `div role=listbox`. Option ids
     come from `util.uid`.
   - Keep the item model in a flat array of `{item, el}` for the active-index math.
   - CSS: rows follow §5.6's picker row (`padding:10px 12px`, gap 12, radius-sm,
     transparent border). The active row uses `--accent-translucent-hover` with an
     `--accent` border, and `aria-selected="true"`. Pick tokens already gated in
     `test_design_tokens_a11y.py`, or add the pairs.
   - Demo: a new `ui-search-section.js` in `areas/admin/design-language/` with about 12
     sample agents in two groups and an empty-state query, wired like the other `ui-*`
     sections.
3. **The modal options.**
   - Extend `build()`. With `layout:'chooser'`, build `header` (`h2` plus the close
     button), then the `body` node, then the `footer`, and set no `aria-describedby`.
   - Apply `width` and `top` as inline styles on the card, or through a class plus CSS
     custom properties.
   - In `open()`, use `opts.initialFocus` when it is connected inside the card.
   - Extend `ui-modal-section.js` with a chooser demo.
4. **`listPane`.**
   - Add `'chats'` to `ROW_STYLES`, and branch `buildRow` on `opts.rowStyle === 'chats'`
     for the two-line text with `time`.
   - Build the action button in `setItems` (the row and the action share the `li`), and
     extend `setStop` to set the actions' tabindex.
   - In `setItems`, before clearing, map the item id to an armed `li` (`li.classList
     .contains('confirm-delete')`), and reuse it in place of a new `li` for that id.
   - Extend `focusedEntry` and `restoreFocus` to know whether focus was on the row or the
     action, and to fall back to the neighbouring index.
   - Add the `dataset` loop in `buildRow`, and add `data-confirm-title` to the label span.
   - Extend `ui-lists-section.js` with a chats-style demo that includes row actions.
5. **Data.**
   - In `api.py`, add `"platform": session.platform` to `_session_summary`.
   - In `store.js`:
     - add `sessions: '/api/chat/sessions'`;
     - add `prime(name, rows)` per AC20, exported beside `get` and the other functions;
     - update the header comment.
   - In `chat.js`'s `session_list` handler, add the prime with the mapped rows.
   - Add the invalidation calls at the agent rename and Purge-now sites in `studio.js`
     (re-grep `chat/sessions` and `purge` for the per-session sites).
6. **Docs, registry, inventory, the index pin, and the gates** (AC23–AC25). Update the
   flight log with the gate numbers and the falsifications.

## Edge Cases

- **A `searchList` `source` that returns empty groups:** drop them, so no caption is left
  without options.
- **Duplicate option ids across groups** (the picker's "All agents" repeats "Recently
  used"): option element ids must stay unique. Derive them from the group and item ids, or
  from `util.uid`, never from the item id alone. `onPick` still receives the item.
- **`prime` while a `get` is in flight:** the old request's resolution must not overwrite
  the primed value or notify subscribers (the `gen` check). Callers that await the old
  `get` still get its own data copy.
- **A row action on a filtered-out row:** the `li` is hidden, so its action is too. The
  tab-stop derivation ignores hidden `li`s.
- **The armed `li` reused for an item whose label changed:** keep the old node until it
  disarms. A stale label for at most 3s is acceptable; document it.
- **Lane `--list` with an unknown lane:** it still exits 2 with the error text.

## Files Affected

- `scripts/run-tests.sh` — the `contracts` lane, `--list`, comments.
- `tests/test_run_tests_lanes.py` — new.
- `the_one/interfaces/web/static/js/ui/search-list.js` — new.
- `the_one/interfaces/web/static/js/ui/modal.js`, `ui/list-pane.js` — the options.
- `the_one/interfaces/web/static/css/components.css` — the `searchList`, chooser,
  chats-row and action styles.
- `the_one/interfaces/web/static/index.html` — the `search-list.js` script tag.
- `the_one/interfaces/web/static/js/areas/admin/design-language/ui-search-section.js` —
  new, plus its wiring.
- `the_one/interfaces/web/static/js/areas/admin/design-language/ui-modal-section.js` and
  `ui-lists-section.js` — the demos.
- `the_one/interfaces/web/static/js/store.js` — `sessions` and `prime`.
- `the_one/interfaces/web/static/js/areas/chat.js` — prime on `session_list`.
- `the_one/interfaces/web/static/js/areas/studio.js` — the invalidation calls.
- `the_one/interfaces/web/api.py` — `_session_summary.platform`.
- Tests:
  - `tests/browser/test_ui_search_list_contract.py` — new;
  - `tests/browser/test_ui_modal_contract.py` and `tests/browser/test_ui_library_contract.py`,
    or a new chats contract file;
  - `tests/browser/test_store.py`;
  - `tests/test_store_static.py`, `tests/test_db_api.py`,
    `tests/test_index_asset_cache_busting.py` and `tests/test_design_tokens_a11y.py`.
- Docs: `docs/ui-control-inventory.md`, `docs/ui-testid-registry.md`, `CLAUDE.md` and
  `the_one/agents.md`.

## Citation Audit

Checked by the Flight Director against `af86324`:
- `run-tests.sh` lane case, lines 85–107;
- `list-pane.js`: `ROW_STYLES` line 7, `buildRow` around 187–240, `setStop` around 245,
  `focusedEntry`/`restoreFocus` around 314–339, `setItems` around 341–380;
- `modal.js`: `build` lines 89–184 and `open` lines 188–198;
- `store.js`: `URLS` lines 29–35 and `invalidate` lines 84–89;
- `confirm.js`: arms with `itemEl.classList.add('confirm-delete')` and a
  `[data-confirm-title]` title swap;
- `api.py`: `_session_summary` around 4441 and `list_chat_sessions` around 4287;
- `test_store_static.py`: `LITERAL_LIST` line 17 and the five-collection pin line 41.
