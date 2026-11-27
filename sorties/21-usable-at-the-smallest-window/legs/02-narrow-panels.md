# Leg: narrow-panels

**Status**: completed
**Flight**: [Usable at the smallest window](../flight.md)

## Objective
Below 768px the agent panel and GleepGlorp's drawer fill the area right of the rail, take focus when the operator opens them, keep keyboard and screen readers out of the covered panes while open (the rail stays usable), close on Escape, on their Close button and on any navigation except a GleepGlorp fill's, and return focus when they close; at 768px and wider both behave exactly as today.

## Context
- Flight DD4 (as revised after Architect cycle 2) is the spec for this leg; read it first. Operator calls: panels fill the pane below 768px; the agent panel's Close button shows below 768px only; navigation closes a fill-mode panel (GleepGlorp fills exempt); the agent panel's narrow open state is session-only and starts closed on every load.
- The approved mockup board "Agent panel open at 624×321" shows the whole-pane panel with an icon-only ✕ labelled "Close agent panel" in its header.
- Leg 1 (landed, uncommitted) added `js/shell-pane.js` (`App.shellPane.visiblePane()`, `focusVisible()`, the `(max-width: 767.98px)` media listener, the `data-pane` stamp), the router's `paneIntent()` / `onPaneIntentChange()`, and `tests/browser/test_flow_narrow_layout.py` in the `layout` lane. Media queries use the classic `(max-width: 767.98px)` form, not range syntax (leg 1 design review; flight DD2 annotated).
- The two drawers never coexist: the agent panel lives only on Chats, and GleepGlorp's drawer never shows on Chats (`gleepglorp-drawer/shell.js::canShow`). No coordinator.
- Short-height rules, corner-button clearance and width clamps are leg 3.

## Inputs
- `js/ui/drawer.js` (180 lines): `MODES = ['push', 'overlay']`; `open(opener)` never moves focus; `close()` returns focus to the opener only if focus is inside; `beforeClose()` runs before that return; Escape handled by one keydown listener on the `<aside>`; `setMode` validates against `MODES`; `reserveHeaderEnd` pads the header only in overlay mode (CSS `.ui-drawer--overlay.ui-drawer--reserve-end`).
- `css/components.css`: `.ui-rail` `width: 72px` (~:55); `.ui-drawer--overlay` absolute, `z-index: 10` (~:1891-1898); `.chat-drawer-toggle` sits above the overlay at `z-index: 11` (`css/chat.css` ~:69-74); `.ui-corner-button` `z-index: 9`.
- `js/areas/chat/agent-drawer.js`: `state = {mode, open: readOpen()}` with `localStorage` `chat-drawer-open` `{push, overlay}` (~:100-131); `onOpenChange` persists only non-`applying` changes (~:191-198); the header toggle flips `state.open[state.mode]` and calls `apply()` (~:204-219); `apply()` is the one visibility path (~:600-612); one `matchMedia('(min-width: 1280px)')` listener (~:614-623); `destroy()` (~:635).
- `js/gleepglorp-drawer/shell.js`: Close button `gg-drawer-close` (~:99-107); `onOpenChange` → `apply()`, `notifyOpen`, `focusInitial()` (~:136-146); `rescueFocus()` focuses `#main-content` (~:178-184); `apply()` hides the slot directly (`slot.hidden`) and toggles `gg-corner-on` (~:194-204); `applyMode()` from one `matchMedia(PUSH_QUERY)` (~:255-258).
- `js/gleepglorp-drawer/fill.js` (~:84) and `chat.js` (~:137) navigate with `App.router.go(..., {opener: <element inside the drawer>})`.
- `js/router.js` keeps per-decision options on `deciding` (`opener`, ~:809-826; set in `beginDecision`, joined in `go()` ~:822-827, `bypassGuard` literal ~:831, arrival join in `handleArrival`); `keepCovered` is carried on the decision the same way, with the merge rules of step 3.

