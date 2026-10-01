# Leg: unified-leave-guard

**Status**: completed
**Flight**: [Shell and Router](../flight.md)

## Objective

Replace the interim, per-area guard with one leave guard, `App.nav`. It covers:
- per-area dirty sources with a teardown "discard";
- a thin router adapter that keeps today's synchronous fast path;
- one `beforeunload`;
- a bubble-phase in-app link interceptor;
- explicit focus rules after Stay and Continue;
- removal of every per-area gate copy.

`App.confirmDialog` gains an `opener` option and drops its single-open policy, keeping
an open-count so `isOpen()` still reports correctly.

## Context

- **Flight decision:** DD5 is this leg's spec, with DD6's singleton deferral. Read both
  in `flight.md`. The design review (2026-10-01) checked this leg against the code as
  left by legs 1–4; the names below are the real ones.
- **The router hook today** is `runGuard()` in `router.js` (~L378-390). It calls
  `area.confirmLeave(proceed, abort)` and resolves **Stay** when `dialogOpen()` (~L324)
  is true, with a defensive Stay after the call. It already has single-flight and join
  semantics through `deciding`: `go()` joins and the latest target wins; traversals
  retarget `deciding.target`. The callbacks are synchronous, so a `go()` with no dirty
  source commits in the same tick. **Keep that fast path.**
- **Area hooks:**
  - `_confirmLeaveImpl` is at `admin.js:~678` and `studio.js:~3074`.
  - The area `confirmLeave` descriptors are at `admin.js:~830` and `studio.js:~3142`.
  - `beforeunload` listeners are at `admin.js:~236` and `studio.js:~356`.
  - `isDirty` predicates to port:
    - admin `inEditor` (~L679): `providers` with `providerFormMode`, `tools` with
      `toolFormMode`, or `currentCategory==='knowledge'`;
    - studio (~L3075-3088): `agents` with a selection or `_createMode`;
      `mcpSourceFormMode`; `connectorFormMode`; `knowledge` with `_selectedKbId`.
- **The remaining inline `App.confirmDialog` gates** are exactly two. There is **no**
  connector-open gate.
  - the **connector editor `onBack`** (`studio.js:~999`);
  - **agent `enterCreateMode`** (`studio.js:~1962`).

  Admin has none left: its provider `enterCreateMode` became a `go()` in leg 4.
- **Teardown helpers to reuse:**
  - studio `closeOpenItem()` (~L1092) clears the agent selection, `_createMode`, the
    MCP and connector form modes, the KB id and poll, the MCP focus and `dirty`, and
    empties `editorEl`;
  - admin `_closeOpenItem` (~L765) is state-only: it resets provider and tool state and
    `dirty`.
- **`href="#…"` producers** after leg 4: `markdown.js:~746` (`safeHref` → `#`, a
  fragment, or an agent-authored route such as `#settings/providers`) and the skip link
  (`index.html:23`). The interim top-bar buttons (`app.js:~30`) call `go()` directly
  and are not anchors. The leg 6 rail will be `<a>` links through this interceptor.
- **Load order:** `dialog.js` loads after `router.js`, so `nav.js` looks up
  `App.confirmDialog` and `App.ui` **lazily**. `confirmLeave` must be callable before
  `router.start` without throwing.

## Inputs

- `static/js/router.js` (`runGuard`, `dialogOpen`, `deciding`, `resolve`, the header
  comment ~L43-46 about null-state arrivals), `app.js`, `dialog.js` (adapter; `open`
  var; comment ~L50-52), `ui/modal.js` (comment ~L32), `areas/studio.js`,
  `areas/admin.js`, `areas/studio/knowledge-section.js` (~L480 stale comment),
  `markdown.js`.
- Tests that reference the hooks: `test_router_guard.py`, `test_router_core.py`,
  `test_flow_cross_area_dirty_gate.py`, `test_flow_dirty_confirm.py` (the singleton
  test at ~L511, the synthetic `beforeunload` tests at ~L468-510), and the provider
  equivalents.

## Outputs

- **`static/js/nav.js`** (new, loaded right after `router.js`). It provides:
  - `App.nav.registerSource(areaId, {isDirty, discard})`;
  - `App.nav.isDirty()`;
  - `App.nav.isPending()`;
  - `App.nav.confirmLeave(ctx) → Promise<boolean>`;
  - `App.nav._sources()`, a read-only view for tests;
  - one `beforeunload` listener;
  - the link interceptor.
