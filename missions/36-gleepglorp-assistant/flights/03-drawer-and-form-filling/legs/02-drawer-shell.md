# Leg: drawer-shell

**Status**: completed
**Flight**: [The GleepGlorp drawer and form filling](../flight.md)

## Objective
Put the GleepGlorp corner button and an empty drawer frame on every
destination except Chats. The frame has its header, its "Looking at" line,
Close and Esc, its setup and off states, and push or overlay by width. Leg 3
mounts the drawer's chat into it.

## Context
- **Flight DD1** (the drawer and the corner button) and the operator-approved
  board: https://claude.ai/artifact/SmbUk6Qt97V2866fpp72kL
  - **"Drawer closed"** artboard (`OptionBClosed`): a 48 px violet tile with
    the white Lucide robot, 24 px from the bottom-right.
  - **"B. Right drawer"** (`OptionB`) and the panel (`Overlay`): a 360 px
    drawer. Its header has the robot tile, "GleepGlorp", New chat, Open in
    Chats, a divider and a labelled **Close**. Under it is the "Looking at"
    line.
  - **"Panel states"** (`States`): this leg draws only the **setup** state.
    The empty, working and filled states need the chat (Legs 3 and 6).
- **The header's New chat and Open in Chats buttons are Leg 3.** This leg's
  header has the robot tile, the title and Close only, laid out so Leg 3 adds
  the two buttons and the divider before Close.
- **Operator decisions (2026-11-19):**
  - no corner button or drawer on Chats;
  - the standard robot icon, not the pixel mark;
  - a labelled Close and Esc;
  - the drawer starts closed.
- **Leg 1** (`01-chat-instance`) lifts the Chats area into
  `App.chat.create`. This leg does not depend on it and must not touch the
  chat modules. If Leg 1 is still uncommitted when this leg runs, both legs
  edit `index.html` (different lines); keep Leg 1's lines intact.
- **Today:**
  - `App.ui.drawer` (`js/ui/drawer.js`) is a non-modal `<aside>` with push and
    overlay modes. `open()` never moves focus. `close()` refocuses the
    recorded opener only when focus is inside, **before** hiding. Its own
    keydown handler closes on Esc.
  - The Chats agent drawer (`areas/chat/agent-drawer.js` ~:102, ~:614)
    switches mode with `matchMedia('(min-width: 1280px)')`.
  - The shell (`index.html` ~:25-30) is `.app-shell-row` holding `#app-rail`,
    `#app-sidebar`, `<main id="main-content">` and `#chat-drawer`.
  - `tests/browser/test_shell_rail.py` (~:75-80) pins the row's children's
    ids and the body's children.
  - The router notifies `onCommit(fn(destId))` subscribers only from
    `applyShell` (`router.js` ~:597-611). `sync()` (~:754) canonicalises
    in-area routes and notifies no one. `describeRoute(route, hint)` (~:524)
    builds the spoken labels (`{parts, key}`).
- **GleepGlorp's state** comes from `App.gleepglorp` (`js/gleepglorp.js`,
  `get()`, `subscribe(fn)`, with `state` in `off`, `needs_model`,
  `provider_missing` or `ready`). `App.chat.gleepglorpBanner(state)` gives the
  plain sentence for a not-ready state, and
  `App.chat.agentKind('GleepGlorp').settingsHref` gives the settings link
  (`areas/chat/agent-kind.js`).

## Inputs
- The working tree after Leg 1 (or `3aa9ea94` plus the planning artifacts, if
  Leg 1 has not landed). This leg's files do not overlap Leg 1's, except
  `index.html`.

## Outputs
- **New `App.ui.cornerButton`** (`js/ui/corner-button.js`): the 48 px violet
  tile button with an icon. It has a catalogue row in
  `docs/ui-control-inventory.md` and an engine-parametrized contract test
  file, `tests/browser/test_ui_corner_button_contract.py` (Chromium and
  WebKit, `contracts-controls` lane).
- **A `bot` icon** in `js/icons.js` (the Lucide robot; the same paths as
  `studio`).
