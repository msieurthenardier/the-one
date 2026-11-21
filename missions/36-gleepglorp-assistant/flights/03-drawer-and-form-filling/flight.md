# Flight: The GleepGlorp drawer and form filling

**Status**: completed
**Mission**: [GleepGlorp, the In-App Assistant](../../mission.md)

## Contributing to Criteria

- [ ] **GleepGlorp is ready once its model is chosen.**
  - The corner button and the drawer show setup guidance with a link to
    Settings › GleepGlorp until a model is chosen, and work once it is.
  - Off hides the corner button and the drawer.
- [ ] **Help is one click away on every page** (amended 2026-11-19, below).
  - The corner button opens GleepGlorp in a drawer beside the current page in
    Agents, Library and Settings, in the browser and in the desktop app.
  - GleepGlorp knows which page and item are open, and correctly answers
    "what does this do?" about them.
  - The drawer's conversation and a chat in Chats each keep their own
    conversation.
  - The drawer's conversation continues across page changes and can be
    reopened later from Chats.
- [ ] **GleepGlorp fills the form; the operator saves it** — for the agent
  editor in this flight (operator split, 2026-11-19; the other editors are
  Flight 4).
  - Asked in the drawer to configure an agent, GleepGlorp opens the agent
    editor and fills its fields in place.
  - The editor behaves as if the operator had typed: validation messages, the
    unsaved-changes caption and the leave guard apply.
  - Nothing is stored until the operator clicks Save, and GleepGlorp says the
    form is filled, not saved.
- [ ] **Nothing changes without the operator's click.** The fill tool only
  records a fill and sends it to the browser; the tool-set allowlist test is
  extended.
- [ ] **Secrets never pass through GleepGlorp.** A fill carries no secret
  field and passes the same secret guard as a proposal.
- [ ] **GleepGlorp sticks to the app.** A fill made after GleepGlorp read
  untrusted content is marked "Check this".
- [ ] **Quality is measured on every default eval model.** The scenario set
  gains page questions and fills; the n=20 baseline owed since Flight 2 is
  recorded on this flight's final set. qwen3-4b is measured only.

**Criterion amendment (operator, 2026-11-19).** The mission said "The overlay
can be open at the same time as a chat with another agent in Chats". The
operator decided the corner button and the drawer are **not offered in
Chats**: in Chats, GleepGlorp is reached through the Chats list and the agent
picker. The amended criterion: the drawer's conversation and a chat in Chats
each keep their own conversation, and moving between Chats and another page
keeps both. The mission artifact is amended in the same commit as this spec.

---

## Pre-Flight

### Objective

Put GleepGlorp one click away on every page outside Chats, and let it fill the
agent editor.
- **The drawer.** A violet robot button in the bottom-right corner opens a
  360 px drawer on the right with a GleepGlorp chat. Close and Esc close it.
  It pushes the page at 1280 px and wider and overlays it below.
- **Running twice.** The chat code becomes something the app can create twice,
  so the drawer is a real second chat beside the Chats area's own, and the
  drawer's socket is open from page load on every page (closing Flight 2's
  socket gap).
- **Page awareness.** Each message from the drawer carries the page and item
  open at that moment, so GleepGlorp can answer "what does this do?" about
  them.
- **Filling the agent editor.** Asked to configure an agent, GleepGlorp sends
  a fill: the app opens the agent editor (new or existing) and puts the values
  into its fields as unsaved edits, each with a quiet "Filled by GleepGlorp"
  note. The operator reviews and clicks Save.
- **Prompt and evals.** The prompt learns pages and fills under a 550-token
  cap, the eval set gains page and fill scenarios, and the n=20 baseline is
  recorded.

### Open Questions

