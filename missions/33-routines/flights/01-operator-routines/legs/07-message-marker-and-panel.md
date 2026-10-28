# Leg: message-marker-and-panel

**Status**: ready
**Flight**: [Operator Routines, End to End](../flight.md)

## Objective

The chat shows a routine run for what it is:
- **The message.** The run's message renders as the routine's: a user-side
  bubble attributed to the routine's name with a "Routine" chip, never "You"
  and never `[routine] `.
- **The open chat.** An open chat treats a routine turn as in flight: Stop
  works, sends are held, and `done` ends it.
- **The panel.** The agent panel shows the chat's routine ("Routine: {name} ·
  last ran {time}") and a read-only Routines group listing the agent's
  routines.

## Context

- Flight DD7 (the client half: the transcript and the in-flight state) and
  DD10 (the panel).
- **What the server sends** (Batch A, legs 3-4):
  - a live `user` frame with `source: "routine"`, `routine_id` and
    `routine_name`;
  - stored USER events from `messages_to_ui_events` with `routine_id` and
    `routine_name`;
  - `session_joined`'s `session_metadata.routine = {id, name, last_run_at}`;
  - a `session_updated` after each run, which makes the client re-join;
  - `GET /api/agents/{name}/routines`, returning the row shape with
    `next_run_at`, `finished_at` and `enabled`.

  Re-read the Batch A flight-log entries for the actual field names.
- **Library rule:** new UI is built from `App.ui` controls, and a new
  factory option needs its inventory row and contract test.
- **`App.ui.message`:** `source` accepts only `api` (it throws on anything
  else), and the "Operator only" chip appears only on non-user roles
  (`ui/message.js:60-91`).

## Inputs

All paths are under `the_one/interfaces/web/static/js/`.

- `areas/chat/transcript.js`:
  - `addMsg(cls, text, attribution, opts)` and `sideFor(role, opts)`
    (`:56-103`);
  - history replay of user events, with the source prefix (`:153-157`).
- `areas/chat/turn-frames.js`:
  - live `user` handling, with the source prefix (`:66-79`);
  - the `done` handler, which clears `inFlightSessions` and `ownTurn`
    (`~:185-200`).
- `areas/chat/send.js`:
  - the own send sets `state.inFlightSessions[active]` and
    `state.ownTurn[active]`, then calls `updateStopControl` and
    `showThinking` (`:53-64`).
- `areas/chat/socket.js`:
  - `session_joined` handling of `is_processing` and the hold queue
    (`:240-275`);
  - `agentDrawer.refreshNotes()` (`:268`);
  - `session_updated` re-joins any open chat (`:117-129`).
- `ui/message.js`: its options and the chip (`:60-100`). Its inventory row is
  in `docs/ui-control-inventory.md` (`~:109`), and its contract test is
  `tests/browser/test_ui_message*.py` in the `contracts-chat` lane.
- `areas/chat/agent-drawer.js`:
  - `facts(pairs)` (`:280-288`);
  - the agent render's facts (`:582-586`);
  - `uses(row)` and its groups (`rulesGroup` at `:329`, `notesGroup` at
    `:410`);
  - `ensureFetches` (`:607-671`);
  - the view `{agent, sessionId}`, built in `areas/chat.js:299`.
- `App.time` (`time.js`): `formatClock`, `formatDate`. Every time shown to a
  person goes through it.

## Outputs

- **`ui/message.js`:** a new `marker` option, `{label: string}`, renders an
  `App.ui.chip` (size sm) inside a new owned span, `ui-message-marker-chip`,
  on any role. The inventory row and the contract test are extended.
- **Transcript:**
  - `transcript.js` and `turn-frames.js` render a user event with
    `routine_name` as a user-side bubble with attribution
    `routine_name`, side `you`, and `marker: {label: 'Routine'}`;
  - the bubble gets no `[routine] ` prefix;
  - `data-routine-id` is set on the bubble root by `addMsg`, with
    `msg.el.setAttribute`, following the `data-visibility` precedent. The
    factory gains only `marker`.
- **In-flight state:** a live `user` frame with `source === 'routine'` for
  the bound chat sets `state.inFlightSessions[sid] = true` (not `ownTurn`),
  then calls `updateStopControl()`, `applyComposerState()` and
  `showThinking()`. The `done` handler already clears it.
- **Panel (`agent-drawer.js`):**
  - **The routine metadata** reaches the drawer through a new export,
    `agentDrawer.setSessionMetadata(sessionId, meta)`. `socket.js` calls it on
    every `session_joined`, next to `refreshNotes()`, which includes the
    re-join after `session_updated`. The drawer keeps it keyed by session id
    and renders it only while its view's `sessionId` matches, so chat A's
    routine never shows in chat B. Leaving a chat, a pending chat, a delete,
    or joining a different chat drops it. The view itself is unchanged.
  - **A "Routine" fact.** `facts(pairs)` gains an optional fourth pair
    element, the row testid. The row is testid `chat-drawer-routine`, shown
    when
    `sessionMetadata.routine` is set: "{name} · last ran {day} {h:mm AM/PM}".
  - **A "Routines" group** after Notes (`data-group="routines"`). It lists
    routines A-Z with meta "Next {day} {time}", "Off" or "Done". It is
    fetched per open like Rules (404 means none) and refetched on each
    `session_joined`.
