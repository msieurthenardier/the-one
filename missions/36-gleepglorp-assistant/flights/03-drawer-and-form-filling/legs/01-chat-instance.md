# Leg: chat-instance

**Status**: completed
**Flight**: [The GleepGlorp drawer and form filling](../flight.md)

## Objective
Lift the Chats area's body into a factory, `App.chat.create(config)`, that
the app can call twice. The Chats area becomes its first caller (the "Chats
profile") with no change in behaviour, so Leg 3 can create the drawer's
instance from the same code.

## Context
- **Flight DD2:** a factory with two profiles, not a lighter second client.
  This leg builds the factory and the Chats profile only. The drawer profile
  is Leg 3.
- **Flight DD3 is not this leg.** The window-frame split and the drawer
  socket are Leg 3. The socket's behaviour is unchanged here.
- **Today**, `the_one/interfaces/web/static/js/areas/chat.js` (629 lines) is
  an `App.registerArea({id:'chat'})` descriptor whose `init(sidebar, content)`
  does everything:
  - builds a closure `state`, `chatState = App.chat.createSessionState()` and
    `ctx`;
  - creates the Chats list, the pane, the composer, the health banner, the
    agent drawer (on `#chat-drawer`), the telemetry and the copy status node;
  - defines `renderPane`, `renderChatsList`, `showWelcome`, `showChrome`,
    `computeBlocked`, `applyComposerState`, `refreshAgentsAndSetup`,
    `setSessionHealth` and `stopTurn`;
  - creates the ten per-turn modules, leaves first (`chat.js` ~:524-533);
  - sets the test seams on the descriptor (~:563-612);
  - registers the picker host and subscribes to the stores, `App.time` and
    `App.gleepglorp`.
- **The ten per-turn modules are already `App.chat.X.create(ctx)`
  factories:** holdQueue, attachments, transcript, turnWork, send,
  proposalCards, signIn, turnFrames, sessionFlow and socket. They reach
  everything through `ctx`.
- **The Chats-only couplings in those modules:**
  - `App.router.sync('chat', …)` at `session-flow.js` ~:200 and ~:323, and
    `socket.js` ~:224;
  - `App.router.go` to `#chats/~new/{agent}` in `session-flow.js::goPick`
    (~:107-113);
  - `ctx.renderChatsList()` (session-flow, socket);
  - `ctx.agentDrawer` (socket ~:20, turn-frames ~:16);
  - `ctx.signIn` (socket ~:397, turn-frames ~:124-126).
- **Flight 2 debrief lesson:** a short code survey before the spec (done:
  the planning survey plus this leg's reads).

## Inputs
- `main` at `3aa9ea94` plus the uncommitted Flight 3 planning artifacts on
  `flight/03-drawer-and-form-filling`.
- `the_one/interfaces/web/static/js/areas/chat.js` and `areas/chat/*.js` as
  of that commit.

## Outputs
- **New** `static/js/areas/chat/instance.js`: `App.chat.create(config)`, the
  lifted body (state, ctx, module wiring, `stopTurn`, the subscriptions and
  the returned instance).
- **New** `static/js/areas/chat/instance-render.js`: the pane and list
  renders and the composer state (`renderPane`, `renderChatsList`,
  `renderWelcome`/`showWelcome`/`showChrome`, `computeBlocked`,
  `applyComposerState`, `refreshAgentsAndSetup`, `setSessionHealth`), created
  from `ctx` like the other modules. Each new file stays at or under about 500
  lines.
- **`chat.js`** is the descriptor only: it builds the Chats profile config,
  calls `App.chat.create`, and keeps every `_*` seam and `activate`/
  `deactivate` behaviour. It should be well under 200 lines.
- **Router adapter.** `ctx.router` replaces direct router calls in the chat
  modules and the lifted body:
  - `ctx.router.sync(sub)`;
  - `ctx.router.goNew(agent, opts)`;
  - `ctx.router.go(href, opts)`.

  The Chats profile's adapter calls `App.router` with exactly today's
  arguments.
- **Picker hooks.** `config.picker` is `{open(opener)}`. The Chats profile
  passes `App.chat.openPicker`. It drives the pane's New chat and Pick a
  different agent buttons and the list's New chat. With no `config.picker`,
  those buttons do nothing.
- **CSS scope.** In `css/chat.css`, `.area-chat` becomes `.chat-instance`,
  a mechanical rename. Every one of its 57 rules styles content (the chrome,
  header, new-chat, welcome, proposals, messages and queued regions), and
  specificity is unchanged at one class. The three `components.css` hits are
  comments; update their wording. The Chats content panel carries both
  `area-chat` and `chat-instance`.
- **The handle** exposes `root` (the instance's content element) for Leg 3.
- **Not in this leg:** scoping `_chats.py`'s page-wide locators. It moves to
  Leg 3, where a second chat is actually in the DOM. Here the second instance
  is detached, so no page-wide locator can match it.
- **`index.html`** loads `instance-render.js` and `instance.js` after
  `socket.js` and before `chat.js`.
- **Docs.** `the_one/agents.md` "Chat module map" describes the factory, the
  profile config, `ctx.router` and the CSS scope.

## Acceptance Criteria
- [ ] **AC1. The factory exists.** `App.chat.create(config)` builds a
  complete chat instance from a config object and returns an instance
  handle. `chat.js` contains no chat logic beyond building the Chats config,
  calling the factory, and exposing the handle's seams (`wc -l` under 200).
- [ ] **AC2. The config is the only route to the Chats-only parts.**
  - The factory reads these from `config`:
    - `sidebar` (the list mount; the Chats list is created only when it is
      given);
    - `content` (the pane mount);
    - `drawerSlot` (the agent drawer; created only when given);
    - `pickerHost` (a boolean: register the picker host);
    - `signIn` (a boolean; when false, `ctx.signIn` is null and every caller
      guards it);
    - `router` (the adapter: `sync`, `goNew`, `go`);
    - `picker` (optional `{open(opener)}`);
    - `testids`: the composer's nine (`chat-input`, `chat-attach-btn`,
      `chat-image-input`, `chat-model`, `chat-stop-btn`, `chat-send-btn`,
      `chat-attachments`, `chat-attachments-status`,
      `pending-queued-region`), `chat-telemetry` and `chat-copy-status`.
      The pane's and the library controls' testids stay fixed; Leg 3 handles
      duplicates.
  - **No direct router calls.** No chat module or instance file calls
    `App.router.sync(` or `App.router.go(` directly.

    ```
    grep -n "App.router.sync(\|App.router.go(" areas/chat/session-flow.js \
      areas/chat/socket.js areas/chat/chat-pane.js areas/chat/instance*.js
    ```

    finds nothing.
    - `setSessionHealth`'s settings button (`chat.js` ~:515) uses
      `ctx.router.go`.
    - The pane's guidance link (`chat-pane.js` ~:222) uses a `go` option
      passed to `chatPane.create` from the adapter.
    - The agent drawer's "Open agent settings" (`agent-drawer.js` ~:224)
      stays as is, because the drawer exists only in the Chats profile.
  - **Absent parts are guarded.**
    - With no list, `ctx.renderChatsList` is a no-op, `ctx.chatsList` is null,
      and every `chatsList.*` use in the lifted body is guarded (`render`,
      `PENDING_ID`, and `setNewDisabled` at `chat.js` ~:478 and ~:608).
    - With no drawer, a stub agent drawer has `render`, `setActive`,
      `setSessionMetadata`, `refreshNotes` and `refreshRoutines` as no-ops,
      and a detached element as `toggle` (never null).
    - With `signIn: false`, `ctx.signIn` is null and its three call sites
      are guarded.
- [ ] **AC3. The descriptor's seams are unchanged.** `_connect`, `_ws`,
  `_refreshAgentsAndSetup`, `_serialize`, `_hydrate`, `_joinSession`,
  `_sessionState`, `_telemetry`, `_transcript`, `_turnWork`, `_turnFrames`,
  `_agentDrawer`, and the `_currentSessionId` and `_pendingJoinId` accessors
  exist on the `chat` area descriptor with today's meaning, all pointing at
  the Chats instance. `serializeState`, `hydrateState`, `activate` and
  `deactivate` behave as today.
- [ ] **AC4. Two instances can be created.** A browser test creates a second
  instance in the page with a minimal config:
  - a detached `content` element and no sidebar, drawer slot or picker host;
  - `signIn: false`;
  - a recording router adapter;
  - `gg-`-prefixed testids.

  It asserts all of the following:
  - The Chats area still works: a pick, a send and the Chats list, through
    `_chats.py`.
  - The second instance's DOM is only inside its own `content`.
  - No router call reached `App.router` from the second instance.
  - Destroying it, or never connecting it, leaves Chats untouched.
  - It asserts that the descriptor still exposes every `_*` seam from AC3, a
    `typeof` loop.

  The test also creates a **third** instance with the same minimal config and
  connects it, so `destroy()`'s socket and timer paths are exercised:
  - it waits for its socket to open;
  - calls `destroy()`;
  - asserts its socket closed;
  - asserts no new WebSocket was constructed within 3 s (`destroy` stops the
    2 s reconnect);
  - asserts Chats still sends and receives.

  A connected minimal instance's `onopen` runs the Chats-style startup (store
  reads, `list_sessions`, the idle rules) inside its own detached DOM. That
  is acceptable here; Leg 3 gives the drawer profile its own `onopen`.
- [ ] **AC5. Chats is unchanged.** Every Chats-related browser lane passes
  with its **assertions unedited**: `chats`, `chats-transcript`,
  `chats-widgets`, `contracts-chat`, `routing`, `agent-tabs` (it emits
  `config_changed` through the Chats socket) and `shared`. The only test
  change is the new AC4 test file.
- [ ] **AC6. Styles are unchanged.**
  - `chat.css` uses `.chat-instance` where it used `.area-chat`, and the
    Chats content panel carries both classes.
  - `scripts/ui_capture.py`'s chat surfaces, captured before and after the
    change, are pixel-identical apart from the regions the tool already
    masks.
  - A control run must show the noise floor first. If the control run is not
    zero, a small-tolerance comparison is used and its threshold reported.
- [ ] **AC7. The `destroy()` contract.**
  - `destroy()` sets a destroyed flag, so late callbacks do nothing.
  - It releases the instance's subscriptions through their unsubscribe
    handles: `App.store.subscribe` (`store.js` ~:122-128), `App.time.onChange`
    with **no** `ownerEl` (`time.js` ~:96-102), and `App.gleepglorp.subscribe`
    (`gleepglorp.js` ~:72).
  - It clears the socket's reconnect timer and suppresses `onclose`'s
    reconnect (`socket.js` ~:99), then closes the socket.
  - It clears the hold queue's timers (`hold-queue.js` ~:163-167), calls
    `transcript.clearLog()` (which destroys widget cards), and removes the
    instance's DOM.
  - The Chats instance never calls it.
- [ ] **AC8. The unit tier and the static guards pass:**
  `THE_ONE_TEST_NETNS=1 make test-unit`, including
  `tests/test_ui_guards.py` (no HTML sink in `areas/chat*`),
  `tests/test_ui_ownership.py` and `tests/test_store_static.py`.
- [ ] **AC9. Docs.** The `the_one/agents.md` "Chat module map" section
  documents the factory, the config keys, the instance handle, `ctx.router`,
  the `.chat-instance` scope and the AC4 test. `ruff` and the lint pair are
  clean for any Python touched.

## Verification Steps
- **AC1:**
  - `wc -l the_one/interfaces/web/static/js/areas/chat.js
    the_one/interfaces/web/static/js/areas/chat/instance*.js`.
  - Read `chat.js` to confirm it is the descriptor plus config.
- **AC2:** the grep in AC2. Read the three `ctx.signIn` call sites and the
  `renderChatsList`/`agentDrawer` uses for their guards.
- **AC3:** read the seams. The existing tests that use them (`_chats.py`,
  `test_flow_chat_*`) pass in AC5.
- **AC4:** the new test file passes in Chromium in its assigned lane
  (`chats`; it matches `test_flow_chat*`).
- **AC5:** run each lane one at a time with
  `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python bash
  scripts/run-tests.sh --lane <lane>`. Run them sequentially, never alongside
  the unit tier, and confirm with `ps` that no other test process is running.
  `git diff --stat tests/` shows only the new test file.
- **AC6:**
  - Capture the chat surfaces with
    `THE_ONE_TEST_NETNS=1 .venv/bin/python scripts/ui_capture.py --out <dir>`,
    where `<dir>` is outside the repo. Use `--list` to name the chat
    surfaces, and `--surfaces` to limit the run to them. The tool starts its
    own instance (port 8490+, data dir under `$HOME`).
  - **Control:** capture the unchanged code twice and compare. That gives the
    noise floor.
  - **Before and after:** capture once before editing any CSS or JS, and
    once after the change.
  - Compare each PNG pair with a short Pillow script in the scratch
    directory. Report the noise floor, the differing pairs and a crop of
    each.
- **AC7:** read `destroy()`. The AC4 test's connected third instance passes:
  it closes, and nothing reconnects within 3 s.
- **AC8:** `THE_ONE_TEST_NETNS=1 make test-unit`. Expect the documented skip
  count of 15 under netns.
- **AC9:** read the section. Run `ruff check` and `ruff format --check` on
  touched Python.

## Implementation Guidance

1. **Survey first (read only).**
   - Read `chat.js` and every `areas/chat/*.js` module that `chat.js`
     creates.
   - List every `ctx.*` member each module reads, every `App.router.*` call,
     every `document`/`window` listener (`agent-drawer.js` ~:386 and its
     `matchMedia` listener ~:614), and every module-level singleton
     (`agent-picker.js` ~:48-50 `host`, `queue`, `openModal`; `agent-drawer.js`
     ~:100 `STORAGE_KEY`).
   - Record the list in the flight log's leg entry. It is the map for AC2.

2. **Capture the "before" images** for AC6, before changing any CSS or JS.

3. **Create `instance.js` with `App.chat.create(config)`.**
   - Move the body of `init(sidebar, content)` into the factory, keeping its
     order: state, session state, list (if `config.sidebar`), pane, composer
     (testids from `config.testids`), banner, agent drawer (if
     `config.drawerSlot`, else a stub with `render`, `setActive`,
     `setSessionMetadata`, `refreshNotes`, `refreshRoutines` and any other
     method its callers use, all no-ops, and a detached `toggle`), telemetry,
     copy status node, ctx, modules leaves first, subscriptions, picker host
     (if `config.pickerHost`), and the `App.gleepglorp` subscription.
   - The mascot and welcome stay as today for the Chats profile. Make them
     part of the pane build, so a later profile can choose them.
   - **The picker hooks.** The pane's `onNewChat` and `onPickDifferent`, and
     the list's `onNew`, call `config.picker.open(opener)` when a picker is
     given, and do nothing otherwise. Today all three call
     `App.chat.openPicker` directly (`chat.js` ~:112, ~:146, ~:149). With no
     host registered, `openPicker` queues forever and may move the router to
     Chats.
   - **The handle** carries:
     - `root`, `connect`, `ws`, `refreshAgentsAndSetup`, `serialize`,
       `hydrate`, `joinSession`;
     - `sessionState`, `telemetry`, `transcript`, `turnWork`, `turnFrames`,
       `agentDrawer`;
     - `currentSessionId()`, and `pendingJoinId()` / `setPendingJoinId(v)`;
     - `destroy()` (AC7). The Chats instance never calls it; AC4's test does.
   - Subscriptions today are "never released" (`chat.js` ~:389-404). Keep
     the unsubscribe handles that `App.store.subscribe`, `App.time.onChange`
     (with no `ownerEl`) and `App.gleepglorp.subscribe` return, so `destroy`
     can release them.
   - `destroy()` needs a hook in `socket.js` (a `close({noReconnect:true})`
     or similar that clears `reconnectTimer` and stops `onclose` from
     scheduling one) and one in `hold-queue.js` (clear its timers). Keep each
     hook small; the Chats path is unchanged.

4. **Split the render functions into `instance-render.js`.** Use
   `App.chat.instanceRender.create(ctx)`, returning the functions `ctx` used
   to carry. Keep `ctx.renderPane`, `ctx.renderChatsList` and the others as
   the same names, so no module changes for this.

5. **Router adapter.**
   - Add `ctx.router = config.router`. Replace `App.router.sync('chat', x)`
     in `session-flow.js` and `socket.js` with `ctx.router.sync(x)`.
   - Replace `session-flow.js::goPick`'s `App.router.current()` /
     `App.router.go(App.router.href({destination:'chats', create:true,
     agent}), goOpts)` with `ctx.router.goNew(agent, goOpts)`.
   - Replace `setSessionHealth`'s settings button
     `App.router.go(...settingsHref)` (`chat.js` ~:515) with
     `ctx.router.go(href)`.
   - Give `chatPane.create` a `go` option. Its guidance link
     (`chat-pane.js` ~:222) calls `opts.go(href)`, and the factory passes
     `ctx.router.go`.
   - The Chats adapter implements all three with today's exact calls,
     including the `current()` check `goPick` makes.
   - `App.router.href(...)` calls that only build links (chat-pane,
     chats-list, proposal-cards, agent-kind) stay. They are pure.
   - `agent-drawer.js` ~:224 stays. The real drawer is Chats-only.

6. **Guard the optional parts.**
   - `ctx.signIn` null: `turn-frames.js` ~:124-126 and `socket.js` ~:397.
   - `ctx.renderChatsList` is a no-op when there is no list.
   - `ctx.chatsList` is null with no list, so guard every `chatsList.*` use
     in the lifted body (`render`, `PENDING_ID`, and `setNewDisabled` at
     `chat.js` ~:478 and ~:608).
   - The stub agent drawer covers socket ~:20 and ~:299-301, turn-frames
     ~:16 and ~:107-110, and the header's `toggle` append (`chat.js` ~:179).

7. **Rewrite `chat.js`** as the descriptor.
   - `init(sidebar, content)` adds `chat-instance` to the content panel
     (`content.classList.add('chat-instance')`), then builds the Chats config:
     - `sidebar` and `content`;
     - `drawerSlot`: `#chat-drawer`;
     - `pickerHost: true`, `signIn: true`;
     - `picker: { open: function (opener) { return
       App.chat.openPicker({ opener: opener }).catch(function () {}); } }`;
     - the Chats router adapter;
     - today's testids.
   - It calls `App.chat.create`, then sets every `_*` seam from the handle
     (keep `Object.defineProperty` for `_currentSessionId` and
     `_pendingJoinId`).
   - `activate`/`deactivate` stay as today, using the handle.

8. **CSS scope.** In `css/chat.css`, rename every `.area-chat` to
   `.chat-instance`.
   - All 57 rules style content, none styles the sidebar panel, and none
     targets the panel element itself without a descendant (design review,
     confirmed against the file). Re-check that before renaming.
   - The three `components.css` hits are comments; update their wording.
   - Tests that name `.area-chat` keep matching, because the content panel
     keeps the class: `test_flow_chat_proposals.py` ~:60-64 and
     `test_visual_snapshots.py` ~:181-184.

9. **AC4 test.** Add `tests/browser/test_flow_chat_instance_factory.py`.
   - Chromium is enough; it is not a library control. It lands in the
     `chats` lane through `chats_files()`, and `tests/test_run_tests_lanes.py`
     needs no change.
   - Use the standard app fixture, open Chats, and run a pick and a send
     through `_chats.py`.
   - In the page, call `App.chat.create({...minimal...})` with a recording
     router adapter.
   - Assert the AC4 points and the seams loop.
   - Call `destroy()`, then do one more send in Chats.
   - Create the third, connected instance (count WebSocket constructions with
     an init script installed before navigation), destroy it, and assert no
     reconnect within 3 s.
   - Follow the browser-test rules in CLAUDE.md: `_nav` and `_chats`
     helpers, no raw route hashes, no retired selectors, and
     `page.wait_for_timeout`, never `time.sleep`.

10. **`index.html`.** Add the two scripts after `socket.js` and before
    `chat.js`.
    - `tests/test_index_asset_cache_busting.py` (~:106-111) requires every
      `areas/chat/` script before `chat.js`.
    - `tests/test_store_static.py` globs `areas/chat/*.js`, so keep
      `instance*.js` free of literal `App.store.get('<name>')` fetches it
      would flag (the lifted `refreshAgentsAndSetup` already uses
      `App.store.get`, so check that its existing allowance covers the new
      file path).

11. **Docs (AC9),** then run the AC5 lanes and the unit tier as listed.

## Edge Cases
- **Never-released subscriptions.** The Chats instance must behave as today:
  subscriptions live for the page. Only `destroy()` releases them.
- **`App.time.onChange` owner semantics.** If it is given an `ownerEl`, a
  detached second instance's listener could drop at once. Use explicit
  unsubscribe handles instead, or confirm the semantics.
- **The picker host is a module singleton.** Only the Chats profile
  registers it. A second instance must not call `registerPickerHost`.
- **The `agent-drawer.js` document listener and `matchMedia` listener.**
  They are created only when a real drawer is built (Chats). The stub adds
  none.
- **Load order.** `instance-render.js` must load before `instance.js` if the
  factory references `App.chat.instanceRender` at creation time. Either order
  works if it is only called inside `create`. Keep both before `chat.js`.
- **Hidden ordering assumptions.** `ctx.socket` is created last, and modules
  reach later-created modules only at call time. Keep the leaves-first order
  exactly.
- **`self._refreshAgentsAndSetup` is used by `activate()`.** Keep it.
- **The CSS rename.** If the re-check finds a rule that styles the sidebar
  panel, it keeps `.area-chat`. The AC6 images include the list's hover and
  armed-delete surfaces.
- **The second instance's create-time fetch.** `App.gleepglorp.get()` runs
  at create (`chat.js` ~:606). It is harmless, but must not double a request
  that a test counts; `App.gleepglorp.get` without `force` should join or
  reuse the cached value.
- **Duplicate testids** from the pane and the library controls are expected
  in a second instance. Leg 3 handles them; AC4's instance is detached.

## Files Affected
- `the_one/interfaces/web/static/js/areas/chat.js` — reduced to the descriptor.
- `the_one/interfaces/web/static/js/areas/chat/instance.js` — new, the factory.
- `the_one/interfaces/web/static/js/areas/chat/instance-render.js` — new, the renders.
- `the_one/interfaces/web/static/js/areas/chat/session-flow.js` — `ctx.router`.
- `the_one/interfaces/web/static/js/areas/chat/socket.js` — `ctx.router`, the
  `signIn` guard.
- `the_one/interfaces/web/static/js/areas/chat/turn-frames.js` — the `signIn`
  guard.
- `the_one/interfaces/web/static/js/areas/chat/chat-pane.js` — the `go`
  option.
- `the_one/interfaces/web/static/js/areas/chat/hold-queue.js` — a timer-clear
  hook for `destroy`.
- `the_one/interfaces/web/static/css/chat.css` — the `.chat-instance` rename;
  `css/components.css` — comment wording.
- `the_one/interfaces/web/static/index.html` — two script tags.
- `tests/browser/test_flow_chat_instance_factory.py` — new (AC4).
- `the_one/agents.md` — the "Chat module map" section.

## Citation Audit
Checked against the working tree at `3aa9ea94` (no earlier leg in this
flight):
- `areas/chat.js::init` (:21-613) — the full body to lift: state :25-95,
  session state :101, list :110-136, pane :144-151, composer :155-170 with
  testids, banner :173, agent drawer :178 on `#chat-drawer`, ctx :226-249,
  renders :278-521, modules :524-533, stopTurn :538-561, seams :563-593,
  picker host :599-603, the GleepGlorp subscription :606-611 — verified.
- `areas/chat.js::activate` (:615-623) and `deactivate` (:625-629) — verified.
- `areas/chat/session-flow.js` ~:107-113 (`goPick`: `App.router.current`,
  `go`), ~:200 and ~:323 (`App.router.sync('chat', null)`) — verified (grep).
- `areas/chat/socket.js` ~:20 (`ctx.agentDrawer`), ~:224
  (`App.router.sync('chat', joinedEff.sync)`), ~:397
  (`ctx.signIn.settleClose`) — verified (grep).
- `areas/chat/turn-frames.js` ~:16 (`ctx.agentDrawer`), ~:124-126
  (`ctx.signIn`) — verified (grep).
- `areas/chat/agent-picker.js` ~:315-317 (`App.chat.openPicker`,
  `registerPickerHost` globals) — verified (grep).
- `areas/chat/agent-drawer.js` ~:386 (a `document` listener for
  `App.approvals.CONFIG_CHANGED`) — verified (grep). The `matchMedia`
  listener ~:614 is from the planning survey and is unverified here.
- `static/js/app.js` ~:158-162 — `.area-{id}` on both the sidebar and the
  content panel — verified.
- `css/chat.css` (57 `.area-chat`), `css/components.css` (3) — verified
  (grep -c).
- `index.html` :90-109 — the chat module script order — verified.
- Design review (Developer, cycle 1) added and verified:
  - the `App.router.go` sites at `chat.js:515`, `chat-pane.js:222` and
    `agent-drawer.js:224`;
  - the picker callbacks at `chat.js` ~:112, ~:146 and ~:149;
  - the unsubscribe returns: `store.js:122-128`, `time.js:96-102`,
    `gleepglorp.js:72`;
  - the reconnect at `socket.js:99`;
  - the hold-queue timers at ~:163-167;
  - every `.area-chat` rule in `chat.css` is content, and the
    `components.css` hits are comments;
  - `test_index_asset_cache_busting.py:106-111`;
  - the `chats` lane takes `test_flow_chat_instance_factory.py`.
- Moved to Leg 3 by the review: scoping `_chats.py`'s page-wide locators
  (`message_sel` :144, `messages` :158, `turn_groups` :163).