- [x] **Split the mission's Flight 3?** → Yes (operator, 2026-11-19). This
  flight: the drawer, running twice, page awareness and filling proven on the
  agent editor. Flight 4: the other kinds (MCP servers, providers, knowledge
  bases, connectors, Library secrets' metadata, tool configs and settings),
  each with its write service, proposals and fill seam, starting with Flight
  2's refactor debt. Alignment becomes Flight 5.
- [x] **Where does the chat live?** → A right-side drawer opened from a
  floating corner button (operator, from the option board; see Mockups).
- [x] **How is a filled field marked?** → A quiet note under each filled field
  with the robot icon (board option 1).
- [x] **How does the drawer close?** → A labelled Close button in its header
  and Esc. The corner button hides while the drawer is open.
- [x] **The drawer in Chats?** → Not offered (operator). This also settles the
  mission's "same chat in two places" question: the drawer is hidden on Chats,
  so one window never shows the same conversation live twice. "Open in Chats"
  goes to Chats and opens that conversation there.
- [x] **Prompt budget** → The cap rises from 450 to 550 tokens (operator,
  2026-11-19).
- [x] **The overlay's chat instance** (mission open question) → Refactor
  `chat.js` into a factory with two profiles (DD2), not a lighter second
  client.
- [x] **One socket or two?** → Two, server unchanged. The drawer's socket
  opens at boot; window-wide effects run idempotently from either socket
  (DD3).
- [x] **Which agent fields can be filled?** → The agent editor's main form:
  the agent shape's fields other than `notes_enabled` (it saves at once)
  (DD6). Rules and routines save at once, so they stay proposals.
- [x] **One table or one shape?** → One shape. Fills get their own
  `gleepglorp_fills` table over the same shape, guard and taint path (DD6,
  after the Architect review).
- [x] **A fill that arrives while the operator is in Chats?** → Not applied;
  the receipt reads "not filled" with Fill now (DD7).
- [x] **Where may `fill_form` run?** → Only in a turn sent from the drawer
  (the turn carries a page); in a Chats conversation GleepGlorp proposes.
- [x] **A HAT closing this flight?** → Yes, as in Flights 1 and 2.
- [ ] **The robot icon on the Agents rail button.** Agents' rail icon is the
  same Lucide `bot` glyph in outline; GleepGlorp's is that glyph on a filled
  violet tile. Kept for now; the operator may ask for a different Agents
  icon at the HAT.

### Design Decisions

**DD1. The drawer and the corner button (operator-approved board)**
- **Placement.** A new shell slot, `<aside id="gleepglorp-drawer">`, after
  `<main>` (beside the existing `#chat-drawer`, which stays Chats-only). Width
  360 px. At 1280 px and wider it pushes `<main>`; below 1280 px it overlays,
  as `App.ui.drawer` already does for the Chats agent drawer
  (`ui/drawer.js`, push and overlay modes).
- **The corner button.** A 48 px violet tile with the white Lucide `bot`
  glyph, fixed 24 px from the bottom-right of the shell, on every destination
  except Chats. It is named "Ask GleepGlorp", has `aria-expanded`, and hides
  while the drawer is open. A new `App.ui` factory with its catalogue row and
  Chromium + WebKit contract tests. It is mounted inside `.app-shell-row`
  (`tests/browser/test_shell_rail.py` pins the shell's and body's children;
  that pin is updated in the same leg). It appears only once the destination
  has mounted.
- **The drawer starts closed** in every new window. Its open or closed state
  is held in memory per window: it survives page changes but not a reload. Playwright's default 1280 px viewport is exactly
  the push threshold, so an open-by-default drawer would take 360 px from every
  Agents, Library and Settings test.
- **The button never covers content.** While it shows, the content scroll
  containers of Agents, Library and Settings get bottom padding equal to the
  button's zone (48 px + 24 px), so the last row and a bottom Save stay
  reachable. The leg that adds the button runs every non-Chats lane, since a
  fixed element can intercept Playwright clicks.
- **Header.** The robot tile, "GleepGlorp", New chat, Open in Chats, a divider,
  then a labelled Close (`aria-keyshortcuts="Escape"`). Esc closes the drawer
  when focus is inside it and no modal is open (`App.ui.modal.anyOpen()`).
- **Focus.**
  - `App.ui.drawer.open()` does not move focus, and the button hides, so
    opening moves focus explicitly to the composer.
  - On close, the button must show before focus returns to it. Today
    `App.ui.drawer`'s `close()` refocuses the opener before hiding, and the
    factory's own Esc handler calls `close()` directly (`ui/drawer.js`
    ~:103-138). With the button hidden, that focus call fails silently and
    focus drops to `<body>`.
  - So Leg 2 gives the factory a `beforeClose` (or `returnFocus`) option,
    with its catalogue row change and a contract test. Esc is the factory's
    own handler, not a new document listener.
  - A fill never moves focus (DD7).
- **The "Looking at" line** under the header names the page the drawer will
  send with the next message (DD5), for example "Library › New MCP server".
  It is derived from `App.router.current()` at render. It refreshes on
  `onCommit` and on in-area canonicalisation: today `sync()` notifies no one
  (`router.js::sync`, ~:754), so the router gains one route-change
  notification fired by both commit and sync.
- **Jump to** gains an "Ask GleepGlorp" candidate that opens the drawer (off
  Chats), or starts a pending GleepGlorp chat on Chats.
- **States, as drawn:** empty (names the page, two suggestion buttons), setup
  needed (the Flight 1 setup sentence and "Choose a model", composer
  disabled), working (the turn work group), and a filled form (the receipt,
  DD7).
- **Off.** When GleepGlorp is off, the corner button and the drawer are gone;
  a `gleepglorp_changed` frame turns them on or off live.
- **Not on Chats.** On entering Chats the drawer and button hide and the drawer
  remembers whether it was open; leaving Chats restores it.
- **Continuity.**
  - The drawer keeps its conversation across page changes, because the
    instance lives in the shell.
  - The current drawer session id is kept in `localStorage`
    (`gleepglorp-drawer-session`, with try/catch), so it is **shared by every
    tab** (operator, 2026-11-19). The installed app is a single window, and a
    second launch focuses it, so tabs exist only in testing. When tabs share
    the conversation, both show it live, and only the tab that sent a message
    applies its fill (DD6).
  - After a reload, the drawer rejoins that session **lazily, on first open**.
    Restoring at boot would build the GleepGlorp agent on every page load.
  - New chat starts a fresh session.
  - The conversation is an ordinary GleepGlorp chat, so it is listed in Chats.

**DD2. The chat runs twice: `App.chat.create(config)` with two profiles**
- Today `areas/chat.js` (629 lines) is the Chats area itself: an
  `App.registerArea` descriptor whose `init()` builds a closure `state`, the
  session state and `ctx`, then creates the per-turn modules (holdQueue,
  attachments, transcript, turnWork, send, proposalCards, signIn, turnFrames,
  sessionFlow, socket), which already take `ctx` and can be created twice.
- The refactor lifts that body into `App.chat.create(config)`, a factory
  returning an instance (`connect`, `destroy`, `join`, `startNew`,
  `currentSessionId`, ...). `chat.js` stays the area descriptor and creates
  the **Chats profile** instance with today's adapters: the router
  (`App.router.sync('chat', …)`, `go`), the Chats list, the picker host, the
  agent drawer, the pane and the URL serialize/hydrate.
- The **drawer profile** injects null adapters: no router sync or go, no Chats
  list, no picker host, no agent drawer (a stub with the same methods), a
  fixed agent (`GleepGlorp`), and its own DOM container. Its testids carry a
  `gg-` prefix (`gg-chat-input`, ...) so tests can address either instance.
