# Leg: drawer-chat

**Status**: completed
**Flight**: [The GleepGlorp drawer and form filling](../flight.md)

## Objective
Mount a real GleepGlorp chat in the drawer: a second `App.chat.create`
instance (the "drawer profile") with its own socket opened at page load.
- **Conversation.** It keeps its conversation across pages and reloads,
  offers New chat and Open in Chats, and shows the empty and working states.
- **Window-wide frames.** It carries those frames for every page, which
  closes the socket gap. Chats still behaves as before.

## Context
- **Flight DD1 to DD4**, and the board's "Panel states" artboard: the
  **empty** state names the page, offers suggestions, and says "I fill forms
  and suggest changes. Nothing is saved until you click."; the **working**
  state is the turn work group.
- **Operator decisions (2026-11-19):**
  - the drawer is not on Chats;
  - all tabs share one drawer conversation (`localStorage`);
  - Open in Chats moves to Chats.
- **Leg 1 (landed, uncommitted).** `App.chat.create(config)`
  (`areas/chat/instance.js`) builds an instance from a config:
  - the content mount, an optional sidebar and drawer slot (a stub without
    it), `pickerHost`, `signIn`, the `router` adapter
    (`sync`/`goNew`/`go`), `picker`, and composer/telemetry/copy testids;
  - it returns a handle with `root`, `connect`, `ws`, `joinSession`,
    `sessionState`, `currentSessionId()`, `destroy()` and others.
- **Leg 2 (in flight)** builds the drawer frame:
  - `App.gleepglorpDrawer` with `open`, `close`, `isOpen` and `bodySlot()`;
  - the header (robot tile, title, Close);
  - the "Looking at" line and the setup state;
  - hidden on Chats and when off;
  - focus moves to the `h2` on open.

  **This leg depends on Leg 2's landed API.** Re-read
  `js/gleepglorp-drawer/shell.js` before starting and record any difference
  in the flight log.
- **The socket today** (`areas/chat/socket.js`):
  - `onopen` (~:71-91) runs `ctx.refreshAgentsAndSetup()` (forced
    `providers`, `agents` and GleepGlorp reads), then `list_sessions`. Its
    reply (~:170-210) runs the reconnect rules and `runIdleRules`, which
    auto-join the newest chat of any agent.
  - The window-wide frames are handled before the gate:
    - `sessions_changed` (~:120-128): `state.sessions`, `pruneDrafts`, the
      store prime;
    - `config_changed` (~:130-135): `App.approvals.record`;
    - `gleepglorp_changed` (~:137-153): the notes event, `App.gleepglorp.prime`
      and a joined GleepGlorp chat's re-join.
- **`session-flow.js`:**
  - `pickAgent(agent)` (~:117-131) moves to `pending(agent)` with no router
    involvement.
  - `goPick` goes through `ctx.router.goNew`.
  - `runIdleRules` (~:207-213).
- **Construct-time testids.** These would duplicate in a second instance
  mounted in the page:
  - `chat-pane.js` (~:162 `chat-welcome`, ~:190 `chat-agent-line`, ~:192
    `chat-header`, ~:234, ~:240, ~:254, ~:277 the new-chat state);
  - `hold-queue.js` (~:66 `pending-queued-status`, ~:159
    `pending-queued-full`);
  - `instance.js` (~:237 `chat-welcome-mascot`).

  Playwright locators are strict, so a duplicate visible or hidden element
  can break existing tests that use page-wide testids.

## Inputs
- Legs 1 and 2 landed (uncommitted) in the working tree.

## Outputs
- **`instance.js` gains the drawer-profile options:**
  - `profile: 'drawer'` turns on everything below;
  - `testidPrefix` (`'gg-'` for the drawer) is applied to every testid the
    instance and its modules create **at construction** (`chat-pane.js`,
    `hold-queue.js`, the mascot);
  - `agent` (a fixed agent, `'GleepGlorp'`);
  - `onSessionChange(id)`, called when the bound session changes (a
    `session_joined`, a promotion from starting, a reset to pending);
  - `emptyState` (a Node or a builder the drawer supplies, shown in place of
    the Chats new-chat state while pending).

  The Chats profile passes none of these, so Chats is unchanged.
