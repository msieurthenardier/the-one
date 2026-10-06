# Leg: start-flow-client

**Status**: completed
**Flight**: [Chats and Jump-to](../flight.md)

## Objective

Move the chat area onto "create the session on the first send" (DD1, DD2). This is done
on the **existing** DOM: the look is unchanged, and the semantics and protocol change.
- **A pure session state machine** gates every inbound WebSocket frame.
- **The `#chats/~new/{agent}` route.**
- **Picking an agent** sends only `leave` and shows a pending chat.
- **The first Send** sends the leg 2 `start_session` action. The first turn behaves like
  any later turn.
- **Reconnects** re-send while starting and re-join while joined.
- **Retired:** the client's `new_session` path, its 10s timer, and the server's
  `new_session` branch. This closes squawk 0111.
- **Tests:** the `_chats.py` helper bodies built in leg 3a are flipped to the new flow.

## Context

- **Flight DD1 and DD2 are authoritative.** Read DD1's state-machine, "first turn",
  "reconnect" and "interim UI" bullets, and DD2's router bullets.
- **Leg 2 constraint.** While `starting`, the client re-sends `start_session` and
  **never** `join`. A `join` can pop a just-created in-memory session before its DB insert.
- **Leg 2 fact.** `join` with an unknown id auto-creates a default-agent session (`app.py`
  `join` branch). So a reconnect re-join is sent only for an id the client saw joined.
