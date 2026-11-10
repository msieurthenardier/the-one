# Leg: widget-lifecycle

**Status**: completed
**Flight**: [Live Visuals](../flight.md)

## Objective
Add the module-level manager that decides, for every widget card on the page, whether it is loaded, running, auto-paused, waiting or stopped. It covers:
- run in view, pause off screen;
- at most 3 running and 8 loaded;
- pause on `document.hidden`;
- start paused under reduced motion;
- the DD9 hang guard: a per-page crash record, stall detection and heartbeat loss.

Everything sits on leg 4's card API, with Chromium + WebKit contract tests.

## Context
- **Flight DDs:** DD7 (lifecycle, as amended: no `stopped-focus`) and DD9 (hang guard; WebView2 157 measured responsive, WebKitGTK frozen; the suspend measurement was skipped, so the default rule treats a gap over 60 s as a suspend).
- **Leg 3 design review findings this leg adopts** (flight log, Flight Director Notes):
  - **A pure, idempotent decision function.** `reconcile(facts) -> {desired state per instance, unload set}`. The facts per instance are `inView`, `userPaused`, `stopped`, `loaded`, `startOrder`, `lastVisibleAt`, `loadedAt`, plus the global `hidden`. Every event (an `IntersectionObserver` callback, `visibilitychange`, Start, destroy, the tick) only updates facts and calls `reconcile()`. That removes the observer, cap, ceiling and visibility races.
  - **`destroy` during a pending observer callback is a no-op** for that instance.
  - **"In view":** `IntersectionObserver` with thresholds `[0, 0.05, 0.1, …, 1]` (21 steps), so a callback fires as the visible part changes. An instance is in view when `intersectionRatio >= 0.25`, **or** when `intersectionRect.height >= 0.5 * rootBounds.height` (a 720 px card in a short viewport, such as the drawer's overlay mode). Leg 5's design review found that `[0, 0.25]` alone fires only on crossings, so the half-root rule would never fire. A test uses a short (300 px) viewport with a tall card.
  - **The manager's lifetime counts cards, not loaded frames.** `waiting` cards own no frame but still need the observer.
  - **The crash record carries `hidden`.** Staleness is trusted only when the record was written while visible; otherwise the threshold is at least 90 s (Chromium throttles hidden timers to about once a minute).
  - **Test seams:** `App.ui.widget._clock` (an injectable `now()`) and `App.ui.widget._tick()` (runs one page tick synchronously). A heartbeat-loss test advances the clock 4.9 s, ticks, advances 4.9 s and ticks again in one synchronous `evaluate`: each stall gap stays under 5 s, so only heartbeat age trips. A real runaway test (`setTimeout(()=>{for(;;);},100)`) runs in **full Chromium only** (`channel="chromium"`), whose page stays responsive; WebKit gets the clock and seeded-record tests, because a runaway freezes its page.
- **Leg 4** gives every card: `state()`, `start()`, `pause()`/`resume()` (the operator's), `autoPause()`/`autoResume()`, `unload()`, `stop(kind)`, `restart()`, `destroy()`, `onHeartbeat` wiring, and `App.ui.widget.sweep()`. **Re-check the exact names once leg 4 lands.**

## Inputs
- Leg 4's `js/ui/widget.js` and its contract tests; leg 3a's `widget-frame.js` (`paused` option, heartbeat on captured timers).
- `scripts/run-tests.sh` `contracts-widget` lane (provisional 300 s budget; leg 3a measured 186 s).

## Outputs
- **The manager:** `js/ui/widget-lifecycle.js` (or inside `widget.js` if it stays under 800 lines). It owns:
  - one registry in document order;
  - one `IntersectionObserver`;
  - one page tick (1 s);
  - one `visibilitychange` listener (on `document`, a named handler, removed with the last card);
  - one `pagehide` listener (on `window`);
  - `reconcile(facts)` exposed as `App.ui.util.widgetReconcile` for unit-style contract tests;
  - the crash record;
  - the hang checks.
  
  All of it is installed with the first card and released with the last.
- **Cards register with the manager** at construction and deregister on destroy or sweep. Leg 4's mount-at-construction policy is replaced for **managed** cards: a card starts `waiting` and the manager decides.
- **Card changes in `widget.js`** (design review, high):
  - **The `managed` option** (default `true`). `managed:false` keeps leg 4's behaviour exactly (mount at construction, controls act directly, no registration). Leg 4's `tests/browser/test_ui_widget_card_contract.py` passes `managed:false` in its one `_setup`/`__make` helper: **the single permitted edit to that file**, recorded in the flight log.
  - **An internal event hook to the manager:** the card reports `pause`, `resume`, `restart`, `start` (the cap card's Start and "Start anyway"), `stop`, `escape`, `beat` and `destroy`. For managed cards, **Restart and Start/Start anyway go through the manager**, which applies the cap and the hidden and in-view rules; Pause/Resume set `userPaused`. No control mounts a frame behind the manager's back.
  - **`onHeartbeat`** is wired in `mountFrame`, so each beat is stamped with `_clock()`. The heartbeat baseline is set at the frame's first `load`, not at mount, so a slow first load is not a hang.
  - **`markSeen`** also runs when the manager registers a connected card and on every observer callback, so `sweep()` reaps waiting cards.
  - **`prefers-reduced-motion`** is read once, at card construction (`matchMedia`).
  - **The cap card render (DD7, board 3):** an in-view `waiting` card that cannot run because of the cap shows the body "Paused: three widgets are already running." with a **Start** button. That reuses the `{t}-start` testid with the label "Start"; "Start anyway" keeps that label for stopped states. An off-screen `waiting` card shows the header over an empty body at the slot height. New classes are owned by the `widget` row; CSS goes in `components.css`.
- **Test seams:** `App.ui.widget._clock`, `App.ui.widget._tick()` and `App.ui.widget._counts()` (observers, tick, listeners, registered cards), each documented as test-only.
- **A new lane, `contracts-widget-lifecycle`:** an explicit list, `test_ui_widget_lifecycle*` and `test_ui_widget_hang*`. These are excluded from `contracts_widget_pat` (which becomes the explicit `test_ui_widget_frame*` and `test_ui_widget_card*`). Update the budget table (provisional 300 s), the `contracts` alias, `--help`, `tests/test_run_tests_lanes.py` and CLAUDE.md, as leg 3a did.
- **Contract tests:** `tests/browser/test_ui_widget_lifecycle_contract.py` (lifecycle, both engines) and `tests/browser/test_ui_widget_hang_contract.py` (the hang guard; the real runaway case Chromium-only).
- **Catalogue:** the `widget` row documents the lifecycle, the seams and the limits (3/8/5 s/60 s/10 s/90 s).

## Acceptance Criteria
- [ ] **AC1 — `reconcile` is pure and covers DD7.** Given facts, it returns the desired state per instance and the set to unload:
  - in-view, not stopped, not `userPaused`, under the cap → `running`;
  - in-view, but the cap is reached → stays `waiting` if not loaded (cap card "Paused: three widgets are already running." with Start), or `paused-auto` if loaded;
  - out of view and loaded → `paused-auto`;
  - `userPaused` → `paused-user` whether in view or not;
  - `stopped` → unchanged;
  - `hidden` → every loaded instance is `paused-auto` (running none);
  - **fill order:** in-view instances top to bottom, `paused-auto` resumes before `waiting` starts;
  - **ceiling 8:** when more than 8 would be loaded, unload the `paused-auto` off-screen one with the oldest `lastVisibleAt`, then off-screen `paused-user` by oldest `lastVisibleAt`; if none is off screen, the new instance stays `waiting`;
  - **Start on a capped card:** marks that card start-requested, which outranks the oldest-started `running` card. That card goes `paused-auto` (in view), and the requested one runs.
  - **Reduced motion and `paused-user`:** an in-view, unloaded `paused-user` card **loads** (its frame mounts paused, and one rAF round draws its first frame). Loaded `paused-user` cards do **not** count against the running cap of 3; they **do** count against the loaded ceiling of 8.
  - **Restart and Start anyway** on a managed card become start requests, subject to the cap. A `stopped` card's Start anyway clears `stopped` and makes a start request.
  
  Table-driven tests call `App.ui.util.widgetReconcile` directly in the page, with at least 12 cases, including every rule above. **Falsified:** with the cap check removed, the cap case fails.
- [ ] **AC2 — Live lifecycle, both engines.** In a tall harness page with real scrolling:
  - 4 small widgets in view → 3 running and 1 cap card;
  - scroll one running widget out → it is `paused-auto` with its in-frame counter frozen, and the capped one starts;
  - scroll back → it resumes from where it was (the counter continues, no restart);
  - 9 widgets loaded by scrolling through → exactly one is unloaded, the oldest-visible `paused-auto`, and it restarts from 0 when scrolled back;
  - a `paused-user` widget stays paused across scrolling;
  - hidden → all paused, visible → in-view ones resume. Emulate with `Object.defineProperty(document, 'hidden', {get: …})` plus `visibilityState`, and a dispatched `visibilitychange`; restore with `delete`. The review probe showed this identical in all three engines; a second page brought to front does **not** hide the first. Use `add_init_script` for hidden-at-load;
  - a short viewport (300 px) with a 720 px card counts it in view by the half-root rule;
  - destroying a card inside an observer callback batch is a no-op for that card;
  - reduced motion (`page.emulate_media(reduced_motion='reduce')` before load) → widgets mount `paused-user`, the first rAF frame is drawn (an in-frame flag), and Resume runs them.
- [ ] **AC3 — Hang guard** (DD9 with the review's amendments):
  - **Crash record:**
    - `localStorage["widget-running:{pageId}"] = {keys, ts, hidden}` while any card is loaded, rewritten each tick and cleared on `pagehide`;
    - at load, a foreign record is stale when `ts` is older than 10 s and `hidden` was false, or older than 90 s when `hidden` was true;
    - stale → its keys go into an **in-memory stale-key set kept for the page's lifetime**, and the record is deleted from storage. Every card that registers with a key in the set comes up `stopped-hung` with `stop('hung-last')`, including cards created later by a history render. A key is consumed (removed from the set) when its card's Start anyway is used. A fresh record is ignored;
    - **Residual (documented):** a healthy background tab that Chromium throttles or freezes for more than 90 s leaves a record a new tab reads as stale. Its widgets then show "stopped responding last time" once;
    - every storage access is in try/catch.
  - **Stall:**
    - a `performance.now()` (via `_clock`) gap of at least 5 s and at most 60 s between ticks → every loaded card `stop('hung')`;
    - a gap over 60 s → treated as a suspend (reset, stop nothing);
    - suspended while `document.hidden`;
    - on visible, the tick and every heartbeat are reset.
  - **Heartbeat:** a loaded card (running **or** paused) with no heartbeat for 5 s while the page ticks → `stop('hung')`.
  - **Tests, both engines:**
    - the clock-driven stall (5 s, then 61 s);
    - heartbeat loss via `_clock` + `_tick`;
    - seeded fresh, stale-visible, stale-hidden-at-60 s (not stale) and stale-hidden-at-91 s records;
    - `pagehide` clearing the record;
    - hidden suspending the checks.
    
    **Full Chromium only:** a real runaway widget is stopped within about 7 s while the page keeps ticking.
    - The test launches its **own** browser with `playwright.chromium.launch(channel="chromium")`. It does not use the `engine_page` fixture: that fixture's Chromium is the headless shell, which wedges the whole page on an iframe `for(;;)` (leg 5 review probe).
    - It skips explicitly when that channel cannot launch, and asserts the launched channel before running the widget.
    - It is never parametrized onto WebKit or the shell.
  - **Falsified:** without the `hidden` rule, the stale-hidden-at-60 s case fails; without the heartbeat check, the runaway case fails.
- [ ] **AC4 — Keys.** The card's `key` option identifies it in the crash record. Two cards with the same key are both stopped by a matching record (documented). Tests use explicit keys; leg 6 supplies real ones.
- [ ] **AC5 — Teardown.** The manager releases the observer, the tick and the listeners when the last card is destroyed or swept. Test through `_counts()`: after `sweep()` of all cards, there are 0 observers, no tick and 0 listeners. The `document` listener passes the paired-listener guard.
- [ ] **AC6 — Library rules and budget.**
  - All guards pass: `test_ui_library_source`, `test_ui_guards`, inventory, ownership, emitted classes, tokens, lanes; `ruff` clean.
  - `contracts-widget` time is recorded. If it exceeds about 300 s, split heavy files and record it; budgets are re-measured at the closing gate.

## Verification Steps
- **Browser:** `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane contracts-widget -x`.
- **Unit and static:** the guard set, then `THE_ONE_TEST_NETNS=1 make test-unit`.
- **Falsifications:** AC1 (the cap), AC3 (the `hidden` rule; the heartbeat). Each is restored by editing.

## Implementation Guidance
1. **Write `reconcile` first, as a pure function over plain objects,** and test it table-driven before wiring events.
2. **Events only update facts:**
   - the observer (`inView`, `lastVisibleAt`);
   - `visibilitychange` (`hidden`);
   - Start/Resume/Pause/Restart from the card (`userPaused`, `startRequested`);
   - the tick (the hang checks);
   - destroy.
   
   Each then calls `apply(reconcile(facts))`. `apply` diffs desired against current and calls the card API (`start`, `autoPause`, `autoResume`, `unload`).
3. **The clock:** one `now()` (the `_clock` seam defaults to `performance.now`); store `lastTickAt` and the per-card `lastBeatAt`.
4. **`pageId`:** a random hex string per module load. The record write is `JSON.stringify`, guarded.
5. **Never touch focus, and never install `document` listeners other than the paired `visibilitychange`.**

## Edge Cases
- **A card created while `hidden`:** it waits until visible.
- **A card that is `stopped-*` and then scrolled:** it stays stopped. Start anyway clears `stopped`, and it runs if allowed.
- **`destroy()` inside an observer callback batch:** skip it.
- **A widget whose frame escapes (leg 4's `stopped-escape`):** it frees its running slot, and the manager reconciles.
- **Reduced motion toggled at runtime:** applies at the next mount only.
- **Two tabs:** records are per page id, and fresh foreign records are ignored.

## Files Affected
- `the_one/interfaces/web/static/js/ui/widget-lifecycle.js` - new, or folded into `widget.js`
- `the_one/interfaces/web/static/js/ui/widget.js` - registration; leg 4's mount policy replaced
- `the_one/interfaces/web/static/index.html` - script order
- `tests/browser/test_ui_widget_lifecycle_contract.py`, `tests/browser/test_ui_widget_hang_contract.py` - new
- `tests/browser/test_ui_widget_card_contract.py` - only its make helper passes `managed:false` (record it)
- `the_one/interfaces/web/static/css/components.css` - the cap card body
- `scripts/run-tests.sh`, `tests/test_run_tests_lanes.py`, `CLAUDE.md` - the `contracts-widget-lifecycle` lane
- `docs/ui-testid-registry.md` - only if new testids are emitted
- `docs/ui-control-inventory.md`
- `missions/35-rich-visuals-in-chat/flights/02-live-visuals/flight-log.md`

## Citation Audit
- Leg 4's card API (`js/ui/widget.js`, 341 lines): `state()`, `start`, `pause`, `resume`, `autoPause`, `autoResume`, `restart`, `unload`, `stop(kind)`, idempotent `destroy`; statics `sweep()`, `_instances()`; `App.ui.widgetFrame._has(win)` - verified from the leg 4 report (re-read the file at leg start)
- **Leg 4 finding:** moving (re-parenting) an iframe reloads it, and the frame core counts a reload as an escape. The manager must `unload()` + `start()` and never move a mounted frame - verified (leg 4)
- **Leg 4 finding:** the card emits no testids without an `opts.testid` (the `js/ui` testid guard form) - noted
- `tests/test_ui_guards.py` paired `document` listener guard (`:800`) - verified
- The leg 3 design review's lifecycle and hang-guard findings - recorded in the flight log, Flight Director Notes - verified
