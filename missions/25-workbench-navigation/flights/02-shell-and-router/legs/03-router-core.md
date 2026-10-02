# Leg: router-core

**Status**: completed
**Flight**: [Shell and Router](../flight.md)

## Objective

Bring in the destination router and route the whole app through it:
- `router.js` with the destination and alias tables, the new URL scheme and legacy
  redirects, `go`/`sync`, sequence-stamped history and `popstate` authority, plus the
  boot and unknown-hash rules;
- `app.js` driven by the router through a fixed commit sequence;
- studio changes (a)–(c) that stop Agents and Library leaking into each other;
- an interim guard on **every** `go()` and every traversal;
- the shell bits (aside, `data-destination`, labels);
- the test-helper flip.

Every `App.router.replaceSub(x)` call is replaced **mechanically** with
`App.router.sync('<area>', x)`. The area is explicit at each site (`'chat'`, `'studio'`,
`'admin'`). This is about 28 sites with no behaviour decisions, and the sync keeps
replace semantics. `replaceSub` is then removed; there is no shim. Squawk 0082 is fixed
by construction. The intent and bypass conversions are left to leg `04`.

## Context

- **Flight decisions:** DD1, DD2, DD3 (a)–(c), DD4, DD7 (aside, `data-destination`,
  labels) and DD12. Read them in `flight.md`.
- **Why the leg was split** (design review, 2026-10-01). Leg `04`
  (`item-history-and-exact-rendering`) holds the per-call-path intent and bypass
  conversions (item-level history pushes), dead ids, the Chats row, the links and the
  `mcps-tab` rework. The explicit-area `sync` keeps every intermediate state green:
  - item writes still replace, so Back crosses sections and destinations, which the
    existing cleanup handles;
  - a late write from a non-current area is dropped by the destination rule;
  - legacy in-app hrefs keep working through the redirect table, which also proves the
    redirects in-app;
  - `mcps-tab`'s own `hashchange` listener still works, because `/mcps/` is still in the
    hash.
- **Sequencing:** this leg runs after leg 1 (`_nav` and lanes) and leg 2 (`App.ui.modal`
  and the `App.confirmDialog` adapter, single-open until leg 5). Both touch `index.html`,
  the cache-busting count and the dirty-confirm tests.
- **The interim guard is a narrowed form of the flight's Technical Approach item 3**,
  decided at this leg's review:
  - the router runs the outgoing area's existing `confirmLeave(proceed, abort)` on
    **every `go()` unless `bypassGuard`**, and on every traversal;
  - the in-area gates that would prompt a second time are deleted:
    - studio's section-nav `_confirmLeaveImpl(commit…)` (studio.js:383-448);
    - admin's `setCategory` gate (admin.js:246-260);
  - section-nav `onSelect` becomes `go(section root)`;
  - leg 5 (`unified-leave-guard`) replaces the area hooks with `App.nav`.

## Inputs

- `static/js/app.js`: `registerArea`, `renderTopBar`, `parseHash`, `syncUrlFromState`,
  `switchTo`, `performCrossAreaSwitch`, `confirmLeave`, `hashchange`, boot (:189-219),
  the `App.router` exports (:309-314).
- `areas/studio.js`: `hydrateState` (:84-191; bare branches at :96 and :163), the section
  nav and its gate (:383-448), `setActiveSection` (:1078-1123), `doSelect` (:1796-1798
  forced switch; :1846 stale guard), `_refresh` and `tryConsumePendingSelect`
  (:2931-2948), `_confirmLeaveImpl` (:2965-2985).
- `areas/admin.js`: `setCategory` gate (:246-260), `_setCategory` (:718-732),
  `_confirmLeaveImpl` (:664-673), `hydrateState`.