- **An `App.ui.drawer` option, `beforeClose`.** It is called at the start of
  every close (Close, Esc, `toggle`), **before** focus is returned, so a
  caller can show the opener first. Catalogue row updated; one contract test
  added to the existing drawer contract file.
- **Router: `App.router.onRouteChange(fn)` and `App.router.describeCurrent()`.**
  - `fn({route, destination, parts})` runs at the **end of `commit`**, after
    the area's mount and hydrate (not in `applyShell`, which runs before
    hydrate), and after every successful `sync`.
  - `parts` comes from `describeRoute`, with the same names the announcer
    uses.
  - `describeCurrent()` returns the same `{route, destination, parts}` for
    the current route on demand. The shell calls it when a Library store
    collection loads, because `describeRoute` takes an item's name from a
    synchronous `App.store.peek`. A cold deep link to an MCP server would
    otherwise read "MCP server" until the next navigation.
  - It returns an unsubscribe.
  - `onCommit` is unchanged.
- **The drawer shell** (`js/gleepglorp-drawer/shell.js`, `App.gleepglorpDrawer`):
  - **Slot:** `<aside id="gleepglorp-drawer" aria-label="GleepGlorp"
    data-testid="gg-drawer" hidden>` in `index.html`, after `#chat-drawer`.
    The corner button is mounted as the last child of `.app-shell-row`.
  - **Header:** the robot tile, an `h2` "GleepGlorp", and a labelled Close
    (`gg-drawer-close`, `aria-keyshortcuts="Escape"`). The "Looking at" line
    is `gg-drawer-context`.
  - **Body slot:** `gg-drawer-body`. Leg 3 mounts the chat here, through
    `App.gleepglorpDrawer.bodySlot()`.
  - **Setup state:** `gg-drawer-setup`, shown when the state is
    `needs_model` or `provider_missing`. It holds the plain sentence and a
    primary "Choose a model" link to Settings › GleepGlorp.
  - **Closed by default:**
    - The open or closed state is held in memory per window.
    - The corner button is `gg-corner-button`, named "Ask GleepGlorp", with
      `aria-expanded` and `aria-controls="gleepglorp-drawer"`.
  - **Width:** push at 1280 px and wider, overlay below, by a `matchMedia`
    listener.
  - **Chats and off:** the button and the drawer are hidden on Chats and when
    the state is `off`. The open state is remembered across Chats and
    restored on leaving it.
  - **Focus:**
    - opening moves focus to the drawer's `h2` (`tabindex="-1"`; Leg 3 moves
      it to the composer);
    - closing shows the button, then returns focus to it;
    - Esc closes while focus is inside and no modal is open.
- **Content padding, per scroll container.** While the button shows (a
  `gg-corner-on` class on `.app-shell-row`), the destinations' scroll
  containers get 72 px of bottom padding, so their last control scrolls out
  from under the button. No full-width band is reserved. The containers are:
  - `.area-studio .studio-editor` (`studio.css` ~:21) and
    `.studio-section-content` (~:15), for Agents and Library;
  - `.area-admin .admin-content` (`admin.css` ~:16), for Settings.

  The Library and Agents *lists* sit in `#app-sidebar` on the left and never
  meet the button.
- **Jump to.** An "Ask GleepGlorp" candidate (`data-kind="gleepglorp-ask"`),
  present **only off Chats** while GleepGlorp is enabled. On Chats, the
  existing `GleepGlorp` candidate already starts a chat. Picking it opens the
  drawer from the palette modal's `onClose`, after the modal has returned
  focus to its opener (the `requestPick` pattern in
  `areas/chat/agent-picker.js`), so the drawer's focus move wins.
- **Tests** for the button, the drawer, focus, Chats, off, setup, width,
  the "Looking at" line, the padding and Jump to:
  `tests/browser/test_flow_gleepglorp_drawer_shell.py`, in the `shared`
  lane.