- **Drawer-profile behaviour in the instance and socket:**
  - **`onopen`** sends a `join` directly (never through
    `chatState.reconnectAction`, which needs a session list), and only for:
    - the bound id, while joined or joining;
    - a **pending rejoin id**, set when the drawer asked to rejoin before the
      socket was open (`handle.joinSession` today does nothing on a closed
      socket, `instance.js` ~:405).

    While starting, it re-sends the same `start_session`, as today. While
    pending with no rejoin id, it sends **nothing**. It never calls
    `refreshAgentsAndSetup` and never sends `list_sessions`.
  - **No idle rules.** It never runs `runIdleRules` or the first-list
    reconnect rules. A `session_list` reply that arrives anyway is only
    stored. Guard `session-flow.js` ~:323's `state.listSeen` read
    explicitly.
  - **`refreshSessionList` does nothing in drawer mode** (`session-flow.js`
    ~:397-399). The `sessions_changed` push replaces it. Today it sends
    `list_sessions` from `join_failed`, `start_failed`, a `session_joined`
    with `fromStart` or not accepted, and `session_deleted`.
  - **It is never idle.** With no conversation it is `pending('GleepGlorp')`
    through `pickAgent`, never through the router. These idle exits each
    get one drawer hook: after `clearConversation`, call
    `pickAgent(config.agent)`:
    - `join_failed` (`socket.js` ~:371-380);
    - `session_deleted` (~:390-410);
    - `start_failed`;
    - the deleted-or-pruned bound session (a `sessions_changed` without it).

    The first-list `toIdle` path (~:196-204) is skipped in drawer mode.
  - **The stored id.** `onSessionChange` fires from one place each:
    - the accepted `session_joined` (`socket.js` ~:238-246, where
      `promoteDraft` already runs for `fromStart`), which writes the id;
    - New chat, a `join_failed` for the stored id, and a deleted or pruned
      bound session, which clear it.

    The boot-time pending state, `starting` and a reconnect never write or
    clear it, so a reload keeps it for the first open.
  - **No header, welcome or mascot.** In drawer mode the instance does
    **not build** the chat header, the welcome or the mascot (the drawer has
    its own header), so their testids do not exist there.
  - **Prefixed testids.** The remaining construct-time and reader-paired ids
    take `testidPrefix`:
    - `chat-pane.js`'s new-chat-state ids (~:234, :240, :254, :277) and any
      other it still builds;
    - `hold-queue.js` ~:66, ~:110, ~:159, with the reader at ~:134;
    - `attachments.js` ~:100, ~:120 (the reader);
    - `instance-render.js` ~:270 (`chat-health-banner-action`).
  - **Per-message testids stay fixed:** `message`, `turn-work`,
    `proposal-card`, the notices, charts and widgets. No existing test opens
    the drawer, so they never coexist with Chats' in the suite. The new test
    scopes its own drawer locators to `#gleepglorp-drawer`, and its Chats
    assertions go through `_chats.py`, scoped to the Chats panel.
  - The composer's placeholder reads "Message GleepGlorp…".
- **Window-wide frames on both sockets, deduplicated in one place.**
  - `App.chat.windowFrames.handle(data)` (new, `areas/chat/window-frames.js`)
    performs the global effects and returns whether the frame was
    window-wide. `App.gleepglorp.prime`'s contract is not changed; the Settings
    page Save keeps notifying.
    - **`sessions_changed`:** prime the `sessions` store only when the list
      differs from the store's current value (a JSON compare).
    - **`config_changed`:** `App.approvals.record`, which already
      de-duplicates by proposal id.
    - **`gleepglorp_changed` with settings:** `App.gleepglorp.prime` only
      when the settings differ from `App.gleepglorp`'s current value (a
      stable JSON compare).
    - **Notes-only `gleepglorp_changed`:** fire `gleepglorp-notes-changed`
      at most once per 50 ms window. The two deliveries arrive in separate
      tasks.
  - Each instance's socket calls it, then does its own per-instance reaction:
    - **Chats:** `state.sessions` and `pruneDrafts`, and a joined GleepGlorp
      chat's re-join, as today.
    - **The drawer:** `state.sessions`, and the joined GleepGlorp chat's
      re-join on `gleepglorp_changed`, which runs per instance. If its bound
      session is no longer in a `sessions_changed` list (deleted from Chats or
      purged), it moves to a fresh pending GleepGlorp chat and clears the
      stored id.