- `areas/layout/section-nav.js`, `areas/chat.js` (`serializeState`/`hydrateState`).
- `tests/browser/_nav.py` (`SCHEME`, `LEGACY_URL_TESTS` — 9 entries — `destination_locator`,
  `open_destination`), the leg 1 migration guard, `tests/browser/test_flow_hash_routing.py`,
  `test_flow_studio_navigation.py`, `test_flow_studio_mcp_navigation.py`,
  `test_flow_dirty_confirm.py`, `test_flow_cross_area_dirty_gate.py`,
  `test_flow_keyboard.py`, `test_flow_admin_knowledge_settings.py`.

## Outputs

- **`static/js/router.js`** (new, loaded right after `app.js`). It provides:
  - the destination table;
  - an alias table mapping (area, sub) ↔ route;
  - the redirect table, derived from the alias table plus exceptions;
  - `App.router.{destinations, start, go, sync, href, parse, current, lastRoute,
    isDeciding}`;
  - seq history, `popstate` authority and `hashchange` de-duplication;
  - boot, unknown-hash and element-id rules.

  `App.router.replaceSub` is **removed**. Every call site uses
  `App.router.sync('<area>', sub)` with its own area.
- **`app.js`** keeps the registry, `App.areas`, and a private `mountArea(areaId)` (the
  panel lifecycle). It renders the interim 4-button top bar from
  `App.router.destinations` with `App.ui.util.el`, which removes the `renderTopBar`
  inner-HTML sink and its baseline entry. Boot calls `App.router.start()`. The old
  `switchTo`, `syncUrlFromState`, area-level `hashchange` and boot `switchTo` are
  removed.
- **Studio:**
  - (a) outgoing-section cleanup moves into `setActiveSection`. `hydrateState` captures
    `prev` and passes it in, and **stops assigning `_activeSection` itself**: today it
    assigns before calling `_setActiveSection` (studio.js ~:181), so `prevSection` always
    equals `section` on the hydrate path. That is the root of the leak;
  - **same-section close is preserved.** `commit()`'s same-section branch is lifted into
    one `closeOpenItem()` helper, called from the **section-root branch** of
    `hydrateState`. It closes MCP and connector form modes, KB detail (with
    `clearKnowledgePoll` and a `knowledgeDetailHandle` reset), and agent and create
    mode. Clicking the current section still closes the open editor, as the F4 L7 and
    M10 tests pin. Admin gets the same: `_setCategory` on an unchanged category with an
    item open closes it;
  - (b) `_refresh` re-selects only on Agents;
  - the `doSelect` entry and completion are both guarded against a section change;
  - `tryConsumePendingSelect` and `_refresh` call `doSelect`, not `selectAgent`, so a
    hydrate never re-prompts;
  - the section-nav gate is deleted and `onSelect` calls `go(section root)`;
  - (c) the section nav serves Library only: Knowledge bases, MCP servers and
    Connectors, labelled "Library sections". It is rendered once.
- **Admin:** the `setCategory` gate is deleted and `onSelect` calls `go(section root)`.
  The section nav is labelled "Settings sections".
- **Guard sources (studio and admin `_confirmLeaveImpl`):**
  - **(i)** `proceed` is wrapped to set `dirty = false`, so no phantom prompt follows a
    Continue.
  - **(ii)** studio's `inEditor` adds `|| self._createMode`, so a dirty create form
    prompts.
  - **(iii)** the router's guard wrapper first checks `App.confirmDialog.isOpen()`. If a
    dialog is already open, it resolves **Stay** for *every* entry path. If
    `confirmLeave` didn't open a dialog when dirty, a defensive abort resolves Stay too,
    so `isDeciding` can never stick.
  - `isOpen()` is added to the **adapter** in `dialog.js`, after leg 2 lands; it tracks
    the adapter's own dialog.
- **Shell:**
  - the aside is `hidden` on Agents;
  - `.content-panel.active` carries `data-destination="<id>"`, and inactive panels have
    it removed;
  - the aside `aria-label` is "Chats", "Library" or "Settings";
  - the top-bar buttons carry `data-destination` inside `#app-topbar`.
- **Tests:**
  - `_nav.SCHEME = "new"`;
  - `_nav.destination_locator` and `open_destination` are scoped (Issue 4);
  - the legacy-URL set passes as redirect proofs;
  - the DD4 pinned tests are inverted or renamed;
  - the studio-nav tests, label probes and readiness probes are migrated;
  - new `tests/browser/test_router_*.py`, with a stated exemption in the migration
    guard (AC12).
