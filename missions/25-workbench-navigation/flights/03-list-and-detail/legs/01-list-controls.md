# Leg: list-controls

**Status**: ready
**Flight**: [List and Detail](../flight.md)

## Objective

Ship the control-library and shell groundwork that the destination legs build on, with no
surface yet using the new list or nav:

- **`App.ui.listPane` additions** (DD10). Bring the list pane to reference spec §3 and §6.1
  geometry. Add:
  - a title count;
  - an intro;
  - per-group empty text;
  - row styles;
  - `scrollToSelected`;
  - an accessible-name suffix;
  - focus preservation across `setItems`.
- **`App.ui.navGroups`**, a new factory for the Settings nav (DD6 and DD10).
- **Width tokens and the `data-destination` hook** (DD1). Apply the per-destination aside
  widths.
- **The `_lists.py` test helper** with the retired-selector AST guard and its per-file
  allow-list (DD11).

## Context

- **Flight decisions:**
  - DD1: widths and the mechanism.
  - DD4 and DD5: what the lists need.
  - DD6: the nav.
  - DD10: the control-library work.
  - DD11: the guard and the allow-list.
  
  Read them in `flight.md`.
- **The current list pane:** `static/js/ui/list-pane.js`, about 279 lines.
  - Its API is at `:51-67`.
  - `setItems` (`:221-253`) rebuilds every row.
  - `applyView` hides empty groups (`:193-200`).
  - Rows are links or buttons with `aria-current="page"`.
  - Keyboard uses `util.rovingFocus` (`ui/core.js`), flat and clamped.
  - Its CSS is at `css/components.css:568-660`. The title is 12px, medium weight,
    `--fg-secondary` (`:576-581`); reference spec §3 wants 16px, 600, `--fg`.
  - The selected-row meta already uses `--fg-secondary` (`:658-660`). That is Flight 1's
    A24 resolution.
- **No app consumer yet.** Only the Design-language demo uses the list pane
  (`areas/admin/design-language/ui-lists-section.js`).
- **Patterns to follow:**
  - `App.ui.rail` (`ui/rail.js`, Flight 2) is the nav-of-links pattern for `navGroups`.
  - `tests/browser/test_ui_rail_contract.py` is the contract-test pattern, using the
    `engine_page` fixture for Chromium and WebKit.
  - The factory checklist (CLAUDE.md "Control library") applies: ES5, native elements,
    no HTML-string sinks, testids supplied by the caller, a demo, an inventory row, and
    contract tests in both engines.
- **Shell:**
  - `router.js` `applyShell` (`:406-411`) sets `aside.hidden` and `aria-label`.
  - `css/base.css:25-45` holds the aside width `--sidebar-w`, with 200px under 1280px, and
    `#app-sidebar[hidden] { display: none }` at `:37`.
- **Test guard:** `tests/test_nav_helper.py`'s AST guard over `tests/browser/test_*.py`,
  together with `tests/browser/_nav.py`.
  - The design review's grep finds **29** `test_*.py` files using the retired selectors.
    Compute the allow-list from the live walk, not from this number.
  - The list includes `test_router_announce`, `test_router_guard`, `test_router_items`
    and `test_shell_rail`.
  - **The new guard does NOT exempt `test_router_*.py`.** The route guard exempts it at
    `test_nav_helper.py:150`. Here those files stay on the allow-list until the legs
    that retire the surfaces migrate them.

## Inputs

- `static/js/ui/list-pane.js`, `ui/core.js`, `ui/rail.js`, `ui/menu.js`
- `static/js/router.js` `applyShell`
- `css/components.css` (the list pane), `css/base.css` (the aside), `css/tokens.css`
- `index.html` (script tags, and the cache-busting count in
  `tests/test_index_asset_cache_busting.py`)
- `areas/admin/design-language/ui-lists-section.js` and the Design-language page index
- `docs/ui-control-inventory.md`, `docs/ui-testid-registry.md`
- `tests/test_ui_control_inventory.py`, `tests/test_ui_guards.py`,
  `tests/test_design_tokens_a11y.py`
- `tests/browser/test_ui_library_contract.py` (existing listPane contract tests)
- `tests/test_nav_helper.py`, `tests/browser/_nav.py`
- `tests/browser/test_shell_rail.py` (aside width assertions)

## Outputs

**1. `App.ui.listPane` additions.** Every new option is backward-compatible.

