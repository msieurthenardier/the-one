# Leg: approval-continuation

**Status**: ready
**Flight**: [Proposals and approval](../flight.md)

## Objective
After the operator approves a proposal, GleepGlorp's next turn starts in that
chat with a marked approval message, so a request with several steps continues
one step at a time. A dismissal, or an approval while GleepGlorp is not ready,
is recorded in the chat as a marked message with no turn.

## Context
- Flight DD8 (as amended by Architect cycle 2), DD7 (the routes), DD12
  (`sessions/turn_host.py`).
- Leg 4 built the approve and dismiss routes and `apply_proposal`. Its approve
  route has a `# Leg 5: continuation` marker after the frames on an apply. Its
  dismiss path ends after `push_proposal_changed`. This leg adds one call at
  each.
- The routine runner already starts server-side turns through a `TurnHost`
  (`routines/runner.py` L53: `get_or_restore`, `spawn_turn(session, prompt,
  turn_info)`, `broadcast`, …). `app.py::_RoutineTurnHost` (~L2068) is its
  implementation, registered at lifespan start (`set_turn_host`, ~L550). The
  routes in `api.py` modules cannot import `app.py`, so the protocol moves to a
  neutral module.
- A routine turn's marks travel in `turn_info["routine"]`:
  - `_process_and_broadcast` reads them (~L2560-2595), puts them on the live
    `user` frame (`routine_id`, `routine_name`, `session_id`) and
    `session.add_event`, and binds them onto the stored USER message through
    `_bind_turn_user_marks` (~L2528).
  - The codec stores and projects them (`codec.py` ~L204-210, L270, L398).

  The proposal mark follows the same path.
- **No double add** (Architect cycle 2): `spawn_turn`'s prompt is appended by
  the turn itself as its user message, so Approve never appends separately.
- **The race** (Architect cycle 2): `_locked_message_processing` (~L1274)
  returns early for a GleepGlorp chat that is not `ready`, read under the turn
  lock, and sends a `system` frame. A turn spawned for an approval must then
  store the marked message instead of dropping it.
- **One small client change in this leg** (design review). The client marks a
  server-started turn as in flight only for `source === 'routine'`
  (`static/js/areas/chat/turn-frames.js:81`): busy, Stop, held sends, and
  `turnWork.begin()`. `transcript.js:181` also prefixes any non-web source
  label.
  - This leg treats a `user` frame with `proposal_id` like a routine frame for
    in-flight handling, and suppresses the source prefix for it. That is about
    five lines.
  - Leg 6 draws the quiet line in place of the bubble. Until then the marked
    message renders as a plain user bubble, which is acceptable inside Batch B.

## Inputs
- `the_one/routines/runner.py`: `TurnHost` Protocol (L53-68), `set_turn_host`
  (L74), and `_host`.
- `the_one/interfaces/web/app.py`:
  - `_RoutineTurnHost` (~L2068-2093), `_spawn_routine_turn` (~L1366);
  - `_locked_message_processing` (~L1274-1340);
  - `_process_and_broadcast` (~L2553: `turn_info["routine"]`, `user_event`,
    `current_turn` `TurnContext`), `_bind_turn_user_marks` (~L2528);
  - `_save_session_to_db`, `_send_to_session`, `_broadcast_to_session`;
  - the session cache `_sessions`, `_get_or_restore_session`;
  - the per-session lock through `track_turn` / `the_one.sessions._locks`.
- `the_one/llm/base.py::Message` (L166, the routine fields ~L236-241, the
  constructor ~L309).
- `the_one/db/codec.py` (the message dict ~L204, the decode ~L270, the history
  events ~L398).
- Leg 4's `gleepglorp_proposals_api.py` and `proposals/apply.py`.

## Outputs
- `the_one/sessions/turn_host.py`: the `TurnHost` Protocol (moved; it gains
  `append_marked_message`), `set_turn_host` and `get_turn_host`.
  `routines/runner.py` imports them from there, keeping its old names as
  re-exports.
- `Message` gains `proposal_id: int | None` and `proposal_event: Literal
  ["approved", "approved_no_turn", "dismissed"] | None`.
  - `approved` marks the user message of a continuation turn.
  - `approved_no_turn` marks an approval appended with no turn (GleepGlorp
    unready, the race branch, or a failed spawn), so Leg 6's quiet line can
    say "You approved this change." without "GleepGlorp is continuing." The codec stores and projects them on the
  stored message and in history events, and the live `user` frame carries
  them.
- `app.py`:
  - the host keeps its name, `_RoutineTurnHost`
    (`tests/test_routines_runner.py:168-176` patches it by name), and
    implements `append_marked_message`;
  - `_process_and_broadcast` reads `turn_info["proposal"]`;
  - `_locked_message_processing` stores the marked message on the
    unready-GleepGlorp branch.
