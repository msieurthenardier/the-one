# Flight: Chats and Jump-to

**Status**: completed
**Mission**: [Workbench Navigation and Control Library](../../mission.md)

## Contributing to Criteria

- [x] **SC3 — Start a chat by choosing an agent.**
  - One primary New chat action opens an agent picker with search, a Recently used group
    and the full A–Z list.
  - Choosing an agent starts a new conversation with no further step.
  - The history lists conversations across all agents.
  - A drawer shows the conversation's agent read-only (description, model, provider, what
    it can use), with a one-step route to its settings.
  - *(behavior-test-backed: the new `start-a-chat`)*
- [x] **SC5 — Jump to anything.** Ctrl K and a visible rail control open a palette that
  finds agents, conversations, Library items, Settings pages and the New chat action, and
  opens the chosen one. *(behavior-test-backed: the new `jump-to-palette`)*
- [x] **SC2 — Work is never lost** (the jump-to and Chat-action half).
  - Leaving unsaved changes through jump-to, or through the agent editor's Chat action,
    asks first.
  - The drawer's settings link goes through the same guard. From Chats it is always a
    clean pass, because leaving a dirty editor for Chats already asked.
- [x] **SC6 — Control library** (continued). The picker and palette's searchable list, the
  drawer, the rail's bottom action and the Chats list rows come from `App.ui`. Each has a
  demo, an inventory row and contract tests in both engines.
- [ ] **SC8 — Matches the approved samples.** The Chats frame, picker, drawer and palette
  follow reference spec §2, §5 and §9. A non-blocking operator preview comes before the
  close gate (DD13), and Flight 6 closes SC8.
  *Flight 4's part is done:* the preview was published (no operator feedback yet), and
  the close-gate runs passed in both themes. The criterion stays open for Flight 6.
- [x] **SC10 — Operable and regression-safe.**
  - The new surfaces are keyboard-operable with visible focus, including Ctrl K, Escape,
    Enter, the arrow keys and the composer's focus ring.
  - Landmarks and the skip link are preserved.
  - Suites, guards and specs pass, and the core flow "start a chat via the picker" passes
    in both themes.

---

## Pre-Flight

### Objective

Make Chats start with the question that matters, *which agent?*, and add a palette that
reaches anything.

- **Chats list column.** It gains one large **New chat** action above a cross-agent history
  grouped by recency. The agent dropdown and the welcome screen's agent list are removed.
- **New chat** opens an **agent picker** (search, Recently used, All agents A–Z). Picking an
  agent starts a new chat with it at once, as a pending conversation that becomes real on
  the first message.
- **Each conversation** has a header ("{title}" with "with {agent}") and a restyled composer.
- **An agent drawer** shows the agent read-only, including what it can use, with **Open
  agent settings**.
- **The agent editor** gains the **Chat** header action, deferred from Flight 3 DD4.
- **A jump-to palette**, opened by Ctrl K or the rail's bottom control, finds agents,
  chats, the New chat action, Library items and Settings pages, and opens the one chosen.

All of these are built from the control library, so they share one searchable-list
control.

### Open Questions

All resolved; see the Design Decisions.

- [x] **A29.** Is a session created when the agent is picked, or on the first send?
  → DD1 (first send, through one atomic, idempotent `start_session` action, with a
  non-persisting `leave` on pick).
- [x] How do "start a chat with X" intents (the agent editor's Chat, "Pick a different
  agent", the palette's "New chat…") reach the chat area? → DD2 (a `#chats/~new/{agent}`
  route, plus an exported `openPicker`).
- [x] Bare `#chats`, the setup guidance and the old welcome. → DD3.
- [x] Does `App.store` hold sessions? → DD4 (yes, a `sessions` collection primed from
  the WebSocket).
- [x] Recency and count rules. → DD4.
- [x] Session delete in the new list. → DD5.
- [x] Drawer: push or overlay, persistence, slot, and "what it can use". → DD7.
- [x] Ctrl K policy. → DD9.
- [x] Palette contents, order, cap and empty state (A17). → DD10.
- [x] Composer details, squawk 0110 and the telemetry row. → DD6.
- [x] Studio's single `dirty` flag (Flight 3 debrief, recommendation 2). → DD8.
- [x] The `shared` lane budget (squawk 0117). → DD11.
- [x] An operator preview before the close gate (Flight 3 debrief, recommendation 1).
  → DD13.

**The operator was not interviewed.** The mission makes execution autonomous, and its
human touchpoints are the sign-off, the post-Flight-3 checkpoint and the alignment flight.
DD13 gives the operator a non-blocking look before the close gate.

### Design Decisions

**DD1 — The session is created on the first send (A29), through one atomic, idempotent
action.**

- **Picking an agent creates no session.** It sends one non-persisting `leave` frame and
  creates the pending chat on the client.
  - The `leave` action is new. The server removes this socket as a subscriber of the bound
    session and sets the socket's `session` to `None`, with no database write.
    - It touches `last_activity`, mirroring the disconnect path.
    - It **never cancels**: a running turn completes and persists. The client discards its
      held message, as a switch does today.
  - Without it, the previous session's frames would render into the pending pane: chunks,
    tool events, `system` and `done`. A connector session receiving Discord traffic is a
    realistic case, since frames carry no `session_id` (`app.py:1442-1457`).
  - The pending chat shows a selected row at the top of Today: "New chat · now · {agent}".
  - The header reads "New chat" with "with {agent}". The pane shows the new-chat state
    (§5.4). The composer is ready, with the placeholder "Message {agent}…".
  - This is the board's "no further step" (§10 item 13).
- **The client is a state machine**, written as a transition table in the leg 3 design,
  with states `idle`, `joining(id)`, `joined(id)`, `pending(agent)` and
  `starting(clientId)`. **The state gates every inbound frame**, because `leave` cannot
  recall frames already in flight. Cycle 2 found that a late `session_joined` from a
  cold-load auto-join would otherwise take over the pending chat (`chat.js:586-593`,
  `:1230`).
  - **`pending`:**
    - drop every `session_joined`, and every session-scoped frame (`user`,
      `assistant_chunk`, `assistant`, `thinking`, `tool_*`, `system`, `usage`, `done`,
      `cancelled`, `auth_*`);
    - handle `session_list` and `session_deleted` for the list only;
    - suppress the auto-join (`chat.js:1223`); a pick clears `pendingJoinId`.
  - **`starting(cid)`:** accept `session_joined` and `start_failed` only when
    `session_id === cid`, and drop session-scoped frames until joined. That is safe because
    the server sends joined before it spawns.
  - **Opening a conversation** from `pending` or `starting` enters `joining(id)` and
    accepts only that id's `session_joined`.
  - **No more "null means idle".** All 18 `currentSessionId` null-check sites in `chat.js`
    become explicit state checks, including `:1059`, `:1061`, `:1224` and `:1230`. A
    pending pane is never covered by the welcome.
  - **`serializeState`** returns `new/{agent}` while `pending` or `starting`.
  - **Busy, hold and Stop** key on `activeId = currentSessionId || startingId`.
    - `isCurrentBusy()` is true while starting (`chat.js:34-36`, `:1027-1029`).
    - A second Send while starting is held in one slot keyed on `clientId`, and is never
      sent as a plain `message`.
    - Stop while starting sends `cancel`. It is ordered after `start_session` on the socket,
      so it binds to the new session.
- **There is only ever one pending chat.**
  - Picking again **replaces** it (§10 item 14).
  - Opening any conversation **discards** it (item 16).
  - Since nothing was persisted, neither leaves an orphan session.