- **Router adapter.** `runGuard()` keeps the synchronous fast path, sketched below. The
  sketch shows the intent, not the final code. `settle` is the router's existing
  resolver; `ctx` is the context object this leg defines.

  ```
  var d = deciding;
  if (!App.nav.isDirty()) { settle(true); return; }
  if (App.nav.isPending() || dialogOpen()) { settle(false); return; }
  App.nav.confirmLeave(ctx).then(function (ok) { if (deciding === d) settle(ok); });
  ```

  The router's own `deciding` join stays the only join layer for router navigations.
  `App.nav`'s single-flight joins **only repeated calls from the same non-router
  caller**. A router navigation that arrives while a non-router `App.nav` dialog is
  pending resolves **Stay** (`isPending()`); it never joins, which would make Continue
  run both actions.
- **Sources.** Studio and admin each register one source.
  - `isDirty = dirty && editorOpen()`, using the ported predicates.
  - Studio `discard()` = `closeOpenItem()`, plus emptying `sectionContentEl` for
    non-agent editors (MCP, connector, KB), so no stale editor DOM lingers.
  - Admin `discard()` = `_closeOpenItem()`.
    - On the knowledge settings page, discard is `dirty = false`. Re-entry re-renders
      from saved settings, because the hydrate branch checks `!dirty`.
  - Discard **bumps a per-area generation**. An in-flight save that resolves after a
    discard (e.g. provider `onSaveSuccess`) checks the generation and does not resurrect
    the editor state.
- **Removed:**
  - both `_confirmLeaveImpl`;
  - both area `confirmLeave` descriptors;
  - both per-area `beforeunload` listeners;
  - both remaining inline gates, which become
    `App.nav.confirmLeave(ctx).then(function (ok) { if (ok) doX(); })`.

  After this leg, `App.confirmDialog(` is called only from `nav.js` and the
  design-language demo (`ui-modal-section.js`).
- **Bypass paths.** `discard()` is added only on the **vanish and bounce** paths, where
  an editor for a dead item may be open: the KB-poll 404, the save→delete race, and
  post-delete.
  - **Exempt:** post-save bypass (e.g. `replaceWithAgent_` after create). It lands on
    the same item, and save already clears `dirty`; a discard would empty the editor and
    lose the "Saved" flash.
  - Root-route hydrates already tear down.
- **`dialog.js`:**
  - `opts.opener` is passed to `modal.open(opts.opener || computed)`.
  - The single `open` var is replaced by an **open-count or stack**, so `isOpen()` stays
    true while any confirm is open, and closing the top one doesn't clear the one
    beneath.
  - The header comment and `modal.js:~32` comment are updated.
- **Link interceptor** (bubble phase, on `document`). It handles
  `e.target.closest('a[href^="#"]')`, which also matches anchors containing child
  nodes, and reads `getAttribute('href')` rather than `.href`.
  - It **skips** modifier clicks, a non-primary button, `target`, `download` and
    `defaultPrevented`.
  - It resolves the href through `App.router.resolve`:
    - **route:** `preventDefault()`, then `go(route, {opener: anchor})`. A same-route
      click is a replace, per the router's same-route rule.
    - **element** (`#main-content`): native behaviour.
    - **unknown, empty or bare `#`:** `preventDefault()`, with no history entry.
  - Before `router.start`, it still calls `preventDefault()` on routes.
- **Interim top bar** (`app.js`): it passes the clicked button as the opener in the
  guard context.
- **Stale text updated:** `router.js`'s header comment and its null-state revert branch
  (after this leg, only typed URLs produce null-state arrivals), the studio deactivate
  comment (~L3150), and `knowledge-section.js:~480`.
- **Docs:** `agents.md` gets a "Leave guard (`App.nav`)" section covering:
  - sources and the `isDirty` predicates;
  - discard as **teardown only**, never a URL write, with the generation bump;
  - the **synchronous fast path**, which must not be promisified;
  - join-vs-Stay for non-router callers;
  - the paths, the link-interception rules and focus;
  - the desktop scope note.

  CLAUDE.md gets a one-line pointer.
- **Flight log:** the leg entry.

## Acceptance Criteria

- [x] **AC1 — `App.nav`.**
  - `registerSource` replaces on re-registration. `isDirty()` is true if any source
    reports dirty. `isPending()` is true while a non-router decision is pending.
  - `confirmLeave(ctx)`:
    - resolves `true` with no dialog when nothing is dirty;
    - otherwise opens one `App.confirmDialog({opener: ctx.opener, …})`: "Unsaved
      changes", Stay / Continue, Stay focused;
    - Continue calls `discard()` on each dirty source in try/catch, so a throwing
      discard still navigates and still resets `dirty`, then resolves `true`;
    - Stay resolves `false`;
    - repeated calls from the same non-router caller while pending get the same
      promise.
  - ES5, shell placement, and callable before the router starts.