- `the_one/gleepglorp/proposals/continuation.py`: `approval_text(row)`,
  `dismissal_text(row)`, `on_approved(row)` and `on_dismissed(row)`. Leg 4's
  routes call them, and Leg 8's harness uses the texts.
- Tests and docs.

## Acceptance Criteria
1. **The seam moves.** `the_one/sessions/turn_host.py` holds the `TurnHost`
   Protocol, `set_turn_host(host)` and `get_turn_host()`.
   - `routines/runner.py` uses them and still exports `TurnHost` and
     `set_turn_host` under the old names.
   - No module under `the_one/sessions/`, `the_one/routines/` or
     `the_one/gleepglorp/` imports `the_one.interfaces`. An AST import scan
     asserts this for the new modules, like the existing guards.
   - **One readiness check:** `continuation.py` and the race branch use the
     same function (`gleepglorp.settings.state(...) == "ready"`).
   - The routine runner tests pass unchanged.
2. **`append_marked_message(session_id, text, marks) -> bool`** on the host,
   where `marks = {"proposal_id": int, "proposal_event": "approved_no_turn" |
   "dismissed"}`. It:
   - **restores the session** (`get_or_restore`). An unready GleepGlorp chat
     restores to a degraded status but still returns a `Session`, and the
     append goes ahead. Only `None`, meaning a missing or deleted chat,
     returns `False` and does nothing.
   - **takes the session's lock directly** (`async with session_locks[sid]`,
     the same lock object, `sessions/_locks.py:22`), never `track_turn`. That
     would push `sessions_changed` twice and make the chat flash busy, and
     Leg 4's busy 409 reads that lock.
   - **appends, in order:**
     1. `repair_unanswered_tool_calls(session.agent.messages)`, as the turn
        path does (~L2700);
     2. `session.agent.messages.append(Message(role=USER, content=text,
        created_at=…, proposal_id=…, proposal_event=…))`, setting
        `created_at` the way `Message.user` does (`llm/base.py` ~L309);
     3. `session.add_event(user_event)`, with `messages_to_ui_events`-
        compatible keys (`type: "user"`, `source`, `ts`, the marks).
        `add_event` also sets the title while it is "New chat" (~L938).
   - **saves** through `_save_session_to_db`. That encodes the messages and
     sets `db_fingerprint`, so a later resync is a no-op.
   - **sends** the `user` event to the chat's subscribers.
   - **calls `notify_sessions_changed()` once**, so the Chats list reorders.
   - **returns `True`.**

   It never starts a turn. A test shows that a second, concurrent call and a
   running turn's save both keep the message (no lost write).
3. **The approval turn.** `continuation.on_approved(row)`, called by Leg 4's
   approve route after the frames on an apply:
   - **When GleepGlorp is `ready`** (read now, from the settings) and the chat
     exists, it calls `get_turn_host().spawn_turn(session,
     approval_text(row), {"proposal": {"id": row.id, "event": "approved"}})`.
     The spawn is registered like a web turn: the chat shows busy, Stop
     cancels it, shutdown drains it.
     - `_process_and_broadcast` treats `turn_info["proposal"]` like
       `turn_info["routine"]`. The live `user` frame (~L2589-2594) and the
       history event gain `proposal_id` and `proposal_event`.
     - `_bind_turn_user_marks` gains an explicit `proposal` parameter (not
       folded into `routine`) and binds the marks onto the stored USER
       message at both of its call sites: the cancel save (~L2729) and the
       normal save (~L2981).
     - **The client** (Context): in `turn-frames.js`, a `user` frame with
       `proposal_event === 'approved'` (only that value) is handled like a
       routine frame for in-flight state. `approved_no_turn` and `dismissed`
       mark nothing in flight. `transcript.js` adds no source prefix for a
       `proposal_id` frame. Run the static guards.
     - The turn's `TurnContext` is ordinary (no peer, no routine), so the
       approval message is the operator's own and not a taint source.
   - **When GleepGlorp is not ready, or the spawn fails**, it calls
     `append_marked_message(row.session_id, approval_text(row),
     {"proposal_id": row.id, "proposal_event": "approved_no_turn"})` instead,
     and no turn starts. The race branch (AC4) uses `approved_no_turn` too.
   - **When the chat no longer exists**, it does nothing and the approve
     response is unchanged.
   - It never raises into the route: errors are logged, and the apply already
     committed.