- **The first Send** sends a new WebSocket action:

  ```
  {action: "start_session", session_id: clientId, agent_name, <the normal message keys>}
  ```

  `clientId` is generated by the client with `crypto.getRandomValues`: 32 lowercase hex
  characters, validated by the server.
  - No format assumption breaks. The `mcp/oauth/handlers.py:27-40` docstring says
    "12-char"; its charset argument still holds, so only the wording is updated.

  **Server order**, in one handler step:
  1. **Validate** through a new shared `_validate_message_payload()`, which returns
     `(content, error)`. It includes `_build_user_content`, which today runs after the
     create (`:2718`). The normal message path uses it too.
     - It checks the `clientId` format, the agent name (missing or `"default"` is
       rejected), empty input, and image shape, count and size.
     - A rejected payload creates nothing (`app.py:2621-2687`).
  2. **Existing id.** Run `_get_or_restore_session(clientId)`. If the status is not
     `not_found`, behave **exactly like `join`**, even if the session is another agent's:
     - an OK session is subscribed, then receives `_build_session_joined_ok` and the pause
       snapshot;
     - a degraded session sets `session = None` and receives the degraded joined frame.

     The content is **not** processed again. That makes the action **idempotent**, and it
     also covers a session restored from the DB but not in memory.
  3. **Reserve the id**, then create. A module-level `dict[str, asyncio.Future]` reserves
     `clientId` before any await. That closes the cross-socket race on reconnect, where the
     old handler can still be inside a slow `factory.create` when the new socket's re-send
     arrives. (The "sequential loop" argument covers a single socket only.)
     - The create is a strict variant, `_create_session(agent_name,
       session_id=clientId, strict=True)`, under a broad `except Exception`.
     - A DB persist failure pops `_sessions[clientId]`, because today the insert failure is
       swallowed (`app.py:1140-1153`) and a primary-key collision would go unnoticed.
     - The narrow `(ValueError, KeyError)` catch at `app.py:2693` is the frozen-build
       ImportError lesson. It is also broadened for the bare-message auto-create.
  4. Only after a successful create, **swap** the socket's subscription to the new session.
  5. Send **`session_joined`** with `is_processing: true`, **overriding** the builder.
     `_build_session_joined_ok` derives it from the lock (`app.py:1391`), and the lock is
     not held until the spawned task runs. Then **spawn** the message task exactly as a
     normal message.

  **Every non-success exit** sends a typed `{type: "start_failed", session_id, error}` and
  `continue`s, so the handler never falls into the message path. The client stays pending,
  restores the composer text and images, and shows the error in the pending pane.
- **The first turn behaves like any later turn.**
  - The optimistic bubble survives the `session_joined` that arrives for a brand-new
    session. Today `renderHistory` wipes it (`chat.js:523-525`).
  - The thinking indicator, Stop and the busy hold queue (F09-04) work during the first
    turn, which `is_processing: true` and the client's `starting` state make possible.
  - This is a leg 3 acceptance item.
- **Reconnect.**
  - **While starting:** the `start_session` is **re-sent with the same `clientId`**. The
    server's idempotency joins the existing session or creates it once, so there is
    neither a duplicate session nor a lost first message.
  - **While joined** (a gap that predates this flight, inside its scope): the first
    `session_list` on a fresh socket sends `join(id)`. Today a reconnect leaves the socket
    unbound, so the next Send would auto-create a default-agent session
    (`chat.js:1223-1224`).
  - **On a re-join**, the optimistic bubble is kept only when `history` is empty;
    otherwise `renderHistory` replaces it. An in-flight session's history already holds
    the user event (`app.py:1739`).
- **The client then canonicalises** with `sync('chat', 'sessions/{id}')` (replace).
  - **If the user leaves Chats while starting**, that sync is dropped and the rail's
    `lastRoute('chats')` stays `chats/~new/{agent}`. A hydrate of that route while
    `joined` to the session the same pending chat started (with no pick since) re-syncs to
    `sessions/{id}` instead of making a new pending chat.
- **The interim UI in leg 3**, on the old DOM:
  - the old history list shows the pending "New chat" item at the top (`history-buckets`);
  - the old header badge shows the agent;
  - the welcome is hidden, and the chrome shows with an empty message log.

  Leg 4 replaces all three.
- **Premise verified.** `app.py` already auto-creates a session, sends `session_joined`
  and then processes the message when a message arrives with no bound session
  (`app.py:~2688-2698`). `_create_session` already accepts `session_id=` (`:1120`). The
  WebSocket loop is strictly sequential per socket, so no same-socket race can happen.
- **`new_session` stays through leg 2** (the backend protocol leg) and **is removed in
  leg 3**, with the client change. Its only callers are then the migrated browser tests,
  and no unit test uses it.
- **Squawk 0111 closes by construction.** The 10s stalled-join timer and the `new_session`
  re-send are gone.
- **`join` of an unknown id answers `join_failed` instead of auto-creating a
  default-agent session** (a leg 2 addition from leg 3b's design review). The client is
  then never handed a session it did not ask for. A foreign `session_joined` is always a
  late reply to a superseded request, and is dropped.
- **A lost reply on an open socket is no longer recovered.** The server always replies, so
  only a socket close triggers a re-send. That is a deliberate consequence of retiring
  squawk 0111's timer.
- **Rationale.** This is the board's behaviour exactly, with no orphan empty sessions and
  no cleanup deletes. Traversal and rail restore of a pending chat are harmless, because a
  pending chat is not persisted (DD2).
- **Trade-off.**
  - It is a backend change: two WebSocket actions plus the removal of one. It gets its own
    leg (2, `ws-start-protocol`), with unit tests in the
    `tests/test_ws_message_branch_crash_guard.py` harness style, which drives the real
    `websocket_endpoint`.
  - Every chats-lane test that starts a chat changes (DD12).
  - `test_router_items.py:700-885` pins "two `new_session` frames produce two rows". It is
    inverted by rename, to "two first sends produce two rows".

**DD2 — Start intents are a route; the picker is an area method.**

- **New route `#chats/~new/{agent}`.**
  - `~new` is the reserved create segment (Flight 2). The agent is encoded with
    `encodeURIComponent`, so a leading `~` is `%7E`.
  - It represents the pending new chat with that agent. Hydrating it recreates the pending
    state, which is safe because nothing is persisted.
  - **An unknown or deleted agent**, or the synthetic default, heals to `#chats` (replace).
    So does bare `#chats/~new`, with no agent.
  - **Who navigates here:**
    - the agent editor's **Chat** action (DD8), with `App.router.go`, guarded;
    - picking in the picker, with `go`. A re-pick while already on a `~new` route uses
      `{replace: true}` (§10 item 14);
    - opening the welcome's "Pick a different agent" leaves the route unchanged until a
      new pick.
  - **Building hrefs.** Always use `App.router.href(...)`, which encodes the agent; never
    concatenate strings. The same applies to DD7 and DD8's `#agents/{name}`.
    `App.router.go` takes a route string, so `go({…})` is a bug: it stringifies to
    `[object Object]`.
  - **Changes needed.** The route follows the router's `create: true` convention.
    `href({destination:'chats', id:'~new', …})` would put `~new` through `enc()` and emit
    `%7Enew` (`router.js:117-120`, `:152-153`).
    - `href({destination:'chats', create:true, agent})` returns
      `#chats/~new/{enc(agent)}`.
    - `parse` returns `{destination:'chats', create:true, agent}`.
    - `resolve` maps it to the area sub `new/{seg}`, and folds bare `chats/~new` and any
      extra segments to `chats`, with `redirected: true`.
    - `areaSubToRoute('chat', 'new/x')` returns `chats/~new/x`.
    - In `_nav.py`, `canonical` folds `chats/~new` to `chats`. `legacy_hash` is changed to
      **raise** for this route: today it would emit `#chat/sessions/~new/x`
      (`_nav.py:187-188`), and `#chats/~new/x` never had a legacy form, so it is **not** a
      `DD2_ROWS` row.
    - The route goes into `PARITY_CORPUS`, which lives in `test_router_core.py:270`.
    - **The announcer** names it "New chat with {agent}". The `describeRoute` key is
      `chats//~new/{enc(agent)}`, so a re-pick announces.
    - **The first send's `sync`** from `~new/{agent}` to `sessions/{id}` is **silent**:
      `isCreateToItem` is false for that key, and the message log already announces the
      message and the reply.
- **`App.chat.openPicker({opener})`** is exported from the chat area.
  - The list's New chat button, "Pick a different agent" and the palette's "New chat…"
    (after `go(App.router.href({destination:'chats'}))` resolves `true`) call it.
  - The palette passes `{opener: <the chats-new-btn>}`. Otherwise Escape would return
    focus to the palette's own opener, which is now hidden, and focus would fall to BODY.
  - The picker is a transient chooser, not a route, so a reload does not reopen it.
  - It must work on a cold chat area: the chat area queues the call until its init is done.
- **Rationale.** A route makes the Chat action guarded, pushable and bookmarkable. A modal
  as a route would reopen on reload and on Back, which the modal rule (Flight 1 DD8) does
  not want.

**DD3 — Bare `#chats`, the empty states and the retired welcome.**

- **Bare `#chats`** keeps Flight 2's auto-join of the most recent session
  (`chat.js:1223-1224`). Recent work stays one click away, and the tests and specs that
  rely on it keep working.
- **No sessions and setup complete.** The list shows "No conversations yet.", and the pane
  shows an `App.ui.emptyState` ("Start a conversation", with a **New chat** action that
  opens the picker). The mascot stays in that empty state.
- **Setup incomplete** (no provider or no agent). The pane shows the existing guidance
  links (`welcome.js:23-50`), rebuilt with DOM APIs. New chat stays enabled. The picker
  then shows its own empty state, which links to create an agent.
- **Retired:**
  - the welcome's agent list (`.chat-welcome-item`, `renderWelcomeList`'s ready mode);
  - the sidebar's "Select Agent" `<select>` (`agent-select`);
  - the header's `new-chat-btn`.

  Each goes through the registry's "Retired testids" table and `RETIRED_SELECTORS`
  (DD12). `chat-welcome` is kept as the testid of the pane's empty and guidance state, so
  the visibility checks in about 20 files keep a stable target.