- **Docs and squawk:** squawk 0082's Corrective Action and Verification; the
  `agents.md` router contract (replacing "Hash routing" at about :1751, and fixing
  "App shell — invariants" at about :1745-1749); a CLAUDE.md router pointer;
  `tests/HAT.md` routes.

## Acceptance Criteria

**Router**

- [x] **AC1 — Engine proof first.** A test in **both engines**, run with
  `THE_ONE_REQUIRE_WEBKIT=1`, records in-page and polls the `popstate` and `hashchange`
  events and their order for:
  - Back/Forward;
  - a fragment-only `page.goto(sameURL#x)`;
  - an `<a href="#…">` click.

  It uses `engine_page` with a **`page.route`-fulfilled synthetic http origin** (or a
  tmp `file://` page), **not** the `about:blank` disk harness. If WebKit doesn't fire
  `popstate` for one of these, stop: that is a flight divert criterion.
- [x] **AC2 — Routes, builder and encoding.**
  - `App.router.href({destination, section, id, tab, sub})` and `App.router.parse(hash)`
    round-trip every DD1 shape: spaces, `/`, unicode, a leading `~`, and `!'()*`.
  - On **output** (in `href` and `sync`), a segment that starts with `~` is written as
    `%7E…`, while `serializeState`'s already-encoded segments pass through unchanged.
    So an agent named `~new` never serialises to the reserved `~new` segment.
- [x] **AC3 — Redirects (DD2).**
  - Every row rewrites with `replaceState`, before the unknown-route check, on boot and
    on traversal. The rewrite keeps the entry's seq, or stamps one.
  - The exceptions: `#studio/tools`; `#admin/system`; `/new` → `/~new` (providers and
    MCP only); `#studio/agents/new…` stays an agent named "new"; `#chat/sessions/{id}`;
    and `#agents/~new` → `#agents`.
  - A test walks every row.
  - A parity test feeds a fixed **corpus**: every DD2 legacy form, plus the bare
    destinations. It checks that the JS mapping (via `page.evaluate`) equals the result
    of `_nav`'s mapping functions.
- [x] **AC4 — Boot, unknown and element hashes.**
  - At boot, an unknown or empty hash goes to `#chats`.
  - After boot, it restores the current route (replace).
  - An element-id fragment (`#main-content`) is never routed. While it is present,
    `sync` treats the current URL as unchanged, so the skip-link entry doesn't drop
    later syncs.
  - No destination id equals an element id.
  - The design-language route in non-dev mode follows the after-boot rule (restore
    current), or the boot rule (`#chats`) at boot.
- [x] **AC5 — The commit sequence for `go()` and traversal** is pinned in code comments
  and tests:
  1. resolve the target (redirect or alias);
  2. guard, unless bypassed (joins allowed);
  3. write the URL (push or replace; a traversal is already there, and a null state is
     stamped);
  4. commit the current route and `lastRoute(destination)`;
  5. apply the shell bits;
  6. `mountArea`, which deactivates and activates **only when the area module changes**
     (Agents ↔ Library does not re-activate studio);
  7. `hydrateState(sub)`;
  8. `sync(area, serializeState())`, the post-hydrate canonicalisation that replaces
     `syncUrlFromState`.

  `go()` returns `Promise<boolean>`. A `go()` to the current route is **not skipped**:
  it replaces and hydrates.
- [x] **AC6 — `sync` drop rules.** Every former `replaceSub` site now calls
  `sync('<area>', …)` with its own area. `sync` is dropped when:
  - the mapped destination ≠ the current destination;
  - a decision is pending;
  - `location.hash` ≠ the router's current URL, ignoring element-id fragments.

  Tests cover each rule, including chat's reconnect auto-join while the user is in
  Settings, which today wrongly writes `#admin/sessions/{id}`.