- **Pin updates:**
  - `test_shell_rail.py` ~:75: the row's children become `[..., "chat-drawer",
    "gleepglorp-drawer", "gleepglorp-corner-button"]`. The button has
    `id="gleepglorp-corner-button"`. Body children (~:80) are unchanged.
  - `test_shell_rail.py`'s landmarks test gains one assertion: with the
    drawer open, the landmark list includes the complementary "GleepGlorp".
  - `test_flow_jump_to.py`: the GleepGlorp-on tests (~:952-995), including
    `_jump(page, "gleep", …)` (~:974), the `order` assertion (~:967) and the
    candidates filter (~:994), are re-checked for the new candidate's
    "gleep" match and updated if they now see two results.
- **Docs:**
  - the catalogue rows;
  - `the_one/agents.md`: a new section, "GleepGlorp drawer (M36 F3 L2)";
  - a short CLAUDE.md paragraph.

## Acceptance Criteria
- [ ] **AC1. `App.ui.cornerButton`.**
  - It is a native `<button type="button">` with an `aria-label`, an icon
    (`aria-hidden`), `aria-expanded` and `aria-controls` set by the caller,
    and a caller-supplied `testid`.
  - Its handle is `{el, setExpanded(bool), setHidden(bool), focus()}`.
  - Its colours come from tokens (`--accent-fill`, `--fg-on-accent-fill`), and
    its focus ring is the house focus ring.
  - It has a catalogue row with its owned classes. The contract file passes
    in Chromium and WebKit under `THE_ONE_REQUIRE_WEBKIT=1`.
  - `tests/test_ui_control_inventory.py`, `test_ui_ownership.py` and
    `test_ui_emitted_classes.py` pass.
- [ ] **AC2. `App.ui.drawer` `beforeClose`.**
  - `beforeClose()` runs before the focus return on every close path (the
    `close()` call, `toggle`, Esc), and never when the drawer is already
    hidden (after `close()`'s early return).
  - A contract test shows that an opener hidden at open time and shown in
    `beforeClose` receives focus on Esc.
  - Existing drawer contract tests pass unedited, and the Chats agent drawer
    is unchanged.
- [ ] **AC3. `App.router.onRouteChange` and `describeCurrent`.**
  - It fires once per commit, at the end of `commit` (after the area's
    hydrate).
  - It fires once per successful `sync`, never for a dropped sync.
  - Each call carries `{route, destination, parts}`, where `parts` equals
    `describeRoute(route, hint).parts`. `describeCurrent()` returns the same
    shape for the current route.
  - It returns an unsubscribe. A throwing subscriber never breaks a commit or
    a sync.
  - Router contract tests cover the commit, the sync, a dropped sync, the
    unsubscribe, and a cold item route whose store loads afterwards
    (`describeCurrent()` then names the item).
- [ ] **AC4. The corner button.**
  - It is visible on Agents, Library and Settings while GleepGlorp is not
    `off`.
  - It is hidden on Chats and when `off`.
  - Toggling Enabled in Settings › GleepGlorp and saving hides or shows it
    without a reload, through `App.gleepglorp.subscribe`.
  - It sits at the bottom-right of the shell row, inside `.app-shell-row`.
- [ ] **AC5. Open and close.**
  - A click opens the drawer: `gg-drawer` is visible, the button is hidden,
    and `aria-expanded` is `"true"`. Focus is on the drawer's `h2`.
  - Close or Esc closes it, the button shows again, and focus is on the
    button.
  - The drawer starts closed on every load.
  - Moving between Agents, Library and Settings keeps it open or closed as it
    was.
  - Going to Chats hides both the button and the drawer. Leaving Chats
    restores the drawer's previous state.
- [ ] **AC6. Width.**
  - The drawer is 360 px wide. `--drawer-w` stays 320 px for the Chats
    drawer, and `#gleepglorp-drawer` overrides the width in its own
    stylesheet.
  - At 1280 px and wider the drawer pushes `<main>`: main's width shrinks by
    360 px.
  - Below 1280 px it overlays: `data-mode="overlay"`, and main's width is
    unchanged.
  - Crossing 1280 px while the drawer is open switches the mode live.
  - At the 1024 px minimum, with the drawer open in overlay mode, an agent
    editor's Save button's bounding box is inside `<main>` and does not
    intersect the drawer's box.