**DD4 — `App.store` gains `sessions`; recency and counts come from it.**

- **A sixth collection, `sessions`**, from `GET /api/chat/sessions`.
  - One additive backend field: `_session_summary` (`api.py:4441-4448`) gains `platform`,
    which is null for UI sessions. That is the mission's sanctioned "exposing a session's
    platform" change.
  - The pin `test_store_urls_name_the_five_collections` (`tests/test_store_static.py:41`)
    is renamed and inverted for six.
- **`App.store.prime(name, rows)`** is a new API. It replaces a collection's data from a
  push, bumps its generation and clears its in-flight request, as `invalidate` does. A
  racing older `get` therefore cannot overwrite it, and a later `get` cannot join a
  superseded request.
  - The chat area primes `sessions` from every WebSocket `session_list` reply, mapped to
    the summary shape. While Chats is active, the WebSocket stays the source, with no
    extra REST fetches.
  - **The Chats list renders from the store subscription only**, never from both the
    subscription and `session_list`.
  - Off Chats (the palette from Agents, for example), `get('sessions')` fetches over REST.
  - The `LITERAL_LIST` guard (`tests/test_store_static.py`) gains `/api/chat/sessions`.
- **Invalidation map.** New rows, each with a `test_store_static` pin:
  - **agent rename**, which re-points `chat_sessions.agent_name`
    (`repositories.py:352-359`);
  - the agent's **Purge now** (`studio.js:2893`), and any per-session purge;
  - session delete;
  - every `start_session` join, which is added in leg 3 with the action's client side.
- **Freshness bound.** `activate()` sends `list_sessions` when the socket is already open.
  Today it only refreshes agents (`chat.js:1680-1686`). With that, sessions created by a
  connector appear at the next activate, join, done or delete. The list stays unbounded,
  which is a known scale risk, unchanged (digest §2).
- **Recently used** (the picker): the top 5 agents by the latest `updated_at` over sessions
  where `platform` is null and `agent_name` is a live agent in the `agents` store. This
  excludes connector sessions (A32), the synthetic default and deleted agents.
- **Chats count** (the drawer): all sessions of that agent, including connector ones,
  because the drawer describes the agent.

**DD5 — The Chats list is an `App.ui.listPane` (§5.1).**

- **Width.** The aside moves from `--sidebar-w` (240/200) to `--list-w` (300), like
  Agents and Library (`css/base.css:26-58`). At 1024px the chat pane is 652px.
- **Header.** The `listPane` title "Chats". A full-width **New chat** button
  (`btn-filled-primary btn-lg`, square-pen icon, testid `chats-new-btn`) sits in a new
  header **block** slot, with no filter (mission decision 3).
- **Groups.** Today, Yesterday, Last 7 days, Last 30 days and Older, in sentence case.
  A28: the board draws three, and the app keeps the two older groups so that no
  conversation disappears.
- **Rows.** A new `rowStyle: 'chats'`:
  - line 1 is the title (ellipsis) with the time at the end, 11px, `--fg-muted`;
  - line 2 is the agent name, 11px, `--fg-secondary`;
  - connector rows keep their platform badge after the agent name;
  - the selected row has `aria-current="page"` (A12).
- **Time format.** It is formatted by hand in local time, not with `toLocaleString`, so
  Playwright, WebView2 and WebKitGTK agree whatever their locale. English labels:
  - Today: 24-hour `HH:MM`.
  - Yesterday and Last 7 days: the short weekday (`Mon`).
  - Older: the short month and day (`Sep 12`).
  - The pending row: "now".
- **Delete stays.** It is existing function and tests cover it
  (`test_flow_new_chat.py:192-253`, `test_flow_keyboard.py:85-120`). It moves to a new
  `listPane` **row action**: a sibling icon button per row (`aria-label="Delete chat:
  {title}"`), shown on hover and on focus-within, and driving `App.confirmDelete` as
  today. The board omits it, which is recorded as a deviation for the preview (DD13).
  - **Row-action contract**, specified in leg 1 and pinned by the `listPane` contract tests:
    - **Tab order.** Only the roving stop row's action is tabbable (`tabindex=0`); every
      other row's action is `-1`. So Tab goes from the stop row to its action, and then
      out of the list, preserving `test_flow_keyboard.py:85-120`.
    - **Focus restore across `setItems`.** A focused action restores to the same row's
      action. If that row is gone, focus goes to the **neighbouring row**, not the first
      row. Today `focusedEntry` only matches `row.contains(active)`
      (`list-pane.js:314-321`).
    - **Armed state.** `setItems` never rebuilds a row whose action is armed by
      `App.confirmDelete`; it is patched in place (squawk 0088's third-invariant
      precedent). Store priming makes rebuilds frequent.
    - **Row options.** A `dataset` option sets `data-id` and `data-pending`, and the label
      carries `data-confirm-title`.
    - **Mechanics.** `rovingFocus` rewrites only the rows' tabindex on arrow keys
      (`core.js:125-127`), so `listPane` re-derives each action's tabindex in `setStop`
      and on a body `focusin`.
      - The action is a sibling inside the row's `li`, not a `.ui-list-pane-row`. It is
        hidden with `display:none` and revealed on hover or `li:focus-within`;
        `visibility` or `opacity` would break the Tab reach.
      - The armed detection reads `.confirm-delete` on the `li` (`confirm.js:105`,
        `:118`). That coupling is documented.
      - The pending row has no delete action.
- **Row testids.** `chat-row` with `data-id`, and `chat-row-delete`. The pending row has
  `data-pending`.
- **The header block slot sits outside the `<header>`**, below it, because
  `test_ui_library_contract.py:705` pins the header's children.
- **CSS.** `#app-sidebar[data-destination="chats"]` joins the padding-top-zero rule
  (`base.css:51-53`).

**DD6 — Header, new-chat state, composer and telemetry (§5.2–§5.5).**

- **Header.**
  - An `<h1>` with the title, or "New chat".
  - "with {agent}", 12px, `--fg-muted` (testid `chat-agent-line`).
  - **The drawer toggle is added in leg 6, with the drawer**, not with this header in
    leg 4: `btn-ghost`, icon only, panel-right icon, `aria-label="Show this chat's
    agent"`, `aria-pressed`, `aria-controls` the drawer (testid `chat-drawer-toggle`).
    `aria-controls` must always resolve (DD7), because `_a11y_resolve.js:76-82` checks it
    unless `aria-expanded="false"`.
  - The old `h2.session-agent-badge` is retired (DD12).
- **New-chat state** (§5.4).
  - A `badge--{providerType}` whose text is the **model** (A20 as drawn).
  - An `<h2>` with the agent name, then the description, then "Pick a different agent"
    (`btn-ghost btn-sm`, testid `chat-pick-different-btn`, calls `openPicker`).
  - The container's testid is `chat-new-state`. The board calls this state "the welcome",
    but `chat-welcome` names the empty and guidance state (DD3).
  - No telemetry.