## Outputs
- `App.ui.drawer`: a `fill` mode and an `open(opener, {focus: true})` option, with contract tests and the inventory row updated.
- A `--rail-w` token used by the rail and by `fill`.
- The agent panel: a `fill` mode below 768px with a session-only closed-by-default state, focus-in from its toggle, the header toggle hidden while it fills, a narrow-only Close button.
- GleepGlorp's drawer: `fill` below 768px.
- `App.shellPane.setCovered(owner, on, {el, close})`: `inert` on both panes while a fill drawer is shown, and closing a covering drawer on any commit without `keepCovered`.
- The router carries `keepCovered` on a decision and exposes the applied decision (`{opener, arrived, keepCovered}`) to commit subscribers.
- Panel tests in a new `tests/browser/test_flow_narrow_panels.py` (`layout` lane glob).

## Acceptance Criteria
- [ ] **AC1 Factory.** `App.ui.drawer` accepts `setMode('fill')`: the `<aside>` spans from `var(--rail-w)` to the right edge of its positioned container, full height, above the panes (the overlay's stacking level), no shadow needed. `open(opener, {focus: true})` moves focus into the drawer only on a closed-to-open transition (an `open()` on an already-open drawer does nothing, as today): its first focusable control that is not `[hidden]` and has a layout box (`getClientRects().length`), else the `<aside>` (which already has `tabindex="-1"`); `open(opener)` with no options still never moves focus. For the agent panel the first focusable is its Close button (accepted). `reserveHeaderEnd` applies in overlay mode only. Existing contract tests in `tests/browser/test_ui_drawer_contract.py` pass unedited; new cases cover `fill` geometry and class, `{focus: true}`, and Escape/close focus return in `fill`. The inventory row for Drawer in `docs/ui-control-inventory.md` documents `fill` and `{focus}`.
- [ ] **AC2 Rail token.** A `--rail-w` token (72px) is defined in `css/tokens.css` and used by `.ui-rail`'s width and by `.ui-drawer--fill`; the token guards (`tests/test_token_definitions.py`, `tests/test_design_tokens_a11y.py`, `tests/test_css_layers.py`) pass.
- [ ] **AC3 Agent panel, narrow.** Below 768px the agent panel's mode is `fill`. Its open state there is session-only (`state.open.fill`, never written to `chat-drawer-open`, whose `{push, overlay}` shape `tests/browser/test_flow_chat_drawer.py` pins), `false` on every load, and reset to `false` on every entry into `fill` (a resize from wide to narrow never opens it). Opening it from the header toggle moves focus into it (a one-shot flag consumed by `apply()`); `apply()` re-showing it never moves focus. While it is shown in `fill`, the chat-header toggle (`chat-drawer-toggle`) is hidden and a Close button is shown at the right end of the panel header (appended to the factory's `.ui-drawer-header` after the agent heading block, not inside `.chat-drawer-head`): an `App.ui.button` ghost, icon-only `x`, `aria-label` "Close agent panel", test id `chat-drawer-close` (registered in `docs/ui-testid-registry.md`), hidden in `push` and `overlay` **by CSS keyed on the factory's `data-mode`** (`#chat-drawer:not([data-mode="fill"]) .chat-drawer-close { display: none; }` in the areas layer), never toggled from `beforeClose` or `onOpenChange` (hiding a focused element blurs it and breaks the focus return). Close and Escape close it and focus returns to the chat-header toggle (shown again first in `beforeClose`, as GleepGlorp's `beforeClose` does for its corner button), in Chromium and WebKit.
- [ ] **AC4 GleepGlorp drawer, narrow.** Below 768px its mode is `fill` and its box spans from `--rail-w` to the right edge: `#gleepglorp-drawer { width: 360px }` (`css/gleepglorp-drawer.css` ~:8, `@layer areas`, which beats `components`) gets a `#gleepglorp-drawer[data-mode="fill"] { width: auto; }` rule beside it. Its existing focus-in, Close button and Escape keep working; on close, focus returns to the corner button.
- [ ] **AC5 Inert.** While a drawer is shown in `fill`, `#app-sidebar` and `#main-content` both carry `inert`, and nothing else does (the rail stays live). `inert` is set through `App.shellPane.setCovered(owner, true, {el, close})` on every transition into a shown `fill` state and cleared through `setCovered(owner, false)` on every transition out of it, **before any focus move**. `drawer.close()` runs `beforeClose`, then returns focus to the opener, then hides, then `onOpenChange`, so: each drawer's `beforeClose` calls `setCovered(owner, false)` first (the agent panel's also unhides its toggle there; the Close button is left to CSS); the agent panel's `apply()` calls `setCovered` at its top, before `drawer.open`/`drawer.close`; GleepGlorp's `apply()` calls it before `rescueFocus()`. Each drawer routes these through one sync helper called from `beforeClose`, `onOpenChange` (the Escape path: the agent panel sets `state.open.fill = false`, skips `writeOpen`, syncs `aria-pressed`) and `apply()`. Transitions covered: open, Escape, Close, `close()`, `apply()` hiding the slot directly (GleepGlorp on Chats or turned off; the agent panel's `setActive(false)` or view change), a media change out of `fill`, and `destroy()`. GleepGlorp's `rescueFocus()` uses `App.shellPane.focusVisible()` only when `App.shellPane.visiblePane()` is non-null (below 768px), else keeps today's `#main-content` focus, and falls back to `#main-content` if `focusVisible()` returns false. Leg 1's skip-link handler also redirects to the covering drawer when `#main-content` is `inert`. The leave-guard modal still works while covered (it is in `document.body`).
- [ ] **AC6 Navigation closes.** While a drawer covers the panes, every commit closes it through the `close` callback given to `setCovered`, unless the decision carries an explicit `keepCovered` flag. Only GleepGlorp fills set it: `fill.js` calls `App.router.go(href, {opener, keepCovered: true})`. So a rail click, Back or Forward, Jump to (including Jump to started from inside the drawer, where the opener is inside it), the drawer's own setup link ("Choose a model"), and the agent panel's "Open agent settings" all close it. The router carries `keepCovered` on the decision (`deciding`) like `opener`, and exposes the applied decision to commit subscribers as `App.router.lastDecision()` → `{opener, arrived, keepCovered}` (boot: `{opener: null, arrived: true, keepCovered: false}`), read in an `onCommit` subscriber; `describeCurrent()` unchanged. Accepted: a same-route Back/Forward arrival is a router no-op (no commit), so it does not close the drawer.
- [ ] **AC7 Wide unchanged.** At 768px and wider (1024×768, 1280×800, and 900×700 for the overlay band) both drawers behave exactly as today: same modes, widths, persisted state, focus (no focus-in for the agent panel), toggle visibility and no Close button on the agent panel; no `inert` anywhere. `tests/browser/test_flow_chat_drawer.py`, `tests/browser/test_flow_gleepglorp_drawer_shell.py` and the drawer contract tests pass unedited.
- [ ] **AC8 Charter criterion 2 at 624×321.** In a browser at 624×321, for each panel: it opens by mouse and by keyboard (Enter on its opener), fills the area right of the rail, focus moves in, Tab and Shift+Tab never land in `#app-sidebar` or `#main-content` (the panes are inert; the rail stays reachable), Escape closes it, its Close button closes it, focus returns to the opener, and the main pane is never narrower than 360px when it closes; in Chromium and WebKit.
- [ ] **AC9 Records.** `the_one/agents.md` (the agent drawer and GleepGlorp drawer sections, the App shell invariants for `inert`/`setCovered`, the drawer factory) and the app guide (the agent panel's Close button in small windows) are updated; `tests/test_gleepglorp_guide.py`, `tests/test_ui_control_inventory.py`, `tests/test_ui_ownership.py` pass.

## Verification Steps
- AC1: `tests/browser/test_ui_drawer_contract.py` (its lane via `scripts/run-tests.sh --list`; run with `THE_ONE_REQUIRE_WEBKIT=1`).
- AC2: the static token guards.
- AC3–AC6, AC8: `tests/browser/test_flow_narrow_panels.py` (new) at 624×321, core cases in Chromium and WebKit (`engine_browser` + `credentialed_context`), via `--lane layout` with `THE_ONE_REQUIRE_WEBKIT=1`.
- AC7: `--lane chats`, `--lane gleepglorp-chat`, the contracts lane holding the drawer contract tests, and the new file's wide cases.
- AC9: `tests/test_gleepglorp_guide.py`, `tests/test_ui_control_inventory.py`, `tests/test_ui_ownership.py`.
- Leg end: the static guards (`test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`, `test_css_layers`, `test_ui_ownership`, `test_ui_control_inventory`, `test_nav_helper`, `test_store_static`), `THE_ONE_TEST_NETNS=1 make test-unit`, and the lanes `layout`, `chats`, `gleepglorp-chat`, `gleepglorp-fill`, `contracts-overlay` (or whichever contracts lane holds `test_ui_drawer*` and `test_ui_rail*`), `routing` and `shared`.

## Implementation Guidance

1. **Token.** Add `--rail-w: 72px` to `css/tokens.css` (with whatever registry `tests/test_token_definitions.py` requires) and use it for `.ui-rail`'s width (`components.css` ~:55).

2. **Factory (`js/ui/drawer.js`).** Add `'fill'` to `MODES` and to `setMode`'s class toggling (`.ui-drawer--push` / `--overlay` / `--fill`); `.ui-drawer--fill { position: absolute; top: 0; bottom: 0; left: var(--rail-w); right: 0; width: auto; z-index: 10; }` in `components.css` next to `.ui-drawer--overlay` (`@layer components`). `open(opener, opts)`: only on a closed-to-open transition and when `opts && opts.focus`, after showing, focus the first focusable descendant that is not `[hidden]` and has a layout box (`getClientRects().length`; same selector shape as `shell-pane.js`'s `FOCUSABLE`), else the `<aside>`. Keep the "never moves focus" default, the returned keys (`test_ui_drawer_contract.py` ~:104 pins them) and the single keydown listener. Update the factory's header comment, the inventory row and add contract cases.

3. **Router decision (`js/router.js`).** `go(route, opts)` carries `opts.keepCovered` onto the decision, with explicit merge rules (latest wins; unlike `opener`, it is overwritten, never only set):
   - `beginDecision`: `keepCovered: !!(opts && opts.keepCovered)`;
   - the `go()` join with a pending decision (~:822-827): `deciding.keepCovered = !!opts.keepCovered`;
   - the arrival join in `handleArrival` (where `deciding.arrived = true`): `deciding.keepCovered = false`;
   - the `bypassGuard` path (~:831): pass `keepCovered: !!opts.keepCovered` through.
   In `applyDecision`, before `commit(...)`, record `{opener: d.opener || null, arrived: !!d.arrived, keepCovered: !!d.keepCovered}`; the variable's initial value is `{opener: null, arrived: true, keepCovered: false}` (boot's `commit` in `start()` bypasses `applyDecision`); `App.router.lastDecision()` returns a copy. Add `keepCovered` to the `go()` header comment (~:39). In `js/gleepglorp-drawer/fill.js` (~:84) pass `keepCovered: true` (only there; `chat.js` "Open in Chats" does not). Keep `describeCurrent()` and the public `resolve()` unchanged. Router tests cover the join (fill pending behind a guard, then a rail `go()` → `keepCovered` false) and the arrival override.