- [ ] **AC7. The "Looking at" line.**
  - It names the current page from `onRouteChange` parts, for example
    "Library › New MCP server" on `#library/mcp/~new`, or an agent's name and
    tab on `#agents/{name}/tools`.
  - It updates on a destination change, on an item change within a
    destination, and on a save-create's `sync`.
- [ ] **AC8. The setup state.**
  - With GleepGlorp `needs_model` or `provider_missing`, the open drawer
    shows `gg-drawer-setup` with the same sentence the chat banner uses for
    that state.
  - Its "Choose a model" link goes to Settings › GleepGlorp.
  - With `ready`, the setup block is hidden and the body slot is empty
    (Leg 3 fills it).
- [ ] **AC9. The button never covers content.**
  - On a long Library list, a long Settings page, and an agent editor's
    Tools tab, scrolled to the bottom, the last focusable control's bounding
    box does not intersect the corner button's.
  - A Playwright click on that control succeeds without `force`.
- [ ] **AC10. Jump to.**
  - With GleepGlorp enabled and the route off Chats, the palette's search for
    "ask" lists "Ask GleepGlorp" (`data-kind="gleepglorp-ask"`).
  - Picking it on Library opens the drawer, and focus lands on the drawer's
    `h2` after the palette has closed.
  - It is absent on Chats and when GleepGlorp is off.
- [ ] **AC11. No regressions, and the lanes.**
  - A full browser run passes:
    `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 TEST_TIMEOUT=3600
    PYTHON=.venv/bin/python bash scripts/run-tests.sh --parallel 3`, on a host
    with no other test process.
  - So does the unit tier, run separately: `THE_ONE_TEST_NETNS=1 make
    test-unit`.
  - The only edited existing assertions are the pins listed under Outputs.
    Each is reported with its old and new value.
- [ ] **AC12. Docs.** The catalogue rows (`cornerButton`, `drawer`
  `beforeClose`), the `agents.md` section and the CLAUDE.md paragraph are
  written. The static guards pass: `tests/test_ui_guards.py`,
  `tests/test_token_definitions.py` and `tests/test_design_tokens_a11y.py`.

## Verification Steps
- **AC1, AC2:**
  - Run the contract files with `THE_ONE_REQUIRE_WEBKIT=1` through
    `scripts/run-tests.sh -m browser <files>`.
  - Run the unit-tier catalogue guards.
- **AC3:** the router contract tests (`tests/browser/test_router_*`, the
  `routing` lane).
- **AC4-AC10:** `tests/browser/test_flow_gleepglorp_drawer_shell.py`, using
  `_nav` helpers and the browser fixtures. GleepGlorp's state is set through
  `PUT /api/gleepglorp` in the seed:
  - **ready:** a mock provider with a model;
  - **needs_model:** no model;
  - **off:** `enabled=false`.
- **AC9:** the test measures bounding boxes after scrolling the containers to
  the bottom.
- **AC11:** the full parallel run's `PARALLEL_RESULT` line and the unit
  counts, recorded in the flight log. Expect 15 skipped under netns.
- **AC12:** read the docs, and run the static guards.

## Implementation Guidance

1. **Survey (read only)** before editing. Record the findings in the flight
   log entry.
   - `js/ui/drawer.js` and its contract tests (`tests/browser/test_ui_drawer*`);
     `docs/ui-control-inventory.md`'s `drawer` row.
   - `areas/chat/agent-drawer.js`'s mode switching (~:100-110, ~:595-620).
   - `router.js` `applyShell`, `sync` and `describeRoute`.
   - `app.js` boot order (where `mountRail` and `installJumpToKey` run, and
     when the router starts).
   - `js/gleepglorp.js` (`get`, `subscribe`, `prime`, state names).
   - `jump-to.js` (`candidates`, `emptyMix`, the pick handler).
   - Every test that pins `.app-shell-row`'s children, the body's children,
     the landmark list (`_LANDMARKS_JS`), Jump to's candidate counts or
     orders, or the last focusable element of a page.
   - **The scroll containers** of Agents (editor body, tabs), Library (list
     and detail) and Settings (nav and page), for AC9's padding.