4. **The race branch.** In `_locked_message_processing`, when the GleepGlorp
   readiness check fails and `turn_info` carries `proposal`:
   - the marked message is stored through the same append logic, inline,
     because this code already holds the turn lock (so the host method must
     not be called here; factor the append into a lock-free helper that both
     use);
   - the existing `system` frame is not sent, and `turn_info["error"]` is not
     set (~L1304-1311 sets it today). `_spawn_proposal_turn` does not treat
     "started, but no assistant output" as a failure;
   - the append happens after `_resync_session_from_db`, where the branch
     already sits, so a resync cannot discard it.

   Ordinary messages keep today's behaviour exactly. A test drives it with
   settings flipped between the route's check and the turn.
5. **Dismissal.** `continuation.on_dismissed(row)`, called by Leg 4's dismiss
   path after its frame, calls `append_marked_message(row.session_id,
   dismissal_text(row), {"proposal_id": row.id, "proposal_event":
   "dismissed"})`, with no turn. GleepGlorp reads it with the operator's next
   message.
6. **The texts**, constants in `continuation.py` and shared with Leg 8's
   harness:
   - `approval_text`: "Approved proposal {id}: {summary}. Continue with the
     next step, if there is one."
   - `dismissal_text`: "Dismissed proposal {id} ({title}). Do not apply it."

   Here `summary` is Leg 4's `result.summary`, and `title` is the card title
   built from the shape (for example "change agent Issue digest").
7. **Consecutive user messages.** A dismissal, or an approval while
   GleepGlorp is unready, followed by the operator's next message, leaves two
   USER messages in a row.
   - The builders convert per message, with no alternation logic in
     `the_one/llm/`:
     - `openai_provider.py` ~L267-304;
     - `anthropic_provider.py` ~L687-737;
     - `ollama_provider.py` ~L564-597 and ~L722-754.
   - All these APIs accept consecutive user turns; Anthropic merges them on
     its side.
   - A unit test per provider type (Anthropic and the plan types through the
     shared builder, OpenAI, OpenAI-compatible and OpenRouter, Ollama) feeds
     two consecutive USER messages through its builder entry point. It asserts
     they become two well-formed user entries, not merged and not dropped.
   - No merge code is written. The flight log records that none was needed.
8. **Codec.**
   - `proposal_id` and `proposal_event` round-trip through the stored message
     dict and its decode.
   - History events project them on the `user` event, as `routine_id` is.
   - A test covers save, restore and replay.
   - Messages without the marks are byte-identical to today, with no new keys
     emitted when they are `None`.
9. **Tests**, falsified where marked:
   - `tests/test_gleepglorp_proposals_continuation.py`:
     - the approve path spawns a turn with the marked prompt (fake host),
       falsified by dropping `turn_info`;
     - the unready path appends with no turn;
     - the race branch stores the message, falsified by restoring the early
       return;
     - dismissal appends;
     - a missing chat is a no-op;
     - the texts.
   - `tests/test_turn_host.py`: `append_marked_message` with the lock, the
     concurrent case and the deleted chat.
   - Codec round trip (AC8).
   - Provider conversion (AC7).
   - An integration test reuses `tests/_routine_app.py`'s `routine_app`
     fixture and `Harness` (`h.llm.script`), adding a proposal helper there. It
     shows:
     - an approval on a ready GleepGlorp produces a user message with the
       marks and a scripted reply;
     - a Stop during that turn keeps the marks (the cancel bind site);
     - an approval or dismissal on a reaped session (rebuilt by
       `get_or_restore`) still appends.
   - The existing routine runner, chat and codec tests stay green.
10. **Docs:**
    - `the_one/agents.md`: the continuation, the marked messages and the moved
      seam;
    - the WebSocket table: the `user` frame's new keys;
    - `CLAUDE.md`'s proposals paragraph: one sentence that Approve continues
      the chat.