- **Composer** (§5.5).
  - **Leg 4 removes all three chat sinks**, because it rewrites the header and the welcome
    inside the content markup:
    - the sidebar (`chat.js:257-266`);
    - the content (`chat.js:273-324`), with the composer's markup carried over unchanged;
    - `history-buckets.js`'s `delBtn.innerHTML`.

    The baseline (`tests/test_ui_guards.py:134-140`) empties for chat.
  - **Leg 5 restyles the input area only.**
  - A `<textarea rows=2>` keeps testid `chat-input`, with a visually hidden "Message"
    label and the placeholder "Message {agent}…".
    - **Enter sends** and **Shift+Enter** inserts a newline.
    - Tests that `fill` then press Enter keep working.
  - The box shows the focus ring with `:focus-within`, using the app's pinned focus form
    (A25).
  - **Attach** is a `btn-ghost btn-sm` with a paperclip icon and
    `aria-label="Attach images"`. The attachment really is image-only, so the board's
    "Attach a file" would be untrue.
  - **Squawk 0110.** The hidden file input gets `aria-label="Attach images"`, the squawk's
    primary fix, with a resolver-backed test.
    - `aria-hidden` would not satisfy it: `tests/browser/_a11y_resolve.js:18-20` selects
      every `input:not([type=hidden])` and does not skip `aria-hidden`.
  - **Enter to send** is guarded on `e.isComposing || e.keyCode === 229`, so an IME
    composition's Enter does not send. WebKit's composition-commit Enter can arrive with
    `isComposing: false`.
  - The **model id** comes from the store, in mono, 11px.
  - **Stop** stays (existing function).
  - **Send** is `btn-filled-primary`, with the send icon and label.
- **Telemetry** moves from its absolute overlay to the flex-end row above the composer
  (§5.3). The `_TELEMETRY_RESTING_OPACITY` pin (`tests/test_design_tokens_a11y.py:771`) is
  updated to the new rule rather than deleted.
- **Drafts.** An unsent draft is **not** a leave-guard source. It survives a session switch
  as today, so nothing is lost. Per-session drafts are out of scope.
- **Icons.** `search`, `panel-right`, `paperclip` and `settings` (the gear for Open agent
  settings) are added to `js/icons.js`. `square-pen` already exists (`icons.js:26`).
  with Lucide geometry (reference spec Appendix B).

**DD7 — The agent drawer (§5.7, A13, A21).**

- **The control.** A new `App.ui.drawer` factory: a non-modal `<aside>` with a heading,
  body and footer.
  - Escape closes it while focus is inside, and focus returns to the toggle (the Flight 1
    DD8 rule).
  - It installs no document listener; the factory contract tests pin that.
- **Slot.** It is a shell sibling after `<main>` in `.app-shell-row`, matching the board
  (B3:L166), so the skip link and `<main>` are unchanged.
  - It is shown only on Chats; on other destinations it is not rendered.
  - Its landmark label is "This chat's agent".
- **Push and overlay.**
  - At 1280px and wider it **pushes** (a flex sibling, 320px) and is **open by default**.
  - Below 1280px it **overlays** the right of the chat pane, with a border and
    `--shadow-modal`, no scrim and no outside-click close (a non-modal panel). It is
    **closed by default** there, so the 652px chat pane is not covered on arrival.
  - The open state persists in `localStorage` (`chat-drawer-open`, try/catch), separately
    for the push and overlay modes. The desktop shell keeps it, because
    `desktop/shell.py` sets `private_mode=False`.
  - A **resize across 1280** re-evaluates the mode and applies that mode's persisted state.
  - At 1024 the open overlay covers the right of the composer, Send included. That is
    accepted because the overlay is closed by default, and it is a preview question (DD13).
  - At 1280 and wider the open push leaves a 588px chat pane, narrower than the 652px pane
    at 1024 with the drawer closed. Also a preview question.
- **No chat.** With no conversation or pending chat (the empty or guidance state), the
  header and its toggle are not shown and the drawer is `hidden`.
  - The drawer element is **created once with the chat area** and toggled with `hidden`.
    It is never removed while the header exists, so the toggle's `aria-controls` always
    resolves.
  - On other destinations it is `hidden` too.
- **Header.** 48px, so its hairline lines up with the chat header (A21). It shows the agent
  name and a `badge--{type}` with the **provider type** (A20 as drawn).
- **Body:**
  - the description;
  - a `<dl>` with Model (mono), Provider (display name) and Chats (count, DD4);
  - **"What it can use"** (A13), read-only and computed client-side:
    - **Knowledge bases**, by name (`kb_ids` against the store);
    - **MCP servers**, by name, with tool counts where `App.usage.mcpToolCount` knows
      them. Unknown ids are skipped: the self-configuration loopback source is in
      `mcp_source_ids` (`self_configuration/manage.py:216-218`) but hidden from the plain
      `mcp-sources` list;
    - **Built-in tools** as categories with enabled counts, computed from the agent's
      `enabled_tools` and `disabled_tools` and the global configs (one
      `GET /api/tools/configs` per drawer open);
    - **Self-configuration on**, when it is (one `GET …/self-configuration` per open).
    - The built-in category table is extracted into one shared module
      (`js/tool-categories.js`), replacing the three copies (`studio.js:460-477`,
      `admin/tools-grid.js:19`, `admin/tools-editor.js:81`).
- **Footer.** **Open agent settings** (`btn-outlined-primary`, gear icon, testid
  `chat-drawer-settings-link`).
  - It runs `App.router.go(App.router.href({destination:'agents', id: name}))`, which is
    guarded.
  - On a commit it clears the Agents filter (§10 item 18).
    - The Agents list pane is studio-owned and survives a visit to Chats, because
      `deactivate` does not destroy it.
    - So studio exports `App.studio.clearAgentFilter()`, built on a new
      `listPane.setQuery('')`. The drawer and the palette call it.
- **Synthetic default or deleted agent.** The drawer shows the name and "This agent no
  longer exists", or "The default agent", with **no settings link** (mission "Picker edge
  cases").

**DD8 — The agent editor's "Chat" action; the studio `dirty` flag stays single.**

- **Chat** is a header action on the agent editor (`btn-outlined-primary`, testid
  `agent-chat-btn`).
  - It runs `App.router.go(App.router.href({destination:'chats', id:'~new', agent:
    name}))`, so a dirty editor asks once (SC2). This is the reachable SC2 case: from
    Chats no dirty source can exist, because leaving a dirty editor already asked.
  - It is hidden in create mode.
- **The studio `dirty` flag stays one closure flag in this flight.** The Chat action, the
  drawer link and the palette all leave through `go()`, so no new writer or reader is
  added. Splitting it per editor is part of the next mission's editor-internals redesign.
  This is a deliberate choice against the Flight 3 debrief's "decide before Flight 4",
  recorded here.
- **Squawk 0118 is bundled into this leg.** It documents the editor Cancel and dirty
  contract in `the_one/agents.md`, the same documentation surface the Chat action's
  header chrome extends.

**DD9 — Ctrl K and the rail's jump-to control.**

- **The rail control.** `App.ui.rail` gains a **bottom action** slot. The jump-to control is
  a 44px `btn-ghost` with a search icon, pinned to the bottom of the rail.
  - Its accessible name is "Jump to (Ctrl K)", with `aria-keyshortcuts="Control+K"`.
  - Its testid is `rail-jump-to`.
  - The factory still installs no document listener (`test_ui_rail_contract.py:244`).
- **A shell-level `keydown` listener** lives in `app.js`, alongside the rail mount. Library
  factories may not install document listeners (Flight 1 DD1).
  - **Ctrl+K** opens the palette on Windows and Linux. On macOS it is **Meta+K** only,
    because Ctrl+K is kill-line in Cocoa text fields. It calls `preventDefault()` and works
    **from inside inputs and textareas**: Ctrl K is not a text-editing key on Windows or
    Linux.
  - It is ignored while `e.isComposing || e.keyCode === 229` (IME).
  - If the palette is already open, it focuses the palette's input.
  - It is ignored while another modal is open (the leave-guard confirm or the picker), so
    the topmost-modal rule holds. It asks through a new public `App.ui.modal.anyOpen()`.
  - Escape belongs to the topmost modal, as today.
  - **Opener rule.** The opener is the element focused at keydown. Escape returns focus to
    it, and so does Stay after a guarded pick.
