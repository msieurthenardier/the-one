# Leg: jump-to-palette

**Status**: completed
**Flight**: [Chats and Jump-to](../flight.md)

## Objective

Add the jump-to palette (§9, SC5):
- a **Jump to** control at the bottom of the rail;
- a shell-level **Ctrl K** (Meta K on macOS) listener;
- an `App.ui.modal` with an `App.ui.searchList` that finds agents, chats, the New chat
  action, knowledge bases, MCP servers, connectors and Settings pages, and opens the one
  chosen through the leave guard.

Extract one shared Settings page table. Verify the Ctrl K premise in WebKitGTK with a real
key injection.

## Context

- **Flight decisions:** DD9 (Ctrl K and the rail control), DD10 (palette contents, order,
  cap, keys and picks), DD14 (`modal.ariaLabel`, `modal.anyOpen()` and the rail bottom
  slot, all built here) and DD15 (A10, A11, A17).
- **No library factory may install a document listener** (Flight 1 DD1;
  `test_ui_rail_contract.py:244`). The Ctrl K listener is shell code in `app.js`, beside
  the rail mount.
- **The modal rule's chaining** (Flight 1 DD8): the palette closes **before** it acts, so
  a dirty editor's confirm is the only modal. A dismissed confirm returns focus to the
  palette's opener (the element focused at keydown).
- **Leg 4** exported `App.chat.openPicker({opener})`. **Leg 6** exported
  `App.studio.clearAgentFilter()`.

## Inputs