- **The drawer's chat module** (`js/gleepglorp-drawer/chat.js`):
  - It creates the drawer instance into `App.gleepglorpDrawer.bodySlot()`
    when the shell mounts, and **connects at once**: the window socket. This
    happens even while GleepGlorp is off, because the window socket serves
    every page (the socket gap fix), whether or not GleepGlorp is on.
  - It listens for the drawer's open through `App.gleepglorpDrawer`'s open
    notification. If Leg 2 exposed none, add
    `App.gleepglorpDrawer.onOpenChange(fn)` in `shell.js`, built on
    `App.ui.drawer`'s `onOpenChange`.
  - The current session id is kept in `localStorage`
    `gleepglorp-drawer-session` (try/catch) through `onSessionChange`.
  - **On first open**, it re-joins the stored id (`joinSession`) if one
    exists, else stays pending. If the stored id is gone (`join_failed`), it
    goes pending and clears the id.
  - **The header gains New chat** (`gg-drawer-new-chat`): pending GleepGlorp,
    the stored id cleared, focus to the composer. It also gains **Open in
    Chats** (`gg-drawer-open-in-chats`), shown only while joined: a guarded
    `App.router.go` to `#chats/{id}` with the button as opener. Both go
    before the divider and Close, as drawn.
  - **Focus on open:** the composer when ready, else the setup link (Leg 2's
    setup state). Leg 2's `h2` focus is replaced.
  - **The empty state** (`gg-drawer-empty`):
    - "Ask about this page, or ask me to fill it in.";
    - the quiet line "I fill forms and suggest changes. Nothing is saved
      until you click.";
    - a "What does this page do?" suggestion button
      (`gg-drawer-suggestion`), which sends that text. It is disabled
      whenever the composer is blocked.
- **Test apparatus:**
  - `tests/browser/_chats.py`'s page-wide message and turn locators
    (`message_sel` ~:144, `messages` ~:158, `turn_groups` ~:163, and any
    other helper matching message or turn content page-wide) are scoped to
    the Chats content panel, so the new test's Chats assertions never see
    drawer messages.
  - **`chat_frames`** (~:576-604, every page socket) and **`_HOLD_JS`**
    (`test_flow_chat_gleepglorp.py` ~:59-100, "the last constructed" socket)
    are left alone **unless a run shows they need it.** The drawer socket
    sends nothing until the drawer is opened, and no existing test opens it.
    `_HOLD_JS`'s "last constructed" can become the drawer socket only if the
    Chats socket constructs first and the drawer's reconnects later. Check
    the boot order, and change it only if a test fails for that reason.
  - The new test uses its own per-socket recorder.
  - Assertions are unedited.
- **Tests:** `tests/browser/test_flow_gleepglorp_drawer_chat.py` (the
  `shared` lane).
- **Docs:** `the_one/agents.md` gets the drawer profile and the window frames
  under "Chat module map" and "GleepGlorp drawer"; CLAUDE.md's GleepGlorp
  drawer paragraph is extended.

## Acceptance Criteria
- [ ] **AC1. The drawer chat works.**
  - With GleepGlorp ready (the mock provider), open the drawer on Library and
    send "hello". The drawer shows the user bubble, the work group while
    working, and the reply.
  - The Chats list (opened afterwards) lists the conversation as a
    GleepGlorp chat.
  - The URL never changed while the drawer chatted.
- [ ] **AC2. Chats and the drawer are independent.**
  - Start a chat with an agent in Chats, then go to Agents, open the drawer
    and chat with GleepGlorp. Go back to Chats.
  - The Chats chat is as it was, with its messages, its URL and no drawer
    messages. The Chats list shows the drawer's GleepGlorp chat as a row.
  - Leave Chats again, and the drawer shows its own conversation.
- [ ] **AC3. Continuity.**
  - The drawer conversation persists across page changes.
  - After a reload, the first open of the drawer re-joins the same
    conversation. The join happens on open, not at boot: no `join` frame is
    sent before the drawer opens.
  - New chat starts a fresh pending GleepGlorp chat, and a reload then opens
    pending.
  - A second tab opening the drawer shows the same conversation. It is
    accepted that a New chat in tab A does not move tab B until B reloads;
    there is no `storage` listener.
  - Opening the drawer before its socket is open (the test delays the
    socket) still rejoins once the socket opens.