- **The "Esc" close buttons** (picker and palette) read "Esc", with the accessible name
  "Close (Esc)" (A11; label-in-name holds).
- **Desktop shells.** pywebview defines no accelerators.
  - **WebKitGTK.** The probe (`scripts/webkitgtk_probe.py`) only evaluates JavaScript, and
    a synthetic `dispatchEvent` proves nothing about GTK key handling. Leg 7 extends it
    with a **real key injection**: `xdotool` on WSLg or a synthesized GDK key event,
    against a dev instance on **8486 or higher**. If no real-key path works on this host,
    the premise is recorded as **unverified** and carried forward.
  - **WebView2** is checked at Flight 5's packaged build. That is a cross-flight
    carry-forward, recorded in the mission's Known Issues, because Flight 5's scope is
    window chrome and would not pick it up implicitly.

**DD10 — The jump-to palette (§9, A17).**

- **The control.** `App.ui.modal` (DD14 options) holds an input bar and an
  `App.ui.searchList`.
  - The placeholder is "Jump to an agent, chat, library item or setting".
  - The footer reads "Ctrl K from anywhere · Enter to open".
- **Candidates**, in the board's order:
  1. agents, A–Z;
  2. chats, newest first (from `sessions`);
  3. the **New chat…** action;
  4. knowledge bases;
  5. MCP servers;
  6. **connectors** (where "Library · Connector"; SC5 says "Library items");
  7. Settings pages, in nav order, with Design language only in dev mode.
- **"Where" copy** is per §9. Settings pages read `Settings · {group}`, or `Settings` for
  Providers, as drawn.
- **Matching** is a case-insensitive substring over `label + " " + where`, trimmed, and the
  results are capped at 8. With an empty query the palette shows the first 8 candidates,
  which is the board as drawn: agents first. That is an explicit preview question (DD13),
  not a silent pick.
  - *Superseded 2026-10-06 (DD13 preview, option C; leg 9 `palette-empty-mix`):* the empty
    query now shows up to 3 recent chats, New chat…, up to 4 recently used agents (the
    picker's `recentAgents`), then the board order as fill, 8 in total. A typed query is
    unchanged.
- **A Settings page table** is extracted into one shared module (`App.settingsPages`), used
  by the Settings nav, the router's labels and the palette, so the palette does not
  duplicate `admin.js:174-190`.
- **Empty result.** `No matches for "{q}".`, which the board does not define.
- **Active row and keys** (A10, A11):
  - the first result is active;
  - ↑ and ↓ move, Home and End jump, and the pointer hover sets the active row;
  - Enter opens the active result.
  - It uses `aria-activedescendant` and `aria-selected` (the Flight 1 DD14 combobox plus
    listbox model).
- **Opening a result.** The palette **closes itself first**, then navigates with
  `go(App.router.href({…}))`, so a dirty editor's confirm is the only modal (the Flight 1
  DD8 chaining rule).
  - An agent opens `#agents/{name}` and clears the Agents filter through
    `App.studio.clearAgentFilter()`.
  - A chat opens `#chats/{id}`, which discards any pending chat.
  - **New chat…** goes to `#chats`, then calls `openPicker`.
  - A Library item opens its item route, and a Settings page its section.
- **The palette has no visible title.** The modal gains an `ariaLabel` option ("Jump to").
- **Cold data.** On open it calls `App.store.get` for every collection it lists and renders
  as each one arrives.

**DD11 — Lanes: split `shared` first (squawk 0117).**

- **Leg 1 first adds a `contracts` lane** holding the `test_ui_*` contract files, and
  `shared` stays the complement of all six lanes. That lands before any new dual-engine
  contract.
  - The union check (the file list and test count equal to `-m browser`) is a leg-1
    acceptance item.
  - It updates `CLAUDE.md`'s lane list and the `--lane` usage.
- **New flow tests:**
  - `test_flow_chat_*` (picker, drawer, composer) land in `chats` automatically;
  - `test_flow_jump_to*` lands in `shared` as the complement, with no glob needed;
  - `test_agents_chat_action*` lands in `agents`.
- **Local WebKit must really run.** CI runs it only after merge, with
  `THE_ONE_REQUIRE_WEBKIT=1` (`ci/tasks/browser.yml:34`). So every leg that adds or changes
  a library control runs the `contracts` lane with `THE_ONE_REQUIRE_WEBKIT=1`, and a skip
  there is a failure, not a pass.

**DD12 — Test migration through a `_chats.py` helper.**

- **`tests/browser/_chats.py`:**
  - `start_chat(page, agent)` (via the picker; returns at the pending state);
  - `send_first(page, text)`;
  - `expect_chat(page, agent, title=None)` (the header and agent line);
  - `chat_row(page, id)` and `new_chat_button(page)`.

  These absorb the 45 `.chat-welcome-item` and 51 `.session-agent-badge` sites across 22
  files (digest §7).
- **`seed_session`** in `tests/browser/seeders.py` uses `POST /api/chat/sessions` with
  timestamps and `platform`, to fill the recency groups and the Recently used group.
- **Retired selectors.**
  - **The testids** `agent-select` and `new-chat-btn` go into both the registry's
    "Retired testids" table and `RETIRED_SELECTORS`.
    - `agent-select` must match **exactly**. `_RETIRED_RE` has only a left boundary
      (`test_nav_helper.py:320`), and `agent-select` would otherwise match the live
      Flight 3 testid `agent-select-empty`.
    - The left-only boundary is deliberate: it catches `entity-tile-name`
      (`test_nav_helper.py:318-320`). So leg 4 adds a per-entry exact list,
      `RETIRED_EXACT = ("agent-select",)`, compiled as `(?<![\w-])agent-select(?![\w-])`,
      and the coverage test checks the union of both lists.
  - **The class fragments** go into `RETIRED_SELECTORS` only:
    - `chat-welcome-item`;
    - `session-agent-badge`;
    - `session-item`, `session-list` and `list-item-delete`, which have 33 sites today.

    They are not testids, and the registry-coverage test is one-directional.
  - A retired selector cannot come back (the Flight 3 L6 ratchet).
- **`_lists.py`** gains a `chats` list, so `list_row` and `open_item` work beside
  `_chats.py`.
- **The migration runs seam first.** Leg 3 first moves the 23 files onto `_chats` helpers
  that implement the **old** semantics, and the lane stays green. Then it flips the
  semantics inside the helpers, so the no-session-until-first-send change lands in one
  place.
- **Rewrites budgeted:**
  - **Leg 3:** `test_flow_chat_start_recovery.py` pins the 10s timer and
    `App.chatStartJoinTimeoutMs`. It is inverted by rename into a reconnect re-send test.
  - **Leg 4** deletes or rewrites the tests that pin retired surfaces:
    - `test_flow_new_chat.py`'s welcome listbox, dropdown and header tests;
    - `test_flow_keyboard.py::test_session_list_shape`;
    - `test_shell_rail.py`'s 240/200 Chats aside widths;
    - `test_router_items.py`'s `button.session-item`.

    So leg 4 is not just helper-body changes.
- **The new chat surfaces live in modules** under `areas/chat/*.js` (start flow, list,
  picker, drawer), like studio's sub-modules, rather than growing the 1,691-line `chat.js`
  closure.
- **Every new script** bumps the `index.html` asset-ref pin
  (`tests/test_index_asset_cache_busting.py:73`, currently 71). Dev instances need a
  restart after an `index.html` edit, because it is `lru_cache`d.
- **New testids** are registered: `chats-list`, `chats-new-btn`, `chat-row`,
  `chat-row-delete`, `agent-picker`, `agent-picker-search`, `agent-picker-row`,
  `chat-header`, `chat-agent-line`, `chat-new-state`, `chat-pick-different-btn`,
  `chat-drawer`,
  `chat-drawer-toggle`, `chat-drawer-settings-link`, `agent-chat-btn`, `rail-jump-to`,
  `jump-to`, `jump-to-input` and `jump-to-result`.