- `static/js/ui/rail.js` (links only; no slot), `app.js` `mountRail` (around 21–46),
  `ui/modal.js` (leg 1's chooser options) and `ui/search-list.js`.
- `areas/admin.js` around 174–190 (the Settings groups, in a closure; Design language is
  dev-gated), and `router.js` `SECTIONS`/`SECTION_LABELS` (private).
- The `App.store` collections `agents`, `sessions`, `knowledge-bases`, `mcp-sources` and
  `connectors`.
- `scripts/webkitgtk_probe.py`: it evaluates JavaScript in the desktop engine, and
  refuses 8484 and the default data directory.

## Anchors (checked by the Flight Director after leg 4b)

- **`app.js` `mountRail`** (around 21–46) builds rail items from `App.router.destinations`
  and calls `App.ui.rail({items, brand})`. Its `onCommit` keeps the hrefs current. The
  rail footer slot and the Ctrl K listener go here.
- **`ui/rail.js`**: `App.ui.rail = function (opts)` is at around 39 and validates
  `opts.items`. There is no footer slot.
- **`areas/admin.js`** around 170–192: `navItem(section, label)` builds
  `href({destination:'settings', section})`, with the groups General, Models and Defaults
  for agents, plus a dev-mode Developer group.
  - **The section ids differ from the labels.** For example `navItem('knowledge',
    'Knowledge indexing')` has section id `knowledge`, while its route is
    `#settings/knowledge-indexing`, through the router's mapping.
  - The shared `App.settingsPages` table must carry the **section id as the router knows
    it**, and the palette must use `App.router.href({destination:'settings', section})`.
    Verify the id-to-route mapping, and never hand-build `#settings/...`.
- **`router.js`**: `var SECTIONS = [` at around 81, and `var SECTION_LABELS = {` at around
  417, used by `describeRoute` around 485.
- **Leg 4a's `App.chat.openPicker({opener})`** returns a Promise. It navigates to Chats
  first when needed, and rejects on a guard Stay.
- **Leg 6's `App.studio.clearAgentFilter()`** is a safe stub before studio's init.

## Acceptance Criteria

**A. Controls (DD14).**

- [ ] **AC1. `App.ui.rail` bottom slot.**
  - A `footer` option takes an array of **Nodes**, pinned to the bottom
    (`margin-top: auto`). It throws on a non-array or a non-Node; add cases beside
    `test_rail_edge_rules_throw`.
  - **Footer buttons are their own Tab stops.** They are not `.ui-rail-item`, so they are
    outside the rail's `rovingFocus` arrows.
  - It installs no listener. The footer button's click handler is on the node itself.
  - `mountRail` builds the footer node before `App.ui.rail()`; `onCommit` and `setHref`
    never touch it.
  - Existing rail contract tests stay green. Its new contract cases run in both engines.
- [ ] **AC2. `App.ui.modal` additions.**
  - **`ariaLabel`**, for a chooser with **no `title`** (design review question 1,
    option c):
    - the dialog gets `aria-label`, and **no** `h2`, **no** `aria-labelledby` and **no**
      `.modal-dialog-header` row;
    - the caller's body owns any close button and calls `controller.close()`. The Tab
      wrap includes it through `focusables(card)`.
    - Contract assertions: there is `aria-label` and no `aria-labelledby`, and no empty
      `h2` or header remains.
  - **`App.ui.modal.anyOpen()`** returns `stack.length > 0`. The stack includes every
    `App.confirmDialog` confirm, because it is an adapter over `App.ui.modal`
    (`dialog.js` around 76–93), so there is no second source.
    - Tests: true while a leave-guard confirm is open; false after the stack empties,
      including after a `finish` from a bypassed `close` event.
  - Each gets contract cases in both engines, and the demo is updated.

**B. The rail control and the shortcut (DD9).**

- [ ] **AC3. The control.** A 44px `btn-ghost` with the `search` icon in the rail footer.
  The `search` icon is added to `icons.js`; it does not exist yet.
  - `aria-label="Jump to (Ctrl K)"` and `aria-keyshortcuts="Control+K"`. On macOS these
    are "Jump to (⌘ K)" and `Meta+K`, from the same platform detector as AC4
    (question 5);
  - testid `rail-jump-to`;
  - a click opens the palette with the control as the opener.
- [ ] **AC4. The shell listener** is one `keydown` on `document` in `app.js`, installed
  once per boot outside `mountRail`. It looks up `App.ui.modal`, the palette and
  `App.chat` **lazily at keydown**, because `app.js` loads before `ui/*`.
  - **Platform detection:** `navigator.userAgentData && userAgentData.platform`, falling
    back to `navigator.platform`, matched against `/mac|iphone|ipad/i`. It is a pure,
    exported function, so it is unit-testable.
    - On macOS it accepts only `metaKey`.
    - Elsewhere it accepts only `ctrlKey && !metaKey`.
    - Neither accepts Shift or Alt.
    - The key matches if `e.key.toLowerCase() === 'k'` **or** `e.code === 'KeyK'` (Caps
      Lock, non-Latin layouts).
  - it calls `preventDefault()`, and works **from inside inputs and textareas**;
  - it is ignored while `e.isComposing || e.keyCode === 229`;
  - if the palette is open, it focuses the palette input;
  - else, if `App.ui.modal.anyOpen()`, it does nothing;
  - else it opens the palette with `document.activeElement` as the opener.
- [ ] **AC5. WebKitGTK premise** (DD9). This host has no `xdotool`, `ydotool` or `wtype`.
  It is WSLg (`DISPLAY=:0`, `WAYLAND_DISPLAY`), and the system python3 has `gi` with Gdk
  3.0. **The prescribed method is GDK**:
  1. Realize, show and `grab_focus` the WebView.
  2. Focus a text input with `run_js`.
  3. Send the key with `Gtk.test_widget_send_key(webview, Gdk.KEY_k,
     Gdk.ModifierType.CONTROL_MASK)`, or with a `Gdk.EventKey`
     `KEY_PRESS`/`KEY_RELEASE` pair (keyval `Gdk.KEY_k`, `CONTROL_MASK`, the
     `hardware_keycode` from `Gdk.Keymap.get_default().get_entries_for_keyval`) through
     `webview.event(ev)`.
  4. Poll with `run_js` for `[data-testid=jump-to]`.
  - New CLI flags: `--press-keys` and `--assert-selector`; the current CLI is
    resolver-centric (`parse_args` around 123–141).
  - It runs against a dev instance on **8486 or higher**. `check_safety` keeps refusing
    8484, and **8485 is also refused**, which this leg adds.
  - **Verdict wording** (question 6). A GTK-level synthetic key proves less than an
    OS-level key, so a pass is recorded as **"partially verified (GTK-level key)"**. If
    nothing works, it is "unverified", with the reason. The mission Known Issue for
    WebView2 is amended to mention the WebKitGTK verdict. Neither outcome fails this leg.
  - The probe is the leg's **last** step.

**C. The palette (DD10).**

- [ ] **AC6. The modal.** It is `ariaLabel` "Jump to", `layout:'chooser'`, `width:600`,
  `top:96` and `dismissible:true`, with testid `jump-to`.
  - The input bar holds the search icon, the input (visually hidden label "Jump to",
    placeholder "Jump to an agent, chat, library item or setting", testid
    `jump-to-input`) and the close button ("Esc", "Close (Esc)").
  - The footer reads "Ctrl K from anywhere · Enter to open", both on the left ("⌘ K" on
    macOS).
  - **The "Esc" close button is in the input bar** (the body), built by the palette, and
    calls `controller.close()` (AC2).
  - `initialFocus` is the input.
- [ ] **AC7. Candidates**, in this order: agents A–Z; chats newest first; the "New chat…"
  action; knowledge bases; MCP servers; connectors; Settings pages in nav order (Design
  language only in dev mode). "Where" copy, per §9:

  | Candidate | "Where" |
  |---|---|
  | agent | `Agent` |
  | chat | `Chat · {agent}` |
  | New chat… | `Action` |
  | knowledge base | `Library · Knowledge base` |
  | MCP server | `Library · MCP server` |
  | connector | `Library · Connector` |
  | Settings page | `Settings` for Providers, else `Settings · {group}` |

  The rows are `searchList` items with `label`, and `meta` holding the where text (not
  mono), with `rowTestid` `jump-to-result` and `dataset {kind, id}`.
  - Chats are sorted by `updated_at` descending, stable for equal timestamps.
  - A chat with an empty title is labelled "Untitled chat".
  - Its agent is the stored `agent_name`, or "Default agent" when null.
- [ ] **AC8. Matching and cap.**
  - A case-insensitive substring over `label + " " + where`, trimmed.
  - The first 8 matching candidates in order.
  - The empty query shows the first 8 candidates (the board as drawn, a DD13 preview
    question).
  - No match: `No matches for "{q}".`
- [ ] **AC9. A shared Settings page table** (question 3).
  - `App.settingsPages` (new, `static/js/settings-pages.js`) is a plain data table with
    no dependencies, **loaded before `router.js`** in `index.html`. It holds
    `[{section, label, group, devOnly}]`, where `section` is the **router route segment**,
    for example `knowledge-indexing`.
  - `admin.js`'s `navItem` reads it. Its internal `ROUTE_SECTION` map and the
    `'knowledge'` category alias (around 164) stay internal to `admin.js`.
  - The palette reads it.
  - `router.js` builds the **Settings** entries of `SECTION_LABELS` from it **lazily**,
    inside `describeRoute`. `SECTION_LABELS` keeps its Library keys.
  - `devOnly` is filtered at **call** time (`App.config.dev_mode` is set after the boot
    fetch), never at table construction.
  - **A static test:**
    - `settings-pages.js` precedes `router.js` in `index.html`;
    - the router's `SECTIONS` Settings routes equal the table's sections;
    - `admin.js` holds no duplicate label literals.
- [ ] **AC10. Opening a result.** The palette **captures its opener at open**, closes
  **first**, then calls `App.router.go(route, {opener})` with that opener, never relying
  on `document.activeElement`:
  - **agent:** `go(href({destination:'agents', id}), {opener})`. When the promise
    resolves `true` (a commit), it calls `App.studio.clearAgentFilter()`, guarded with
    `typeof … === 'function'`;
  - **chat:** `go(href({destination:'chats', id}), {opener})`, which discards a pending
    chat;
  - **New chat…:** `App.chat.openPicker({opener})` **alone**, with the palette's opener,
    falling back to `#main-content`. `openPicker` already navigates to Chats and rejects
    on a guard Stay (question 2);
  - **knowledge base, MCP server or connector:**
    `go(href({destination:'library', section, id}))`;
  - **Settings page:** `go(href({destination:'settings', section}))`.
  - **From a dirty editor:** exactly one confirm, because `anyOpen()` is false when `go()`
    runs (the palette has closed).
    - **Stay** keeps the edit, focus returns to the palette's opener, and the palette
      **stays closed**.
    - If the opener left the DOM (a re-render), focus falls back to `#main-content`; that
      is accepted.
- [ ] **AC11. Cold data.** On open, it calls `App.store.get` for every collection. It uses
  `{force: true}` for **`sessions`** (question 4): the WebSocket primes it only while
  Chats is active, so off Chats it may be stale. It re-runs `refresh()` as each one
  resolves, and **only while the palette is still open**: a closed palette's
  `searchList` is never touched. A failed collection is left out silently, the others
  still show, and a test covers one rejected collection.

**D. Tests, gates and docs.**

- [ ] **AC12. `tests/browser/test_flow_jump_to.py`** (in the shared lane):
  - Ctrl K from Agents, from inside a field, and from Settings;
  - the rail control;
  - the empty-query cap of 8;
  - each kind found and opened;
  - "New chat…" opens the picker;
  - a pick from a dirty editor asks once, Stay keeps the edit, and focus returns to the
    opener;
  - Escape;
  - Ctrl K while the picker or the confirm is open does nothing;
  - Ctrl K while the palette is open focuses its input;
  - **Shift+Ctrl+K** and **Ctrl+Alt+K** do nothing;
  - a dispatched `KeyboardEvent` with `isComposing: true` does nothing;
  - the platform detector unit cases, including macOS through `add_init_script`;
  - `test_flow_jump_to.py` runs in **`shared`** (the complement rule), with no
    `run-tests.sh` change;
  - dev-mode Design language.
- [ ] **AC13. Accessibility.** The palette passes the resolver probe. The active row
  follows `aria-activedescendant`. The rail control's name is checked. Focus returns
  correctly after Escape and after Stay.
- [ ] **AC14. Gates.**
  - `make lint` and format;
  - the static guards;
  - `make test-unit`;
  - the lanes `contracts` (`THE_ONE_REQUIRE_WEBKIT=1`), `shared` (`TEST_TIMEOUT=3600`),
    `settings` (the Settings nav reads the shared table), `agents` and `chats`, through
    `scripts/run-tests.sh` with `THE_ONE_TEST_NETNS=1`;
  - the AC5 probe result.
- [ ] **AC15. Docs.**
  - `CLAUDE.md`: a "Jump-to palette (M25 F4 L7)" paragraph covering Ctrl K, `rail-jump-to`,
    `jump-to*`, `App.settingsPages`, and the shell-listener location.
  - `the_one/agents.md`.
  - The inventory (the rail and modal rows; the palette as a composition).
  - The registry.

## Verification Steps

- The lanes and guards in AC14, and the WebKitGTK probe in AC5.
- **A manual pass** in Light and Dark at 1440 and 1024, on a dev instance (port 8486 or
  higher, scratch data dir).
- **Falsify twice:**
  - make the palette navigate before closing, and watch the "one confirm" test fail;
  - drop `anyOpen()` from the listener, and watch the "Ctrl K while the confirm is open"
    test fail.

  Restore each, and record them.

## Edge Cases

- **Ctrl K during a route transition**, while the guard is deciding: `anyOpen()` is true
  while the confirm is open, so it is ignored.
- **The browser's own Ctrl K** (the address bar search in Chromium):
  `preventDefault` on `document` keydown works in pages. The desktop shells are covered
  by AC5 and the Flight 5 Known Issue.
- **An empty data set** (a fresh install): the palette still lists New chat… and the
  Settings pages.
- **A chat title equal to an agent name:** both rows show, told apart by their "where"
  text.

## Files Affected

- New: `static/js/settings-pages.js`, `areas/palette/jump-to.js` (or `static/js/jump-to.js`)
  and `tests/browser/test_flow_jump_to.py`.
- Changed:
  - `static/js/ui/rail.js` and `ui/modal.js`;
  - `app.js` (the rail footer and the Ctrl K listener);
  - `areas/admin.js` and `router.js` (the shared table);
  - `index.html`, `css/components.css` and `js/icons.js` (`search`, unless already added);
  - `scripts/webkitgtk_probe.py`.
- Tests: the rail and modal contract tests, and the static pins.
- Docs: `CLAUDE.md`, `the_one/agents.md`, `docs/ui-control-inventory.md`,
  `docs/ui-testid-registry.md`, and `mission.md`'s Known Issues if AC5 is unverified.