## Verification Steps
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_gleepglorp_proposals_continuation.py tests/test_turn_host.py $(grep -rlE 'routines\.runner|TurnHost|set_turn_host|codec' tests/*.py) -x --timeout 60`
- `THE_ONE_TEST_NETNS=1 make test-unit`.
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane chats`
  and then `--lane chats-transcript`, one at a time. These cover the frame
  and history changes on the server.
- `ruff check` and `ruff format --check` on the touched files.

## Implementation Guidance
1. Move the `TurnHost` Protocol to `sessions/turn_host.py`, adding
   `append_marked_message`. Re-export it from `routines/runner.py`, and run the
   routine runner tests.
2. Add the `Message` fields, then the codec store, decode and projection, with
   a round-trip test.
3. In `app.py`:
   - factor a lock-free `_append_marked_user_message(session, text, marks)`
     (append, add the event, save, send);
   - have the host's `append_marked_message` take the lock and call it;
   - extend `_process_and_broadcast` and `_bind_turn_user_marks` for
     `turn_info["proposal"]`;
   - add the unready race branch in `_locked_message_processing`;
   - add `_spawn_proposal_turn`, registered like `_spawn_routine_turn` (choose
     a `source` label the code accepts; read how `source` is used before
     picking).
4. Write `continuation.py`, and call it at Leg 4's two marked spots.
5. Check each provider's conversion of consecutive user messages, and merge
   only where needed.
6. Write the tests, falsify the marked ones, run the guard set, the two lanes
   and the unit tier, then update the docs.

## Edge Cases
- **The operator sends a message while the approval turn is queued.** The
  per-session lock serializes them, and the queued web message runs after the
  approval turn. That is today's behaviour for two sends.
- **Stop during the approval turn.** It behaves like a stopped web turn, and
  the stored user message keeps its marks (`_bind_turn_user_marks` runs at the
  cancel save site too).
- **A connector chat can never be a GleepGlorp chat** (Flight 1), so the
  connector `visibility` branch does not apply. A test is not needed.
- **The approval turn's own proposal**: the next `propose_change` sees the
  previous proposal `applied`, so the one-open rule (Leg 2) allows it.
- **Two approvals back to back.** Leg 4 refuses an approve while the chat is
  busy (409 `busy`), so a second approval waits for the first turn to end.
- **Shutdown during an approval turn**: drained as a web turn.

## Files Affected
- `the_one/sessions/turn_host.py` (new); `the_one/routines/runner.py` (imports
  and re-exports).
- `the_one/llm/base.py` (`Message` fields); `the_one/db/codec.py`.
- `the_one/interfaces/web/app.py` (the host, the append helper, the proposal
  `turn_info`, the race branch, the spawn).
- `the_one/gleepglorp/proposals/continuation.py` (new).
- `the_one/interfaces/web/gleepglorp_proposals_api.py` and/or
  `proposals/apply.py` (the two calls).
- `static/js/areas/chat/turn-frames.js` and `transcript.js`: the in-flight
  handling and the prefix, with the static guards run.
- `tests/_routine_app.py`: a proposal helper.
- Tests: `test_gleepglorp_proposals_continuation.py`, `test_turn_host.py`,
  codec and provider tests.
- `the_one/agents.md`, `CLAUDE.md`.

## Citation Audit
Checked against the working tree with Leg 1 landed and Leg 2 in progress.
Leg 4 is not yet built, so re-check its marker and names when it lands.
- `routines/runner.py::TurnHost` L53 (`spawn_turn`, `mirror_metadata`,
  `broadcast`, `get_or_restore`), `set_turn_host` L74 — verified.
- `app.py`:
  - `_RoutineTurnHost` ~L2068-2093, with `spawn_turn` calling
    `_spawn_routine_turn` — verified;
  - `set_turn_host(_RoutineTurnHost())` at lifespan ~L550, `None` at ~L653 —
    verified;
  - `_spawn_routine_turn` ~L1366 (calls `_spawn_message_processing(session,
    prompt, "routine", None, turn_info)` and `_register_turn_task`) —
    verified;
  - `_locked_message_processing` ~L1274: the GleepGlorp readiness check under
    `track_turn` returns early after a `system` frame (~L1298-1310) —
    verified;
  - `_process_and_broadcast` ~L2553: `routine = (turn_info or
    {}).get("routine")`, then `user_event` gains `routine_id`,
    `routine_name` and `session_id` (~L2586-2594), followed by
    `session.add_event` and `_send_to_session` (~L2615-2616) — verified;
  - `_bind_turn_user_marks(session, pre_step_len, routine)` ~L2528 binds the
    routine fields and the connector visibility — verified.
- `llm/base.py::Message` L166, with the routine fields ~L236-241 — verified.
- `db/codec.py` routine fields at ~L204-210 (encode), ~L270 (decode) and
  ~L398 (history projection) — verified.
- Design review (Developer, Sonnet), approve with changes. Folded in above:
  - `turn-frames.js:81` keys in-flight handling on `source === 'routine'`
    (high).
  - `track_turn` pushes `sessions_changed` on entry and exit, and
    `session_locks` is at `_locks.py:22` (high).
  - `repair_unanswered_tool_calls` is called at ~L2700. `add_event` is at
    ~L938. `_save_session_to_db` sets `db_fingerprint`.
  - The `_bind_turn_user_marks` call sites are at ~L2729 and ~L2981.
  - The provider builders show no alternation logic.
  - `tests/_routine_app.py`.
  - `test_routines_runner.py:168` patches `_RoutineTurnHost`.

  No second cycle: the reviewer's own fixes, with no new design.