- [x] **AC2 — Router adapter.**
  - `runGuard()` is implemented as in Outputs, with the **sync fast path preserved**.
    The `test_router_core` commit-sequence tests stay green unchanged, which proves no
    microtask delay was added when clean.
  - A grep shows `_confirmLeaveImpl` and the area `confirmLeave` descriptors are gone.
  - A test shows a rail-equivalent `go()`, issued while the `enterCreateMode`
    `App.nav` dialog is pending, resolves Stay and does **not** join.
- [x] **AC3 — Paths** (each with a test: dirty → exactly one dialog; Stay keeps the
  editor and the URL; Continue lands on the target):
  1. top-bar `go()` (the rail is leg 6);
  2. section nav;
  3. an in-app link. The named legacy example is a `#studio/mcp-sources` href in
     content: it redirects, and is guarded;
  4. item selection;
  5. editor Back (create-mode Cancel stays unguarded, as leg 4 already tested; it
     remains tested);
  6. browser Back/Forward and a typed URL;
  7. `beforeunload` (recipe below);
  8. **connector Back** and **agent `enterCreateMode`**, now through `App.nav`.
- [x] **AC4 — Discard is real.** After Continue, the editor is torn down and
  `App.nav.isDirty()` is false. Re-opening the item shows the **saved** value, from the
  cache on an intent `go()` or from the server on a traversal or typed URL. Test:
  - the agent editor, the provider editor, KB detail and the knowledge settings page;
  - each by a **traversal** (Back) and by an **intent** `go()`;
  - one case that checks the cached object is not mutated by form edits (e.g. the
    agent's `_selectedAgent` identity across tab switches).
- [x] **AC5 — Link interceptor.** Each rule is tested:
  - a recognised route uses `go()` with the anchor as the opener, including an anchor
    with an icon child;
  - modifier, middle-button, `target` and `download` clicks are not intercepted;
  - `#main-content` stays native;
  - a chat message containing `[x](#)` and `[x](#installation)`: clicking each leaves
    `location.hash` and `history.length` unchanged;
  - an agent-authored route link (`#settings/providers`) in a message navigates under
    the guard.
- [x] **AC6 — Focus.**
  - **Stay:** focus returns to the opener. The order is an explicit opener (the anchor
    for links, the button for the top bar), else the active element if it isn't
    `body`, else `#main-content`.
  - **Continue:** `#main-content.focus()` runs **after** the commit, i.e. after the
    modal has restored focus to the opener and called `onClose`.
  - Tested for a top-bar click, a link click (in WebKit too, where a mouse click doesn't
    focus a link) and browser Back.
- [x] **AC7 — Confirm stacking and the adapter.**
  - `App.confirmDialog` accepts `opener`.
  - It uses an open-count or stack: with two stacked confirms, `isOpen()` stays true
    after the top one closes and false after both close.
  - `test_singleton_modal_second_call_warns` (~L511) is renamed and inverted to
    `test_second_confirm_stacks_above_first`, using a synthetic double call. Production
    code never stacks two.
  - A grep finds `App.confirmDialog(` only in `nav.js` and `ui-modal-section.js`.
- [x] **AC8 — No phantom prompts.**
  - After each of save, delete, Continue, a create-form Cancel and a background bounce,
    `App.nav.isDirty()` is false, and the next navigation shows no dialog and no
    `beforeunload`. Tested for the agent editor, an MCP source and a provider, each for
    save **and** delete.
  - A stale `dirty` flag with no editor open (set it directly through the test seam)
    triggers neither the guard nor `beforeunload`.
  - Discard during an in-flight provider save, followed by the save resolving: the
    editor is **not** resurrected.
- [x] **AC9 — `beforeunload`.** The single `nav.js` listener calls `isDirty()` inside
  try/catch. Test recipe (Chromium only; WebKit gives no equivalent guarantee):
  1. dirty the editor with **real** input (`fill` + `press`, or a click; a user gesture
     is required);
  2. register `page.on('dialog', lambda d: (seen.append(d.type), d.accept()))`;
  3. call `page.reload()`;
  4. assert `seen == ['beforeunload']`.

  For the clean case, click something, then reload, and assert `seen == []`. The
  existing synthetic-event tests are re-pointed at the `nav.js` listener.
- [x] **AC10 — Docs.** `agents.md` gets the "Leave guard" section, including the sync
  fast path, join-vs-Stay, teardown-only discard and the generation bump. CLAUDE.md gets
  the pointer. The stale comments listed in Outputs are updated.
- [x] **AC11 — Gates pass.**
  - `make lint`;
  - `make test-unit`;
  - all five lanes, one at a time;
  - every `test_ui_*` plus `test_router_*` in both engines with `THE_ONE_REQUIRE_WEBKIT=1`.

  Keep the new test count proportionate: about 25–30 tests.

## Verification Steps

- AC1–AC9: `PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser tests/browser/test_nav_guard*.py tests/browser/test_router_guard.py tests/browser/test_flow_dirty_confirm.py tests/browser/test_flow_provider_dirty_confirm.py tests/browser/test_flow_cross_area_dirty_gate.py -x -rA`.
  Then grep for `_confirmLeaveImpl`, `confirmLeave:`, `beforeunload` (expected only in
  `nav.js`) and `App.confirmDialog(` (expected only in `nav.js` and
  `ui-modal-section.js`).
- AC10–AC11: a doc read and the gates.

## Implementation Guidance

1. **`nav.js`**: sources, `isPending`, single-flight, `beforeunload`, `_sources`. Add
   its script tag and the count bump.
2. **Register the studio and admin sources**: write `editorOpen()` from the ported
   predicates, and `discard()` from `closeOpenItem` and `_closeOpenItem`, plus the
   `sectionContentEl` clear and the generation bump. Guard `onSaveSuccess`-style
   resolvers with the generation.
3. **Router adapter** (sync fast path). Remove both `_confirmLeaveImpl`, both area
   descriptors and both `beforeunload` listeners. Re-point the tests that referenced
   them.
4. **The two inline gates** go through `App.nav`.
5. **Bypass vanish and bounce paths** call `discard()`.
6. **`dialog.js`**: `opener`, open-count, comments. Then the singleton inversion.
7. **Link interceptor.** Pass the top-bar opener.
8. **Tests, docs, gates.**

## Edge Cases

- **A throwing `discard()` on Continue:** navigate anyway and reset `dirty` (AC1).
- **`beforeunload` while a leave dialog is open:** the native prompt wins. This is
  accepted and documented.
- **Chat** registers no source; the composer draft is not "unsaved work" in this
  flight.
- **Discard during an in-flight save:** the generation guard prevents resurrection
  (AC8).
- **Interceptor before `router.start`:** routes are `preventDefault`ed and `go()`
  returns false. Nothing navigates during boot.

## Files Affected

- `static/js/nav.js` (new), `router.js`, `app.js`, `dialog.js`, `ui/modal.js` (comment),
  `areas/studio.js`, `areas/admin.js`, `areas/studio/knowledge-section.js` (comment)
- `index.html`, `tests/test_index_asset_cache_busting.py` (computed from the tree)
- `tests/browser/test_nav_guard*.py` (new), plus the re-pointed `test_router_guard.py`,
  `test_router_core.py`, `test_flow_dirty_confirm.py`,
  `test_flow_provider_dirty_confirm.py` and `test_flow_cross_area_dirty_gate.py`
- `the_one/agents.md`, `CLAUDE.md`
- `missions/25-workbench-navigation/flights/02-shell-and-router/flight-log.md`

## Citation Audit

Real names and lines from the design review against the leg-4 tree:
- `router.js` `runGuard` ~L378, `dialogOpen` ~L324, `deciding`, `resolve` (~L288 uses
  `getElementById` for element ids);
- `_confirmLeaveImpl` admin ~L678 and studio ~L3074; descriptors admin ~L830 and
  studio ~L3142;
- `beforeunload` admin ~L236 and studio ~L356;
- inline gates studio ~L999 (connector Back) and ~L1962 (agent `enterCreateMode`);
- `closeOpenItem` studio ~L1092; `_closeOpenItem` admin ~L765;
- `dialog.js` opener at ~L65;
- `markdown.js` `safeHref` ~L746;
- the `index.html:23` skip link and `:28` `main tabindex=-1`.

Re-check after the leg 4 follow-up lands.

Design review (Developer, 2026-10-01) — "approve with changes". Applied:
- the router adapter keeps the sync fast path, with no second join layer;
- non-router pending → Stay;
- the inline gates corrected (connector **Back** and agent `enterCreateMode`);
- the `App.confirmDialog` `opener` option and focus ordering;
- the discard specifics (studio section clear; admin knowledge page; generation guard
  against in-flight saves);
- discard on vanish and bounce bypass paths only;
- AC4 reworded (saved value from cache or server, traversal and intent);
- the dialog open-count mechanics;
- interceptor details and producers;
- the `beforeunload` recipe verified in Chromium headless;
- real citation names;
- AC wording fixes.

---

## Post-Completion

Completion steps — status transitions, flight-log update, checking off in the parent
flight, and commit — are Flight Control protocol, driven by the execution workflow. Not
repeated here.