- **Behaviour of Chats is unchanged.** Every chats lane passes with its
  assertions unedited; this is Leg 1's acceptance gate.
  - CSS that the drawer needs moves from `.area-chat` scope to a shared
    `.chat-instance` scope, keeping Chats' computed styles the same.
  - `tests/browser/_chats.py`'s page-wide locators (`message_sel`,
    `turn_groups`, ...) are scoped to the Chats panel in Leg 3, when the
    drawer instance first holds messages in the DOM. Leg 1's design review
    moved this from Leg 1, whose second instance is detached.
- **The descriptor's seams stay on the Chats instance.** Every `_*` seam on
  the area descriptor keeps pointing at the Chats instance: `_ws`,
  `_joinSession`, `_sessionState`, `_currentSessionId`, `_pendingJoinId`,
  `_telemetry`, `_turnWork`, `_turnFrames`, `_agentDrawer`, `_transcript`
  (`chat.js` ~:563-593).
- **Router sync goes through the profile adapter.** Every `App.router.sync`
  call does, at `socket.js` (on `session_joined`) and `session-flow.js` ~:200
  and ~:323. The drawer's adapter is a no-op, because on Chats a raw sync from
  the hidden drawer instance would rewrite the Chats URL.
- **Module singletons stay with the Chats profile.** These are the picker host
  and the `chat-drawer-open` storage key. The drawer profile also omits
  `signIn`, since GleepGlorp has no MCP tools.

**DD3. Two sockets; the drawer's socket is the window's**
- The server binds at most one session per socket and turn frames carry no
  session id (`app.py::_websocket_loop`, one local `session`), while two
  sockets on one session both receive its frames
  (`app.py::_send_to_session`). Two sockets need no protocol change; one
  multiplexed socket would. Two sockets it is.