- [ ] **AC4. Open in Chats.**
  - Open in Chats goes to `#chats/{id}`, which shows the conversation, and
    the drawer is hidden.
  - A message sent there appears in the drawer's conversation when the
    operator leaves Chats.
  - Open in Chats is absent while pending.
- [ ] **AC5. The socket gap is closed.**
  - In a window loaded straight on `#agents/{name}` that never visits Chats,
    a GleepGlorp change approved through `POST
    /api/gleepglorp/proposals/{id}/approve` reaches the open agent editor (the
    Flight 2 follow note appears).
  - A `gleepglorp_changed` push updates `App.gleepglorp` (the corner button
    hides when GleepGlorp is turned off from another window).
- [ ] **AC6. The drawer socket is quiet.**
  - On a cold boot to Agents, the drawer's socket sends no `list_sessions`,
    no `join` and no `start_session`.
  - A send, a start failure and a `join_failed` in the drawer send no
    `list_sessions` either.
  - `tests/browser/test_store.py::test_request_counts_per_activation`
    passes unedited.
- [ ] **AC7. Window frames run once.**
  - With both sockets open, one `config_changed` records one approval, and
    one notes-only `gleepglorp_changed` fires `gleepglorp-notes-changed`
    once.
  - A `gleepglorp_changed` with unchanged settings does not notify
    `App.gleepglorp` subscribers.
- [ ] **AC8. A deleted drawer conversation.**
  - Deleting the drawer's conversation from the Chats list moves the drawer
    to a fresh pending chat (the empty state) and clears the stored id.
  - So does a stored id that no longer exists at the first open
    (`join_failed`).
- [ ] **AC9. No duplicate construct-time testids.**
  - With the drawer instance mounted (closed or open, no messages), every
    `[data-testid]` inside `#gleepglorp-drawer` either starts with `gg-` or
    occurs once on the page.
  - The suite's page-wide testid locators are unaffected (AC11).
- [ ] **AC10. Focus.**
  - Opening the drawer with GleepGlorp ready puts focus in its composer.
  - With GleepGlorp not ready, focus goes to the setup link.
  - New chat moves focus to the composer.
  - Open in Chats is a guarded go: a Stay returns focus to the button.
- [ ] **AC11. No regressions.**
  - Every browser lane passes in one `--parallel 3` run on a host with no
    other test process. Record the `PARALLEL_RESULT` line and the start load.
  - The unit tier passes separately.
  - The only edited existing test code is `_chats.py`'s locator scoping,
    plus `chat_frames` or `_HOLD_JS` only if a run proved it necessary
    (report why). No assertion is edited.
  - No existing test opens the drawer.
- [ ] **AC12. Docs.** The `agents.md` sections and the CLAUDE.md paragraph
  are written. The static guards pass: `test_ui_guards.py`,
  `test_token_definitions.py` and `test_design_tokens_a11y.py`.

## Verification Steps
- **AC1-AC10:** `tests/browser/test_flow_gleepglorp_drawer_chat.py`, with
  GleepGlorp ready through a mock provider and `PUT /api/gleepglorp`.
  - It records WebSocket frames per socket: install an init script that wraps
    `WebSocket` and tags each socket by construction order and URL. Assert
    which one is the drawer's through `App.gleepglorpDrawer`'s handle.
  - AC5 seeds a proposal with `seed_gleepglorp_proposal`
    (`tests/browser/seeders.py`) and the `_world` setup used by
    `test_flow_chat_proposals.py` and
    `test_flow_agent_editor_follows_approval.py` (~:21-22, ~:207-219). That
    test visits Chats first; the AC5 test must go straight to
    `#agents/{name}`, approve through the API from the test, and assert the
    follow note.
- **AC9:** an in-page check in the same file.
- **AC11:**
  - Run the unit tier alone: `THE_ONE_TEST_NETNS=1 make test-unit`.
  - Then run the full browser run alone:
    `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 TEST_TIMEOUT=3600
    PYTHON=.venv/bin/python bash scripts/run-tests.sh --parallel 3`.
  - Check `uptime` and `ps` first.