- **`count: true`.** The title row shows a count span after the h2: "{shown} of {total}",
  11px, `--fg-muted` (§6.1).
  - It updates on filter and on `setItems`, always in this form.
  - It is empty while `total` is 0 or before the first `setItems`, which is an accepted
    variation.
- **`intro`** (string). A `<p class="ui-list-pane-intro">` below the title row
  (`padding: 0 16px 8px; 11px; --fg-muted`, §7.1).
- **Per-group `emptyText`.** In `groups[{label, emptyText, items}]`, a group with **zero
  items** still renders its caption and shows a muted line in place of rows.
  - A group whose rows are all **filtered out** stays hidden, as today.
  - Empty-group lines are not focusable rows.
- **Title style.** Per §3: the title row padding is `14px 16px 10px` with a gap of 8px.
  The h2 is 16px (`--font-size-h2`), weight 600, `--fg`. The actions are pushed right.
- **`rowStyle: 'agents' | 'library'`.** Per A8:
  - `'agents'`: row padding `7px 10px` with no inter-row gap, which renders about 48px.
  - `'library'`: `8px 10px` with a 2px gap.
  - **Default: today's style, unchanged.** That means no border, and selection drawn as an
    inset ring (`components.css:~617, ~628`).
- **The border-based selection is opt-in under `rowStyle` only** (design review, M3).
  - Opted-in rows carry `border: 1px solid transparent`. The selected row sets
    `background: var(--accent-translucent)` and `border-color: var(--accent)` (§3), so
    selection causes no layout shift.
  - The forced-colours rule (`:1538`) is updated to cover both models.
  - `rowStyle` padding takes precedence over the `density: 'compact'` padding.
- **`scrollToSelected()`.** Scrolls the selected row into view with `{ block: 'nearest' }`
  inside the body scroller (A26). It is a no-op when there is no visible selected row.
- **Per-item `nameSuffix`** (string). It is appended to the row's accessible name through a
  visually-hidden span, for example ", Claude Max" (A31). It is not shown.
- **Focus preservation across `setItems`** (DD10; design review, M1 and M2).
  - **Before** `body.textContent = ''` (`list-pane.js:224`), find the entry whose `row`
    is, or contains, `document.activeElement`. Record its `item.id`. There is no new
    data attribute: `entries[]` already maps rows to items, and `normalise` guarantees
    unique ids.
  - After the rebuild and **after `applyView()`**, set the tab stop **explicitly**:
    `tabindex=0` on the row with the preserved id (else the selected row, else the first
    visible row), and `-1` on all others. `applyView` would otherwise reset the stop to
    the selected row, and `rovingFocus` (`core.js:96-135`) keeps no state.
  - Restore focus **synchronously** inside `setItems`. Removing the focused node fires
    `focusout`, so any deferral would let focus fall to `body`.
  - When focus was not inside the body, focus and the tab stop follow the normal
    `applyView` rule.
  - Focus on an empty-group line is not a row, so there is nothing to preserve.
  - `setItems` while a filter query is active keeps the query, re-runs the predicate, and
    updates the count.
- **`getItems()`** (optional). Returns the current items for tests.
- **Item `href` normalisation.** This is unchanged. `href` rows stay `<a>`, so `App.nav`'s
  link interceptor guards them.

**2. `App.ui.navGroups({ label, heading, groups, selectedId, testid })`.** This is a new
file, `static/js/ui/nav-groups.js`, built from `util.el`.

- **Signature.**
  - `groups` is `[{ label, items: [{ id, label, href, testid }] }]`.
  - It returns `{ el, setSelected(id), destroy() }`.
- **Markup.** `<nav aria-label="{label}">` containing an `<h2>` heading, then for each
  group a caption `<div>` and a `<ul>` of `<li><a href>` items.
  - Every item needs an `href`. A missing `href` or a duplicate id throws, as listPane does.
- **Selected item.** It carries `aria-current="page"`, the translucent wash and an inset
  1px accent ring (§8.1).
- **Keyboard.** None. These are plain links in Tab order (DD10).
- **Click handling.** No click handlers. The router and `App.nav` handle the links.
- **Geometry (§8.1).**
  - Items: `display: block; padding: 6px 10px; 12px type; border-radius: var(--radius-sm)`,
    with `--fg-secondary` at rest and about 28px tall.
  - Group captions use the §3 group-label style.
  - The heading is 16px and 600, **indented to align with the item text** (A3: 20px from
    the column edge, which is 10px of column padding plus 10px of indent).
  - The column padding (`14px 10px`) and width come from the host, not the factory.