- **Behavior specs are authored against testids and roles, not layout nouns** (Flight 3
  debrief lesson).

**DD13 — An operator preview before the close gate, non-blocking (Flight 3 debrief,
recommendation 1).**

- **After the last UI leg (5) and before the close-gate runs (leg 8)**, the Flight Director
  prepares:
  - a seeded dev instance on 8485 (30+ agents, sessions across agents, ages and a
    connector, knowledge bases, MCP servers);
  - screenshots in both themes at 1440×900 and 1024×768;
  - a comparison page beside the board, published as a private artifact.
- **Explicit questions:**
  - session delete as a row action (DD5);
  - the palette's empty-query content (DD10) (resolved 2026-10-06: option C, leg 9);
  - the drawer closed by default below 1280px, and its overlay covering Send at 1024
    (DD7);
  - the 588px chat pane beside the open drawer at 1280 (DD7);
  - "Attach images" (DD6);
  - the older recency groups (DD5);
  - the picker and palette scrim using the existing `--scrim` (dark 0.5), not the
    board's 0.3 (DD15, A30);
  - the 1024 overlay keeping the header toggle above it (`z-index`), so a mouse user can
    close it. The board has no close control inside the drawer; this is a leg 6 finding;
  - the previously uncategorised `find_platform_destination` built-in now appearing under
    Connectors in the Tools tab and Settings (a leg 6 finding).
- **The operator is notified, and the flight does not wait.** Feedback that arrives before
  PR merge is folded in as a leg, with targeted spec re-runs. That respects the mission's
  autonomous-execution constraint and still moves the visual review ahead of the gate.

**DD14 — Control-library additions, built where consumed (Flight 1 DD14).**

- **`App.ui.searchList`.** A combobox input plus a grouped listbox:
  - `aria-activedescendant` and `aria-selected`, with group labels;
  - an active row with hover and keyboard (↑↓, Home, End, Enter);
  - an empty state;
  - focus stays in the input.

  It is used by the picker and the palette.
- **`App.ui.modal` options**, built in leg 1:
  - `width` and `top` (picker 640 at top 72; palette 600 at top 96);
  - `initialFocus` (the search input, not the first button);
  - a header close button ("Esc");
  - a `footer` slot;
  - a picker/palette layout without the action row.

  **`ariaLabel`** (for a modal without a visible title, the palette) and **a public
  `App.ui.modal.anyOpen()`** (for the Ctrl K rule) are built in leg 7, where they are
  consumed.
  - The backdrop keeps the **existing `--scrim` token**: dark 0.5 (`tokens.css:68`), light
    0.3 (`:215`), already used by `::backdrop` (`components.css:1466`). Flight 1 resolved
    A30, so no token is added or changed.
- **`App.ui.drawer`** (DD7) is **built in leg 6**, where it is consumed.
- **`App.ui.rail`'s bottom action slot** (DD9) is **built in leg 7**, where it is consumed.
- **`App.ui.listPane`** gains, in leg 1:
  - `rowStyle: 'chats'`;
  - a header `block` slot, below the `<header>`;
  - per-row actions under the DD5 row-action contract;
  - a row `dataset` option.

  `setQuery` is built in leg 6, for `App.studio.clearAgentFilter`.
- **Each new or extended factory** gets a demo on the design-language page, an inventory
  row, registered testids and contract tests in both engines (Chromium and WebKit), in the
  new `contracts` lane. They are ES5, with no HTML-string sinks.

**DD15 — Reference spec §15 items owned by Flight 4.**

| Item | Resolution |
|---|---|
| A10 | Active-row, hover and focus-visible styles for picker and palette rows (DD14) and for chat rows. |
| A11 | Ctrl K, Escape and Enter are bound (DD9, DD10). The Esc button's name is "Close (Esc)". |
| A13 | "What it can use" in the drawer (DD7). |
| A16 | The picker matches name, model, provider type slug and description. **Filtered results are A–Z**, not data order, for consistency with the Agents list; a recorded deviation. "All agents" repeats the recent agents, as drawn. |
| A17 | The palette: board order, cap 8, a new empty state, an active row (DD10). The empty query is a mix of recent chats, New chat… and recent agents since leg 9 (operator option C). |
| A20 | Badge text as drawn: the welcome shows the model, the drawer the provider type. |
| A21 | The drawer header is 48px and lines up with the chat header (DD7). |
| A25 | `:focus-within` ring on the composer box. The palette input's ring is on its bar (DD6, DD14). |
| A28 | Today, Yesterday, Last 7 days, Last 30 days, Older (DD5). |
| A29 | Created on the first send (DD1). |
| A30 | Already resolved by Flight 1 (`--scrim` per theme). The picker and palette use it, and the drawer overlay has no scrim (DD7, DD14). The dark 0.5 versus the board's 0.3 is a preview question (DD13). |
| A32 | Connector sessions are excluded from Recently used (DD4). |

**DD16 — Behavior specs and apparatus.**

- **New: `start-a-chat`** (SC3, SC10, both themes), against a seeded instance with 30+
  agents and sessions across agents and ages:
  - **New chat** opens the picker (Recently used, then All agents, with focus on search);
  - search narrows, and Escape closes;
  - **picking** shows the pending row, the header and the new-chat state;
  - **picking again** replaces the pending row;
  - **the first Send** creates exactly one session: one row, and the URL is `#chats/{id}`;
  - **opening another chat** discards a pending one;
  - **the drawer** shows the facts and what the agent can use, pushing at 1440 and
    overlaying at 1024;
  - **Open agent settings** lands on the agent with the filter cleared. It is a clean
    pass: no dirty source can exist on Chats;
  - **the agent editor's Chat**, from a **dirty** editor, asks once. Stay keeps the edit;
    Continue starts a pending chat with that agent. That is the reachable SC2 case;
  - delete from a row.

  It is drafted with this flight (status `draft`) and finalized in leg 8.
- **New: `jump-to-palette`** (SC5, SC2 half, both themes):
  - Ctrl K from Agents, from inside an input and from Settings;
  - the rail control;
  - the empty query and its cap;
  - type to match each kind;
  - ↑, ↓ and Enter;
  - open an agent (filter cleared), a chat, "New chat…" (the picker opens), a knowledge
    base, an MCP server and a Settings page;
  - from a dirty editor, pick → one confirm → Stay keeps the edit;
  - Escape closes it.

  It is drafted with this flight and finalized in leg 8.
- **Apparatus**, audited on both axes:
  - **To act:** the CDP-driven headless Chromium (DD12 of Flight 3, the default) with real
    key events, so Ctrl K reaches the page's `keydown`.
  - **To observe:**
    - the DOM and accessibility tree for rows, groups and `aria-activedescendant`;
    - `location.hash` and `history.length`;
    - the WebSocket frames, through CDP `Network.webSocketFrameSent` (the count of
      `start_session` frames, DD1);
    - the REST `GET /api/chat/sessions` count (exactly one new session per first send);
    - screenshots for the drawer layout at 1440 and 1024.
- **Re-authored** where they name retired surfaces, against testids:
  - `workbench-navigation` step 2;
  - `shell-navigation-smoke` step 3;
  - `chat-roundtrip` step 3;
  - `vision-round-trip` step 1;
  - `agent-purge-now-clears-history` step 6;
  - `stub-connector-round-trip` step 5;
  - re-grep the generic "start a new chat with X" specs at leg 8.
- **Run at close:**
  - `start-a-chat` (Light and Dark);
  - `jump-to-palette` (Light and Dark);
  - `workbench-navigation`;
  - `shell-navigation-smoke`;
  - `chat-roundtrip`;
  - `vision-round-trip`, if the mock vision path is available; otherwise it is recorded as
    not run.

### Citation Audit