- [x] **AC7 — Seq history and traversal.**
  - Every write stamps `history.state = {seq}`; a replace keeps the seq; boot adopts or
    stamps.
  - **Stay** reverts with `history.go(-delta)`, using the live delta, or re-pushes when
    the state is null. The revert's own `popstate` is a no-op.
  - **Continue** doesn't push, and hydrates the latest location.
  - A traversal that arrives while a non-router `App.confirmDialog` is open
    (`App.confirmDialog.isOpen()`, a new adapter method) is **reverted as Stay**, and
    the open dialog stays in charge.
  - Concurrent `go()`s join the pending decision, and the latest target wins.

**Areas and guard**

- [x] **AC8 — Interim guard: no double prompts and no phantom prompts.**
  - The router calls the outgoing area's `confirmLeave` on every `go()` (unless
    bypassed) and on every traversal.
  - The studio section-nav gate and the admin `setCategory` gate are deleted, and
    `onSelect` calls `go(section root)`.
  - `tryConsumePendingSelect` and `_refresh`'s re-select call `doSelect`.
  - Browser tests:
    - **(a)** a dirty agent editor → top-bar Library → **one** dialog. Stay keeps the
      editor and the URL; Continue lands on Library.
    - **(b)** the same flow via browser Back.
    - **(c)** a dirty agent → a hash change to another agent → Continue → **no second
      dialog**. This is the `test_hash_change_to_other_agent_when_dirty_opens_dialog`
      path.
    - **(d)** a dirty agent → Settings → Continue → back to the agent via a restore
      route → **no phantom dialog**.
    - **(e)** a click on the current section, or the current destination's root, while
      dirty → one dialog. Continue **closes the editor**: the same-section close is
      preserved.
    - **(f)** the root-route variant of (d): dirty agent → Settings → Continue → the
      Agents root → a tile click → **no** dialog, because `dirty` was reset by the
      wrapped `proceed`.
    - **(g)** a dirty agent **create** form → top-bar Settings → one dialog.
    - **(h)** with an `App.confirmDialog` already open, a `go()` (not a traversal)
      resolves Stay, and later `sync` calls are **not** dropped (`isDeciding` is false).
    - **(i)** clean same-section re-click closes the open editor in each of these
      (regression of current behaviour): MCP, connector, KB detail, provider, tool.
- [x] **AC9 — Studio (a)–(c) and the leak regression.**
  - (a) Cleanup in `setActiveSection`. `hydrateState` passes `prev` in and no longer
    assigns `_activeSection` itself. The same-section close lives in `closeOpenItem()`,
    called from the section-root branch, **not** in `setActiveSection`, where it would
    close an item being opened.
  - (b) `_refresh` re-selects only on Agents.
  - The `doSelect` **entry** checks the active section and the destination, and refuses
    to force-switch sections when called asynchronously from
    `_refreshAgentAfterSelfConfigurationChange` (:1184), save-create (:2673) or the
    delete fallback (:2092), unless the user is still in Agents.
  - (c) The Library-only section nav is rendered once; Agents has no nav and the aside
    is hidden.
  - **Regression test:** Agents (open an item) → Library → Chats → Library. The user
    ends on Library with `_selectedAgent === null`, `_mcpSourceFormMode === null` and
    `dirty === false`, and **no `GET /api/agents/{name}`** request is issued (list
    fetches are expected).
  - Restoring `lastRoute(library)` to an item deleted meanwhile does not hang: the
    post-hydrate `sync(serializeState())` heals the URL. Full dead-id handling is leg
    `04`.
- [x] **AC10 — Interim top bar and shell bits.**
  - The top bar has 4 buttons rendered from destinations with `util.el`. Each button
    calls `go(dest === current ? root(dest) : lastRoute(dest))`.
  - `nav-chat-btn` is kept and still registered. The Library button uses the existing
    `App.icons.studio` until leg 6's icons.
  - The top-bar sink baseline entry is removed.
  - `data-destination`: on top-bar buttons inside `#app-topbar`, and on
    `.content-panel.active` only.
  - The aside is hidden on Agents, and the aside and section-nav labels are as in
    Outputs.