- **Forced colours.** The selected item gets a `Highlight` border, as the list pane does
  at `components.css:1538`.

**3. Width tokens and the hook** (DD1).

- **Tokens** in `css/tokens.css`:
  - `--list-w: 300px`
  - `--settings-nav-w: 260px`
- **Hook.** `applyShell` sets `aside.dataset.destination = destId`. The router does nothing
  else new.
- **CSS** in `css/base.css`:
  - `#app-sidebar[data-destination="agents"]` and `[data-destination="library"]` get
    `width: var(--list-w)`.
  - `#app-sidebar[data-destination="settings"]` gets `width: var(--settings-nav-w)`.
  - **Specificity** (design review, M4): these selectors are (1,1,0) and already beat the
    `max-width: 1279px` rule's (1,0,0). Placing them after it is harmless.
  - They tie with `#app-sidebar[hidden]` (`:37`, also (1,1,0)). The destination rules
    must **never set `display`**, so `[hidden]` still wins on Agents.
  - **`padding-top: 0` is NOT applied in this leg.** It would shift today's Library and
    Settings content up 10px before their lists exist. Legs 3, 4a and 5a apply it with
    their lists.
  - Chats keeps `--sidebar-w` and its 200px rule.
  - `#app-sidebar[hidden]` must still win, because Agents keeps `sidebar:false` until
    leg 3.
- **Visible effect this leg.** The Library aside is 300px and the Settings aside is 260px,
  both still showing today's section navs. This is harmless and intended.
- **Tests.** `test_shell_rail.py:137-171` parametrizes (1024, 200), (1279, 200),
  (1280, 240) and (1440, 240) over Chats, Library and Settings, and asserts `aside ==
  [72, aside_w]` at `:166`.
  - Split the loop by destination: Chats keeps 240/200; Library is 300 at every width;
    Settings is 260 at every width.
  - Refresh the stale "200px aside" comment in the clipping test near `:176-195`.
  - No other test pins the aside width (design review).

**4. `tests/browser/_lists.py`** (DD11). These helpers work today through the kept testids
(`agent-item`, `knowledge-base-card`, `mcp-source-card`, `connector-card`,
`provider-card`, `tool-card`):

- `list_row(page, dest, name)` returns the row locator by visible name;
- `open_item(page, dest, name)` clicks the row and waits for the route to change to the
  item.

Each later leg adds the helpers its surface needs: `expect_selected`, `filter_agents`
(leg 3), `library_add` (leg 4a), and so on.

**5. The retired-selector AST guard** (DD11).

- **Where.** `tests/test_nav_helper.py` gains a second guard, using the same AST walk as
  the route guard, over:
  - `tests/browser/test_*.py`, with the allow-list;
  - the browser **helper modules** (`tests/browser/_*.py`, `seeders.py`, `conftest.py`),
    with an **empty** allow-list (design review, H2), so no helper can quietly
    reintroduce a retired selector. None uses one today.
- **Scope.** The walk sees Python string literals, which include JS passed to
  `page.evaluate`.
- **What it flags.** String literals naming these retired selectors:
  - `entity-tile`
  - `section-nav-item`
  - `back-agent-btn`
  - `back-knowledge-btn`
  - `back-mcp-source-btn`
  - `back-connector-btn`
  - `back-provider-btn`
  - `back-tool-btn`
- **Allow-list.** `RETIRED_SELECTOR_ALLOWLIST` is a set of test file basenames, and is
  exactly today's violators. The guard fails on any file that is not listed, and on any
  **listed file that no longer violates** (a stale entry).
- **Shrinking.** Later legs remove the files they migrate. Leg 6 asserts that the set is
  empty.
- **Self-test.** A self-test exercises the guard on code snippets, as
  `test_guard_self_test` does. It covers three states: an unlisted violator (fails), a
  stale allow-list entry (fails), and a docstring or comment mention (exempt, as in the
  route guard).

**6. Demos, inventory and registry.**

- **Demos.** The Design-language lists section gains:
  - an "Agents-style" demo with a count, a filter, the agents row style, a name suffix and
    30 or more rows;
  - a "Library-style" demo with an intro, three groups (one empty, with its empty text) and
    the library row style.
  - A new **navGroups** demo shows four groups and a selected item.
- **Inventory.** `docs/ui-control-inventory.md` gains a row for `navGroups`, and the list
  pane row is updated.
