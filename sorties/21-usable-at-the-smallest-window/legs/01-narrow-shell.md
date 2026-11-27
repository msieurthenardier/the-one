# Leg: narrow-shell

**Status**: completed
**Flight**: [Usable at the smallest window](../flight.md)

## Objective
Below a 768px-wide viewport the shell shows one pane at a time, chosen by the operator's intent (the destination's list after a bare-destination navigation, the detail after opening an item), with the current rail icon as the way back to the list and Settings showing its nav on first entry; at 768px and wider nothing changes.

## Context
- Flight DD1 (pane by intent, the hiding rule, focus, scroll), DD2 (768px, range syntax), DD3 (only the rail's Settings href changes), DD8 (recorded shell rules and guide), DD10 (the `layout` lane and the new test file). This leg implements them and nothing from DD4–DD7.
- The operator approved the mockup's Option A (boards A1–A4) with no back links; the Chats list follows what was clicked, and reload or Back on `chats/{id}` shows the chat (flight log, 2026-11-27).
- The panels (agent panel, GleepGlorp drawer) are leg 2. In this leg they keep today's behaviour at every width. Do not change `js/ui/drawer.js`, `agent-drawer.js` or `gleepglorp-drawer/*`. Leg 2 will reuse this leg's `App.shellPane.visiblePane()`.
- Short-height rules, corner-button clearance and width clamps are leg 3. Tests in this leg assert the pane layout, rail and focus, not the charter's full criterion 1.
- Leg design review (cycle 1, Developer) found the sync rule and the Stay-revert case defective; both are fixed below (the sticky rule in step 1, the `reverting` flag in step 2).
- No prior legs. Branch `sortie/21-usable-at-the-smallest-window` from `main` at `e3140b24`.

## Inputs
- `js/router.js`: `resolve()` / `mk()` build targets; `commit(target, fresh, first)` is called only from `applyDecision` (`commit(t, !!d.arrived)`) and `start()` (`commit(target, true, true)`), so `fresh === true` means arrival or boot and `false` means an intent `go()`; `commit` runs steps 4–8 under `inCommit` and calls `notifyRouteChange()` once at step 9; `sync()` notifies outside a commit; `handleArrival()` returns early (no notify) when the arrival's route equals `current.route`; `revertDecision` reverts a refused traversal with `history.go(...)`, which lands in that same-route branch.
- Chats syncs outside commits: `areas/chat/socket.js` (~:269) syncs on every join reply, including re-joins; `areas/chat/session-flow.js` `clearConversation` (~:198) and `heal` (~:323) call `sync(null)`, then `runIdleRules()` auto-joins the newest session and syncs to `chats/{id}`.
- `js/app.js::mountRail`: initial hrefs from `lastRoute` (~:35); on each commit the current destination's href is `App.router.root(destId)`, others `lastRoute(id)` (~:59-63). `App.router.start` is called from `app.js` (~:239).
- `css/base.css` (`@layer base`): the shell row, `#app-sidebar` per-destination widths at (1,1,0), the shell comment at ~:63-75, `#main-content`.
- `js/nav.js::focusMain` (~:56-61), called only from the Continue handler's `setTimeout(focusMain, 0)` (~:96).
- `js/areas/chat/transcript.js` (~:28-53): `isPinned()`, `scrollToBottomIfPinned()`, `pinnedFlag` (scroll listener), `onChartLayout()`; created per chat instance in `areas/chat/instance.js` (~:365).

## Outputs
- A router-owned pane intent with its own accessor and change hook; `describeCurrent()` and the public `router.resolve()` shapes unchanged.
- `js/shell-pane.js` (new): the `data-pane` stamp, the 768px media listener, the focus check, `App.shellPane.visiblePane()` / `focusVisible()`, the skip-link handling below 768px.
- Narrow CSS rules in `base.css` under `@media (width < 768px)`.
- The rail's Settings href rule.
- A transcript re-pin when its box reappears.
- `tests/browser/test_flow_narrow_layout.py` and a `layout` lane.
- Updated `the_one/agents.md`, CLAUDE.md, the app guide, and the pinned tests.

## Acceptance Criteria
- [ ] **AC1 Intent rule.** The router keeps `paneIntent` (`null` before the first commit, then `'list'` or `'detail'`) and a `listSticky` flag:
  - at the start of every commit, `listSticky` is cleared;
  - an intent commit (`fresh === false`) whose target is bare sets `listSticky`; a target is bare when its input was the bare destination (`chats`, `agents`, `library`, bare `settings` via its redirect to `settings/appearance`, and bare `chats/~new` which folds to `chats`); `settings/general`, legacy `#chat`/`#studio` hashes and `library/<section>` are not bare inputs (the last is caught by the settled-route rule);
  - at the end of a commit: `list` if `listSticky`, or if the settled route is exactly `chats`, `agents` or `library`; else `detail`;
  - a `sync()` that lands on a bare route (`chats`, `agents`, `library`) sets `listSticky` and `list`; any other sync gives `list` while `listSticky` is set and `detail` otherwise;
  - so: a rail click on Chats shows the list even when the chat then joins or re-joins; deleting the open item shows the list even after Chats auto-joins the next session; first load on `#chats` shows the auto-joined chat (no intent, flag unset); `agents/~new` → `agents/{name}` (save-create, reached by a commit) stays `detail`.
- [ ] **AC2 Arrivals.** Arrivals and boot (`fresh === true`) ignore bareness and use the settled route. `handleArrival`'s same-route branch sets the intent from `current.route` (clearing `listSticky`) and fires the hook when it changes, **except** when it is the router's own Stay revert: `revertDecision` sets a module flag `reverting` immediately before its `history.go(...)`; the same-route branch, seeing the flag, clears it and leaves the intent alone; a revert that uses `replaceState` (no event) clears the flag itself. So from `chats/A`, a rail click shows the list and Back shows chat A; with a dirty editor, a refused Back leaves the pane as it was. A bare `go()` that joins a pending traversal decision is treated as an arrival (accepted).
- [ ] **AC3 Hook and shapes.** `App.router.paneIntent()` and `App.router.onPaneIntentChange(fn) -> unsubscribe` (its own subscriber list; a throwing subscriber never breaks a commit, a sync or another subscriber) fire whenever the value changes. The first commit always fires (initial `null`). The intent is also stamped provisionally at commit step 4 from the target (bare intent → `list`; else by the target's route), so an area hydrates with its pane already shown or hidden, and finalised at step 9. `App.router.describeCurrent()` keeps exactly `{route, destination, parts}` (`tests/browser/test_router_route_change.py` passes unedited) and the public `App.router.resolve()` does not expose the new field (`tests/browser/test_router_core.py` parity passes unedited).
- [ ] **AC4 Stamp and hiding.** `.app-shell-row` carries `data-pane="list"|"detail"` matching the intent at every width (an attribute, never a class: `test_flow_gleepglorp_drawer_shell.py` pins the row's `className`). In `@layer base`, under `@media (max-width: 767.98px)`: `data-pane="list"` hides `#main-content` and makes `#app-sidebar` fill the area right of the rail; `data-pane="detail"` hides `#app-sidebar` and lets `#main-content` fill it. Only `display: none` is set on the hidden pane; the shown pane gets `flex`/`width` only. The global `[hidden]` reset is untouched; a `sidebar: false` destination still hides the aside; the drawer asides are unaffected.
- [ ] **AC5 Rail.** Every rail href is unchanged except Settings, which is bare `#settings` when Settings is current, and when it is not current but `App.router.lastRoute('settings')` equals `App.router.root('settings')` (`settings/appearance`); this holds for the initial hrefs too. `root('settings')`, `lastRoute`, the `settings/general` alias, the bare-`#settings` redirect and the Jump to targets are unchanged.
- [ ] **AC6 Destinations at 624×321.** At 624×321, exactly one of `#app-sidebar` / `#main-content` is visible and it is at least 360px wide, and `document.scrollingElement.scrollWidth <= clientWidth`, in each of: Chats list after a rail click with a chat open; that chat after opening it; the agent list (`#agents`); an agent's tab; the Library grouped list (`#library`, start page hidden); a Library item; the Settings nav on first entry from another destination (last Settings route = Appearance); a Settings page after choosing it.
- [ ] **AC7 Focus.** Below 768px, after a pane change `document.activeElement` is never `body` and never inside the hidden pane (check `body` and `activeElement.closest('#main-content, #app-sidebar')` against the hidden pane): detail → the detail's existing focus target (the studio breadcrumb's row focus and `App.nav`'s Continue focus still land) else `#main-content`; list → the sidebar's `[aria-current]` row, else its first focusable control. A rail click leaves focus on the rail link. The same check runs on the 768px media change. `focusMain` lands in the visible pane when `<main>` has no layout box (`!main.getClientRects().length`), else it is unchanged; the skip link, below 768px only and only when `<main>` is hidden, moves focus into the visible pane (`preventDefault` + `focusVisible()`); at 768px and wider the skip link is untouched (`test_flow_chat_pane.py` and `test_shell_rail.py` skip-link pins pass unedited).
- [ ] **AC8 Transcript.** A transcript that was pinned to the bottom is still pinned when its box reappears or resizes, including when the chat joined while the list was showing; verified in Chromium and WebKit, including that hiding the pane does not clear the pinned state.
- [ ] **AC9 Wide unchanged.** At 1024×768 and 1280×800, `data-pane` is stamped but no new rule or handler takes effect: both panes visible at today's widths, and every existing shell, rail, skip-link and settings-nav test passes with only the Settings href pins changed (AC5).
- [ ] **AC10 Records.** `the_one/agents.md` "App shell — invariants" and the comment at `css/base.css` ~:63-75 state the new rule (side by side at 768px and wider; one pane by intent below; 1024 no longer the supported minimum); the routing notes describe the intent rule, the sticky flag, the arrival rule and the hook; the app guide (`the_one/gleepglorp/guide/*.md`) says a small window shows one pane, and that clicking the current icon on the left (Settings included) shows its list or menu; `tests/test_gleepglorp_guide.py` passes.
- [ ] **AC11 Tests and lane.** `tests/browser/test_flow_narrow_layout.py` covers AC1–AC9 (core layout assertions in Chromium and WebKit via `engine_browser` + `credentialed_context`), including the input table of AC1 as a parametrised table, the delete-then-auto-join, rail-click-then-join and first-load paths, the Stay-then-Back case with a dirty editor, and a rail click while an editor is dirty. A new `layout` lane globs `test_flow_narrow_*` in `scripts/run-tests.sh` with a provisional, commented budget; `LANE_LIST`, `CANON_LANES`, `tests/test_run_tests_lanes.py` and the lane lists in CLAUDE.md and `the_one/agents.md` are updated; CLAUDE.md lists `layout` with the lanes that run under `THE_ONE_REQUIRE_WEBKIT=1`.

## Verification Steps
- AC1–AC3: the new file's router cases (`App.router.go(...)`, `history.back()`, reload, `App.router.paneIntent()`), with Chats driven by the dev-mode `mock` provider through the existing seeders; `--lane routing` passes with no edits to router suites.
- AC4, AC6, AC9: the new file at 624×321, 1024×768, 1280×800 via `PYTHON=.venv/bin/python THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 bash scripts/run-tests.sh --lane layout`.
- AC5: `test_shell_rail.py` and `test_flow_admin_settings_nav.py` with their Settings href pins updated (lanes via `scripts/run-tests.sh --list`).
- AC7, AC8: focus and transcript assertions in the new file, both engines for AC8.
- AC10: `.venv/bin/python -m pytest tests/test_gleepglorp_guide.py -x --timeout 60`.
- AC11: `.venv/bin/python -m pytest tests/test_run_tests_lanes.py -x --timeout 60`; `scripts/run-tests.sh --list --lane layout`.
- Static guards: `tests/test_ui_guards.py`, `tests/test_token_definitions.py`, `tests/test_design_tokens_a11y.py`, `tests/test_ui_ownership.py`, `tests/test_nav_helper.py`, `tests/test_nav_guard_static.py`, `tests/test_store_static.py`, `tests/test_index_asset_cache_busting.py`; then `THE_ONE_TEST_NETNS=1 make test-unit`.
- Squawk 0334 lanes: `routing`, `settings`, `chats`, `gleepglorp-chat`, `contracts-chat`, `shared`, `layout` (at most 3 at once; never alongside the unit tier).

## Implementation Guidance

1. **Router: the bare flag, the intent and the sticky rule.**
   - In `resolve()`, mark bare inputs on the target: `segs.length === 1 && !redirected` for `chats`, `agents`, `library` (a legacy remap sets `redirected`, ~:279, so `#chat` / `#studio` are not bare); bare `chats/~new` (the `mk('chats', dest, null, true)` fold, ~:318) as its own mark; and the bare-Settings branch's `rootTarget` after `resolve(dest.root)` (~:360-362) as its own mark. Not `settings/general`. Name the field (e.g. `bare`) and make sure the public `router.resolve()` wrapper (~:903-908), which copies explicit fields, does not copy it.
   - Module state: `paneIntent = null`, `listSticky = false`, a separate `paneHooks` list.
   - `commit()`: at step 4 clear `listSticky`, then set it if `!fresh && target.bare`; stamp a provisional value (`listSticky` → `list`, else by `target.route`) and fire the hook if it changed (so the area hydrates into a visible or hidden pane). At step 9, recompute from the settled `current.route` and `listSticky` and fire if changed, alongside `notifyRouteChange()`.
   - `sync()`: after the URL update (keep `tests/test_store_static.py`'s window intact: one `speak(` in `sync`, `prevKey` read before `lastAnnounceKey` is written), apply AC1's sync rule and fire if changed. Inside a commit, do not fire (step 9 will).
   - Expose `paneIntent()` and `onPaneIntentChange(fn)`. Do not touch `describeCurrent()`.
   - Keep the router change small; everything shell-side lives in `shell-pane.js`.

2. **Router: arrivals and the Stay revert.**
   - Arrivals and boot already call `commit(..., fresh=true)`; with step 1 they never set `listSticky`.
   - `revertDecision`: set `reverting = true` immediately before `history.go(...)`; where it reverts with `replaceState`/`pushState` (no popstate), do not set it.
   - `handleArrival`'s same-route branch: if `reverting`, clear it and return as today; else clear `listSticky`, set the intent from `current.route`, fire if changed, then return as today (the null-seq `rewriteInPlace` stays).
   - The flag must not leak: also clear `reverting` in `beginDecision` and at the start of `commit` (a revert whose popstate never arrives, or that is overtaken by a new decision, must not swallow a later genuine same-route Back).
   - Accepted: the same-route branch also receives the return from an element-id fragment (the skip link); recomputing there can turn a sticky `list` into `detail`. It matters only after the skip link at a wide width and a later narrowing; not handled.

3. **`js/shell-pane.js` (new).** Loaded by an `index.html` `<script>` after `nav.js` (it must follow `router.js`, ~:39); it subscribes at script top level, not on `DOMContentLoaded` (`App.router.start` runs from `app.js`). DOM APIs only (no HTML-string sinks; `tests/test_ui_ownership.py` scans every `js/**/*.js`); append nothing to `body` (`test_shell_rail.py` pins `body`'s children).
   - Stamp `.app-shell-row[data-pane]` from `onPaneIntentChange`; stamp `list` only when `#app-sidebar` is not `[hidden]` (a `sidebar: false` destination would otherwise show nothing), else `detail`.
   - `matchMedia('(max-width: 767.98px)')` with a `change` listener. Use the classic `max-width: 767.98px` form, not the range syntax, in CSS and JS: range syntax needs WebKitGTK 2.40+ and Safari 16.4+, and `767.98px` closes the fractional gap the range syntax was meant to close (this supersedes the flight's DD2 note on range syntax).
   - `App.shellPane = { visiblePane(), focusVisible() }`: `visiblePane()` returns `#app-sidebar` or `#main-content` per the current stamp and media state (or `null` at 768px and wider, meaning both); `focusVisible()` focuses `[aria-current]` in the sidebar or its first focusable (list), or `#main-content` (detail).
   - The focus check (AC7), with `setTimeout(0)` after a stamp change and on the media change. Note the ordering: `nav.js`'s Continue `setTimeout(focusMain, 0)` is queued before the commit's step-9 timer, so it runs first; with step 4 below it then lands in the visible pane, and the shell check finds nothing to fix.
   - Skip link: a click listener that acts only below 768px and only when `#main-content` has no layout box: `preventDefault()` + `focusVisible()`.

4. **`nav.js::focusMain`.** If `main` has no layout box (`!main.getClientRects().length`), call `App.shellPane && App.shellPane.focusVisible()`; otherwise the existing path, unchanged.

5. **CSS.** In `css/base.css`, inside `@layer base`: `@media (max-width: 767.98px) { .app-shell-row[data-pane="detail"] > #app-sidebar, .app-shell-row[data-pane="list"] > #main-content { display: none } .app-shell-row[data-pane="list"] > #app-sidebar { flex: 1 1 0; min-width: 0; width: auto; } }` ((1,2,0) beats the (1,1,0) width rules; `flex: 1 1 0; min-width: 0` so content can never push the row wider). Rewrite the shell comment (~:63-75). Before the first commit there is no `data-pane`, so both panes show until boot; accepted.

6. **Rail.** In `js/app.js::mountRail`, for `settings` use the bare `'settings'` route when it is current or when `lastRoute('settings') === root('settings')`, both in the initial hrefs (~:35) and in `onCommit` (~:59-63); other destinations unchanged. Update the comment.

7. **Transcript re-pin.** In `js/areas/chat/transcript.js`, inside `create()`, a `ResizeObserver` on `messagesEl` that runs the `onChartLayout` logic (`if (pinnedFlag) messagesEl.scrollTop = messagesEl.scrollHeight`). Do **not** disconnect it in `clearLog` (which runs on every conversation change); add a `destroy()` to the transcript's API that disconnects it, and call it from the instance's `destroy()` in `instance.js` (~:452, next to `ctx.holdQueue.destroy()`). Guard against a hide clearing `pinnedFlag`: the scroll listener starts with `if (!messagesEl.clientHeight) return;`. This also serves the GleepGlorp drawer's chat instance, harmlessly; at wide widths it re-pins a pinned transcript when the composer's height changes, an accepted, benign change under AC9. No router subscription in the chat area. A transcript the operator had scrolled up before the hide is not re-pinned when it reappears (its scroll position may reset); accepted and stated in the test.

8. **Tests.**
   - New `tests/browser/test_flow_narrow_layout.py`: navigate through `_nav` (`goto_settled`, `open_destination`, `href`), lists through `_lists`, chats through `_chats`; no raw hashes. `engine_browser` + `credentialed_context(...)` (as in `tests/browser/test_flow_admin_settings_nav.py`) for the core layout assertions in both engines; existing seeders and the `mock` provider for Chats.
   - `_nav.href('settings')` folds bare `settings` to `settings/appearance` (`tests/browser/_nav.py` `canonical`, ~:165), and raw hashes are guarded by `tests/test_nav_helper.py`, so add a `_nav` helper for a destination's literal bare hash (proposed `_nav.bare_href(dest)`, scheme-aware like `hash_for`) with its own case in `tests/test_nav_helper.py`.
   - Settings href pins: `tests/browser/test_shell_rail.py` (~:464, :480, :496, and the `startswith(_nav.href(dest))` check at ~:510) and `tests/browser/test_flow_admin_settings_nav.py` (~:506, :518; `root('settings')` at ~:507 stays) use `_nav.bare_href('settings')`. The route after a Settings click is still `settings/appearance`. Rename a test whose intent changes rather than delete-and-readd.
   - The `layout` lane: a pattern array, `LANE_LIST` (~:59) and `CANON_LANES` (~:60), a commented provisional `BUDGET` entry, `tests/test_run_tests_lanes.py`.

9. **Docs.** `the_one/agents.md` (App shell invariants, routing notes, lane list), CLAUDE.md (canonical lane list; `layout` among the `THE_ONE_REQUIRE_WEBKIT=1` lanes), the app guide.

## Edge Cases
- **Rail click on Chats with no chat open but sessions present (idle):** bare intent → `list`, and it stays `list` when the idle rules auto-join (sticky).
- **Rail click while a chat is joining or re-joining:** stays `list` through the join's sync (sticky).
- **Deleting the open item:** `sync(null)` → bare → `list` + sticky; Chats' auto-join of the next session keeps `list`; focus on the list.
- **First load or reload on `#chats` with sessions:** boot is an arrival; settles at `chats` (`list`), then the socket's auto-join syncs to `chats/{id}` with no sticky flag → `detail` (the chat). The list shows briefly until the join; accepted, to be judged in the HAT. With no sessions: stays `list`.
- **Typed `#settings`, or Back/Forward/reload onto `settings/appearance`:** arrivals → `detail` (the Appearance page); clicking the Settings icon shows the nav (the guide says so).
- **Entering Settings when its last route is a page other than Appearance:** the rail href is that page → `detail` (consistent with Chats and Agents restoring their last item).
- **Dead-id heal** during hydrate (inside a commit): settles at the bare destination → `list`.
- **Save-create** (`agents/~new` → `agents/{name}`): a `sync()` after the commit to `~new` (which cleared sticky) → `detail`.
- **Leave guard Stay** after a rail click: no commit; intent and stamp unchanged. After a refused Back: the `reverting` flag keeps them unchanged.
- **A bare `go()` joining a pending traversal decision:** treated as an arrival (accepted; rare).
- **Jump to** an item or a Settings page → `detail`.
- **Resize across 768px** with focus in the sidebar on a `detail` route: the sidebar hides; focus moves to `#main-content`.
- **Element-id fragment** (`#main-content` from the skip link): never routed; no intent change.

## Files Affected
- `the_one/interfaces/web/static/js/router.js` - bare flag, intent, sticky rule, `paneIntent()`, `onPaneIntentChange()`, the arrival and Stay-revert handling
- `the_one/interfaces/web/static/js/shell-pane.js` (new) - stamp, media listener, focus check, `App.shellPane`, skip link below 768px
- `the_one/interfaces/web/static/index.html` - load `shell-pane.js` after `nav.js`
- `the_one/interfaces/web/static/js/nav.js` - `focusMain` falls back to the visible pane
- `the_one/interfaces/web/static/js/app.js` - the Settings rail href rule
- `the_one/interfaces/web/static/css/base.css` - narrow pane rules, rewritten shell comment
- `the_one/interfaces/web/static/js/areas/chat/transcript.js` - ResizeObserver re-pin, hide-safe pinned flag
- `tests/browser/test_flow_narrow_layout.py` (new)
- `tests/browser/test_shell_rail.py`, `tests/browser/test_flow_admin_settings_nav.py` - Settings href pins
- `scripts/run-tests.sh`, `tests/test_run_tests_lanes.py` - the `layout` lane
- `the_one/agents.md`, `CLAUDE.md`, `the_one/gleepglorp/guide/*.md`

## Citation Audit
Checked against the working tree at `e3140b24` on 2026-11-27 (rows marked R re-checked by the leg design review):
- `js/router.js::resolve` - bare `chats`; bare `chats/~new` folds to `mk('chats', dest, null, true)` (~:318); `library` and `library/<section>` → `mk('library', ...)` (~:343, :348); bare `settings` → `resolve(dest.root)`, redirected (~:360-362) - verified (R)
- `js/router.js` public `resolve` wrapper copies explicit fields (~:903-908) - verified (R)
- `js/router.js::commit` - two call sites, `applyDecision` `commit(t, !!d.arrived)` and `start()` `commit(target, true, true)`; steps 4–8 under `inCommit`; step 9 `notifyRouteChange()` - verified (R)
- `js/router.js::handleArrival` same-route branch (~:849-853) and `revertDecision` `history.go(...)` (~:742-748); `deciding` is null after `settle` - verified (R)
- `js/router.js::describeCurrent` returns exactly `{route, destination, parts}` - verified
- `js/router.js` legacy remap sets `redirected` (~:279) - verified (R2)
- `js/areas/chat/transcript.js` has no transcript-level `destroy`; `clearLog` runs on every conversation change; `instance.js` `destroy()` (~:452) - verified (R2)
- `tests/browser/_nav.py::canonical` folds bare `settings` (~:165); `tests/test_nav_helper.py` guards raw hashes; `test_shell_rail.py` ~:510 `startswith(_nav.href(dest))` - verified (R2)
- `areas/chat/socket.js` (~:269) syncs on every join reply; `session-flow.js` `clearConversation` (~:198), `heal` (~:323) then `runIdleRules()` - verified (R)
- `js/app.js::mountRail` (~:35, ~:59-63); `App.router.start` from `app.js` (~:239) - verified (R)
- `css/base.css` - `@layer base`; global `[hidden]`; width rules (1,1,0); comment ~:63-75 - verified (R)
- `js/nav.js::focusMain` (~:56-61), Continue `setTimeout(focusMain, 0)` (~:96) - verified (R)
- `index.html` - skip link (~:24), `router.js` (~:39), `nav.js` (~:40) - verified (R)
- `js/areas/chat/transcript.js` (~:28-53) `pinnedFlag`, `onChartLayout`; `instance.js` (~:365) - verified (R)
- `tests/browser/test_shell_rail.py` (~:464, :480, :496; body children ~:88); `test_flow_admin_settings_nav.py` (~:506, :518); `test_flow_gleepglorp_drawer_shell.py` row `className` pins (~:184, :202) - verified (R)
- `tests/test_store_static.py` window over `function sync(` - verified (R)
- `scripts/run-tests.sh` `LANE_LIST` (~:59), `CANON_LANES` (~:60), `BUDGET`, pattern arrays - verified (R)

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