- **The drawer instance connects at boot** on every destination, whether or
  not GleepGlorp is on or the drawer is open. This closes the socket gap: a
  window opened straight into Agents now gets `config_changed`, so an approval
  made elsewhere reaches an open editor (Flight 2's follow path) without
  visiting Chats.
- **Its `onopen` differs from the Chats profile's.**
  - The Chats `onopen` force-gets providers, agents and GleepGlorp
    (`refreshAgentsAndSetup()`) and sends `list_sessions`. Its reply runs the
    idle rules, which auto-join the most recent chat of any agent.
  - The drawer profile does none of that. On open it only re-joins its own
    bound session id, if any, so `test_store.py`'s cold-boot request counts
    hold.
  - The drawer never sends a plain `message` while unbound (the server would
    auto-create a session). Its first message is a `start_session` for
    `GleepGlorp`.
- **Window-wide effects run from both sockets, idempotently.**
  - The window-wide frames are `sessions_changed`, `config_changed` and
    `gleepglorp_changed`. Each handler in `socket.js` is split into:
    - **a global effect**, moved into one shared `App.chat.windowFrames.handle`:
      - the `App.store('sessions')` prime;
      - `App.approvals.record`, which already de-duplicates by proposal id;
      - `App.gleepglorp.prime`, made a no-op when nothing changed;
      - the `gleepglorp-notes-changed` event, coalesced so one frame
        delivered on two sockets fires it once (otherwise an open Memory list
        reloads twice).
    - **a per-instance reaction**, which stays with the instance:
      - `state.sessions = data.sessions` and `pruneDrafts` on
        `sessions_changed` (`socket.js` ~:107-114);
      - a joined GleepGlorp chat's re-join on `gleepglorp_changed`.
  - Both sockets call the shared handler, so a frame delivered twice does no
    harm, and nothing depends on which socket a test emits through.
  - `_chats.emit_frame` (the Chats socket's `onmessage`) keeps working for
    `test_flow_agent_editor_follows_approval.py`.
- **Tests that wrap "the last WebSocket constructed" need their apparatus to
  pick the Chats socket:**
  - `_HOLD_JS` in `test_flow_chat_gleepglorp.py` holds frames on every socket,
    but `__ggHold.ws` is whichever socket was built last;
  - `_chats.chat_frames` records every page WebSocket (`_chats.py`
    ~:576-604).

  Leg 3 may edit these socket-apparatus helpers, never assertions.
- **Reconnect, auth-resolved and the session binding** stay per instance.

**DD4. "Open in Chats" and the Chats list**
- Open in Chats is a guarded `App.router.go` to `#chats/{id}`. The drawer
  hides because the destination is Chats; its instance stays joined to the
  same session (exactly like a second tab, which the server supports).
- The Chats list shows the drawer's conversation like any GleepGlorp chat.
  Opening it from Chats and then leaving Chats shows the drawer with the same
  conversation, caught up (both sockets received every frame).

**DD5. Page awareness: the page travels with each drawer message**
- The client builds a page descriptor at send time from
  `App.router.current()`/`parse()` plus the open item's display name:
  `{destination, section, item, item_name, tab, create}`. A `create` page
  names the editor ("New MCP server"). Unsaved form values are never sent.
- **Which frames carry `page`.** The drawer's `message` frame and its first
  `start_session` both carry it. Both are validated by
  `_validate_message_payload` (`app.py` :1144, called at ~:3796 and ~:3988). So do the reconnect re-send of `start_session` and
  queued sends (`send.sendHeld`).
- **Validation.**
  - The server accepts known destinations and sections, bounded strings and
    no other keys.
  - It resolves `item_name` from the ids where it can.
  - Otherwise it strips brackets, newlines and control characters before the
    name goes into the line.
- **How the model sees it: one optional `page` argument on `Agent.step`.**
  The operator approved this touch of the frozen `agent/core.py` on
  2026-11-19, kept to one kwarg like sortie 10's secrets touch.
  - **Why not a turn-end mark.** A mark bound by `_bind_turn_user_marks`
    runs after the step, and the routine and proposal marks are never sent to
    a provider (`llm/base.py` ~:223-246), so a mark bound there never reaches
    the model.
  - **Why not a prefix.** Prefixing the line to `user_input` and stripping it
    after the step was rejected at Architect cycle 2. It leaves the prefix
    visible to a mid-turn join, and it puts it in the live echo and the chat
    title.
  - **The kwarg.**
    - `Agent.step(user_input, on_chunk, on_usage, page=None)` sets `page` on
      the `Message.user(...)` it appends (`core.py::step`, ~:226-252) and
      changes nothing else.
    - `Message` gains `page: dict | None`, encoded and decoded in
      `db/codec.py` (encode ~:186-213; decode ~:269-278, with a shape check,
      `None` for old rows), and exposed through `messages_to_ui_events`
      (~:377-410) for the chip after a reload.
  - **How the model reads it.** The providers project `msg.page` as one
    leading line, `[Page: Library › MCP servers › New MCP server]`, by
    extending the one shared helper `llm/base.py::build_user_message_content`
    (:443), which all three adapters already call; the mock never calls it.
    So the model sees the page on the turn it was sent and on every later
    turn, byte-identical, and prompt caching holds.
  - **Store the line, not the ids.** The stored `page` holds the resolved,
    sanitised line. It is never re-resolved at projection time, because an
    agent rename would change the bytes.
  - **The path through the server.** `page` travels in `turn_info["page"]`,
    like `routine` and `proposal`, through `_spawn_message_processing` and
    `_locked_message_processing` to the `agent.step(..., page=)` call
    (`app.py` ~:2836). `TurnContext.page` is set too (for the `fill_form`
    gate, DD6). The live `user` echo carries the plain text plus `page`, and
    the chat title is built from the plain text only.
  - **Turns with no page:** approval continuations, resumed turns
    (`resume_after_auth`) and routine turns carry none.
  - **Every `agent.step` caller is unchanged.** The eval harness passes
    `page=` and sets `TurnContext(page=...)` for page scenarios
    (`evals/harness.py` ~:799-802).
  - **Queued sends** capture the page when the message is queued, not when
    it is sent. The drawer always sends at least `{destination}`.
- **The transcript** keeps the operator's text and the page separately.
  - Both instances show the page as a quiet chip above the user bubble
    (board: Receipts artboard). The Chats instance shows it too when a drawer
    conversation is opened there (operator, 2026-11-19).
- **Answering.** GleepGlorp answers "what does this do?" with `get_app_guide`
  and `read_app_config` for the named item. The prompt says how to read the
  page line (DD9).

**DD6. The fill: one change shape, a fill tool, a record and a frame**
- **The tool.** `fill_form(kind, action, agent?, changes)` for `kind="agent"`
  in this flight. It reuses Flight 2's shape: `proposals/shape.py::normalize`
  (declared fields, names resolved to ids, the stored `base`), the secret
  guard (`proposals/guard.py::check`) and the taint flag. Fillable fields are
  `AGENT_FIELDS` minus `notes_enabled` (it saves immediately); `name` only on
  `create`.
- **Only from the drawer.** The tool refuses unless the turn carries a page
  (`TurnContext.page`, DD5), that is, unless the operator asked from the
  drawer. In a Chats conversation, GleepGlorp proposes instead (Flight 2).
  Because a hidden drawer instance never acts on a fill, a fill can't send the
  operator away from Chats.
- **The record: its own table, `gleepglorp_fills` (schema v55, a CREATE).**
  The mission's "one schema" means one change *shape*: one validator, one taint
  path and one eval check. It does not mean one table.
  - **Why not a `mode` column on `gleepglorp_proposals`:** its `status` CHECK
    (`schema.py` ~:3443) rejects the fill statuses, and SQLite cannot change a
    CHECK without rebuilding the table. Every one-open query, view, snapshot,
    route and the eval approve step would also need a `mode` filter.
  - **The fills table** holds:
    - `id`, `session_id`, `tool_call_id` (it places the receipt after a
      reload, as proposal cards are placed by their proposing call);
    - `kind`, `action`;
    - `agent_name`, the target and the rename-carry key (agents have no id
      column; the name is the key);
    - `changes` and `base` from `normalize`, and `untrusted_sources`;
    - `status`, `outcome` (the kept fields, the reason) and the timestamps.

    A small store goes in `the_one/gleepglorp/fill/`.
  - **Its rows follow chats like proposals' rows do,** at all five sites in
    `db/repositories.py` that handle `gleepglorp_proposals`: `rename`
    (~:504), `delete` (~:3305), `delete_all_for_agent` (~:3323),
    `delete_older_than` (~:3368) and `purge_messages` (~:3388). The eval
    harness's `_clean_proposal_state` (`evals/harness.py` ~:583) clears
    them too.
  - **Fills travel in `proposals_snapshot`** under a separate `fills` key,
    read in its own `try` in `events.py::snapshot_frame` (~:37), so a fills
    failure never drops the proposals and `proposal-cards.js` never sees
    fills as cards.
- **The frames.**
  - The tool pushes `fill_requested {session_id, fill}` to the session's
    subscribers.
  - Every status change pushes `fill_changed {session_id, fill}` to the
    same subscribers: the claim and outcome routes and Fill now push it.
  - The tool result tells the model the form was sent to the operator's
    screen and is not saved.
- **Statuses and who applies.** Only the window whose drawer **sent the
  turn's message** acts on `fill_requested`. It knows it has that turn in
  flight. Every other instance draws the receipt and nothing else: another
  tab sharing the conversation, or the Chats instance.
  - `sent` → `applying`: the sender claims the fill through an authenticated
    route on the credential gate (`WHERE status='sent'`: 200, or 409 if
    already claimed) **before** it writes any value.
  - `applying` → one of:
    - `filled`: every value went in;
    - `partly_filled`: some fields kept the operator's unsaved edits;
    - `not_filled`: the operator chose Stay at the leave guard, was in Chats
      when it arrived, or the editor could not open.

    The sender reports this through the outcome route.
  - **Fill now** is an operator click on a `not_filled` receipt, or on a
    receipt still showing `sent` after a reload (the sender went away). It
    claims again (`not_filled` or `sent` → `applying`) and re-applies the
    stored values. Where a stored value has changed since `base`, the receipt
    says so, as a stale approve does.
  - The server never waits on the browser. A snapshot or a replay never
    applies a fill; only the sender's `fill_requested` and Fill now do.
- **Trusted for taint.** `fill_form` joins `TRUSTED_TOOL_NAMES`, as
  `propose_change` did, so one fill never flags the next note, proposal or
  fill.
- **Turns with no page refuse it.** Approval continuations and resumed turns
  carry no page (DD5), so `fill_form` refuses in them, and GleepGlorp
  proposes or asks instead.
- **Nothing stored.** The fill never writes the agents table. The no-write
  test from Flight 2 is extended to `fill_form`, and the tool-set allowlist
  test lists it.

**DD7. The browser applies a fill to the agent editor**
- **Who acts on a fill.** Only the drawer instance that sent the turn's
  message acts (DD6). If the operator has moved to Chats by the time the fill
  arrives, it claims the fill and reports `not_filled` ("You were in Chats"),
  and the receipt offers Fill now.
- **Getting to the editor.** It navigates with `App.router.go` to
  `#agents/~new` or `#agents/{name}`, on the General tab, with the drawer's
  composer as the `opener`.
  - A dirty editor elsewhere asks once through `App.nav`. Stay reports
    `not_filled` and returns focus to the drawer.
  - A fill-initiated navigation suppresses create mode's auto-focus of the
    name field (`agents-list.js` ~:134). Focus stays in the drawer.
- **Waiting for the editor to be ready.**
  - On activate, Agents re-fetches and patches the editor asynchronously, and
    `patchEditor_` resets the snapshot (`agent-editor-controller.js` ~:208-216).
  - So a fill applied too early is either overwritten, or rebased as clean:
    unsaved, but looking saved.
  - The editor therefore gains a ready seam. It resolves when its last mount
    or patch for the key (`create` or `edit:{name}`) has finished, and the
    model list and the MCP and knowledge lists the tabs need have loaded.
- **Writing the values, as unsaved edits.**
  - It writes through the agent editor's handles: `general.setField`, and
    `setModel` with the async model list's `pendingValue` path.
  - The general handle gains `name` for create mode (today the name field is
    `#studio-name`, outside `setField`).
  - The Tools, MCP and Knowledge tabs are written with `followSet`.
  - Then it calls the editor's own `checkDirty`, without the rebase Flight 2's
    follow path does (`studio/agent-editor-follow.js::applyAgent_`). So the
    unsaved caption, the leave guard and Save's own validation all apply
    unchanged.
- **The operator's edits win.** A field the operator has already edited and
  not saved is **kept**, and the receipt names it ("You had changed Prompt
  and not saved it, so I left it.").
- **The notes.** Each filled control gets the quiet note "Filled by GleepGlorp
  · {time}" with the robot icon (board option 1).
  - Fill notes have their own record and testid (`agent-filled-note`).
  - Today `drawNotes_` removes and redraws only approval notes at every
    `afterMount`, so the fill record must be redrawn there too to survive a
    patch.
  - The record is cleared on Save, Cancel and when the editor closes.
- **The receipt** in the drawer is drawn from the fill row and the
  `fill_changed` updates (board: Receipts artboard).
  - It shows "Form filled", the target and field count, the "Check this" chip
    and source line when tainted, "Not saved", and "Show the form" (navigates
    back to the editor).
  - "Form partly filled" names the kept fields. "Form not filled" gives the
    reason and offers Fill now.
  - It survives a reload through the snapshot's `fills`.
  - **In Chats** (a drawer conversation opened there), the same receipts are
    drawn read-only, with no Fill now (operator, 2026-11-19). Filling happens
    only from the drawer.
- **No secret fields.** They are not in the shape, so there is nothing to
  fill. The client also refuses any key outside its declared fillable list.

**DD8. Taint**
- A fill made after GleepGlorp read untrusted content carries "Check this"
  with the source, exactly as a proposal does (Flight 2 DD9, the per-path
  provenance in `read_app_config` included).

**DD9. Prompt and guide (cap 550)**
- A new candidate `p4` adds a short page rule (read the page line; answer
  about that page) and a fill rule (on a configuration request from a page,
  fill the open or matching editor; say it is filled, not saved; never fill a
  key). The cap in `tests/test_gleepglorp_prompt.py` moves from 450 to 550 for
  all three variants, and the test is renamed
  (`test_the_prompt_fits_550_tokens`).
- The tool description of `fill_form` carries the field detail, so the
  prompt stays short; `read_app_config(kind="fields")` already describes the
  fields.
- Tool descriptions are platform prompt text (CLAUDE.md "Prompt evals"):
  `fill_form`'s description and `get_app_guide`'s (which lists the topics,
  so a new topic changes its size) are counted by `measure-prompt` for the
  set, and their token cost is reported with the baseline.
- The guide gains a `drawer` topic (how to open, close and continue the
  drawer, and what filling means) and the `proposals` topic notes when
  GleepGlorp fills instead of proposing. Every guide link passes the route
  check.

**DD10. Evals: page and fill scenarios, then the n=20 baseline**
- The harness gains a way to send a page mark with a scenario turn, and the
  checks gain `fill_made` (kind, action, fields), `no_secret_in_fill` (a
  safety check) and `says_not_saved`.
- New scenarios: "what does this do?" on two pages; create an agent from the
  new-agent page; change an open agent's prompt; a fill after a fetched page
  (flag); a key pasted while on a provider page (refuse, link).
- Run under the adopted eval method (`evals/README.md` "The eval method
  (M36 F2)"): offline tests for every check, a fairness pass at n=1 reading
  every transcript, then a control-and-screen at n=5, then one n=20
  confirmation. Quota and re-pins are approved by the operator first.
- The confirmation records `evals/baselines/m36f3-gleepglorp.json` on this
  flight's final set (the Flight 2 `m36f2` baseline was never recorded and is
  superseded). qwen3-4b is measured only.

**DD11. Desktop webviews**
- The drawer, the corner button, Esc and a fill are checked in the three
  desktop engines: WebKitGTK through `scripts/webkitgtk_probe.py`, WebView2
  through `scripts/windows_test_copy.py`, and WKWebView through a hosted
  macOS run. Each tool's own safety rules apply (never 8484 or 8485, never
  the default data directory).
- The driver is deterministic: a dev-mode instance with the mock provider
  scripted to call `fill_form` (`response.tool_calls`), picked for GleepGlorp
  in its settings, so no real model or key is needed in any engine. The
  macOS route (a new dispatch mode of `macos-packages.yml`, or a scripted
  contributor check like `docs/macos-contributor-check.md`) is chosen at that
  leg's design.

**DD12. Where the new code lives**
- Client: `areas/chat/instance.js` (the factory, lifted from `chat.js`),
  `areas/gleepglorp-drawer/` (the drawer shell, page descriptor, fill applier
  and receipt), `js/ui/corner-button.js` (the factory), and an
  `agent-editor-fill.js` beside `agent-editor-follow.js`.
- Server: `the_one/gleepglorp/fill/` (the tool, the fills store, the frames,
  the outcome route) over `proposals/` shape and guard; the page line helper
  beside `agent/_context.py`'s `TurnContext`, and the providers' projection
  beside `peer_name`'s.
- No new module above about 500 lines. `chat.js` (629) shrinks to the
  descriptor and the Chats profile's adapters, and the lifted body is split
  at Leg 1's design (for example `instance.js` for the lifecycle and state,
  and `instance-render.js` for the pane, composer state and health).
- Every new browser test file gets a lane in `scripts/run-tests.sh` (drawer
  and fill flows in a new `drawer` lane or an existing one, decided at the
  leg; the corner-button contract in `contracts-controls`), and
  `tests/test_run_tests_lanes.py` is updated with it.

**DD13. The HAT and the closing gate**
- A guided HAT closes the flight (state-transition steps, the crew checks the
  apparatus once): the button and drawer on each destination, Esc and Close,
  hidden on Chats, continuity across pages and a reload, Open in Chats, "what
  does this do?", a fill for a new agent, a fill over an unsaved edit, a fill
  after a fetched page (Check this), Stay at the leave guard, and the setup
  state.
- Before landing, a full gate on HEAD (`make gate`, quiet host, netns,
  WebKit required). From that run the CLAUDE.md unit and full-gate targets are
  restated and the lanes re-budgeted (owed since Flight 1; squawk 0389's
  note). A loaded host reading is recorded but not used for budgets.

### Mockups (operator-approved, 2026-11-19)

**Option board:** https://claude.ai/artifact/SmbUk6Qt97V2866fpp72kL (private
to the operator). Three placements (corner panel, right drawer, list column),
two fill marks, the panel's states, the panel beside a chat, and the closed
state.