## Implementation Guidance

1. **Survey** (read only; record in the flight log):
   - Leg 2's `shell.js` API and where it mounts.
   - Every construct-time `data-testid` across `instance.js`,
     `instance-render.js` and the ten modules. Grep `setAttribute('data-testid'`
     and `testid:` in factory options, and note which run at create.
   - Every use of `state.sessions`, `firstListPending`, `listSeen`,
     `runIdleRules` and `refreshAgentsAndSetup` in the socket and the flow.
   - The tests that wrap WebSockets or read the last socket: grep
     `WebSocket` in `tests/browser/`.

2. **`window-frames.js`.**
   - Move the global effects out of `socket.js`. `socket.js` calls
     `App.chat.windowFrames.handle(data)`, then its per-instance reaction,
     and returns for those three frame types as today.
   - Deduplicate inside `windowFrames`, as listed under Outputs. Do not change
     `App.gleepglorp.prime`, so its subscribers keep today's behaviour:
     `gleepglorp-page.js` ~:659, `agent-drawer.js` ~:633,
     `studio-subscriptions.js` ~:81, and the instances.
   - Load the script before `socket.js`.

3. **Profile options in `instance.js`, `instance-render.js`, `socket.js` and
   `session-flow.js`.**
   - Read `config.profile === 'drawer'` once into `ctx.profile`. Guard these
     on it:
     - the `onopen` startup;
     - the `session_list` rules;
     - `runIdleRules`;
     - `refreshSessionList`;
     - the idle exits listed under Outputs, each followed by
       `pickAgent(config.agent)`.
   - Keep a `pendingRejoinId` that `onopen` consumes.
   - In drawer mode, skip building the header, the welcome and the mascot.
     Thread `testidPrefix` into `chatPane.create`, `holdQueue.create` and
     `attachments.create`, and onto the banner action in `instance-render.js`.
     Readers paired with a writer use the same prefixed id.
   - In drawer mode, `renderPane` uses `config.emptyState` while pending.
   - Call `config.onSessionChange` only at the sites listed under Outputs.
   - Add the handle methods `startNew()` (which calls
     `pickAgent(config.agent)` and clears the stored id) and `sendText(text)`.
     `joinSession(id)` sets `pendingRejoinId` when the socket is not open.

4. **`js/gleepglorp-drawer/chat.js`.**
   - Build the drawer config (no sidebar, drawer slot, picker host or
     sign-in; `profile: 'drawer'`; `agent: 'GleepGlorp'`; `testidPrefix:
     'gg-'`; and testids `gg-chat-input` and so on).
   - Its router adapter: `sync` is a no-op, `goNew` resolves `false` without
     navigating, and `go` is `App.router.go`.
   - Create the instance into the body slot and connect. Start pending.
   - Hook the drawer's open (Leg 2's `onOpenChange`, or a hook Leg 2
     exposes) for the lazy rejoin and focus.
   - Add New chat and Open in Chats to the header.
   - Wire the empty state's suggestion button to send through the
     instance. The handle needs a `sendText(text)`; add it, calling
     `ctx.send.sendText`.

5. **Test apparatus.** Scope `_chats.py`'s message and turn locators to
   `#main-content .area-chat`. Leave `chat_frames` and `_HOLD_JS` alone
   unless a run shows they need it (Outputs). Edit no assertion.

6. **Tests,** then the docs, then the unit tier, then the full browser run
   (AC11), each alone.

## Edge Cases
- **GleepGlorp off or not ready at boot.** The drawer instance still
  connects (the window socket) and stays pending. Leg 2's shell hides it or
  shows setup. A send is impossible while not ready: the composer is
  blocked by the pending GleepGlorp state (`computeBlocked`).
- **The drawer is hidden on Chats while its turn runs.** The instance keeps
  receiving frames. When the operator leaves Chats, the drawer shows the
  finished turn.
- **The same session open in Chats and in the drawer instance (hidden).**
  Both sockets are subscribed. A Stop in Chats cancels the turn for both, as
  two tabs do today.
- **`localStorage` throws** (private mode): the drawer works without
  persistence.
