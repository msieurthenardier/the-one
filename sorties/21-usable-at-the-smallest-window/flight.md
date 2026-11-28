# Sortie: Usable at the smallest window

**Status**: completed

## Charter

### Outcome
Shrink the desktop window to its smallest size (640×360) and every page still works: you can read and write a chat, browse and edit agents, Library items and settings, and open the side panels, without anything squeezed, cut off or covered.

### Why Now
The v1.0.0 desktop app allows a 640×360 window (`the_one/interfaces/desktop/window_state.py::MIN_SIZE`), but the web UI has no layout rules for small sizes. At that size (about a 624×321 page) the rail and list column leave the main pane roughly 250px wide; in a narrower browser window the transcript wraps about one character per line. An outside PR (#393, closed unmerged) brought it to light.

### Success Criteria
- [ ] **Every page works at 624×321**: Chats with an open chat, Agents and every agent tab, Library and every editor, Settings and every page. On each, the main pane is at least 360px wide, the page never scrolls sideways, an open chat shows at least three lines of transcript above the composer, and every control can be reached by scrolling with nothing covering it (including the GleepGlorp corner button).
- [ ] **The list column, the chat's agent panel and the GleepGlorp drawer stay usable at that size**: each opens and closes by mouse and keyboard (Escape closes it), none pushes the main pane below 360px, and focus moves into a panel when it opens and back to what opened it when it closes.
- [ ] **Narrower than the desktop minimum, in a plain browser**: no page scrolls sideways and nothing is pushed off-screen.
- [ ] **At 1024×768 and 1280×800, every page looks and behaves as it does today.**

### Constraints
- The desktop minimum window size stays 640×360.
- It works in all three desktop webviews (WebKitGTK 4.1 on Linux, WKWebView on macOS, WebView2 on Windows), and is checked in a real desktop window at its minimum size on at least one platform, not only in the browser test engines.
- Accessibility and the control library don't regress: the contrast gate, forced colours, reduced motion, keyboard access; new controls are `App.ui` factories with inventory rows and registered test ids; the app guide is updated for any changed control or page.
- Out of scope: everything from the dropped Mission 38 (hierarchy and accent, first-run checklist, agent reach, naming and consistency, motion), phone layouts, and any visual redesign.
- PR #393's branch (`origin/flight/01-narrow-window-layout`, `d84ad6b4`) is reference only. None of its design decisions are adopted unless this flight's design chooses them again.

---

## Pre-Flight

### Objective
Below a 768px-wide viewport, the app shows one pane at a time: the list column (or the Settings nav) when the operator asked for a destination, the detail when they opened an item. Clicking the current destination's rail icon shows its list. Below 768px the agent panel and GleepGlorp's drawer fill the pane, take focus when opened from their toggle, and return it when they close; the agent panel gains a narrow-only Close button. Short windows get compact chat chrome and a scrolling rail, every scroll container clears the GleepGlorp corner button, and fixed widths clamp so no page scrolls sideways. At 768px and wider nothing changes except two operator-accepted fixes (DD5, DD6). This closes issue #225.

**Mockup (operator-approved, 2026-11-27):** [Sortie 21: small-window layout options](https://claude.ai/artifact/Xhmyh5poVyiNSPzd1A7bbH). The operator chose Option A (boards A1–A4) over Option B (list as an overlay), no back links, and the whole-pane agent panel (the "Agent panel open" board). The narrow-only Close button in the agent panel header (DD4) follows the GleepGlorp drawer's existing Close control.

### Open Questions
- [x] One pane at a time or the list as an overlay? → one pane at a time (DD1; operator, from the mockup)
- [x] A back link in the header? → no; the rail's current-destination icon is the way back (DD1; operator)
- [x] Where does the layout switch? → 768px, content-driven (DD2; operator asked for best practice)
- [x] How big is a panel below the breakpoint? → the whole pane (DD4; operator)
- [x] HAT leg? → yes (operator)
- [x] Real desktop window check? → the WebKitGTK probe on this host (DD9; operator)
- [x] Chats: the route cannot show the list (bare `#chats` re-opens the current chat) → the pane follows what the operator clicked; reload or Back on `chats/{id}` shows the chat (DD1; operator, after Architect review cycle 1)
- [x] Settings: a real bare `#settings` route breaks recorded contracts → keep Settings routing unchanged; only the rail's Settings href changes (DD3; Architect recommendation, operator told)
- [x] The agent panel has no Close button of its own → add one, below 768px only (DD4; operator)
- [x] Fixes that also show at wide widths → the corner-button clearance everywhere, and compaction in any window under 480px tall, accepted as exceptions to charter criterion 4's "as today" (DD5, DD6; operator)
- [x] Leg split → three legs plus the HAT (operator; over the sortie's soft limit, still one design cluster)

### Design Decisions

**DD1. One pane at a time below 768px, chosen by what the operator asked for.** The shell row carries `data-pane="list"|"detail"`. Below 768px, `list` hides `#main-content` and lets `#app-sidebar` fill the area right of the rail; `detail` hides `#app-sidebar` and lets `#main-content` fill it.
- **Intent, not only the settled route.** Bare `#chats` keeps whatever chat is open and the router's post-hydrate sync rewrites it to `chats/{id}` (`js/areas/chat.js:18-20`, AC9b, pinned by `tests/browser/test_flow_chat_start_flow.py`); idle rules auto-join the newest session. So the pane cannot be read from the final URL alone.
- **The stamp rule (one formula).** `list` if the commit's input was the bare destination (kept until the next commit or arrival), or if the settled route is the bare destination (`chats`, `agents`, `library`); otherwise `detail`.
  - The flag is computed in `resolve()` after the legacy remap and carried on the target. The bare-Settings branch (`js/router.js` around :359-362) sets it on `rootTarget`; `#library/<section>` (an alias resolving to `library`, around :344-348) is caught by the settled-route half. The join in `go()` and `handleArrival` carry it through the target.
  - Syncs inside a commit (the bare-`#chats` re-canonicalise, `heal()` → `sync(null)` during hydrate) leave a bare-input `list` in place; a later sync to the bare destination (a delete, a dead-id heal) gives `list` by the settled-route half; a sync from `~new` to the created item stays `detail`.
  - **Arrivals (Back, Forward, reload, first load) stamp from the settled route only**, including the router's same-route no-op arrival. So Back from the Chats list (whose history entry was rewritten to `chats/{id}`) shows the chat, and a reload on `chats/{id}` shows the chat (operator-accepted).
  - The flag is exposed through its own accessor (proposed `App.router.paneIntent()`), not added to `describeCurrent()`, whose exact shape is pinned by `tests/browser/test_router_route_change.py`.
- **Hook.** `App.router.onRouteChange` (`js/router.js` around :449; fires at the end of each commit and after every sync, around :680-682 and :826). `onCommit` runs at commit step 5, before hydrate and the sync, so it is not used for this.
- **Hiding.** `@media (width < 768px) { .app-shell-row[data-pane="detail"] > #app-sidebar, .app-shell-row[data-pane="list"] > #main-content { display: none } }`, written in `@layer base` (where `base.css` lives) or a later layer, so its specificity (1,2,0) beats the destination width rules (1,1,0). It only ever sets `display: none`, so the global `[hidden]` reset and the "destination width rules never set display" invariant (`the_one/agents.md` "App shell — invariants") still hold. The shown pane gets only `flex`/`width`, never a `display` value.
- **The way back.** The current destination's rail href already points at its root (`js/app.js::mountRail`, `onCommit`), which is the bare destination, so the stamp shows the list. Agents and Library editors keep their breadcrumb (`js/ui/editor.js::buildBreadcrumb`). No new back control.
- **Library.** Below 768px `#library` shows the grouped list with its Add menu (the start page is the hidden main pane). Any `~new` or item route is detail. Recorded trade-off: narrow windows do not show the Library start page.
- **Focus.** `App.focusAfter` is token-based and covers in-place actions only (`js/focus-after.js`), so it is not the hook. A shell check, deferred with `setTimeout(0)`, runs after each `onRouteChange` **and on the 768px `matchMedia` change** (a resize can hide the pane holding focus): if `document.activeElement` is `body`, or is inside the pane that is now hidden (check both; WebKit can leave focus on a `display: none` element), focus `#main-content` (detail) or the open-item row, else the list's first control (list). A rail click leaves focus on the rail link, which stays visible. The studio breadcrumb's own deferred row focus and `App.nav`'s Continue `setTimeout(focusMain)` (`js/nav.js` around :96) still land; `focusMain` and the skip link target the visible pane.
- **Scroll.** Hiding a pane with `display: none` can lose its scroll position; when the chat pane is shown again the transcript re-pins to the bottom (`transcript.js` pins only on new content today), with a test. Charts in a hidden pane may get 0-width resize callbacks; they redraw when shown.
- **Accepted:** in the narrow Settings list, the document title, route announcer and GleepGlorp page context still say "Settings — Appearance" (the route is still `settings/appearance`).
- Navigation still goes through `App.nav`, so the leave guard is unchanged.

**DD2. The breakpoint is 768px, content-driven.** *(Leg 1 design review cycle 2: the range syntax below is replaced by the classic `(max-width: 767.98px)` / `(min-width: 1280px)` forms, because range syntax needs WebKitGTK 2.40+ and Safari 16.4+; `767.98px` closes the same fractional gap. See the flight log.)* The list column fits beside a 360px main pane down to 72 + 300 + 360 = 732px; 768px is the common breakpoint just above it. Rules use the range syntax `(width < 768px)` (and `(width >= 1280px)` where the drawers' query is touched), so a fractional viewport cannot fall between two queries. JS that must know the mode uses `matchMedia('(width < 768px)')` with a `change` listener, the drawers' existing pattern. A 1920 half-screen (960) stays side by side; a 1920 third (640) gets one pane.

**DD3. Settings: only the rail's href changes.** Making bare `#settings` a real route would change the wide URL and break recorded contracts: `admin.serializeState` returns `appearance`, GleepGlorp page awareness sends a Settings page with no section that the server rejects (`the_one/gleepglorp/page.py` around :148-150), and the redirect is pinned in `tests/browser/test_router_core.py` (`REDIRECT_ROWS`, `PARITY_CORPUS`), `tests/browser/_nav.py::canonical`, `tests/test_nav_helper.py`, `tests/browser/test_shell_rail.py`, `tests/browser/test_flow_admin_settings_nav.py` and `tests/test_gleepglorp_guide.py`. So the redirect, `App.router.root('settings')`, `lastRoute`, the `settings/general` alias and the Jump to targets stay exactly as they are. Only the rail's Settings href changes: it is bare `#settings` when Settings is the current destination, **and also when `lastRoute('settings')` is the root** (`settings/appearance`), so entering Settings from another destination shows its nav first, as Chats, Agents and Library show their lists (operator). The router still redirects bare `#settings` to `settings/appearance`, and DD1's bare-input flag stamps `list`, so below 768px the Settings nav fills the pane. At 768px and wider the redirect renders Appearance as today. *(Flight review: the rail's Settings href is bare `#settings` at every width, so its hover target and the URL during a click differ from today at 1024 and 1280 before the redirect lands on `settings/appearance`; an intended consequence of this decision, recorded alongside DD5 and DD6 as a wide-width difference.)* The rail href pins in `test_shell_rail.py` (including the first-boot pin around :464) and `test_flow_admin_settings_nav.py` change on the record.

**DD4. Below 768px the agent panel and GleepGlorp's drawer fill the pane.** Both are `App.ui.drawer` instances with push/overlay at 1280px (`js/areas/chat/agent-drawer.js`, `js/gleepglorp-drawer/shell.js`, `PUSH_QUERY`).
- **A `fill` mode on the factory.** `App.ui.drawer` gains a third mode, `fill` (alongside `push`/`overlay`, via `setMode`): the box spans from the rail's edge (a new `--rail-w` token replaces the rail's literal 72px, so the factory does not hard-code shell geometry) to the right edge, and `open(opener, {focus: true})` moves focus in (first control, else the heading, else the aside). The factory stays unaware of the viewport and the shell; each caller picks the mode from its `matchMedia`. `reserveHeaderEnd` stays overlay-only. The contract test that pins "open() never moves focus" (`tests/browser/test_ui_drawer_contract.py`) stays true for the default call and gains `fill` and `{focus: true}` cases; the inventory row (`docs/ui-control-inventory.md`, the drawer row) is updated.
- **The agent panel.** Below 768px its open state is **session-only and starts closed on every load** (operator): it is not written to `chat-drawer-open`, whose stored shape `{push, overlay}` is pinned by `tests/browser/test_flow_chat_drawer.py`, so the 1024 and 1280 behaviour is untouched and an open panel is never restored over an inert `<main>` at boot. The toggle opens it through `apply()`, so a one-shot "opened from the toggle" flag moves focus in; `apply()` restoring visibility never does. In `fill` mode the chat-header toggle (`.chat-drawer-toggle`, drawn above the overlay at `z-index: 11`, `chat.css:69-74`) is hidden while the panel is open, and the panel gains a **Close button in its header, shown below 768px only** (operator): the icon-only ✕ labelled "Close agent panel" from the approved board, an `App.ui.button` with a registered test id and inventory coverage. Escape closes as today.
- **GleepGlorp's drawer.** It already moves focus in at every width (`focusInitial`) and has a Close control; below 768px it switches to `fill`. A GleepGlorp fill that changes the page while the drawer covers it is left as is: the drawer shows the fill's card, and the operator closes the drawer to see the page.
- **Navigation closes a fill-mode drawer** (operator). A commit not started from inside the drawer (a rail click, Back or Forward, Jump to) closes an open `fill` drawer, so the operator sees where they went. GleepGlorp fills (`gleepglorp-drawer/fill.js`) are exempt. Tested.
- **Inert behind, owned by the shell.** One shell helper (proposed `App.shell.setCovered(owner, on)`) sets `inert` on both `#app-sidebar` and `#main-content` (a fill can move the route from list to detail underneath). Each drawer calls it from its visibility path before any focus move, on every transition into or out of a shown `fill` state: open, `close()` (from `beforeClose`, which runs before focus returns to the opener, `js/ui/drawer.js`), `apply()` hiding the slot directly (GleepGlorp's `slot.hidden` on Chats or when turned off, `shell.js:199-200`), the mode change on resize (`agent-drawer.js` around :615, `shell.js` around :257) and `destroy()`. GleepGlorp's `rescueFocus` and `focusMain` target the visible, non-inert pane. `inert` does not affect the leave-guard modal (it goes to `document.body` via `showModal`), the chat socket or composer drafts.
- The two drawers never coexist (`gleepglorp-drawer/shell.js::canShow` is false on Chats; the agent panel lives only on Chats), so no coordinator is needed. At 768px and wider the agent panel's behaviour is unchanged.

**DD5. Short windows compact the chat chrome, and the rail scrolls.** Under `@media (height < 480px)`: the chat header, message spacing and composer padding tighten (the A2 board shows the target: 40px header, Send beside the input); the rail's items and footer tighten and the rail scrolls vertically if they still do not fit. The rules a measurement at 624×321 shows are needed (three transcript lines above the composer with the toolbar, telemetry and an attachment row shown) are added; no more. **Accepted exception (operator):** this also applies to a wide window under 480px tall; 1024×768 and 1280×800 are unaffected.

**DD6. Every scroll container clears the GleepGlorp corner button.** Today only `.studio-editor`, `.studio-section-content` and `.admin-content` reserve 72px under `gg-corner-on` (`css/gleepglorp-drawer.css:138-140`), and the reservation sits on a flex column that may not be the scroller (agent editor tab panels). Each scroll container that can sit under the button reserves its space on the element that actually scrolls. **Accepted exception (operator):** this fixes the clearance at every width, so the bottom spacing of some scroll containers changes at 1024 and 1280. Proven by the criterion-1 test: the last control in each container, scrolled into view, is the element at its own centre point.

**DD7. Fixed widths clamp.** The modal's 320px `min-width` becomes `min(320px, 100% - 24px)`, the tool tile grid's `minmax(280px, 1fr)` becomes `minmax(min(280px, 100%), 1fr)`, form and page paddings step down (32px → 16px) below 768px, and any other fixed width found by the criterion-3 test is clamped the same way. The clamps resolve to today's values at 768px and wider.

**DD8. The shell's recorded rules change on the record.** `the_one/agents.md` "App shell — invariants" (fixed widths at every supported width, 1024px the supported minimum) and the routing notes are rewritten: side by side at 768px and wider, one pane at a time below by intent, panels fill the pane below 768px. `tests/browser/test_shell_rail.py` (`test_shell_geometry_at_supported_widths`, `test_settings_nav_labels_and_chat_rows_do_not_clip_at_1024`, the rail href pins) keeps its 1024+ assertions. The app guide (`the_one/gleepglorp/guide/*.md`) describes the narrow layout, how to get back to a list, and the panel's Close button.

**DD9. The real-window check is the WebKitGTK probe at 640×360.** `scripts/webkitgtk_probe.py` builds a real `Gtk.Window` with a `WebKit2.WebView` (WebKitGTK 2.52.6 on this host) and hard-codes `window.set_default_size(1280, 900)`.
- It gains `--window-size WxH` (default unchanged), covered by its existing safety tests.
- Observation channel: a setup script must complete with exactly `true`, and its return value does not reach the output; the probe echoes `window.__probeReport` as `"report"`. Setup runs right after `location.hash = …`, before the router commits, so the setup script defines `__probeReport` as a getter (measured when read), and `--root-selector` waits for a settled state (for example `.app-shell-row[data-pane="detail"]`).
- The report includes `innerWidth`, `innerHeight`, `devicePixelRatio`, the visible pane's width and `scrollWidth <= clientWidth`. `pin_environment` does not pin `GDK_SCALE`, and `MIN_SIZE` is the outer window size, so the run asserts the viewport is at most 640×360 and records the DPR; it is also run at 624×321.
- Run against a dev instance (port 8490 or higher, scratch data dir under `$HOME`; the probe refuses 8484/8485 and the default data dir) on an open-chat route and the Settings nav; output recorded in the flight log.

**DD10. Tests and lanes.** A new `tests/browser/test_flow_narrow_layout.py`, created in leg 1 and extended in each later leg so no leg lands without its proof. It carries the charter criteria at 624×321 (every destination and tab), 480×321 and 360×640 (no sideways scroll), and 1024×768 / 1280×800 (unchanged), plus the pane-intent, rail and panel focus tests. The core layout assertions run in Chromium and WebKit through `engine_browser` + `credentialed_context(...)` (the live-app pattern in `tests/browser/test_flow_admin_settings_nav.py`); the rest in Chromium. Navigation goes through `_nav.goto_settled`. A new **`layout`** lane in `scripts/run-tests.sh` (glob `test_flow_narrow_*`, a provisional budget), with `CANON_LANES`, `tests/test_run_tests_lanes.py`, and the lane lists in CLAUDE.md and `the_one/agents.md` updated. `THE_ONE_REQUIRE_WEBKIT` is set per run, not per lane (`run-tests.sh` around :116), and `make test-browser` does not set it, so the leg either has `run-tests.sh` set it for the `layout` lane or records the `layout` lane alongside the contracts lanes in CLAUDE.md's "run with `THE_ONE_REQUIRE_WEBKIT=1`" list; the leg picks one and says which. Tests whose pinned shapes this sortie must not break: `tests/browser/test_router_route_change.py` (the exact `describeCurrent()` dict; DD1 uses a separate accessor) and `tests/browser/test_flow_chat_drawer.py` (the stored `{push, overlay}` state; DD4 does not persist the narrow state). The squawk 0334 grep picks the extra lanes each leg runs (DD5 touches composer and chat-header CSS: the chats and contracts-chat lanes). `scripts/ui_capture.py` gains 640×360 and 624×321 sizes (its default widths stay 1280,1024).

### Citation Audit

Verified against the working tree at `e3140b24` (rows marked A re-checked by the Architect, review cycle 1):

| Citation | Status |
|---|---|
| `the_one/interfaces/desktop/window_state.py::MIN_SIZE` is `(640, 360)`, the outer size | verified (A) |
| `js/app.js::mountRail` `onCommit`: current destination's href is `App.router.root(destId)`, others `lastRoute` | verified |
| `js/areas/chat.js:18-20`: bare `#chats` keeps the open chat; the post-hydrate sync re-canonicalises the URL | verified |
| `js/router.js` exports `onCommit`, `onRouteChange`, `describeCurrent`, `lastRoute`, `root`; `onCommit` runs at commit step 5, `onRouteChange` after each commit and sync | verified (A) |
| `js/router.js` `resolve`: bare `settings` redirects to `dest.root`; `settings/general` aliases to `settings/appearance`; `library/<section>` redirects to `library` | verified (A) |
| `js/ui/editor.js::buildBreadcrumb` builds an `a.editor-breadcrumb-link` with a caller-supplied href | verified |
| `js/areas/chat/agent-drawer.js`: `PUSH_QUERY = '(min-width: 1280px)'`, one `apply()`, `reserveHeaderEnd`, header toggle `chat-drawer-toggle`, per-mode `chat-drawer-open` storage, no Close button | verified (A) |
| `js/gleepglorp-drawer/shell.js`: `PUSH_QUERY`; `canShow()`; `focusInitial`; a Close control; `gg-corner-on`; `apply()` hides via `slot.hidden` | verified (A) |
| `js/ui/drawer.js`: `open()` never moves focus; `beforeClose` runs before focus returns; Escape only while focus is inside | verified (A) |
| `js/focus-after.js`: token-based, in-place actions only | verified (A) |
| `css/gleepglorp-drawer.css:138-140`: `gg-corner-on` reserves 72px on three containers only | verified |
| `tests/browser/test_ui_drawer_contract.py` pins "open() never moves focus" | verified (A) |
| `tests/browser/_ui_engines.py::engine_page` is a disk harness; the live-app two-engine pattern is `engine_browser` + `credentialed_context` | verified (A) |
| `scripts/webkitgtk_probe.py`: `set_default_size(1280, 900)`; setup scripts must complete `true`; `window.__probeReport` echoed as `"report"`; `pin_environment` does not pin `GDK_SCALE` | verified (A) |
| `scripts/ui_capture.py::SIZES` holds only 1280×900 and 1024×768 | verified |
| The Settings redirect pins listed in DD3 | verified (A) |

### Prerequisites
- [x] WebKitGTK 4.1 with GObject introspection on this host for the probe (`/usr/bin/python3`, WebKit2 2.52.6)
- [x] Playwright WebKit installed (`~/.cache/ms-playwright/webkit-2370`); re-verify at leg start
- [ ] The WSLg display works for the probe: a smoke run at leg 3 start
- [ ] A dev instance for the probe and the HAT: port 8490 or higher, scratch data dir under `$HOME`, started from a scratch cwd (CLAUDE.md "Behavior-test credential convention"); re-verify at each leg that uses it
- [ ] Branch `sortie/21-usable-at-the-smallest-window` from `main` (nothing else is in flight)

### Pre-Flight Checklist
- [x] All open questions resolved
- [x] Design decisions documented
- [x] Citation Audit complete — every code-asserting design decision verified
- [ ] Prerequisites verified (the leg-start re-verifies remain)
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach
1. **Narrow shell (leg 1).** The router's bare-input flag, the `data-pane` stamp from `onRouteChange`, the 768px pane rules, the focus subscriber, the Settings rail href, the shell invariants, guide and shell tests rewritten, the new `layout` lane, and `test_flow_narrow_layout.py` with the pane, rail and focus assertions.
2. **Panels (leg 2).** `App.ui.drawer`'s `fill` mode and `{focus: true}` with contract tests and inventory row; the agent panel's narrow state, narrow-only Close button and focus-in from the toggle; GleepGlorp's drawer in `fill`; `inert` behind; panel tests added to the file.
3. **Height, clearance, clamps and proof (leg 3).** Measure at 624×321; the short-height rules and rail scroll; the corner-button reservation on the real scrollers; width clamps; capture sizes; the probe's `--window-size` and the run at 640×360 and 624×321; the remaining criterion tests; the closing gate.
4. **HAT (leg 4).** A guided session with the operator at 640×360, a snapped third (640 wide, full height) and a half-screen (960), in both themes, with fixes through the fix-vs-feature gate.

### Checkpoints
- [ ] Below 768px each destination shows one pane; clicking the current rail icon shows its list (Chats included); Settings shows its nav; 768px and wider unchanged
- [ ] Panels fill the pane below 768px with focus in from the toggle, Escape, the agent panel's Close button and focus return; unchanged at 1024 and 1280
- [ ] Every criterion-1 assertion passes at 624×321 in Chromium and WebKit
- [ ] No sideways scroll at 480×321 and 360×640
- [ ] The probe at 640×360 in WebKitGTK reports the viewport, DPR, a visible pane at least 360px wide and no horizontal overflow
- [ ] `make gate` green

### Adaptation Criteria

**Divert if**:
- The bare-input flag cannot be added without changing what a URL means at 768px and wider
- One pane at a time breaks the leave guard or the studio breadcrumb's focus in a way the shell subscriber cannot handle
- Any change is needed at 768px and wider beyond DD5 and DD6

**Acceptable variations**:
- The exact short-height compactions (DD5), set by measurement
- The intent accessor's name (DD1) and the shell helper's name (DD4)
- The `layout` lane's budget (DD10), provisional until a quiet-host reading

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses.

- [x] `narrow-shell` - Pane by intent below 768px (DD1, DD2), the Settings rail href (DD3), the shell invariants, guide and shell tests (DD8), the `layout` lane and the first narrow tests (DD10)
- [x] `narrow-panels` - The drawer `fill` mode and focus option, the agent panel's narrow state and Close button, GleepGlorp in `fill`, `inert` behind (DD4), with tests
- [x] `height-clamps-and-proof` - Short-height rules and rail scroll (DD5), corner-button clearance (DD6), width clamps (DD7), capture sizes, the probe option and run (DD9), the remaining criterion tests, the closing gate
- [x] `uat-and-alignment` - Guided HAT at 640×360, a snapped third and a half-screen, both themes, with fixes (two look-and-feel fix batches and one promoted feature, `legs/04a-hat-feature-narrow-tabs-and-actions.md`: a tabs menu and a ⋯ More actions menu below 768px)

---

## Post-Flight

### Completion Checklist
- [x] All legs completed
- [ ] Code merged
- [x] Tests passing
- [x] Documentation updated
- [ ] Issue #225 closed with a link to the PR
- [x] Follow-up comment on PR #393 (see the flight log's post-landing actions)

### Verification
- Charter criteria 1–3: `tests/browser/test_flow_narrow_layout.py` at 624×321 (Chromium and WebKit for the core assertions), 480×321 and 360×640.
- Charter criterion 4: the same file at 1024×768 and 1280×800, plus every existing lane (`make gate`, contracts lanes and the `layout` lane with `THE_ONE_REQUIRE_WEBKIT=1`), with DD5 and DD6 as the accepted exceptions.
- Real desktop engine: `scripts/webkitgtk_probe.py --window-size 640x360` (and 624x321) on a dev instance, output recorded in the flight log.
- Static guards: `tests/test_ui_guards.py`, `tests/test_token_definitions.py`, `tests/test_design_tokens_a11y.py`, `tests/test_gleepglorp_guide.py`, `tests/test_ui_control_inventory.py`, `tests/test_ui_ownership.py`.
- Captures: `scripts/ui_capture.py --widths 624,640` across the four destinations, both themes, for the HAT.
- HAT sign-off by the operator.