2. **Icons and `App.ui.cornerButton`.** Follow the existing factory
   conventions (`js/ui/button.js` style: ES5, `App.ui.util.el`, no HTML
   strings).
   - **Its CSS** goes in `components.css` inside `@layer components`, with an
     owned class such as `ui-corner-button`. It is `position: absolute;
     right: 24px; bottom: 24px` within `.app-shell-row`, with a `z-index`
     below menus (20-50) and modals and below the overlay drawer (10), for
     example 9. Record the value in the row.
   - **The catalogue row** (`docs/ui-control-inventory.md`, the columns at
     ~:38/47): classified `library: App.ui.cornerButton`, with its owned
     classes listed.
   - **The contract file** must contain the text `App.ui.cornerButton(`
     (`tests/test_ui_control_inventory.py`). It covers the focus ring,
     `aria-*`, `setHidden`, `setExpanded`, click, and keyboard Enter and
     Space.
   - **Every emitted class is owned** (`tests/test_ui_emitted_classes.py`).
     Owned classes must not appear in CSS or JS outside `js/ui/` and their
     own CSS (`tests/test_ui_ownership.py`), so the shell styles its own
     wrapper classes, never `ui-corner-button`.
   - Check `tests/test_ui_listener_cleanup.py` for factories with `destroy`.
   - The `bot` icon uses Lucide's `bot` paths with `studio`'s stroke
     attributes.

3. **`App.ui.drawer` `beforeClose`.** In `close()`, call
   `opts.beforeClose()` first, wrapped in try/catch, then run today's
   focus-return and hide. Add the contract test.

4. **`App.router.onRouteChange` and `describeCurrent`.** Keep a hooks list
   like `commitHooks`.
   - Call it at the end of `commit` (after step 8, the hydrate), with the
     current route's description. Do not call it from `applyShell`.
   - Call it at the end of a successful `sync`, after `titleFor`.
   - Guard each subscriber with try/catch.
   - Expose `onRouteChange` and `describeCurrent()` on `App.router`.

5. **The shell slot and the drawer shell.**
   - Add the `<aside>` to `index.html`. Create `js/gleepglorp-drawer/shell.js`
     and load it after the `ui/` factories and `gleepglorp.js`, before
     `app.js`'s boot uses it. Check where `app.js` mounts the rail; mount the
     drawer shell right after it.
   - Build the drawer with `App.ui.drawer({el, label: 'GleepGlorp', heading:
     <header node>, body, beforeClose})`.
   - Build the corner button and append it to `.app-shell-row`.
   - Subscribe to `App.gleepglorp`, `App.router.onCommit` (Chats or not) and
     `App.router.onRouteChange` (the "Looking at" line).
   - Also subscribe to the five Library store collections (`providers`,
     `knowledge-bases`, `mcp-sources`, `connectors`, `secrets`) and re-render
     the line from `describeCurrent()` when one loads.
   - Mount right after `mountRail()` and `installJumpToKey()` (`app.js`
     ~:195-197), before `router.start` (~:233), so the first commit is seen.
   - **`App.gleepglorp.get()` at mount.**
     - It is not an `App.store` collection, so `test_store.py`'s counts are
       unaffected (verify).
     - Until a state is known the button stays hidden.
     - A failed `get()` notifies no one, so the shell retries it on the next
       `onCommit` while the state is still unknown.
     - Settings › GleepGlorp's Save already primes `App.gleepglorp`
       (`areas/admin/gleepglorp-page.js` ~:427, ~:602).
     - These tests route-mock `**/api/gleepglorp`, so run them as named
       files and confirm the drawer's earlier GET does not consume their mock
       or leave a stale cache:
       - `test_flow_settings_gleepglorp.py` (~:207, ~:266);
       - `test_flow_settings_gleepglorp_memory.py` (~:218);
       - `test_flow_chat_gleepglorp.py`.
   - The `matchMedia` listener sets the mode.
   - Expose `App.gleepglorpDrawer = {open(opener), close(), isOpen(),
     bodySlot(), setContext(...)}` for Leg 3 and the tests.