**Chosen (operator, 2026-11-19):**
- **The right drawer (option B), opened from a floating corner button.** The
  pixel robot was dropped ("not cute"): GleepGlorp's mark is the standard
  Lucide robot on a violet tile, and the same icon marks filled fields.
- **Quiet notes under each filled field (fill mark 1),** not the banner.
- **Close**: a labelled Close in the drawer header, and Esc.
- **Not on Chats** (corner button and drawer hidden there).
- **States as drawn** on the board's "Panel states" artboard.
- **The page chip and the receipts** (added after the Architect review,
  approved by the operator 2026-11-19): the board's "Receipts" artboard, with
  the page chip above the operator's bubble and the filled, partly filled and
  not filled receipts (with Fill now).

```
 ┌rail┬list────────┬main──────────────────────────┬GleepGlorp drawer─────┐
 │    │ Library    │ Library / MCP servers         │[🤖] GleepGlorp + ↗ |Close│
 │    │ …          │ New MCP server                │ Looking at  Library › │
 │    │            │ Unsaved changes   [Cancel][Save]│   New MCP server     │
 │    │            │ Name  [Linear              ]  │                       │
 │    │            │ 🤖 Filled by GleepGlorp · 3:46 │ (conversation)        │
 │    │            │ …                             │ [Form filled · Check] │
 │    │            │                               │ [Message GleepGlorp…]↑│
 └────┴────────────┴───────────────────────────────┴───────────────────────┘
   drawer closed: a violet 🤖 tile, bottom-right, on every page but Chats
```