- **The stored id belongs to a deleted session.** `join_failed` moves the
  drawer to pending and clears the id, through the drawer hook on
  `socket.js` ~:371-380.
- **A second socket per window** doubles the server's WebSocket
  connections on boot. Note it in `the_one/agents.md`; no security change.
- **A reconnect while the drawer is pending** sends nothing, because there
  is no binding.
- **Ctrl K's "Ask GleepGlorp"** (Leg 2) opens the drawer. Focus follows
  AC10's rule.

## Files Affected
- `the_one/interfaces/web/static/js/areas/chat/instance.js`,
  `instance-render.js`, `socket.js`, `session-flow.js`, `chat-pane.js`,
  `hold-queue.js` — the profile options.
- `the_one/interfaces/web/static/js/areas/chat/window-frames.js` — new.
- `the_one/interfaces/web/static/js/gleepglorp.js` — `prime` no-op on
  unchanged settings.
- `the_one/interfaces/web/static/js/gleepglorp-drawer/chat.js` — new.
- `the_one/interfaces/web/static/js/gleepglorp-drawer/shell.js` — header
  buttons, the open hook and focus (only what Leg 2 left open).
- `the_one/interfaces/web/static/index.html` — two scripts.
- CSS for the empty state and the header buttons (the drawer's stylesheet).
- `tests/browser/_chats.py`, `tests/browser/test_flow_chat_gleepglorp.py` —
  the apparatus only.
- `tests/browser/test_flow_gleepglorp_drawer_chat.py` — new.
- `the_one/agents.md`, `CLAUDE.md`.

## Citation Audit
Checked against the working tree after Leg 1 landed (uncommitted). Leg 2 is
in flight; re-check `shell.js` and `index.html` after it lands.
- `areas/chat/instance.js::create`:
  - `config` keys (~:5-18);
  - the stub drawer (~:50-61);
  - pane creation (~:199-203);
  - the mascot testid (~:237);
  - ctx (~:274-292);
  - module creation order (~:297-306);
  - `App.gleepglorp.get` and `subscribe` (~:374-380);
  - `destroy` (~:382-396);
  - the handle (~:398-419).

  Verified (read in full).
- `areas/chat/socket.js`:
  - `close()` (~:56-62);
  - `onopen` (~:71-91): `refreshAgentsAndSetup` then `list_sessions`;
  - `onclose` (~:93-113): the reconnect after 2 s;
  - the window-wide frames (~:120-153);
  - `session_list` (~:170-210): `runIdleRules`.

  Verified.
- `areas/chat/session-flow.js`: the exports (~:416-440), `goPick` through
  `ctx.router.goNew` (~:106-114), `pickAgent` (~:117-131) and
  `runIdleRules` (~:207-213) — verified.
- Construct-time testids: `chat-pane.js` ~:162, :190, :192, :234, :240,
  :254, :277; `hold-queue.js` ~:66, :159 — verified (grep). Whether each runs
  at create is checked in step 1.
- `tests/browser/_chats.py` ~:144/:158/:163 (the locators), ~:576-604
  (`chat_frames`); `test_flow_chat_gleepglorp.py` ~:59-100 (`_HOLD_JS`) —
  from the Architect review; re-verify in step 1.
- **Design review (Developer, cycle 1)** added and verified:
  - `socket.js` `join_failed` ~:371-380, `session_deleted` ~:390-410, the
    first-list `toIdle` path ~:196-204, `session_joined` ~:238-246;
  - `session-flow.js` `clearConversation` ~:192-204, `refreshSessionList`
    ~:397-399, `listSeen` ~:323;
  - `instance.js` `joinSession` ~:405;
  - the testids `chat-pane.js` :156, :212, :221, `hold-queue.js` :110/:134,
    `attachments.js` :100/:120, `instance-render.js` :270;
  - the `App.gleepglorp` subscribers (`gleepglorp-page.js` :659,
    `agent-drawer.js` :633, `studio-subscriptions.js` :81, `instance.js`
    :375);
  - `seed_gleepglorp_proposal` (`seeders.py`);
  - the global WebSocket wrappers in `test_flow_chat_start_reconnect.py`
    :46/:64 and `test_router_items.py` :790/:800, which only touch the Chats
    socket while the drawer stays unopened.