- **Registry and tests:**
  - `docs/ui-testid-registry.md` gains `chat-drawer-routine` and the
    Routines group's testids, and any new testid;
  - `tests/browser/test_flow_chat_routine_marker.py` (new) is added to
    `chats_transcript_pat` in `scripts/run-tests.sh`;
  - the drawer tests in the `chats` lane (the existing drawer test file)
    gain the panel cases.
- **Docs:** `the_one/agents.md` gains notes in its "Chat transcript on the
  library" and "Agent drawer" sections.

## Acceptance Criteria

- [ ] AC0. **Marker DOM and validation details** (design review).
      - **Placement:** `span.ui-message-marker-chip` holds an `App.ui.chip`
        (label, `size: 'sm'`). It comes after the operator chip and before the
        hidden peer label and the body.
      - **Validation:** `marker: null` and `undefined` are no-ops. A `marker`
        whose `label` is empty or not a string throws.
      - **Where it is documented:** the options header comment in
        `ui/message.js`. The inventory row adds the owned class.
      - **CSS:** in `components.css`.
      - **Contract cases:** they go in the existing `test_ui_message*.py` file
        that already calls `App.ui.message(`.
- [ ] AC1. **The `marker` option.** `App.ui.message({..., marker: {label}})`
      renders the chip on any role.
      - With no marker the DOM is unchanged, pinned by the existing contract
        test.
      - The marker text is part of the bubble's accessible text, in the same
        way as the "Operator only" chip.
      - A bad `marker` (not an object with a non-empty string `label`)
        throws.
      - The contract test (Chromium and WebKit) covers both.
      - The inventory row lists the option and the owned class
        `ui-message-marker-chip`.
      - `tests/test_ui_emitted_classes.py` and `tests/test_ui_ownership.py`
        pass.
- [ ] AC2. **Live and replayed routine messages.**
      - The bubble is user-side and right-aligned, like the operator's.
      - The attribution name is the routine's name, and the bubble carries a
        "Routine" chip and `data-routine-id`.
      - The bubble text is the prompt with no prefix, never "You".
      - On a connector chat the user bubble shows no "Operator only" chip
        (user bubbles never do), and the agent reply's chip follows its
        stored visibility after the re-join.
      - Other sources keep today's prefix behaviour, so `api` is unchanged.
- [ ] AC3a. **Gating, ordering and the re-join** (design review).
      - **Gate:** a routine `user` frame sets the in-flight state only when
        `data.session_id === chatState.boundId()`, with the same gate as the
        chat's other turn frames. A frame for another chat changes nothing,
        and a test covers it.
      - **Order:** `showThinking()` runs after `addMsg`.
      - **Re-join:** the runner's `session_updated` arrives after `done`
        (leg 4 AC9). If a re-join happens mid-run, the join reply's
        `is_processing` restores the in-flight state; a test injects that
        order.
      - **Held messages:** at `done` of a routine turn with a held message,
        the held message is sent and gets `ownTurn`, the thinking indicator
        and Stop reset, and the composer state is re-applied.
      - **Drafts:** the open chat's unsaved draft survives a `session_updated`
        re-join (per-chat drafts, M31 F6 L10c).