4. **Shell (`js/shell-pane.js`).** Add `App.shellPane.setCovered(owner, on, opts)`: a registry keyed by owner string (`'chat-drawer'`, `'gleepglorp'`); while any owner is covering, set `inert` on `#app-sidebar` and `#main-content`, else remove it; never on the rail. Subscribe `App.router.onCommit` (at script load; it then runs before GleepGlorp's own `onCommit`, which is fine): unless `App.router.lastDecision().keepCovered`, call each covering owner's `opts.close()`, iterating a copy of the registry (a close re-enters `setCovered(false)`), then schedule leg 1's focus check (`setTimeout(0)`), so a close whose opener is unmounted by the same navigation (the agent panel's "Open agent settings", GleepGlorp's setup link or "Open in Chats") never leaves focus on `<body>`. `setCovered` is idempotent and removes `inert` only when the registry is empty. When `setCovered(owner, true)` finds `document.activeElement` on `<body>` or inside a pane it is about to make inert, it moves focus to `opts.el` (the `<aside>`). Make `focusVisible()` skip an `inert` pane (it returns false and leaves focus alone). Extend leg 1's skip-link handler: when `#main-content` is `inert`, `preventDefault()` and focus the covering drawer's `<aside>`.

5. **Agent panel (`js/areas/chat/agent-drawer.js`).**
   - A second `matchMedia('(max-width: 767.98px)')`; one `modeFor()` computes `fill` when it matches, else `push`/`overlay` from the 1280px query; the initial `state.mode` at `create()` uses `modeFor()` (both queries), and `state.open` gains `fill: false` beside what `readOpen()` returns. Both listeners call one `onMedia`: `var prev = state.mode; state.mode = modeFor(); if (state.mode === 'fill' && prev !== 'fill') state.open.fill = false; apply();` The reset lives only in `onMedia`, never in `apply()` (a store-driven `apply()` while narrow and open must not close the panel; test it).
   - `state.open.fill` is never read from or written to storage (`writeOpen` keeps serialising only `{push, overlay}`; both the toggle's `onClick` and `onOpenChange` skip `writeOpen` in `fill`).
   - The toggle's `onClick` in `fill` sets a one-shot `focusOnOpen`. `apply()` takes and clears it unconditionally at its top (`var f = focusOnOpen; focusOnOpen = false;`) and uses it only for `drawer.open(toggle, {focus: f})` (the factory focuses only on a closed-to-open transition), so a click while `apply()` does not open never leaks into a later `apply()`.
   - One sync helper (`syncCover(shown)`): `setCovered('chat-drawer', shown && mode === 'fill', {el: drawer.el, close: closeFromShell})`, the toggle's visibility (`toggle.hidden = !view || (mode === 'fill' && shown)`) and `aria-pressed`. The Close button's visibility is CSS only (AC3).
   - When the drawer closes because `view` became null (the chat was deleted) and the toggle is therefore hidden, the focus return has no visible target: after the close, if focus is on `<body>`, call `App.shellPane.focusVisible()`. Call it at the TOP of `apply()` with the wanted state (before `drawer.open`/`close`), from `beforeClose` with `false` (so `inert` is cleared and the toggle is visible before the factory returns focus to it), from `onOpenChange` (the Escape path: in `fill`, set `state.open.fill = false`, no `writeOpen`), and with `false` in `destroy()`. `closeFromShell` sets `state.open.fill = false` and calls `apply()`.
   - The Close button: `App.ui.button({variant: 'ghost', icon: 'x', iconOnly: true, ariaLabel: 'Close agent panel', className: 'chat-drawer-close', testid: 'chat-drawer-close', onClick: ...})` appended to the factory's `.ui-drawer-header` (`drawer.el.firstChild`) after the agent heading block; visible only in `fill` through the `data-mode` CSS rule (AC3).

6. **GleepGlorp drawer (`js/gleepglorp-drawer/shell.js`).** `applyMode()` picks `fill` below 768px (a second media query), `overlay` below 1280px, else `push`, records it in a `mode` variable declared before the first `apply()`, and re-runs `apply()`. On a transition into `fill` (`prev !== 'fill'`), an open drawer closes (`userOpen = false`), matching the agent panel (FD call: a drawer open in a wide window does not suddenly cover the whole pane when the window narrows). Add `#gleepglorp-drawer[data-mode="fill"] { width: auto; }` beside `#gleepglorp-drawer { width: 360px }` in `css/gleepglorp-drawer.css` (~:8). One sync helper calls `App.shellPane.setCovered('gleepglorp', drawerShown && mode === 'fill', {el: slot, close: function () { api.close(); }})`: from `beforeClose` with `false` first (before the factory returns focus to the corner button), and in `apply()` before `rescueFocus()` runs. `rescueFocus()` uses `App.shellPane.focusVisible()` only when `App.shellPane.visiblePane()` is non-null, else today's `#main-content` focus, and falls back to `#main-content` if `focusVisible()` returns false. Clear the cover on destroy if the module has one.

7. **CSS for the agent panel in fill.** The chat-header toggle sits at `z-index: 11` over the overlay; in `fill` it is hidden by `apply()` (step 5), so no stacking change is needed. Confirm the drawer header's right end is clear for the Close button in `fill` (`reserveHeaderEnd` is overlay-only).

8. **Tests.** New `tests/browser/test_flow_narrow_panels.py` (globbed into `layout`): AC3–AC8 at 624×321 in Chromium and WebKit for the core open/focus/Tab/Escape/Close cases; the navigation-close cases (rail click, Back, Jump to; a GleepGlorp fill does not close); the session-only state (reload → closed at narrow; the stored `{push, overlay}` unchanged); a resize from narrow-open to 1280 (no `inert` left, push state as stored); AC7's wide cases. Drawer contract additions in `tests/browser/test_ui_drawer_contract.py`. Falsify the inert, focus-in, navigation-close and session-only cases.

9. **Docs.** `the_one/agents.md` (drawer factory, agent drawer, GleepGlorp drawer, App shell invariants), `docs/ui-control-inventory.md` (Drawer row; the agent drawer's Close button in the chat pane or agent drawer row), `docs/ui-testid-registry.md` (`chat-drawer-close`), the app guide.

## Edge Cases
- **Resize from 1280 (push, open) to 624:** `fill` state is `false` → the panel closes; no `inert` remains; focus that was inside moves to the visible pane (leg 1's media check).
- **Resize from 624 (fill, open) to 1280:** mode `push`, shown per the stored push state; `setCovered('chat-drawer', false)`; no focus move needed.
- **Chat closed or deleted while the panel fills:** `setActive`/`view` change → `apply()` hides it → `setCovered(false)` before focus rescue.
- **GleepGlorp turned off while its drawer fills:** `setState('off')` → `apply()` hides → `setCovered(false)` first, then `rescueFocus()`.
- **A GleepGlorp fill that navigates while covering:** `keepCovered` → stays open; the panes underneath change; `inert` stays.
- **Jump to started from inside a covering drawer** (Ctrl K with focus in it): no `keepCovered` → closes.
- **Same-route Back/Forward while covered:** router no-op, no commit → stays open (accepted).
- **Resize from narrow back to narrow** (wide in between): `state.open.fill` was reset on entering `fill` → closed.
- **GleepGlorp drawer open at 1280, window narrowed to 624:** it closes on entering `fill`; focus that was inside it returns to the corner button; no `inert` left.
- **A guarded GleepGlorp fill pending, then a rail click joins it:** the latest target wins and `keepCovered` is false → the drawer closes on commit.
- **"Open agent settings" / GleepGlorp's setup link / "Open in Chats" while covering:** the navigation closes the drawer; the scheduled focus check keeps focus off `<body>` (assert at 624×321).
- **The open chat is deleted while the agent panel fills:** the panel closes with its toggle hidden; focus goes to the visible pane, not `<body>`.
- **The leave guard during a covered state:** the modal is in `document.body`; a rail click with a dirty editor underneath (only reachable via a fill) shows the guard; Stay leaves the drawer open; Continue commits and closes it.
- **Escape inside a focused composer in the GleepGlorp drawer:** the factory's existing keydown handling (IME composition ignored).
- **Both drawers' `onOpenChange` with `applying`:** the agent panel still persists only push/overlay changes made by the user.

## Files Affected
- `the_one/interfaces/web/static/css/tokens.css` - `--rail-w`
- `the_one/interfaces/web/static/css/components.css` - `.ui-rail` width token, `.ui-drawer--fill`
- `the_one/interfaces/web/static/js/ui/drawer.js` - `fill` mode, `open(opener, {focus})`
- `the_one/interfaces/web/static/js/router.js` - `lastDecision()`
- `the_one/interfaces/web/static/js/shell-pane.js` - `setCovered`, navigation close
- `the_one/interfaces/web/static/js/areas/chat/agent-drawer.js` - fill mode, session-only state, focus-in, Close button, toggle hiding, `setCovered`
- `the_one/interfaces/web/static/js/gleepglorp-drawer/shell.js` - fill mode, `setCovered`, `rescueFocus`
- `tests/browser/test_flow_narrow_panels.py` (new), `tests/browser/test_ui_drawer_contract.py`
- `docs/ui-control-inventory.md`, `docs/ui-testid-registry.md`, `the_one/agents.md`, `the_one/gleepglorp/guide/*.md`

## Citation Audit
Checked against the working tree on 2026-11-27 (leg 1 landed, uncommitted):
- `js/ui/drawer.js` - `MODES = ['push', 'overlay']`; `open()` never moves focus; `beforeClose` before focus return; `reserveHeaderEnd` overlay-only - verified
- `css/components.css` - `.ui-rail` `width: 72px` (~:55); `.ui-drawer--overlay` (~:1891-1898) z-index 10; `.ui-drawer--overlay.ui-drawer--reserve-end` (~:1901) - verified
- `js/areas/chat/agent-drawer.js` - `STORAGE_KEY`, `PUSH_QUERY` (~:100-101); `readOpen`/`writeOpen` `{push, overlay}`; `onOpenChange` skips persistence while `applying`; toggle `onClick` flips `state.open[state.mode]` and calls `apply()`; `apply()` (~:600-612); media listener (~:614-623) - verified
- `js/gleepglorp-drawer/shell.js` - `closeBtn` `gg-drawer-close` (~:99-107); `onOpenChange` → `focusInitial` (~:136-146); `rescueFocus` (~:178-184); `apply()` sets `slot.hidden` (~:194-204); `applyMode` (~:255-258) - verified
- `js/gleepglorp-drawer/fill.js` (~:84), `chat.js` (~:137) - `App.router.go(..., {opener})` with an opener inside the drawer - verified
- `js/router.js` - `deciding.opener` set from `opts.opener` (~:809-826) - verified
- `docs/ui-control-inventory.md` - Drawer row (~:102) - verified
- `tests/browser/test_ui_drawer_contract.py` - "open() never moves focus" (~:196) - verified
- `js/shell-pane.js` - `NARROW_QUERY`, `FOCUSABLE`, `App.shellPane` (leg 1) - verified; re-check after leg 1's review fixes, if any
- `css/chat.css` `.chat-drawer-toggle` `z-index: 11` (~:69-74) - verified (leg design review)
- `css/gleepglorp-drawer.css` ~:8 `#gleepglorp-drawer { width: 360px }` in `@layer areas` - verified (leg design review)
- `js/jump-to.js` (~:276-298) uses the element focused at Ctrl K as the opener - verified (leg design review)
- `js/ui/drawer.js::close` order: `beforeClose` → opener focus → hide → `onOpenChange` - verified (leg design review)
- `tests/browser/test_ui_drawer_contract.py` ~:104 pins the returned keys; ~:146 the unknown-mode error; modes looped explicitly as `('push','overlay')` - verified (leg design review)

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