- **Registry.** New testids are added to `docs/ui-testid-registry.md`. The registry sync in
  `test_ui_guards.py` passes.
- **`index.html`** gains the script tag for `ui/nav-groups.js`.
  `test_index_asset_cache_busting.py` asserts `len(refs) == 72` with a comment ledger.
  It becomes **73**, plus one more for any new demo script file. Add a ledger line for
  each.

**7. Contrast.**

- **A24 is already covered.** `test_design_tokens_a11y.py:676-693` lists the selected-row
  meta, badge and count selectors, and `test_selected_row_meta_passes_body_aa` is at
  `:756`. Verify it, with no change.
- **Add** the new 11px text pairs, `--fg-muted` on the aside surface (`--sidebar-bg`),
  for both themes:
  - the list-pane intro;
  - the empty-group line;
  - the title count.
- If any pair fails AA, use the `--fg-secondary` resolution that Flight 1 applied to
  selected meta, and record it.

**8. Docs.** `the_one/agents.md` "Control library (`App.ui`)" documents the listPane
additions and `navGroups`, and "App shell — invariants" documents `data-destination` and
the two width tokens. CLAUDE.md gets a one-line pointer to `_lists.py` and the
retired-selector guard.

## Acceptance Criteria

- [ ] **AC1 — listPane additions.** Every option in Outputs §1 behaves as specified, and
  existing callers and demos are unchanged unless they opt in. Contract tests run in
  **Chromium and WebKit** and cover:
  - **Count:** "{shown} of {total}" on load, after a filter, after `setItems` (including
    `setItems` with an active filter query), and "0 of N" on no match.
  - **Intro:** present, and styled per §7.1.
  - **Group empty:** a zero-item group shows its caption and empty line; a fully filtered
    group stays hidden; empty lines are not in the roving set.
  - **Row styles:** the computed padding and gap for `'agents'` and `'library'`; the 1px
    transparent border at rest; selection changes no row height.
  - **`scrollToSelected`:** a selected row at index 25 of 30 is inside the scroller's
    visible box after the call.
  - **`nameSuffix`:** the row's accessible name includes the suffix (checked through the
    accessibility snapshot) and the suffix is not visible.
  - **Focus preservation:** with focus on row "b", `setItems` with "b" still present
    keeps focus on "b" and makes it the tab stop, even when "b" is not the selected row. With "b" removed, focus goes to the
    selected row or the first row. A `setItems` triggered while roving (after an
    ArrowDown) keeps focus. With focus outside the pane, focus is untouched.
- [ ] **AC2 — `navGroups`.** The contract tests, run in both engines, check:
  - the markup: a nav landmark with its label, an h2, captions, links in group order;
  - `aria-current="page"` on exactly the selected item, and `setSelected` moves it;
  - no click listeners (navigation is native);
  - throws on a missing `href` or a duplicate id;
  - geometry: an item renders 28px ±1px tall at 12px; the heading indent lines up with
    the item text, checked by comparing the left edges within 1px;
  - the forced-colours selected border.
- [ ] **AC3 — Shell widths.**
  - At 1440×900, `#app-sidebar` measures 300px on Library and 260px on Settings, and Chats
    is unchanged at 240px.
  - At 1024×768, Library is still 300px, Settings 260px and Chats 200px.
  - On Agents the aside stays hidden (`[hidden]` wins).
  - `data-destination` follows every destination change, including Back and Forward.
  - Tests that pinned the old widths are updated.
- [ ] **AC4 — `_lists.py` and the guard.**
  - `list_row` and `open_item` work against today's surfaces in each destination, proved
    by a small test per destination.
  - The retired-selector guard passes with its allow-list equal to today's violators (29
    files at design time). It fails when a listed file stops violating, or when an
    unlisted file or any helper module starts. Its self-test covers the three states.
- [ ] **AC5 — Demos, inventory, registry and cache-busting** all pass:
  - `test_ui_control_inventory.py`;
  - the `test_ui_guards.py` registry sync, with no new HTML-string sinks;
  - `test_index_asset_cache_busting.py`.

  The Design-language page renders the new demos in both themes with no console errors.
- [ ] **AC6 — Contrast.** The existing selected-row meta test still passes. The new intro,
  empty-group and title-count text pairs are asserted in both themes and pass AA, with
  any fix recorded.