- [ ] AC3. **An open chat during a routine run.** When a routine run starts in
      the open chat:
      - the thinking indicator shows;
      - Stop is enabled, and clicking it sends `cancel`;
      - typing and pressing Enter holds the message in the hold queue;
      - after `done`, the held message is sent and the state returns to
        idle.

      The routine turn sets `inFlightSessions` but never `ownTurn`. A test
      drives the injected socket frames (the `SocketScript` helper pattern
      from `scripts/ui_capture.py`, or `_chats.py`'s frame tools), with no
      real run.
- [ ] AC4. **The Routine fact.** After a routine run, the open chat re-joins
      on `session_updated`. The panel then shows the fact
      `chat-drawer-routine` with the routine's name and its last run, both
      through `App.time`. A chat with no routine metadata has no such row.
- [ ] AC5a. **Refresh without flicker** (design review).
      - `refreshRoutines()` is exported and called from `socket.js` next to
        `refreshNotes()`. It is a no-op while the drawer is closed or the view
        is not a named agent.
      - A refetch while data is shown keeps the list until the response
        arrives, the `loadNotes(..., refresh)` pattern, so "Loading…" never
        flashes.
      - Responses are guarded by `gen` and agent.
      - The default and deleted agents' render omits the group, not only the
        fetch.
      - **Meta precedence:** Done (`finished_at` set) wins over Off
        (`enabled` false), which wins over "Next {weekday} {h:mm AM/PM}"
        (the weekday helper `chats-list.js` uses, plus
        `App.time.formatClock`).
      - **Testids:** `chat-drawer-routines` (the list) and
        `chat-drawer-routine-item` (each row), registered next to the other
        `chat-drawer-*` rows.
- [ ] AC5. **The Routines group.**
      - Placement and data: it sits after Notes, lists the agent's routines
        A-Z by name, and the meta reads "Next Tue 9:00 AM" (through
        `App.time`), "Off" or "Done".
      - States: "None" when there are none; "Loading…" then the list; and
        "Couldn't load" on an error other than 404.
      - It is refetched on each `session_joined`.
      - It is read-only; Open agent settings is unchanged.
      - The default agent and a deleted agent show no group.
      - Routine names are rendered with `textContent` only.
- [ ] AC6. **Gates.**
      - **Lanes** (`THE_ONE_TEST_NETNS=1`): `chats`, `chats-transcript`, and
        `contracts-chat` with `THE_ONE_REQUIRE_WEBKIT=1`.
      - **Static guards:** `tests/test_ui_guards.py` (including the registry
        diff and the HTML-sink baseline, which stays empty),
        `tests/test_token_definitions.py` and
        `tests/test_design_tokens_a11y.py`.
      - **Also:** `make test-unit` and `make lint`.

## Verification Steps

- AC1: `tests/browser/test_ui_message*.py`
  (`--lane contracts-chat`, `THE_ONE_REQUIRE_WEBKIT=1`).
- AC2-AC3: `tests/browser/test_flow_chat_routine_marker.py`.
  - The replay case seeds a session whose messages include a USER message
    with `routine_name`, through `seeders.seed_session(..., messages=...)`.
  - The live case injects frames.
- AC4-AC5: the drawer browser tests. They seed routines through the REST API
  (leg 1 routes) and a session through
  `seeders.seed_session(..., session_metadata=...)`. That new optional kwarg
  in `tests/browser/seeders.py` is a one-line pass-through, since
  `ChatSession` has the field. Seeded messages use the stored shape from
  `encode_messages`, carrying `routine_id` and `routine_name`.
- AC6: the commands.

## Implementation Guidance

1. **The factory option, the inventory row and the contract test** (AC1).
2. **Transcript** (AC2): one helper decides the user bubble's attribution,
   side, marker and prefix from an event, and both replay and live call it.
   That puts the two prefix sites in one place.
3. **In-flight** (AC3): in `turn-frames.js`'s `user` branch, when
   `data.source === 'routine'` and the frame is for the bound chat, set the
   in-flight state. `inFlightSessions` is what `updateStopControl` reads, so
   Stop's `cancel` goes through the existing path.
4. **Session metadata plumbing** (AC4): `socket.js` stores
   `data.session_metadata` on `state` at `session_joined`, `chat.js` passes it
   in `drawerView`, and the drawer renders the fact.
5. **The Routines group** (AC5): copy `rulesState`'s fetch shape. Refetch from
   the same place `refreshNotes` is called on `session_joined`; add a
   `refreshRoutines()` export.
6. **Registry, docs and lanes.**

## Edge Cases

- **A routine renamed after a run.** The stored message keeps the name it ran
  under, and the panel's group shows the current name. That is intended.
- **A long routine name.** It wraps in the attribution and is ellipsized in
  the group, with the full name in `title`.
- **A routine run in a chat that is not open.** The Chats row activity
  (M31 F6 L10b) already shows working and new. Nothing else changes.
- **`session_updated` arriving while the operator is typing.** Per-chat
  drafts (M31 F6 L10c) keep the draft across the re-join. Verify this in the
  AC3 test.

## Files Affected

All `static/js` paths are under `the_one/interfaces/web/static/js/`.

- `static/js/ui/message.js`, `static/css/components.css` (the marker chip
  layout)
- `static/js/areas/chat/transcript.js`, `turn-frames.js`, `socket.js`,
  `agent-drawer.js`, `static/js/areas/chat.js`
- `docs/ui-control-inventory.md`, `docs/ui-testid-registry.md`,
  `scripts/run-tests.sh` (`chats_transcript_pat`)
- `tests/browser/seeders.py` (the `session_metadata` kwarg), `CLAUDE.md`
  (the chat transcript paragraph),
- `tests/browser/test_ui_message*.py`,
  `tests/browser/test_flow_chat_routine_marker.py` (new), the drawer browser
  test file
- `the_one/agents.md`

## Citation Audit

Checked on the working tree:
- `transcript.js:56-103`, `:153-157`;
- `turn-frames.js:66-79`, `~:185-200`;
- `send.js:53-64`;
- `socket.js:117-129`, `:240-275`;
- `ui/message.js:60-100`;
- `agent-drawer.js:280-288`, `:329`, `:410`, `:582-586`, `:607-671`;
- `areas/chat.js:299`.

The Batch A server fields come from their plans; re-read the flight log
before starting.

---

## Post-Completion
Completion steps (status transitions, flight-log update, checking off in the
parent flight, and the commit) are Flight Control protocol, driven by the
execution workflow, and are not repeated here.