From the Flight 4 research digest (read-only reconnaissance of `c3f0a86`, saved in the
flight log's Reconnaissance Report). Leg designs re-verify at leg start.

| Citation | Status |
|---|---|
| `app.py` WebSocket handler: `new_session` persists at once (`:2559-2580`; `_create_session` `:1117-1155`); a message with no bound session auto-creates and sends `session_joined`, then processes (`:~2688-2698`) | verified (research; Flight Director read `app.py:2688-2700`) |
| `app.py` `_session_to_list_payload` carries `platform` (`:1356-1379`); REST `_session_summary` lacks it (`api.py:4441-4448`) | verified (research) |
| `chat.js` `startSessionWith` `:470-498`; `armPendingStartTimer` `:509-521`; `session_list` drain `:1196-1211`; auto-join `:1223-1224`; `renderHistory` `:523`; `showWelcome` and `showChrome` `:434-443`; sinks `:257-266`, `:273-324` | verified (research) |
| `history-buckets.js` buckets `:6-33`; rows `:35-109`; delete button `:97-106` (`delBtn.innerHTML` sink `:138-140`) | verified (Architect, cycle 1) |
| `app.py` `_send_to_session` payloads carry no `session_id` (`:1442-1457`); `new_session` leaves before creating (`:2561-2565`); message validation precedes the auto-create (`:2621-2687`); the narrow `(ValueError, KeyError)` catch (`:2693`); `is_session_processing` is lock-based (`sessions/_locks.py:23-31`) | verified (Architect, cycle 1) |
| `--scrim` exists per theme (`tokens.css:68`, `:215`), used by the modal `::backdrop` (`components.css:1466`); `_a11y_resolve.js:18-20` does not skip `aria-hidden`; `_RETIRED_RE` left boundary only (`test_nav_helper.py:320`); `list-pane.js:314-321` `focusedEntry`; index asset-ref pin `test_index_asset_cache_busting.py:73` (71) | verified (Architect, cycle 1) |
| `chat.js:586-593` `joinSession` sets `currentSessionId` before the reply; the stale-join guard `:1230` passes while it is null; busy and hold key on `currentSessionId` (`:34-36`, `:1027-1029`); `_create_session` swallows a DB insert failure (`app.py:1140-1153`); `chat_sessions.id` is the PK (`schema.py:92`); `_build_session_joined_ok` derives `is_processing` from the lock (`app.py:1391`); `router.js:117-120` `enc()` would turn `~new` into `%7Enew`; `_nav.py:187-188` `legacy_hash`; `PARITY_CORPUS` in `test_router_core.py:270`; `square-pen` exists (`icons.js:26`); `_a11y_resolve.js:76-82` `aria-controls` check; `_TELEMETRY_RESTING_OPACITY` at `:771` | verified (Architect, cycle 2) |
| `router.js` chats parse and href id-only `:152-153`, `:180-181`; `go` `:637-659`; `sync` `:668-701`; `SECTIONS` `:80-93` private | verified (research) |
| `store.js` five collections `:29-35`; no prime API; pinned by `tests/test_store_static.py:41` | verified (research) |
| `ui/rail.js` links only `:55-75`; `test_ui_rail_contract.py:244` forbids document listeners | verified (research) |
| `ui/modal.js` `open()` focus order `:198`; card `max-width:480px` (`components.css:1446-1480`) | verified (research) |
| `ui/list-pane.js` `rowStyle` `'agents'|'library'` only `:7`, `:118`; no block slot or row action | verified (research) |
| `studio.js` `var dirty` `:365`; `isDirty` source `:3855-3858`; `editorOpen` `:3848-3853` | verified (research) |
| `admin.js:174-190` Settings groups in a closure; tool category tables `studio.js:460-477`, `tools-grid.js:19`, `tools-editor.js:81` | verified (research) |
| `tests/test_ui_guards.py:134-137` chat sink baseline | verified (research) |

### Prerequisites

- [x] Flight 3 completed (`c3f0a86`). The branch `flight/04-chats-and-jump-to` stacks on
  `flight/03-list-and-detail`.
- [ ] PR #219 merged to `main`. **Not required to start.** After the squash, rebase with
  `git rebase --onto origin/main c3f0a86`. Check at each leg start.
- [ ] A dev instance on 8485 with a scratch data dir. 8485 currently runs the Flight 3
  checkpoint instance (`/tmp/the-one-f3-checkpoint`).
  - Keep it until PR #219 merges, or until DD13 reuses it after a reseed. **Re-verify its
    `/proc/<pid>/environ` before any reseed.**
  - Leg checks use their own ports (8486 and up), with the environment verified from
    `/proc/<pid>/environ`. **Never 8484.**
- [x] The behavior apparatus: a CDP-driven Chromium, as in Flight 3's ten runs. goldfinch
  input is still unverified, so it is not used.
- [x] `THE_ONE_TEST_NETNS=1` for browser lanes on this host.
- [ ] **WebKit runs locally, not skipped.** Per leg, the `contracts` lane runs with
  `THE_ONE_REQUIRE_WEBKIT=1` (DD11).
- [ ] The WebKitGTK probe, with a real key-injection path for the Ctrl K premise (DD9).
  Built and verified in leg 7, on 8486 or higher.

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Citation Audit complete
- [ ] Prerequisites verified, or explicitly deferred with a re-check point
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

The order is controls and data first, then the protocol, the client flow, the list and
picker, the composer, the drawer and the palette. Behavior specs and the close gate come
last, after the non-blocking preview. Each control is built in the leg that consumes it
(Flight 1 DD14).

1. **`controls-and-data`.**
   - The `contracts` lane split comes first (DD11).
   - Then the `App.ui` additions that leg 4 consumes (DD14):
     - `searchList`;
     - the `modal` options (`width`/`top`, `initialFocus`, header close, footer);
     - the `listPane` additions (`chats` row style, block slot, row actions under the DD5
       contract, `dataset`).

     Each comes with its demo, inventory row and dual-engine contracts, with WebKit
     actually running.
   - The `sessions` store collection with `prime`, the invalidation rows (except the
     `start_session` row), the `LITERAL_LIST`, and the REST `platform` field (DD4).
2. **`ws-start-protocol`** (DD1, server side).
   - `_validate_message_payload()`, shared with the message path.
   - The `leave` action: non-persisting, touches `last_activity`, never cancels.
   - The idempotent `start_session`: validate, existing-id join, id reservation, strict
     create, swap, then joined with `is_processing: true`, then spawn; `start_failed` on
     every non-success exit.
   - The broadened auto-create catch.
   - Unit tests in the `test_ws_message_branch_crash_guard.py` style. `new_session` is
     kept.
3. **`chats-test-seam`** (3a, DD12). `_chats.py` and `seed_session`, migrating about 23
   files onto the helpers with today's semantics. No app change, and every lane stays
   green. It was split from 3b at 3b's design review.
4. **`start-flow-client`** (3b; DD1 client side, DD2), on the existing DOM.
   - The state machine (`idle`, `joining`, `joined`, `pending`, `starting`), with inbound
     frame gating, the explicit state checks at the 18 `currentSessionId` sites, the
     `activeId` busy/hold/Stop, reconnect (re-send while starting, re-join while
     joined), and the first turn behaving like any turn.
   - The router's `#chats/~new/{agent}` (create convention, resolve folding,
     `areaSubToRoute`, the announce key, the silent first-send sync), `_nav` and
     `PARITY_CORPUS`.
   - The existing entry points rewired to `go(href({destination:'chats', create:true,
     agent}))`, with the interim pending UI.
   - `new_session` removed, and the `start_session` invalidation row.
   - Tests:
     - the `_chats.py` bodies flipped;
     - `test_flow_chat_start_recovery.py` inverted;
     - `test_router_items` inverted by rename.

   This closes squawk 0111.
5. **`chats-sidebar-and-picker`** (4a) and **`chats-pane`** (4b). These were split at
   leg 4's design review (DD3, DD5, DD6 header and new-chat state).
   - The Chats list on `listPane`: groups, hand-formatted times, the delete row action, the
     New chat block, the 300px aside and the padding rule.
   - The picker (`searchList` in `modal`), the header with its agent line, the
     `chat-new-state`, and the empty and guidance states.
   - The retired welcome list, dropdown and `new-chat-btn`, through the registry,
     `RETIRED_EXACT` and the class fragments.
   - **All three chat sinks removed.**
   - The pinned old-surface tests rewritten (DD12).
6. **`composer-and-telemetry`** (DD6). The input area restyled:
   - the textarea, with Enter and Shift+Enter and the IME guard;
   - the focus-within ring;
   - attach, with squawk 0110 (`aria-label`);
   - the model id, Stop and Send;
   - the telemetry row, with the opacity pin updated.