6. **CSS.**
   - Add a small `css/gleepglorp-drawer.css` (link it in `index.html`) or a
     section in `components.css`, for the drawer's width (360 px), the
     header row, the robot tile, the "Looking at" line and the setup block.
     Use the board's sizes and tokens only (`tests/test_token_definitions.py`).
   - The corner button's own styles belong to the factory's owned classes.
   - **Width.** `--drawer-w` is 320 px (`tokens.css` ~:60;
     `.ui-drawer { width: var(--drawer-w) }`, `components.css` ~:1879). Do
     not change the token. Set `#gleepglorp-drawer`'s width to 360 px in the
     shell's stylesheet.
   - **Layers.** `tests/test_css_layers.py` fails on unlayered rules, so the
     new stylesheet uses the project's layer convention (read the test), and
     the id override must win over the `@layer components` width.
   - The push and overlay layout reuse `.ui-drawer--push` and `--overlay`;
     `.app-shell-row`'s `position: relative` anchors the overlay.

7. **Content padding (AC9).**
   - `.app-shell-row.gg-corner-on .area-studio .studio-editor`,
     `.app-shell-row.gg-corner-on .area-studio .studio-section-content` and
     `.app-shell-row.gg-corner-on .area-admin .admin-content` get
     `padding-bottom` of their current value plus 72 px.
   - Read each container's existing padding first. None uses `!important`;
     verify.
   - Nothing changes while the button is hidden.

8. **Jump to.**
   - Add the candidate off Chats only (the enabled check through
     `App.chat.gleepglorpEnabled()`; the destination through
     `App.router.current()`).
   - On pick, open the drawer in the palette modal's `onClose`, after focus
     has returned, as the agent picker's `requestPick` does.
   - Do not add it to `emptyMix`, so existing order pins hold. Then re-check
     `test_flow_jump_to.py`'s GleepGlorp-on tests (Outputs, pin updates).

9. **Tests (AC4-AC10)** in `test_flow_gleepglorp_drawer_shell.py`. Then grep
   and update the pins, then the docs.

10. **The full browser run and the unit tier (AC11),** each alone on the
    host: check `uptime` and `ps` first, and run the unit tier after the
    browser run, never at the same time. Record the results in the flight
    log.
    - Before the full run, run the likely victims of a click intercepted by
      the corner tile one at a time, and fix any interception there:
      `agents`, `agent-tabs`, `agent-routines`, `library`, `settings`,
      `settings-tools`, `providers` and `knowledge`.
    - Also run `test_flow_chat_drawer.py`, `test_flow_chat_drawer_notices.py`,
      `test_flow_chat_composer.py` and `tests/test_nav_helper.py`, since they
      touch the shell or `chat-drawer`.

## Edge Cases
- **The 1280 px default viewport.** Every browser test runs at 1280 px, the
  push threshold, so the drawer stays closed unless a test opens it. Any test
  that opens it gets a 360 px narrower `<main>`.
- **Focus when the drawer closes while focus is elsewhere** (a destination
  change to Chats hides it): `App.ui.drawer`'s rule applies, so focus is not
  stolen. The button's hidden state on Chats does not matter.
- **A modal open** (`App.ui.modal.anyOpen()`, `App.confirmDialog`): Esc
  belongs to the modal. The drawer's handler only sees keys while focus is
  inside it, and a modal moves focus.
- **The state changes while the drawer is open.** `ready` to `needs_model`
  shows the setup block. `off` closes and hides it, and focus moves to
  `<main>`, not `<body>`, if it was inside.
- **`App.gleepglorp.get()` fails at boot.** Keep the button hidden until a
  state is known, and retry on the next `subscribe` notification. Never show
  the button in an unknown state.