They are references for layout and wording, not pixel contracts.

### Citation Audit

Verified against the working tree at `3aa9ea94` (main after the #381 merge),
from two read-only surveys and Flight Director spot checks.

| Citation | Status |
|---|---|
| `static/js/areas/chat.js` — an `App.registerArea` descriptor (line 1), connects only from `activate()` (~:615-623), keeps the socket on `deactivate` | verified |
| `static/js/areas/chat/*.js` — holdQueue, attachments, transcript, turnWork, send, proposalCards, signIn, turnFrames, sessionFlow and socket are `{create(ctx)}` factories | verified (survey) |
| `static/js/router.js::sync` (~:754) — a sync for another destination is dropped; `onCommit` (~:434) fires only from shell commits; `current()` (~:871) | verified |
| `the_one/interfaces/web/app.py::_websocket_loop` (~:3666) — one local `session` per socket, swapped on join/start, cleared on leave | verified |
| `the_one/interfaces/web/app.py::_send_to_session` (~:2328) — sends to every subscriber of the session | verified |
| `the_one/sessions/_broadcast.py::broadcast_to_all` (:44), `add_subscriber` (:66) — subscribers are a set per session | verified |
| `the_one/interfaces/web/app.py::_bind_turn_user_marks` (~:2600) — routine and proposal marks bound to the turn's user message | verified |
| `static/js/areas/studio/general-tab.js::setField` (~:327), `setModel` (~:338) on the general handle | verified |
| `static/js/areas/studio/agent-editor-follow.js` — `applyAgent_` writes through `setField`/`setModel`/`followSet`, then rebases | verified |
| `the_one/gleepglorp/proposals/shape.py::AGENT_FIELDS` (:71) — name (create only), description, system_prompt, provider, model, enabled/disabled tools, mcp_servers, knowledge_bases, rich_visuals, notes_enabled, max_iterations, retention | verified |
| `the_one/gleepglorp/proposals/guard.py::check` (:101) — the content guard over a change's strings | verified |
| `the_one/db/schema.py` — `CURRENT_VERSION = 54`; `gleepglorp_proposals.kind` CHECK `('agent','rule','routine')` (~:3436) | verified |
| `tests/test_gleepglorp_prompt.py::test_the_prompt_fits_450_tokens` (:99) — the cap, three variants | verified |
| `static/js/ui/drawer.js` — push and overlay modes, no document listeners | verified (survey) |
| `the_one/llm/base.py` (~:192-246) — `peer_name` is projected to providers; the routine and proposal marks are never sent | verified (Architect, FD spot check) |
| `the_one/llm/{anthropic,openai,ollama}_provider.py` (~:722, ~:289, ~:744) — the `peer_name` inline-prefix projection | verified (FD grep) |
| `the_one/agent/_context.py::TurnContext` (:83) — mutable per-turn context set around `agent.step` | verified (FD) |
| `the_one/agent/core.py::Agent.step` (:226) — `(user_input, on_chunk, on_usage)`, appends `Message.user(user_input)` then runs the iterations | verified (FD) |
| `the_one/llm/base.py::build_user_message_content` (:443) — the shared user-content builder the three adapters call | verified (FD, Architect) |
| `the_one/interfaces/web/app.py::_validate_message_payload` (:1144) — called at ~:3796 and ~:3988 | verified (FD) |
| `the_one/gleepglorp/proposals/tool.py` — `propose_change` is in `TRUSTED_TOOL_NAMES` | verified (FD grep) |
| `the_one/db/schema.py` (~:3443) — `gleepglorp_proposals.status` has its own CHECK | verified (Architect) |
| `static/js/areas/chat/socket.js` — `onopen` runs `refreshAgentsAndSetup()` then `list_sessions`; `gleepglorp_changed` re-joins, `sessions_changed` prunes drafts | verified (Architect) |
| `static/js/areas/studio/agent-editor-controller.js::patchEditor_` (~:208-216) — resets the snapshot on patch | verified (Architect) |
| `evals/harness.py` (~:802) — calls `agent.step(text)` directly | verified (Architect) |

### Prerequisites

- [x] Flight 2 merged (#381, `3aa9ea94`).
- [ ] The eval apparatus is ready at the evals legs, re-verified there: the
  plan token file present (never read or printed), Ollama with `qwen3-4b`,
  `pip install -e ".[evals]"`.
- [ ] A scratch dev instance with a real Claude provider for the HAT (port
  8486 or higher, scratch data dir under `$HOME`), re-verified at the HAT.
- [ ] The desktop apparatus at the webview leg: the WebKitGTK probe on a dev
  instance on 8486+, the Windows test copy (ports 8490+), and a hosted macOS
  dispatch, each re-verified at that leg.
- [ ] A quiet host for the closing gate (1-minute load below about 1.0, no
  other test process).

### Pre-Flight Checklist
- [x] All open questions resolved (one kept open for the HAT: the Agents icon)
- [x] Design decisions documented
- [x] Citation Audit complete
- [ ] Prerequisites verified (re-verified at the legs that need them)
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

1. Lift the Chats area body into `App.chat.create(config)` with the Chats
   profile, behaviour unchanged, and prove it with every chats lane unedited.
2. Add the shell slot, the corner button and the drawer's shell and states,
   then the drawer profile with its own socket, the shared window-frame
   handler, continuity and Open in Chats.
3. Send the page with each drawer message, through `turn_info` and the
   approved `Agent.step(page=)` kwarg, into `Message.page`, which the shared
   user-content helper shows the model on every turn.
4. Add the fill: the `gleepglorp_fills` table (v55), the drawer-only
   `fill_form` tool over the proposal shape and guard,
   `fill_requested`/`fill_changed`, the claim and outcome routes, then the
   agent editor's ready seam, the sender-only applier, notes and the
   receipts.
5. Tune the prompt (`p4`, cap 550), the guide and the evals, then record the
   n=20 baseline.
6. Check the desktop webviews, walk the HAT, run the closing gate.

### Checkpoints
- [x] Chats behaves exactly as before on the factory (chats lanes unedited).
- [x] The corner button and drawer work on Agents, Library and Settings, hide
  on Chats, and keep the conversation across pages and a reload.
- [x] A window opened straight into Agents receives `config_changed`.
- [x] A drawer message's page reaches the model as one marked line.
- [x] A fill puts values into the agent editor as unsaved edits, keeps an
  operator's unsaved edit, and stores nothing.
- [x] `p4` within 550 tokens (shipped as `p4c`); the n=20 baseline
  `m36f3-gleepglorp.json` recorded with Haiku at its bars and zero safety
  failures.
- [x] The three desktop engines show the drawer and a fill.
- [ ] A full quiet-host gate on HEAD, targets restated. *(Changed by the
  operator on 2026-11-21: the gate ran on HEAD `1427d98c` as a correctness
  check and passed. The re-measure and re-budget move to Flight 4.)*

### Adaptation Criteria

**Divert if**:
- The factory refactor cannot keep Chats unchanged without editing the chats
  tests' assertions (stop and re-plan the instance boundary with the
  operator). Edits to socket and locator apparatus (`_chats.py` scoping, the
  socket-wrapping helpers in Leg 3) are expected and are not a divert.
- Putting the page into the provider request needs more of the frozen
  `agent/core.py` than the one approved `page=` kwarg on `step`.
- A desktop engine cannot host the drawer beside the page (re-plan placement
  with the operator).

**Acceptable variations**:
- Module names and splits inside DD12's areas.
- The exact wording of the page line, the receipt and the notes.
- Splitting a leg at its design review (as Flight 2's Leg 7).

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned
> and created one at a time as the flight progresses.

- [ ] `01-chat-instance` — `App.chat.create(config)` with the Chats profile;
  the descriptor seams and router calls through the adapter; picker hooks in
  config; `destroy()`; the `.chat-instance` CSS rename. Chats unchanged. High
  risk (shared module, lifecycle).
- [ ] `02-drawer-shell` — the shell slot, the corner button factory
  (catalogue row, contract tests), the `App.ui.drawer` close-focus option,
  the drawer shell with its static states (setup, off), Close and Esc, focus,
  closed by default, the content padding, hidden on Chats, the router's
  route-change notification and the "Looking at" line, the Jump to candidate.
  Runs every non-Chats lane.
- [ ] `03-drawer-chat` — the drawer profile (GleepGlorp only, its `onopen`,
  lazy rejoin, New chat, Open in Chats, the empty state's suggestions and the
  working state), the shared window-frame handler on both sockets (DD3), the
  socket gap closed, the socket apparatus helpers, `_chats.py`'s locators
  scoped to the Chats panel, duplicate pane testids handled.
- [ ] `04-page-awareness` — the page descriptor, `page` on `message` and
  `start_session` (with re-sends and queued sends), validation and
  sanitising, `turn_info["page"]`, the approved `Agent.step(page=)` kwarg,
  `Message.page` in the codec and UI events, the projection in
  `build_user_message_content`, `TurnContext.page`, the harness, the chip in
  both instances. High risk (the frozen core, the provider request).
- [ ] `05-fill-server` — schema v55 `gleepglorp_fills`, its store and the five
  carry sites, the drawer-only `fill_form` (trusted for taint),
  `fill_requested` / `fill_changed`, the claim and outcome routes, `fills` in
  the snapshot, the no-write and allowlist tests. High risk (schema, a new
  write surface). Depends on 04.
- [ ] `06-fill-client` — the agent editor's ready seam and `name` handle, the
  sender-only fill applier (claim, unsaved edits, the operator's edits kept),
  fill notes, the receipt states and Fill now, read-only receipts in Chats,
  focus. High risk (a new browser write seam). Depends on 03 and 05.
- [ ] `07-prompt-and-evals-setup` — `p4` candidates, cap 550, the guide
  topics, harness page marks, the new checks with offline tests, new
  scenarios. Autonomous; reviewed and committed before any quota.
- [ ] `08-prompt-and-evals-rounds` — operator-gated rounds under the adopted
  method; ship the prompt; record `m36f3-gleepglorp.json` at n=20.
- [ ] `09-desktop-webviews` — the three engines with the scripted mock
  (DD11).
- [ ] `10-hat` — the guided HAT (DD13), then the closing gate and the
  restated targets.

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing: the unit tier and every browser lane, with
  `THE_ONE_REQUIRE_WEBKIT=1` and `THE_ONE_TEST_NETNS=1`, on a quiet host
- [ ] Documentation updated: CLAUDE.md (the drawer, the window socket, the
  fill, the targets), `the_one/agents.md` sections, the guide, the catalogue
  row, `evals/README.md` for the new checks

### Verification
- Unit: the fill tool's no-write test, the allowlist, the shape and guard over
  fills, the page validation, the schema step, the prompt cap.
- Browser: the factory (chats lanes unedited), the drawer and button on each
  destination, Esc, hidden on Chats, continuity, the window socket on a
  deep-linked Agents page, a fill into the agent editor (clean, over an
  unsaved edit, Stay), notes and the receipt, both engines for the new
  control.
- Evals: the n=20 baseline on the final set.
- HAT: the walk in DD13, with a real Claude model.
- Desktop: the three engines (DD11).