7. **`agent-drawer-and-chat-action`** (DD7, DD8).
   - `App.ui.drawer` (demo, inventory, contracts), created once and toggled with `hidden`.
   - The header toggle.
   - Push and overlay, and "what it can use".
   - The shared tool-categories module.
   - `listPane.setQuery`, `App.studio.clearAgentFilter`, and Open agent settings.
   - The agent editor's Chat.
   - Squawk 0118's documentation.
8. **`jump-to-palette`** (DD9, DD10).
   - The rail's bottom slot and control.
   - The modal's `ariaLabel` and `anyOpen`.
   - The shell Ctrl K listener (Meta on macOS, the IME guard, the opener rule).
   - The shared Settings page table.
   - The candidates and picks.
   - The WebKitGTK probe's real key injection.
9. **`behavior-specs-and-close`.**
   - The DD13 preview, published and not awaited.
   - Finalize the two new specs and re-author the affected specs.
   - The gates: unit, all six lanes and both engines.
   - The flight-end review, then the close-gate runs.
   - The behavior-test crew-file update (Flight 3 debrief, recommendation 5).

### Checkpoints

- [ ] L1: the `contracts` lane is live and the six-lane union is exact.
  - `searchList`, the `modal` options and the `listPane` additions pass their contracts in
    Chromium and WebKit, with WebKit actually running. Each has a demo and an inventory row.
  - `sessions` is in the store and primed from the WebSocket, and REST carries `platform`.
- [ ] L2: unit tests pin the `leave` and `start_session` behaviour:
  - validate first;
  - every failure path sends `start_failed` and creates nothing;
  - the idempotent join of an existing or restored id;
  - the reserved-id race;
  - `is_processing: true`;
  - `leave` never cancels.
- [ ] L3a: every chat-starting browser test goes through `_chats.py`, with all lanes green
  and no app change.
- [ ] L3b: picking (still through the old entry points) creates a pending chat.
  - It sends only a `leave`, and no session-creating frame.
  - Frames in flight cannot take the pending chat over, including a late
    `session_joined` on a cold `#chats`.
  - The first send creates exactly one session, and the first turn behaves like any turn
    (hold queue, Stop).
  - A reconnect while starting re-sends idempotently, and a reconnect while joined
    re-joins.
  - `#chats/~new/{agent}` works, and the chats lane is green on the flipped `_chats.py`.
- [ ] L4a and L4b: New chat opens the picker.
  - The list is cross-agent and grouped, with row delete under the row-action contract.
  - The dropdown and the welcome list are gone, the retired selectors are guarded, and the
    chat sinks are gone.
- [ ] L5: the composer is a textarea with a focus-within ring, Enter sends (IME-safe),
  squawk 0110 is closed, and telemetry sits in its row.
- [ ] L6: the drawer pushes at 1440 and overlays at 1024.
  - It shows what the agent can use, and Open agent settings is guarded and clears the
    filter.
  - Chat from a dirty agent editor asks once, and the squawk 0118 documentation is written.
- [ ] L7: Ctrl K and the rail control open the palette, it finds every kind, and each pick
  lands. A pick from a dirty editor asks once. The WebKitGTK Ctrl K premise is verified,
  or recorded as unverified.
- [ ] L8:
  - the preview is published;
  - the specs are finalized and re-authored;
  - all gates are green;
  - the flight-end review is confirmed;
  - the close-gate runs pass.

### Adaptation Criteria

**Divert if**:
- The pending-chat isolation cannot be achieved: the client's state gate cannot tell a
  stale frame from a current one. Or the idempotent `start_session`, with its id
  reservation, cannot avoid both a double session and a lost first message across a
  reconnect. (A same-socket race cannot happen, because the loop is sequential; the
  cross-socket race is what the reservation covers.)
- WebKitGTK swallows Ctrl K before the page sees it, so there is no page-level fix (DD9).
  The fallback is the rail control plus a documented alternative shortcut, as a design
  change.
- The `listPane` extensions cannot meet both Agents and Chats without breaking Flight 3's
  contracts.

**Acceptable variations**:
- Leg 5 merges into leg 4 if the composer restyle turns out small.
- The tool-categories extraction updates only the drawer's reader, if migrating the three
  existing copies risks Settings or Agents regressions. The other copies are then left for
  the next mission, and a squawk is logged.
- Drawer default-open widths, and the palette's empty-query content, adjusted after the
  DD13 preview feedback.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [ ] `controls-and-data`:
  - the `contracts` lane (squawk 0117);
  - `searchList`;
  - the `modal` options;
  - the `listPane` (`chats` rows, block slot, row actions, `dataset`);
  - the `sessions` store collection with `prime`, the invalidation rows, and REST
    `platform`.
- [ ] `ws-start-protocol`: the shared payload validation; `leave`; the idempotent
  `start_session` with `start_failed`; the broadened auto-create catch; unit tests.
- [ ] `chats-test-seam` (3a): `_chats.py` and `seed_session`, with every chat-starting
  test migrated onto the helpers, on **today's** semantics; no app change.
- [ ] `start-flow-client` (3b):
  - the client state machine with frame gating, on the existing DOM;
  - `#chats/~new/{agent}`;
  - reconnect;
  - `new_session` removed;
  - the helper bodies flipped;
  - closes squawk 0111.
- [ ] `chats-sidebar-and-picker` (4a):
  - the Chats list on `listPane`, 300px wide, with groups, row delete and the pending row;
  - the agent picker and `openPicker`;
  - the dropdown and `history-buckets.js` retired, and the sidebar sink removed.
- [ ] `chats-pane` (4b):
  - the header `h1`, the new-chat state, and the empty and guidance states under
    "Hello.";
  - `composer.js` extracted;
  - the welcome list, `new-chat-btn` and the badge retired;
  - the seam guard swapped for `RETIRED_SELECTORS`;
  - the last chat sink removed.
- [ ] `composer-and-telemetry`: the textarea composer, the focus ring, attach, squawk 0110,
  the IME guard and the telemetry row.
- [ ] `agent-drawer-and-chat-action`:
  - `App.ui.drawer` and its toggle;
  - push and overlay, and what it can use;
  - shared tool categories;
  - `setQuery` and Open agent settings;
  - the agent editor's Chat;
  - squawk 0118's documentation.
- [ ] `jump-to-palette`:
  - the rail's bottom slot and control;
  - the modal's `ariaLabel` and `anyOpen`;
  - the Ctrl K shell listener;
  - the shared Settings page table;
  - the palette and its picks;
  - the WebKitGTK real-key probe.
- [ ] `behavior-specs-and-close`:
  - the DD13 preview;
  - `start-a-chat` and `jump-to-palette` finalized;
  - the affected specs re-authored;
  - the crew-file update;
  - the gates;
  - the close-gate runs.

---

## Post-Flight

### Completion Checklist

- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing: unit, six browser lanes, both engines for library controls
- [ ] Documentation updated:
  - `CLAUDE.md`: the lanes, the Chats conventions and the palette;
  - `the_one/agents.md`: the start flow, the drawer, the palette, the store `sessions`
    collection and the editor contract (0118);
  - `docs/ui-control-inventory.md` and `docs/ui-testid-registry.md`
- [ ] Squawks 0110, 0111, 0117 and 0118 closed
- [ ] Published design system updated (the new controls) by the Flight Director

### Verification

- **Unit and static guards:**
  - the store pin;
  - the nav-helper `DD2_ROWS` and parity;
  - the retired selectors and registry;
  - the UI guards (the chat sinks removed);
  - the token definitions;
  - the contrast (`--scrim`, the composer ring, the telemetry pin).
- **Browser:** all six lanes under `THE_ONE_TEST_NETNS=1`. The `contracts` lane runs every
  library control in Chromium and WebKit.
- **Behavior:**
  - `start-a-chat` and `jump-to-palette` (both themes);
  - `workbench-navigation`, `shell-navigation-smoke`, `chat-roundtrip` and
    `vision-round-trip`.
- **Desktop.** Ctrl K is verified in WebKitGTK through `scripts/webkitgtk_probe.py` (leg 7),
  and WebView2 at Flight 5's packaged build.