**Tests and docs**

- [x] **AC11 — Test flip.**
  - `_nav.SCHEME = "new"`, plus the scoped `destination_locator` and
    `open_destination` (`#app-topbar [data-destination=…]`,
    `.content-panel.active[data-destination=…]`).
  - The legacy-URL set (9 entries) passes as redirect proofs. Its entries in
    `test_flow_hash_routing.py` (`test_studio_root_redirects_to_agents`,
    `test_studio_knowledge_section_persists_on_refresh`) survive.
  - **Pinned tests:**
    - The history-growth test inverts to the push policy (renamed).
    - The other-destination restore test in `test_flow_studio_navigation.py` inverts
      (renamed).
    - The current-destination-click and `#studio` → Agents tests keep their behaviour.
  - **Migrations:**
    - **`test_flow_studio_navigation.py`.** About 8 tests pin the 4-button nav and
      Agents roving. They are rewritten against the Library-only nav, plus
      `open_destination('agents')`. `_wait_studio_ready` gets a new readiness probe.
    - **Library section-nav tests.** In `test_flow_studio_mcp_navigation.py`, the
      `section_nav_includes_mcp_servers` and `click_to_mcp_sources` tests now start
      from Library.
    - **Agents → Library nav clicks** in `test_flow_dirty_confirm.py` become
      `open_destination('library')`.
    - **Label probes.** The "Agent Studio sections" probes become
      `[data-destination=…]`, and the "System sections" probes
      (`cross_area_dirty_gate`, `keyboard`) become "Settings sections".
    - **Hrefs and dead ids.** `test_studio_mcps_tab.py`'s `"mcp-sources" in href`
      assertion becomes the redirect-tolerant form. The `test_flow_provider_grid`
      unknown-id test tightens to `settings/providers`.
- [x] **AC12 — The migration guard stays green.**
  - `tests/browser/test_router_*.py` are **exempt at file level**: they are the router's
    contract tests and need literal legacy and new hashes.
  - The exemption is stated in the guard and its self-test, and the guard still
    rejects raw hashes in every other file.
- [x] **AC13 — Squawk 0082.**
  - **Test.** A sub-route change via `sync`, followed by a `hashchange` back to the
    previous sub, is honoured. Build it on
    `test_flow_admin_knowledge_settings.py`'s workaround site, and remove the
    workaround.
  - **Paperwork.** Corrective Action and Verification are written; the squawk closes in
    the flight commit.
- [x] **AC14 — Docs.**
  - `agents.md`: the router contract replaces "Hash routing" (about :1751), and
    "App shell — invariants" (about :1745) is updated. They cover destinations, scheme,
    `go`/`sync`, the commit sequence, history, redirects, the interim guard and the
    shim's deprecation.
  - CLAUDE.md gets a router pointer, and `tests/HAT.md` its routes.
- [x] **AC15 — Gates pass.**
  - `make lint`;
  - `make test-unit`;
  - all five lanes, one at a time;
  - every `test_ui_*` in both engines;
  - the WebKitGTK probe at `#agents` and `#settings/general` (`--root-selector body`),
    with results recorded.

## Verification Steps

- AC1–AC7:
  `PYTHON=.venv/bin/python THE_ONE_REQUIRE_WEBKIT=1 bash scripts/run-tests.sh -m browser tests/browser/test_router_*.py -x -rA`,
  then the hash-routing file.
- AC8–AC10: the guard, leak and shell tests named above; read the diffs of the deleted
  gates.
- AC11–AC13: the five lanes, plus the migration guard.
- AC14–AC15: a doc read, the gates and the probe JSON in the flight log.

## Implementation Guidance

1. **Engine proof (AC1).** It decides whether `popstate` can be the authority.
2. **`router.js` behind the existing app** (AC2–AC7), with `test_router_*`.
3. **Wire `app.js`.** Use `mountArea` and `App.router.start()`; remove `switchTo`'s URL
   logic and the old listeners; build the interim top bar.