- **Look unchanged.** Leg 4 replaces the old list, dropdown and welcome. This leg only
  rewires them:
  - a welcome item, the dropdown change and the header `new-chat-btn` all become
    `App.router.go(App.router.href({destination:'chats', create:true, agent}))`;
  - the pending state renders through the old DOM (DD1's "interim UI").
- **Leg 3a has already built the seam.** Every chat-starting test goes through
  `_chats.py`, with today's semantics and all lanes green. This leg flips the helper
  bodies together with the app.
- **Effects as data.** The state module returns its effects as data (for example
  `{leave: true, discardHeld: id}` or `{render: 'history'|'keep', refreshList: true}`), so
  the transition table is testable as `page.evaluate` input and output with no chat DOM.

## Inputs

- Leg 1 landed: the `sessions` store collection with `prime`, and the chat area priming on
  `session_list`.
- Leg 3a landed: `_chats.py`, `seed_session`, and every chat-starting test on the
  helpers.
- Leg 2's `join_failed` (AC8a): `join` of an unknown id no longer auto-creates.
- Leg 2 landed:
  - `leave`;
  - `start_session`, idempotent and reserved;
  - `start_failed`;
  - `_build_session_joined_ok(is_processing=…)`.
- `static/js/areas/chat.js`:
  - `serializeState` and `hydrateState` (lines 8–25);
  - `inFlightSessions`, `isCurrentBusy` (around 34) and `updateStopControl`;
  - the F09-04 hold queue (`pendingQueuedMessages`, `showPendingQueued`);
  - `startSessionWith` (around 470–498), `armPendingStartTimer` (around 509–521) and
    `DEFAULT_START_JOIN_TIMEOUT_MS`;
  - `renderHistory` (around 523), `joinSession` (around 586) and `refreshSessionList`;
  - `performSend` and `send` (around 990–1043);
  - `connect()`, and the `onmessage` handlers `session_list` (around 1196–1225) and
    `session_joined` (around 1228–1327);
  - the done, cancelled and system frames;
  - the dropdown `change` (around 1653) and the header `new-chat-btn` (around 1660);
  - the area exports (around 1664–1677).
- `static/js/areas/chat/history-buckets.js`, `renderSessionList`.
- `static/js/router.js`: chats parse, href and resolve (around 152, 180, 209–215,
  287–291), `describeRoute` and `itemName` (around 432–440), `go` and `sync`, and
  `lastRoutes`.
- `tests/browser/_nav.py`: `canonical` and `legacy_hash` (around 187–188). The JS parity
  corpus `PARITY_CORPUS` is in `tests/browser/test_router_core.py` around 270.
- `the_one/interfaces/web/app.py`: the `new_session` branch.

## Outputs

- `static/js/areas/chat/session-state.js` (new): `App.chat.createSessionState()`, a pure,
  DOM-free state machine, with unit tests for the AC2 and AC2b rows (including a quick A,
  then B, open with a late `joined(A)`, the abandoned-start list refresh, and the
  suppressed auto-join).
- `static/js/areas/chat.js`, rewired onto it. Removed: `pendingStart`, the 10s timer and
  `App.chatStartJoinTimeoutMs`.
- `static/js/router.js`: the `#chats/~new/{agent}` route.
- `static/js/areas/chat/history-buckets.js`: the interim pending row.
- `the_one/interfaces/web/app.py`: the `new_session` branch removed.
- `tests/browser/_chats.py`: the helper bodies flipped. It was built in leg 3a, with
  `seed_session`.
- **Tests whose expectations change at the flip.**
- **Inverted, renamed or new tests:**
  - `test_flow_chat_start_recovery.py` is inverted, by rename, into a reconnect re-send
    test;
  - `test_router_items.py`'s two-`new_session`-frames tests are inverted by rename;
  - new state-machine tests;
  - new route parity rows.
- **Docs:** `the_one/agents.md` (the chat start flow and the state table; the router's
  chats create route) and `CLAUDE.md` (the destination router line gains
  `#chats/~new/{agent}`). Squawk 0111 is closed: its status, corrective action and
  verification are filled in, and the sign-off waits for the flight review.

## Acceptance Criteria

**A. The state machine (DD1).**

- [ ] **AC1. Shape.** `App.chat.createSessionState()` is pure: no DOM, no WebSocket, no
  timers. It returns an object with:
  - `state()`, returning `{name, id, agent, clientId, startedFrom, suppressAutoJoin}`;
  - the transitions `pick(agent)`, `openConversation(id)`, `startSend(clientId, payload)`,
    `onFrame(frame)` and `reset()`. Each returns an **effects** object, for example
    `{leave, discardHeld, render: 'history'|'keep', refreshList, notice, toIdle}`;
  - the queries `accepts(frame)`, `activeId()`, `serialize()`,
    `reconnectAction(listedIds, boundOnEarlierSocket)` (returning
    `{send: 'start_session'|'join'|null, toIdle, notice}`) and `idleRules(list)`.

  The states are `idle`, `joining(id)`, `joined(id)`, `pending(agent)` and
  `starting(clientId, agent, payload)`.
- [ ] **AC2. The transition table**, as implemented and tested. Every row is a test case
  in `tests/browser/test_flow_chat_session_state.py` (in the chats lane), which runs the
  pure module through `page.evaluate`.

  | From | Event | To | Effect the caller performs |
  |---|---|---|---|
  | `pending(A)` or `starting(cid, A)` | `pick(A)` (the **same** agent) | unchanged | **none**: no `leave`, no reset. This covers the header button, a re-click and a re-hydrate. |
  | any other | `pick(agent)` | `pending(agent)` | send `leave` if the state is `joined`, `joining` **or `starting`**; clear `pendingJoinId`; discard the previous held message (keyed on `activeId()`); set `currentAgentName`; clear `startedFrom` and `suppressAutoJoin` |
  | `pending(agent)` | `startSend(cid, payload)` (socket **open**, not `rebinding`) | `starting(cid, agent, payload)` | send `start_session`; optimistic bubble; busy |
  | `starting(cid)` | frame `session_joined` with `session_id === cid`, status ok | `joined(cid)`, remembering `startedFrom = {agent, cid}` | `sync('chat','sessions/'+cid)` (replace). **Only `renderHistory` is conditional:** skipped when `history` is empty (keep the bubble), else run. Every other block of today's handler still runs: `hideThinking`, `resetTelemetry`, `clearPendingQueued`, the `is_processing` busy block (re-shows thinking and Stop), `showPendingQueued` for the hold keyed on `cid`, and `showChrome`. Then the badge and list refresh as today |
  | `starting(cid)` | frame `session_joined` with `session_id === cid`, status **not ok** (degraded) with empty history | `pending(agent)` | as `start_failed`: remove the bubble, restore the text to an empty composer, show the degraded reason |
  | `starting(cid)` | frame `start_failed` with `session_id === cid` | `pending(agent)` | remove the optimistic bubble; clear busy, thinking and Stop; restore the text **only if the composer is empty**; **re-stage** `payload.images` into `stagedImages` and re-render the previews; restore any held message as the composer text if it is empty, else drop it with a notice; show the error in the pending pane |
  | `pending` | frame `session_joined` (a late reply to a superseded start or join) | unchanged | dropped; effect `{refreshList: true}`, so a session created by an abandoned start appears in the list |
  | any | `openConversation(id)` | `joining(id)` | send `join(id)`; clear `startedFrom` and `suppressAutoJoin` |
  | `joining(id)` | frame `session_joined` with `session_id === id` | `joined(id)` | render the history, as today |
  | `joining(id)` | frame `session_joined` with **another** id | unchanged | dropped: always a late reply to a superseded join, because leg 2's `join_failed` means the server never auto-creates on `join` |
  | `joining(id)` | frame `join_failed` with `session_id === id` | `idle` | notice "That conversation no longer exists"; set `suppressAutoJoin`; `{refreshList: true}` |
  | `joined(id)` | frame `session_joined` with the **same** id | unchanged | dropped, with no render. A `starting` re-send can produce two replies on one socket |
  | `joined(id)` | frame `session_joined` with another id (a late answer to a superseded join) | unchanged | dropped |
  | `joined(id)` | frame `session_deleted` with `id` | `idle` | today's delete behaviour; `idleRules` then runs on the next list |
  | any | `reset()` | `idle` | clear `suppressAutoJoin` |

  These frames are no-ops in the listed states:
  - a `session_joined` for any other id in `idle` or `starting`;
  - a `start_failed` or `join_failed` for any other id.
- [ ] **AC2b. The idle rules.** One `idleRules(list)` runs on **every** `session_list`, but
  **only while the state is `idle`**:
  1. `pendingJoinId`, if it is listed → `openConversation`;
  2. else `sessions[0]` → `openConversation`, **unless `suppressAutoJoin`** is set;
  3. else the welcome or empty state.

  `pending` and `starting` never auto-join and never show the welcome.
  `hydrateState('sessions/id')` while the socket is **closed** keeps today's behaviour: it
  sets `pendingJoinId` and sends no `join`, and the state stays `idle` until the first
  list. On an open socket, the hydrate join is not checked against the list; that is
  pre-existing and accepted, and leg 2's `join_failed` now makes it safe.
- [ ] **AC3. The frame gate** (`accepts(frame)`).
  - **Session-scoped frames:**
    - **accepted only in `joined(id)`**;
    - **dropped** in `idle`, `pending`, `starting` and `joining`.

    They are `user`, `assistant_chunk`, `assistant`, `thinking`, `tool_call`,
    `tool_result`, `system`, `usage`, `done`, `cancelled`, `auth_required`, `auth_*`,
    and any other frame not listed below.
  - **Always accepted:** `session_list` and `session_deleted`. They update the list only;
    they never change the state, except the `joined(id)` delete row above.
  - **The global part of `auth_resolved` and `auth_failed`** (`closeOauthPopup`) always
    runs. Only their inline rendering is gated.
  - **`joining`:** `join_failed` follows AC2. Every `system` frame is dropped.
  - `session_joined` and `start_failed` follow AC2.
  - **The test** feeds frames from a previous session after `pick`. The pane shows none
    of them, and a late `session_joined(old)` after `pick` leaves the state `pending`.
- [ ] **AC4. No "null means idle".** **Every** truthiness or null check of
  `currentSessionId` in `chat.js` (about 19 of its 47 uses at leg 1's tip) is replaced by
  an explicit state check (`state().name`), or by `activeId()`.
  - The flight log has a table of site, old check and replacement.
  - A pending or starting chat is never covered by the welcome.
  - **The exports keep their meaning.** `_currentSessionId` stays "the joined or joining
    id", derived from the state, and `_pendingJoinId` and `_joinSession` keep working.
    `test_router_core.py` (around 521 and 538) uses them.
- [ ] **AC5. `serialize()`.**
  - `pending` and `starting` → `new/` plus `encodeURIComponent(agent)`;
  - `joining` and `joined` → `sessions/{id}`;
  - `idle` → `null`.

  The area's `serializeState` returns it. `hydrateState('new/' + seg)` calls
  `decodeURIComponent(seg)`, because `resolve` hands the area the still-encoded segment.
  A parity row covers an agent name with a space and a leading `~`.
- [ ] **AC6. Busy, hold and Stop on `activeId()`.** `activeId()` is `clientId` in
  `starting`, `id` in `joined`, and `null` otherwise.
  - `isCurrentBusy()`, the F09-04 hold queue and the Stop control key on it.
  - **`isCurrentBusy()` is true whenever `state().name === 'starting'`**, independent of
    the in-flight map.
  - **A second Send while starting** is held in the one slot keyed on `activeId()` (equal
    to `cid` throughout, since the server uses the client's id). It is **never** sent as a
    plain `message`.
    - `session_joined`'s existing `showPendingQueued(...)` restores the chip.
    - The `done` handler's `var sid = currentSessionId` becomes `activeId()`, and its
      `performSend(held)` uses the joined path, never `startSend`.
  - **Stop while starting** sends `cancel`. It is ordered after `start_session` on the
    socket, so the server binds it to the new session.
  - **`onclose` while starting** must **not** clear the held slot or re-enable Send. Today
    it clears `inFlightSessions` and `pendingQueuedMessages` and sets
    `sendBtn.disabled = false` (around 1148). The re-sent `start_session` restores
    `is_processing`. A test sends in the reconnect gap and asserts that no plain `message`
    frame is sent.
  - **`/reset` typed in `pending` or `starting`** is a client-side no-op with a notice
    ("Send a message to start the chat first"). It is never sent or held, and the
    `delete pendingQueuedMessages[...]` line keys on `activeId()`.
  - **`inFlightSessions` is keyed by `activeId()`, never `currentSessionId`.** That
    includes `performSend` (`chat.js` around 1001), which `done` calls for a held message,
    so it must use the joined id.
  - **Send in `pending` with the socket not open** returns before `startSend`. It keeps
    the composer text, and the state stays `pending`.
- [ ] **AC7. The first turn behaves like any turn.**
  - The optimistic user bubble is still shown after `session_joined(cid)`; the history is
    empty, so `renderHistory` is not called for it.
  - The thinking indicator shows, Stop is visible and Send is disabled until `done`.
  - A browser test asserts the bubble, the thinking indicator, Stop, the hold chip on a
    second send, and the reply, and that the session count rose by exactly one.

**B. Reconnect (DD1).**

- [ ] **AC8. Reconnect.**
  - **A per-socket binding record.** The client sets `boundOn = <socket>` whenever it
    sends `start_session`, `join` or `leave`, or receives `session_joined`, on the current
    socket. Reconnect actions run **only for a binding made on an earlier socket**.
  - **`starting` re-sends at `onopen`**, not at the first list: if the binding was made on
    an earlier socket, re-send the same `start_session` at once. No list is needed, which
    removes the delay behind `refreshAgentsAndSetup`'s REST round trip.
  - **`joined` and `joining` act at the first `session_list` on the fresh socket**, through
    `reconnectAction(listedIds, boundOnEarlierSocket)`. A per-socket flag is set in
    `onopen` and cleared after that first list, so later lists (the refresh after `done`)
    never re-run it.
  - **`rebinding`.** It is set in `onopen` when the state is `joined` or `joining`, and
    cleared when that state resolves (`session_joined`, `join_failed` or `idle`). While it
    is set, or while `ws.readyState !== OPEN`:
    - `send()` returns early and keeps the composer text;
    - the Stop handler (`chat.js` around 1647) does nothing.

    Otherwise a message would reach an unbound socket, where the server auto-creates a
    default-agent session, and a Stop on a closed socket throws.
  - **`starting(cid, agent, payload)`** → re-send the **same** `start_session` (the same
    `cid` and payload) at `onopen`, as above. **Never** `join` (the leg 2 constraint).
  - **`joined(id)`** → if `id` is in the fresh `session_list`, move to `joining(id)` and
    send `join(id)`, so the replay re-enters through the gated row. If it is **not** in
    the list (deleted while the socket was down), go to `idle`, show a notice, and apply
    the idle rules. **Never `join` an unknown id**: the server would auto-create a
    default-agent session.
  - **`joining(id)`** → the same check: re-send `join(id)` if it is listed, else `idle`.
  - **`pending`** → nothing.
  - **`idle`** → today's rules: `pendingJoinId`, else auto-join, else the empty or
    welcome state.

  **Tests**, in two drop variants:
  - **The `start_session` never reached the server.** Drop the first send with the
    init-script `WebSocket.prototype.send` interception that
    `test_flow_chat_start_recovery.py` uses, **then call `App.chat._ws().close()`**. A lost
    reply on an **open** socket is intentionally no longer recovered: there is no timer,
    the server always replies (the reservation wait is bounded at 30s), and only a socket
    close triggers the re-send. The flight log records this as a deliberate removal under
    squawk 0111.
  - **It reached the server.** Call `App.chat._ws().close()`; the client reconnects after
    about 2s.

  Each asserts exactly one session for the start, with the first message delivered once
  (the leg 2 empty-history rule), and that the socket is re-bound: a send after the
  reconnect lands in the same session. A further test deletes the joined session through
  REST while the socket is down, then asserts `idle` and that no new default-agent
  session exists.
  - `test_flow_chat_start_recovery.py` (which pinned the retired 10s timer) becomes the
    "re-send while starting" test, **renamed**, for example
    `test_flow_chat_start_reconnect.py`. The old name is removed so git records the shift.
- [ ] **AC9. The rail-restore edge.** A hydrate of `new/{agent}` while `joined(id)` re-syncs
  to `sessions/{id}` (replace) and does not make a new pending chat when:
  - the remembered `startedFrom` is `{agent, cid: id}`;
  - no pick or open happened since, both of which clear it.

  The case: leave Chats while starting, then come back by the rail. It has a test.
- [ ] **AC9b. Bare `#chats` while pending** keeps the pending chat, as a joined session is
  kept today. `hydrateState(null)` returns early, and the router re-syncs the URL to
  `chats/~new/{agent}`. A test pins this.

**C. Route (DD2).**

- [ ] **AC10. The router.**
  - `App.router.href({destination:'chats', create:true, agent:'x'})` returns
    `#chats/~new/x`, with the agent through the same `enc()` agents use (a leading `~` is
    `%7E`).
  - `parse('#chats/~new/x')` returns `{destination:'chats', create:true, agent:'x'}`.
  - `resolve` maps it to the area sub `new/x`. Bare `#chats/~new`, or extra segments,
    fold to `#chats` with `redirected: true`.
  - `areaSubToRoute('chat','new/x')` returns `chats/~new/x`.
  - `describeRoute` gives the title and announcement "New chat with x", with the key
    `chats//~new/{enc(x)}`. Today it would produce `['Chats','New']`, so this is a special
    case for destination `chats`. A re-pick of another agent announces.
  - The first-send sync from `new/x` to `sessions/{id}` is **silent**: it must not speak
    a bare "Chats". `isCreateToItem` only matches keys ending in `/~new`, so the longer
    key makes this silent **by construction**. A test pins it, since it is an accidental
    property.
  - **Router specifics** (`router.js`, line numbers at review):
    - **`parse`** (around 176–183): test `segs[1] === RESERVED_NEW` first, and return
      `agent: dec(segs[2])`. **Bare `~new`** returns `{destination:'chats'}`, never an
      agentless create.
    - **`resolve`** (around 287–290): at the top of the `head === 'chats'` block:

      ```
      if (segs[1] === RESERVED_NEW) return segs.length > 2
          ? mk('chats/~new/' + segs[2], dest, 'new/' + segs[2], redirected || segs.length > 3)
          : mk('chats', dest, null, true)
      ```

      The area sub segment stays encoded, matching AC5.
    - **`areaSubToRoute`** (around 205–214): in the chat branch,
      `if (segs[0] === 'new') return segs.length > 1 ? 'chats/~new/' + escapeEncoded(segs[1]) : 'chats'`.
    - **`href`** (around 149–153): `if (spec.create) { if (spec.agent)
      segs.push(RESERVED_NEW, enc(spec.agent)); } else if (spec.id != null) …`. So
      `href({create:true})` with no agent returns `#chats`.
    - **`describeRoute`** (around 447–460): `if (p.destination === 'chats' && p.create)`,
      `parts = ['Chats', 'New chat with ' + agent]` and `key = 'chats//~new/' + enc(agent)`.
  - Tests: the router unit and contract tests, and `PARITY_CORPUS` in
    `test_router_core.py`.
- [ ] **AC11. `_nav.py`.**
  - `canonical` folds `chats/~new` to `chats`.
  - `legacy_hash` **raises** for `chats/~new/x`; it never had a legacy form, so it is not
    a `DD2_ROWS` row.
  - `tests/test_nav_helper.py` pins both.
- [ ] **AC12. Hydrate, guard and heal.**
  - **`hydrateState('new/x')` sets the state synchronously.** The router calls
    `sync(area, serializeState())` straight after hydrate (`router.js` around 553).
    - With the agents store already loaded (`peek`), it validates and picks at once.
    - On a cold load it enters `pending(x)` immediately, showing a neutral loading pane
      (not the welcome), and validates when `App.store.get('agents')` resolves.
  - An unknown or deleted agent, the agent `default`, or an empty agent makes the area
    call `App.router.sync('chat', null)` (replace) and fall back to the idle rules.
  - **Re-picks.** A pick while already on a `~new` route uses `go(…, {replace:true})`.
    Otherwise it is a pushed `go`.
  - **Heal.** Call `state.reset()`, then `App.router.sync('chat', null)`.
    `decodeURIComponent` is wrapped in try/catch, because a malformed `%` throws
    `URIError`; on failure it heals.
- [ ] **AC13. The entry points.** The header `new-chat-btn` uses `currentAgentName ||
  agentSelect.value || the first agent`, and is inert when there is no agent. The welcome item click and keyboard pick, the dropdown
  `change`, and the header `new-chat-btn` all call
  `App.router.go(App.router.href({destination:'chats', create:true, agent}))`.
  - The header button uses the current agent.
  - No code path sends `new_session` any more; `grep -rn new_session static/js` is empty.
- [ ] **AC14. The interim pending UI** on the old DOM:
  - the history list shows a pending item at the top of Today, selected, reading "New
    chat" with the agent and `data-pending`. `renderSessionList` takes a `pending` option,
    so the item survives every `session_list` re-render. `highlightActiveSession`
    handles a pending item;
  - the header badge shows the agent;
  - the welcome is hidden;
  - the chrome is shown with an empty message log;
  - the composer is enabled (unless setup is incomplete).

  Leg 4 replaces this rendering.

**D. Server and tests.**

- [ ] **AC15. `new_session` removed.** The `new_session` branch is deleted from
  `app.py`'s WebSocket handler. Any test that still drives it after leg 3a's migration is
  moved to `start_session`, or deleted with a reason in the flight log.
- [ ] **AC16. The flip** (AC17, the seeder, moved to leg 3a). From the leg 3a hand-off:
  - the bodies to flip are `start_chat`, `send_first` and `expect_chat`;
  - `tests/browser/test_chats_helper.py` asserts today's `new_session` frames, so it
    flips with them (to the `leave` and `start_session` frames);
  - `the_one/agents.md` gains the `_chats.py` note that leg 3a could not add (its AC4
    forbade `the_one/` changes);
  - leg 3a's `CHAT_SEAM_ALLOWLIST` (`test_flow_new_chat.py`) is untouched here, because
    leg 4 empties it. The `_chats.py` helper bodies from leg 3a change to the new
  flow:
  - `start_chat` returns at **pending**, with no session;
  - `send_first` creates the session;
  - `expect_chat` follows the interim UI.

  Tests that asserted a session right after the start now call `send_first`. The largest
  are `test_flow_new_chat.py`, `test_flow_chat_image_attach.py` and
  `test_flow_markdown_chat.py`. The flight log records the before and after numbers.
- [ ] **AC18. Inverted tests.** `test_router_items.py`'s tests that pinned "two
  `new_session` frames produce two rows" are **renamed and inverted** to "two first sends
  produce two rows". Back still steps between the sessions with exactly one `join`.
- [ ] **AC19. Store.** After `session_joined` from `starting`, the existing list refresh
  runs and primes `sessions`. That is the DD4 `start_session` invalidation row, and
  `test_store_static.py` pins it. `the_one/agents.md`'s invalidation map gains the row.
- [ ] **AC20. Squawk 0111.**
  - `pendingStart`, `armPendingStartTimer`, `DEFAULT_START_JOIN_TIMEOUT_MS` and
    `App.chatStartJoinTimeoutMs` are gone (a grep pin in a static test).
  - The squawk file's Corrective Action and Verification are written, with the status
    `completed` pending sign-off. The flight-end review signs it off.
- [ ] **AC21. Gates.**
  - `make lint` and format;
  - the static guards: `test_ui_guards`, `test_token_definitions`,
    `test_design_tokens_a11y`, `test_nav_helper`, `test_store_static` and
    `test_index_asset_cache_busting` (the new script tag bumps the pin);
  - `make test-unit`;
  - the browser lanes `chats`, `shared` (`TEST_TIMEOUT=3600`), `agents` and `settings`,
    plus `library` if any migrated file lives there. Each runs through
    `scripts/run-tests.sh` with `THE_ONE_TEST_NETNS=1`.
  - The numbers go in the flight log.

## Verification Steps

- **The state machine:** `bash scripts/run-tests.sh --lane chats` with
  `THE_ONE_TEST_NETNS=1`, plus the new state-machine and reconnect tests.
- **Falsify AC3 once.** Let session-scoped frames through in `pending`, and watch the
  "frames from the previous session" test fail. Restore, and record it.
- **Falsify AC8 once,** on the dropped-send variant, where it fails deterministically:
  re-send nothing (or `join`) instead of `start_session` while starting, and watch the
  reconnect test fail. Restore, and record it.
- **AC10–AC12:** the router contract and unit tests, `test_nav_helper.py`, and
  `test_router_core.py` parity.
- **A manual check** on a dev instance (port 8486 or higher, scratch data dir, dev mode,
  a mock provider and agents):
  - pick an agent, and confirm the URL, the pending item, and no session in
    `GET /api/chat/sessions`;
  - send, and confirm one session;
  - use the rail away and back while starting.

  Stop the instance afterwards.
- AC21's commands.

## Implementation Guidance

1. **Confirm the seam.** Check that leg 3a's lanes are green at this leg's start.
2. **The state module.** Write `areas/chat/session-state.js` as a pure factory, with an
   `index.html` tag before `areas/chat.js` (bump the asset pin). Unit-test it through
   `page.evaluate` (AC2).
3. **Wire `chat.js` onto it.**
   - Replace `startSessionWith` with `pickAgent(agent)`: `state.pick`, then `leave`,
     then the interim pending render.
   - The first send in `pending` builds the `start_session` payload: a `cid` from
     `crypto.getRandomValues` (32 hex), the `message`, and `images` from the staged list.
   - Route every `onmessage` frame through `state.accepts`/`state.onFrame` before the
     existing handlers.
   - Replace the null checks (AC4).
   - Implement `reconnectAction` in the `session_list` handler, on the first list per
     socket.
   - Delete `pendingStart` and the timer.
4. **The router** (AC10) and `_nav.py` (AC11). Add tests first; the router has a contract
   suite.
5. **Hydrate** (AC12) and **the entry points** (AC13).
6. **The flip** (AC16): update the helper bodies and the expectations.
7. **Server.** Remove the `new_session` branch (AC15).
8. **Inverted tests** (AC18). **Store pin** (AC19). **Squawk 0111 file** (AC20).
9. **Docs**, then **gates** (AC21). Update the flight log with the null-check site list,
   the falsifications and the numbers.

## Edge Cases

- **A pick of another agent while already `starting`** (before the first reply). This
  is `pick`, which leaves `starting` and sends `leave`. A pick of the same agent is a
  no-op (AC2). The server's
  `start_session` may still create that session, and it then appears in the list as a
  normal chat. That is acceptable: the message was sent. Do not cancel it.
- **A pick with the WebSocket closed.** `pick` is local. The `leave` is skipped (nothing
  is bound on a fresh socket), and `pending` holds until a send. A send while closed
  returns before `startSend` (AC6). `reconnectAction` in `pending` does nothing.
- **`start_failed` after the user navigated away** (state no longer `starting(cid)`): the
  frame is ignored (AC2).
- **Cold load of `#chats/~new/x` before the agents store loads:** enter `pending(x)`
  synchronously with a loading pane, then validate when `App.store.get('agents')`
  resolves; heal if it is unknown (AC12).
- **Delete of the joined session from another tab:** `session_deleted` moves `joined` to
  `idle`, as today.
- **Setup incomplete** (no provider or agent): the entry points stay inert, as
  `startSessionWith` was.

## Files Affected

- `the_one/interfaces/web/static/js/areas/chat/session-state.js` — new.
- `the_one/interfaces/web/static/js/areas/chat.js` — rewired.
- `the_one/interfaces/web/static/js/areas/chat/history-buckets.js` — the pending item.
- `the_one/interfaces/web/static/js/router.js` — the chats create route.
- `the_one/interfaces/web/static/index.html` — the script tag.
- `the_one/interfaces/web/app.py` — `new_session` removed.
- Tests:
  - `tests/browser/_chats.py` (the helper bodies flipped);
  - `tests/browser/_nav.py`;
  - the browser tests whose expectations change after the flip;
  - `tests/browser/test_flow_chat_session_state.py` — new;
  - the reconnect test, renamed from `test_flow_chat_start_recovery.py`;
  - `tests/browser/test_router_items.py`, `tests/browser/test_router_core.py`;
  - `tests/test_nav_helper.py`, `tests/test_store_static.py`,
    `tests/test_index_asset_cache_busting.py`.
- `squawks/0111-chat-stalled-join-orphan-session.md`.
- `the_one/agents.md`, `CLAUDE.md`.

## Citation Audit

Checked by the Flight Director against `af86324`:
- `chat.js`:
  - `serializeState` and `hydrateState`: lines 8–25;
  - `isCurrentBusy`: lines 34–36;
  - `startSessionWith`: lines 470–498;
  - `armPendingStartTimer`: lines 509–521;
  - `renderHistory`: line 523;
  - `joinSession`: lines 586–596;
  - `performSend` and `send`: lines 990–1043;
  - the `session_list` drain and auto-join: lines 1196–1225;
  - the `session_joined` stale guard: line 1230.
- `app.py`: the `join` `not_found` fall-through to auto-create (around 2509–2533) and the
  `new_session` branch (around 2559–2580).