- [ ] **AC7 — Gates.**
  - `make lint`;
  - `make test-unit`;
  - all five browser lanes, one at a time, with `THE_ONE_TEST_NETNS=1`;
  - every `test_ui_*` contract test in both engines.
  
  Report counts and durations. Re-run any failure alone and classify it.

## Verification Steps

- AC1–AC2:
  `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser tests/browser/test_ui_library_contract.py tests/browser/test_ui_nav_groups_contract.py -x -rA`.
  The second file is a new name; another name is fine.
- AC3: the shell width test, in both engines if it is engine-parametrized, else in
  Chromium.
- AC4–AC6: `make test-unit`.
- AC7: the gates.

## Implementation Guidance

1. **listPane first.**
   - Make every option additive.
   - The focus-preservation logic goes in `setItems`, as specified in Outputs §1: look up
     the focused row in `entries[]` before the rebuild, set an explicit tab stop after
     `applyView()`, and restore focus synchronously.
   - Keep all keyboard handling on the body (DD1: no document listeners).
2. **navGroups.** Write it with `util.el` only and no `innerHTML`. Mirror rail.js for
   `aria-current` and for links without click handlers.
3. **Tokens and the hook,** then fix the width tests.
4. **`_lists.py` and the guard.** Compute the allow-list from a grep of today's
   violators. Make the stale-entry check strict.
5. **Demos, inventory, registry, `index.html` and the cache-busting count.**
6. **Docs, then the gates.**

## Edge Cases

- **A selected id absent from the items.** `setSelected` treats it as no selection (as
  today). The detail pane is not the list's concern.
- **A filter that hides the selected row.** The selection stays recorded, the tab stop
  moves to the first visible row, and `scrollToSelected` is a no-op. When the filter
  clears, `scrollToSelected` brings the row back into view if the caller asks.
- **The count with groups.** Count across all groups. Library does not show a count, but
  the option must be well-defined.
- **`nameSuffix` on a link row.** Do not set `aria-label`, because that would override the
  visible name for voice control. Use a visually-hidden text span instead.
- **WebKit.** `scrollIntoView` options work in WebKit 26. Verify `block: 'nearest'` in the
  WebKit contract run.
- **`data-destination` before the router starts.** The aside has no attribute, so the
  default `--sidebar-w` applies until the first commit, which is acceptable.

## Files Affected

- `static/js/ui/list-pane.js`, `static/js/ui/nav-groups.js` (new), `static/js/router.js`
  (`applyShell`, one line)
- `css/components.css`, `css/base.css`, `css/tokens.css`
- `index.html`
- `areas/admin/design-language/ui-lists-section.js`, plus the navGroups demo (a new
  section file, or added to the lists section)
- `docs/ui-control-inventory.md`, `docs/ui-testid-registry.md`
- `tests/browser/_lists.py` (new), `tests/test_nav_helper.py`
- `tests/browser/test_ui_library_contract.py`, `tests/browser/test_ui_nav_groups_contract.py`
  (new), `tests/browser/test_shell_rail.py` (widths), and the `_lists` smoke tests
- `tests/test_design_tokens_a11y.py` (if the pair is missing),
  `tests/test_index_asset_cache_busting.py`
- `the_one/agents.md`, `CLAUDE.md`
- `missions/25-workbench-navigation/flights/03-list-and-detail/flight-log.md`

## Citation Audit

The Flight Director checked these against `4828d53`:

| Citation | Status |
|---|---|
| `ui/list-pane.js` API `:51-67`, `applyView` hides groups `:193-200`, `setItems` rebuild `:221-253` | verified |
| `css/components.css` list-pane block `:568-660`; title style `:576-581`; selected meta `--fg-secondary` `:658-660`; forced colours `:1538` | verified |
| `router.js` `applyShell` `:406-411` | verified (Architect, cycle 1) |
| `css/base.css` aside `:25-45`; `[hidden]` `:37` | verified |
| `tests/browser/test_ui_rail_contract.py`, `_ui_engines.py` `engine_page` | verified |
| `core.js:96-135` `rovingFocus` is stateless; `test_shell_rail.py:137-171,166`; `test_nav_helper.py:150` `ROUTER_CONTRACT_GLOB`; `test_design_tokens_a11y.py:676-693,756`; cache-busting `len(refs) == 72` | verified (leg design review) |

---

## Post-Completion

Status transitions, the flight-log update, checking off in the parent flight, and the
commit are Flight Control protocol, driven by the execution workflow. They are not
repeated here.