4. **Studio and admin.** Delete the gates, add the `doSelect` routing and guards,
   changes (a)–(c), the Library-only nav and labels.
5. **Shell bits.**
6. **Flip `_nav` and migrate the tests** (AC11–AC12).
7. **Squawk 0082, docs, gates** (five lanes, about 25 minutes), and the probe.

## Edge Cases

- **Reload on any route:** the seq is adopted; the item re-opens through the pending
  path.
- **A typed URL while a guard dialog is pending:** it joins, and the latest target wins.
- **`#studio/agents/new/tools`** → `#agents/new/tools`. It is not `~new`.
- **An empty `#`** (a bare-`#` link) after boot restores the current route; the link
  interceptor arrives in leg 5.
- **A link-click traversal** (`<a href="#…">`) arrives as a `popstate` with **null**
  state and an unknown delta. **Stay** re-pushes the stayed route, which leaves one
  duplicate entry in history. This is accepted, documented in `agents.md`, and tested:
  the screen and URL agree after Stay. Leg 5's interceptor routes such clicks through
  `go()` and removes the case.
- **perf.js `area-switch` marks:** keep them, or rename them `destination-switch`; no
  consumers.

## Files Affected

- `static/js/router.js` (new), `app.js`, `areas/studio.js`, `areas/admin.js`,
  `areas/chat.js` (only if needed for the post-hydrate sync),
  `areas/layout/section-nav.js` (labels only), `dialog.js` (`isOpen()`)
- `index.html`, `tests/test_index_asset_cache_busting.py`, `tests/test_ui_guards.py`,
  `docs/ui-testid-registry.md`
- `tests/browser/_nav.py`, the migration guard in `tests/test_nav_helper.py`,
  `tests/browser/test_router_*.py` (new), and the migrated tests listed in AC11
- `squawks/0082-*.md`, `the_one/agents.md`, `CLAUDE.md`, `tests/HAT.md`
- `missions/25-workbench-navigation/flights/02-shell-and-router/flight-log.md`

## Citation Audit

Checked by the leg design review against the working tree on 2026-10-01, with leg 1
mid-edit:
- `admin.js:718-732 _setCategory`; `:664-673 _confirmLeaveImpl`; `:246-260 setCategory`
  gate ✔ (the flight cited `_setCategory` at :664-680 — corrected here).
- `studio.js:96/:163` bare branches clear selection; `:383-448` section-nav gate;
  `:1184/:2673/:2092` async `doSelect` callers; `:2931-2948`;
  `:26/:38/:48` `serializeState` encodes ✔
- `_ui_engines.py:197` `load_harness` uses `set_content` on `about:blank` ✔
- `agents.md` "Hash routing" is at about :1751 ✔
- `LEGACY_URL_TESTS` has 9 entries (leg 1, in progress) — re-check at implementation.

Design review (Developer, 2026-10-01): **needs rework**. Resolved by:
- the split at the shim seam (this leg plus `04`);
- the interim guard on every `go()` and traversal, with the in-area gates deleted;
- the `doSelect` routing;
- scoped `data-destination`;
- the router-contract test exemption;
- the post-hydrate sync;
- same-section close moved to `04`;
- the `doSelect` entry guard;
- encoding on output;
- the expanded test surface;
- the engine-proof apparatus;
- the top-bar click semantics;
- the low items.

Cycle 2 (Developer, 2026-10-01) — "approve with changes". Applied:
- explicit-area `sync` at all 28 sites, with no shim, so the destination drop rule
  works;
- the same-section close preserved via `closeOpenItem()`;
- an already-open dialog → Stay on every path, plus a defensive abort;
- `hydrateState` passes `prev` and stops assigning `_activeSection`;
- `proceed` resets `dirty`;
- `inEditor` includes `_createMode`;
- the null-state re-push documented;
- the deleted-item restore heals.

---

## Post-Completion

Completion steps — status transitions, flight-log update, checking off in the parent
flight, and commit — are Flight Control protocol, driven by the execution workflow. Not
repeated here.