- **The desktop webviews.** The fixed tile must not cover the native window's
  resize corner. It sits inside the web content, so this is fine; Leg 9
  checks.
- **Ctrl K** works unchanged. The drawer adds no document-level listener.

## Files Affected
- `the_one/interfaces/web/static/js/ui/corner-button.js` — new factory.
- `the_one/interfaces/web/static/js/ui/drawer.js` — the `beforeClose` option.
- `the_one/interfaces/web/static/js/icons.js` — `bot`.
- `the_one/interfaces/web/static/js/router.js` — `onRouteChange`.
- `the_one/interfaces/web/static/js/gleepglorp-drawer/shell.js` — new.
- `the_one/interfaces/web/static/js/jump-to.js` — the candidate.
- `the_one/interfaces/web/static/js/app.js` — mount the drawer shell.
- `the_one/interfaces/web/static/index.html` — the slot, scripts and
  stylesheet.
- `the_one/interfaces/web/static/css/*.css` — the drawer and the padding.
- `docs/ui-control-inventory.md` — `cornerButton` row; `drawer` row.
- `tests/browser/test_ui_corner_button_contract.py` — new.
- `tests/browser/test_ui_drawer*` — one `beforeClose` test.
- `tests/browser/test_router_*` — the `onRouteChange` tests.
- `tests/browser/test_flow_gleepglorp_drawer_shell.py` — new.
- `tests/browser/test_shell_rail.py`, and any other pin found by the step 1
  grep.
- `the_one/agents.md`, `CLAUDE.md` — docs.

## Citation Audit
Checked against the working tree at `3aa9ea94`. Leg 1 is in flight and does
not touch these files, except `index.html`; re-check `index.html` after Leg 1
lands.
- `js/ui/drawer.js::App.ui.drawer` — `open()` never moves focus; `close()`
  refocuses the opener only when focus is inside, before setting `hidden`; a
  keydown handler on the `<aside>` closes on Esc; `setMode('push'|'overlay')`
  — verified (read in full).
- `areas/chat/agent-drawer.js` ~:102 `PUSH_QUERY = '(min-width: 1280px)'`,
  ~:614 `matchMedia` — verified (grep).
- `index.html` ~:25-30 — the shell row and `#chat-drawer` — verified.
- `tests/browser/test_shell_rail.py` ~:75 (row children ids), ~:80 (body
  children) — verified.
- `router.js::onCommit` (~:434) and `applyShell` (~:597-611, the commit
  hooks) — verified. `router.js::sync` (~:754-790) has no notification —
  verified. `describeRoute` (~:524) returns `{parts, key}` — verified.
- `app.js::mountRail` (~:27-66), the rail's `footer` holds Jump to —
  verified.
- `jump-to.js::candidates` (~:125-165), the existing `gleepglorp` candidate
  (~:131) — verified (grep).
- `areas/chat/agent-kind.js` — `gleepglorpBanner`, `gleepglorpEnabled`,
  `GLEEPGLORP_STATUSES`, the settings href — verified (grep).
- `tests/browser/test_store.py::test_request_counts_per_activation` (~:345)
  counts `/api/agents` and `/api/providers` only — verified.
- **Design review (Developer, cycle 1)** added and verified:
  - `--drawer-w` 320 px (`tokens.css` :60; `components.css` :1879);
  - the scroll containers (`studio.css` :15, :21; `admin.css` :16);
  - `commit`'s step order, with `applyShell` before hydrate, and
    `describeRoute`'s store-peek names;
  - `App.gleepglorp.prime` on Settings Save (`gleepglorp-page.js` :427,
    :602);
  - the route-mocking GleepGlorp tests;
  - `test_flow_jump_to.py` :952-995;
  - the catalogue columns (`docs/ui-control-inventory.md` :38/47, `drawer`
    row :101);
  - the boot order (`app.js` :195-197, :233);
  - the script order (`gleepglorp.js` :85, `agent-kind.js` :90,
    `ui/drawer.js` :64);
  - the lanes for the two new test files.
