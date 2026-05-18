# Leg: dispatcher-broadcast-when-subscribed

**Status**: completed
**Flight**: [Chat UI — Unified History, Visibility Distinction, Operator Console](../flight.md)

## Objective

After the dispatcher completes a connector-driven turn and persists
the updated history, emit per-message UI events to any live WS
subscribers of that session_id via the neutral
`the_one.sessions.broadcast_to_session` helper. Zero subscribers
remains a clean no-op (current behavior); the dispatcher gains a
non-mandatory live-broadcast surface so an operator observing the
session in Chat sees each peer-driven message as it lands, with the
visibility tagging already applied by leg 3's helper. No dispatcher
behavior change for the no-subscribers case; no agent loop change.

## Context

- **Flight slot**: F5 L6 — the inbound-side live observation surface.
  The dispatcher persists the turn (already correct), then projects
  the new messages into UI events and broadcasts them. The active
  operator in Chat sees the platform-side conversation arrive in
  real time, with the operator-only marker on the right bubbles.
- **Flight design decision — "Broadcast surface generalization — lift
  `_sessions` registry access AND the broadcast helper to the neutral
  module (architect-revised)"** (flight.md L70-74): F5 L2 has landed
  the `the_one/sessions/` package (`subscribers_for`,
  `broadcast_to_session`, `add_subscriber`, `remove_subscriber`).
  The import direction stays one-way: `connectors._inbound →
  the_one.sessions` is allowed; the leg never imports back into
  `interfaces.web.app`.
- **Flight In-Flight § Leg 6** (flight.md L167-170): the cadence
  decision is **per-message events** (one event per new Message),
  NOT a single end-of-turn batch. Matches the WS-stream cadence so
  an operator observing in real time sees each message as it lands.
- **Live-broadcast visibility — naturally correct here**: unlike the
  WS-typed path (F5 L5's known limitation), the dispatcher emits its
  events AFTER `tag_post_step_visibility` has tagged every new
  message. The codec's `messages_to_ui_events` reads `Message.visibility`
  on each Message and includes it on every projected event. The
  broadcasted events therefore carry `visibility="operator"` (or
  absent, peer-visible) correctly. **This leg implicitly resolves
  the F5 L5 gap on the inbound path** — the WS-typed path's
  symmetric resolution is a separate follow-on.
- **Mission constraint**: agent loop in `the_one/agent/core.py` is
  not modified. Dispatcher's `agent.step` driver is unchanged; the
  leg adds a broadcast step AFTER step + tagging + persist.
- **F5 L1/L2/L3/L4/L5 carry-forward state**: the codec already
  emits `visibility` (F3 L2); F5 L2 owns the broadcast helper; F5
  L3 owns the tagging helper; F5 L4 owns the WS shim; F5 L5 owns
  the render layer. Leg 6 wires the dispatcher to the broadcast
  helper.
- **No schema change.** Pure additive at the dispatcher's tail.

## Inputs

- `the_one/connectors/_inbound.py:155-229` — `dispatch_inbound`'s
  per-session-lock block. The post-`agent.step` flow:
  - Line 183: `pre_step_len = len(agent.messages)` snapshot.
  - Line 193-194: `async for _ in agent.step(envelope.text): pass`.
  - Line 209: `tag_post_step_visibility(agent.messages, pre_step_len)`.
  - Line 218-225: encode + `chat_repo.update(updated)` (persistence).
  - Line 226-229: `finally:` block resets the ContextVar.
  - **Insertion point**: AFTER line 225 (`chat_repo.update`
    complete) and BEFORE line 226 (`finally:`) — inside the
    `try` body, still under the `async with session_locks[…]:`
    block. Holding the lock prevents a concurrent operator-typed
    turn on the same session_id from interleaving broadcasts
    mid-stream.
- `the_one/sessions/_broadcast.py:40-60` — `broadcast_to_session(
  session_id, payload, *, exclude=None)`. Iterates a snapshot of
  the subscriber set; sends each payload via `ws.send_json(payload)`;
  prunes dead WSes. Zero-subscriber case: clean no-op.
- `the_one/db/codec.py:114-187` — `messages_to_ui_events(messages)`.
  Projects a `list[Message]` into UI event dicts compatible with the
  frontend's `ws.onmessage` handler. Emits `visibility` when non-None.
  The function takes the FULL `messages` list but the leg passes the
  POST-STEP SLICE `agent.messages[pre_step_len:]` so only newly-
  appended messages get broadcast.
- `messages_to_ui_events` namespacing detail
  (`the_one/db/codec.py:148,163`): the codec uses
  `enumerate(messages)` and emits `parent_message_id =
  f"replay-msg-{i}"` for assistant-with-tool_calls. Replay-vs-live
  namespacing is disjoint, but **across multiple dispatcher turns
  on the same session** the codec restarts `i` at 0 every call
  (the dispatcher passes a slice). If the leg passed
  `agent.messages[pre_step_len:]`, two consecutive inbound turns
  with an assistant-with-tool_calls at index 0 of each slice would
  BOTH produce `replay-msg-0`, and the frontend's
  `getOrCreateTrace(parent_message_id)` would bucket the second
  turn's tool_call+tool_result events into the FIRST turn's
  trace shell. **This is a real collision**; the leg avoids it
  by extending the codec with an `index_offset` parameter (see
  Outputs) so the dispatcher passes the slice plus
  `index_offset=pre_step_len` and the codec generates ids using
  the ABSOLUTE index `i + index_offset`. Absolute indices are
  unique within a session's lifetime regardless of how many
  inbound turns fire.
- `the_one/connectors/_inbound.py:194` — `async for _ in agent.step(...)` — currently zero on_chunk / on_usage callbacks. **The leg does NOT add streaming chunk broadcast** (the dispatcher doesn't stream — it drives agent.step synchronously per turn).
- `tests/test_connectors_inbound.py` — F4 L4 ground-truth tests for
  the dispatcher's tagging behavior. Regression net: after this
  leg, the dispatcher's behavior in the zero-subscriber case is
  byte-identical to today's tests; the new leg-6 tests assert the
  broadcast path when subscribers exist.

## Outputs

- `the_one/db/codec.py` — `messages_to_ui_events` gains an
  optional `index_offset: int = 0` parameter. When non-zero, all
  internal `enumerate(messages)` indices are offset by
  `index_offset` (i.e. `i + index_offset` is used instead of `i`)
  so `parent_message_id` generation produces
  `f"replay-msg-{i + index_offset}"`. Default `0` preserves
  byte-identical behavior for the existing
  `_restore_session`/`_get_or_restore_session` call sites that
  pass the full messages list. This is the namespace-collision
  fix for repeated dispatcher broadcasts on the same session.
- `the_one/connectors/_inbound.py` — `dispatch_inbound` gains a
  broadcast step AFTER persistence and BEFORE leaving the
  per-session lock. Imports for `messages_to_ui_events` and
  `broadcast_to_session` go at the **module top** alongside the
  existing `from the_one.sessions import session_locks` at line
  40 — neither has a known import cycle with `connectors._inbound`,
  so function-local-imports are unnecessary. The existing
  function-local imports for `db.repositories` / `encryption` /
  `config` stay function-local because those DO have cycle
  concerns (per the module's own comment at lines 100-103).
  Implementation:
  ```python
  # F5 L6: broadcast per-message UI events to live observers.
  # Zero-subscriber case: clean no-op (broadcast_to_session
  # iterates an empty set). The codec emits visibility on each
  # event from Message.visibility (already tagged by
  # tag_post_step_visibility above), so live observers see the
  # operator-only marker on the right bubbles without any
  # per-event tagging here. The broadcast loop is intentionally
  # inside the per-session lock — see Edge Cases for the
  # serialization trade-off.
  new_msgs = agent.messages[pre_step_len:]
  if new_msgs:
      events = messages_to_ui_events(new_msgs, index_offset=pre_step_len)
      for event in events:
          await broadcast_to_session(session_row.id, event)
  ```
- New test file `tests/test_connectors_inbound_broadcast.py` —
  per-message-broadcast contract:
  - **`test_dispatch_inbound_broadcasts_per_message_when_subscribed`**:
    register a fake WS subscriber for the session_id via
    `add_subscriber`; drive `dispatch_inbound` with a stub envelope
    + stubbed agent that yields a plain-text ASSISTANT (no
    tool_calls); assert the fake WS received TWO `send_json` calls
    — one `user` event (the peer inbound, codec-projected from the
    USER message that `agent.step` appends internally) + one
    `assistant` event.
  - **`test_dispatch_inbound_zero_subscribers_is_noop`**: no
    `add_subscriber` calls; drive the same dispatch; assert no
    exception and no broadcast side effect. Pins back-compat.
  - **`test_dispatch_inbound_broadcasts_carry_visibility`**:
    subscriber registered; dispatch yields an ASSISTANT-with-
    tool_calls (the tool_call is `send_to_platform_channel`) +
    TOOL whose content starts with `PLATFORM_SEND_OK_PREFIX`. The
    stub ASSISTANT has empty `content` (LLM emits ONLY tool calls
    in this case) — the codec's `if msg.content:` skips an
    assistant-content event for empty content. Expected
    broadcast sequence: USER event (peer inbound, NO visibility
    key — peer-visible by default); TOOL_CALL event (visibility
    inherited from the assistant Message → "operator"); TOOL_RESULT
    event (NO visibility key — the leg-3 helper's send-success
    carve-out makes the TOOL Message's visibility None →
    codec omits the key). Assertions use `"visibility" not in
    event` (NOT `event.get("visibility") is None`) to pin the
    contract that the key is omitted, not present-as-None.
  - **`test_dispatch_inbound_broadcasts_after_persistence`** (list-
    mutation approach, deterministic): patch `chat_repo.update`
    to append `"persist"` to an ordered list; `FakeWS.send_json`
    appends `"broadcast"`. Assert the resulting list starts with
    `"persist"` and the broadcast entries follow.
  - **`test_dispatch_inbound_broadcast_exception_does_not_corrupt_state`**:
    register a subscriber whose `send_json` raises; drive
    dispatch; assert the dispatcher completes without
    propagating the exception (per `broadcast_to_session`'s
    contract: dead WSes get discarded; exceptions are swallowed
    inside the per-WS try/except in `_broadcast.py:55-58`).
  - **`test_dispatch_inbound_multi_turn_parent_message_ids_do_not_collide`**:
    register a subscriber; drive `dispatch_inbound` TWICE on the
    SAME session_id, each turn yielding an ASSISTANT-with-
    tool_calls. Collect the broadcasted `parent_message_id`
    values across both turns. Assert all values are distinct.
    This is the regression test for the codec `index_offset`
    fix.
- The dispatcher's existing tests at
  `tests/test_connectors_inbound.py` continue to pass byte-
  identically (zero subscribers → no observable change).
- Existing codec tests at `tests/test_db_codec.py` (or
  equivalent) continue to pass byte-identically — the
  `index_offset` parameter defaults to 0; all current call sites
  produce identical output.

## Acceptance Criteria

- [ ] `messages_to_ui_events` in `the_one/db/codec.py` gains an
      `index_offset: int = 0` parameter. When non-zero, all
      internal `enumerate(messages)` indices are offset by it so
      `parent_message_id = f"replay-msg-{i + index_offset}"`.
      Default 0 preserves byte-identical behavior for existing
      callers.
- [ ] `dispatch_inbound` at `the_one/connectors/_inbound.py:155-229`
      gains a per-message broadcast step after persistence:
      project `agent.messages[pre_step_len:]` via
      `messages_to_ui_events(new_msgs, index_offset=pre_step_len)`;
      iterate; call `broadcast_to_session(session_row.id, event)`
      for each event.
- [ ] The broadcast runs INSIDE the `async with session_locks[…]:`
      block so the lock is held — preventing interleaving with a
      concurrent operator-typed turn from the WS path on the same
      session_id.
- [ ] The broadcast runs AFTER `chat_repo.update(updated)`
      (persistence) — observers don't see "future" state that's
      not yet on disk.
- [ ] Zero-subscriber case: `broadcast_to_session`'s existing
      empty-set iteration handles it cleanly; no exception, no
      side effect. Existing dispatcher tests at
      `tests/test_connectors_inbound.py` pass byte-identically.
- [ ] Imports of `messages_to_ui_events` and `broadcast_to_session`
      go at the **module top** of `_inbound.py` alongside the
      existing `from the_one.sessions import session_locks` at
      line 40 — neither has a known import cycle with this module.
- [ ] Six new tests land in
      `tests/test_connectors_inbound_broadcast.py`:
      (1) per-message broadcast when subscribed; (2) zero-subscriber
      no-op; (3) visibility carried correctly on broadcast events
      (using `"visibility" not in event` assertions for omitted-key
      contract); (4) broadcast-after-persistence ordering via
      list-mutation; (5) broadcast exception isolation; (6) multi-
      turn parent_message_id namespace non-collision (regression
      for the codec `index_offset` fix).
- [ ] `make test-unit` clean. F5 L5 baseline was 1977 passed;
      expected ~+6 from this leg's new broadcast tests. Confirm
      the delta is the new tests, not unrelated breakage.
- [ ] `make lint` clean.
- [ ] No regression on F1-F4 or earlier F5 leg tests; specifically:
      `tests/test_connectors_inbound.py`,
      `tests/test_connectors_e2e_session.py`,
      `tests/test_connectors_e2e_platform_send.py`,
      `tests/test_connectors_visibility_helper.py` all green
      byte-identically.
- [ ] Import-direction grep: `grep -rn "from the_one.interfaces"
      the_one/connectors/ the_one/sessions/` returns empty (the
      one-way `connectors → sessions` and forbidden
      `connectors|sessions → interfaces.web` continue to hold).
- [ ] The agent loop in `the_one/agent/core.py` is untouched.

## Verification Steps

- **Focused leg-6 tests**:
  `docker exec the-one pytest tests/test_connectors_inbound_broadcast.py -x --timeout 30 -v`
- **Dispatcher regression net**:
  `docker exec the-one pytest tests/test_connectors_inbound.py -x --timeout 30 -v`
  — F4 L4 ground-truth tests stay green.
- **e2e regression**:
  `docker exec the-one pytest tests/test_connectors_e2e_session.py tests/test_connectors_e2e_platform_send.py tests/test_connectors_e2e_ws_into_connector.py -x --timeout 60 -v`
- **Codec + visibility helper**:
  `docker exec the-one pytest tests/test_db_codec.py tests/test_connectors_visibility_helper.py -x --timeout 30 -v`
- **Full unit-suite**: `make test-unit` clean.
- **Import-direction grep**:
  `grep -rn "from the_one.interfaces" the_one/connectors/ the_one/sessions/`
  → empty.
- **Lint**: `make lint` clean.

## Implementation Guidance

1. **Extend the codec** (`the_one/db/codec.py`):
   - Modify `messages_to_ui_events`'s signature:
     `def messages_to_ui_events(messages: list[Message], *, index_offset: int = 0) -> list[dict[str, Any]]:`
     The keyword-only marker makes future call sites explicit.
   - Replace `for i, msg in enumerate(messages):` (codec.py:148)
     with `for relative_i, msg in enumerate(messages): i = relative_i + index_offset`.
     Then the existing `f"replay-msg-{i}"` construction at
     line 163 uses the offset-adjusted index.
   - Default `index_offset=0` keeps all existing callers
     byte-identical.
   - Run focused regression:
     `pytest tests/test_db_codec.py -x --timeout 30 -v`; green
     (codec output unchanged for the no-offset case).

2. **Add the broadcast step to `dispatch_inbound`**
   (`the_one/connectors/_inbound.py`):
   - At the module top, add the imports near the existing
     `from the_one.sessions import session_locks` at line 40:
     ```python
     from the_one.db.codec import messages_to_ui_events
     from the_one.sessions import broadcast_to_session, session_locks
     ```
   - After the `await chat_repo.update(updated)` call at line 225,
     and BEFORE the `finally:` block at line 226, insert:
     ```python
     # F5 L6: per-message broadcast to live WS observers. Zero
     # subscribers is a clean no-op. The codec emits visibility
     # on each event from Message.visibility (already tagged by
     # tag_post_step_visibility above), so live observers see
     # operator-only markers correctly. The broadcast loop is
     # intentionally inside the per-session lock — operator-typed
     # turns on the same session_id queue behind the broadcast
     # rather than interleaving (Edge Cases documents the
     # serialization trade-off). index_offset=pre_step_len keeps
     # parent_message_ids unique across consecutive inbound
     # turns on the same session (regression coverage in
     # test_dispatch_inbound_multi_turn_parent_message_ids_do_not_collide).
     # No exclude — the inbound came from the connector gateway,
     # not from any WS subscriber.
     new_msgs = agent.messages[pre_step_len:]
     if new_msgs:
         events = messages_to_ui_events(new_msgs, index_offset=pre_step_len)
         for event in events:
             await broadcast_to_session(session_row.id, event)
     ```
   - The `if new_msgs:` guard is defensive — if `agent.step`
     returns without appending anything, there's nothing to
     broadcast.
   - Run focused regression:
     `pytest tests/test_connectors_inbound.py -x --timeout 30 -v`;
     should still be green (zero subscribers → byte-identical).

3. **Add the broadcast contract tests**
   (`tests/test_connectors_inbound_broadcast.py`):
   - Mirror `tests/test_connectors_inbound.py`'s fixture shape.
     Today's tests already construct a stub agent and a stub
     connector account.
   - For each test:
     - Build a stub `FakeWS` with an `async def send_json(payload)`
       that captures payloads to a list.
     - `from the_one.sessions import add_subscriber,
       remove_subscriber, clear_subscribers_for_test`.
     - In a test's setup: `add_subscriber(expected_session_id, fake_ws)`.
     - In an autouse fixture (or a per-test `try/finally`):
       `clear_subscribers_for_test()` — to keep tests isolated.
       The F5 L2 autouse `_clear_pool_locks_registry` fixtures
       already call `the_one.sessions.clear_for_test()` for the
       existing connector-test files; this new file gets its own
       autouse cleanup wired similarly.
     - Drive `dispatch_inbound(agent_name, account_id, envelope,
       factory=fake_factory)`.
     - Inspect `fake_ws.payloads` for the expected event types
       and visibility keys.
   - For the broadcast-after-persistence ordering test
     (`test_dispatch_inbound_broadcasts_after_persistence`):
     - Mock `chat_repo.update` to record its call timestamp;
       `FakeWS.send_json` records its call timestamp; assert
       the update timestamp < send_json timestamp.
     - This may require monkey-patching `chat_repo.update` after
       it's instantiated, OR providing a fake `chat_repo`.
     - Alternatively use a simple ordered list mutation: the mock
       update appends `"persist"` to a list; `send_json` appends
       `"broadcast"`; assert `list == ["persist", "broadcast", ...]`.
   - For the broadcast-exception-isolation test
     (`test_dispatch_inbound_broadcast_exception_does_not_corrupt_state`):
     - `FakeWS.send_json` raises a generic exception.
     - Drive `dispatch_inbound`; assert no exception bubbles to
       the caller. `broadcast_to_session` already catches
       exceptions per-WS and prunes dead subscribers; the
       dispatcher inherits that safety.
   - For visibility-carried test
     (`test_dispatch_inbound_broadcasts_carry_visibility`):
     - Stub agent yields ASSISTANT with `tool_calls=[ToolCall(id="tc1",
       name="send_to_platform_channel", arguments={"target":"...","content":"..."})]`,
       then TOOL with `tool_result=ToolResult(tool_call_id="tc1",
       content=PLATFORM_SEND_OK_PREFIX + " ...", is_error=False)`.
     - After dispatch, the broadcast payloads list:
       - First event (USER, the peer's inbound): NO `visibility`
         key (peer-visible by default).
       - Subsequent ASSISTANT event: `visibility="operator"`.
       - Subsequent TOOL_CALL event: `visibility="operator"`
         (the assistant's call is operator-context).
       - The TOOL_RESULT event (the successful platform-send):
         NO `visibility` key (peer-visible per leg-3 carve-out).

4. **Verify import direction**:
   - `grep -rn "from the_one.interfaces" the_one/connectors/ the_one/sessions/`
     → empty.

5. **Full-suite + lint**:
   - `make test-unit` clean.
   - `make lint` clean.

6. **Update flight log** with leg 6's outcomes — files touched,
   tests added, any deviations, the implicit closure of the
   inbound-side live-broadcast gap (the dispatcher's events now
   carry visibility through to live observers; the WS-typed path's
   symmetric gap remains as documented in F5 L5).

## Edge Cases

- **Zero subscribers**: `subscribers_for(sid)` returns an empty set
  copy; `broadcast_to_session` iterates nothing; no exception, no
  side effect. THE regression net for back-compat.

- **`agent.step` raised mid-turn before appending anything**:
  `pre_step_len == len(agent.messages)`; `new_msgs = []`; the
  `if new_msgs:` guard skips the broadcast block. Safe.

- **A broadcast event raises mid-loop**: each
  `broadcast_to_session` call is wrapped in its own internal
  per-WS try/except per `_broadcast.py:55-58`; one bad WS doesn't
  prevent other subscribers from receiving the same event, and
  subsequent events still go out. The outer dispatcher loop
  iterates events in order; if `broadcast_to_session` itself
  raised (it shouldn't per its contract), that exception WOULD
  propagate past the lock, but `broadcast_to_session`'s body
  only awaits `ws.send_json` inside the inner try/except and
  catches generic Exceptions. Safe.

- **Multiple subscribers**: each gets each event in order.
  Per-WS dead-detection runs per-broadcast; a slow WS that
  delays one broadcast briefly stalls subsequent ones for ALL
  subscribers because the dispatcher's loop awaits each call.
  Acceptable for v1; single-user local tool has at most one
  observer.

- **Live operator typing concurrently into the same session via WS
  while a dispatcher inbound is being broadcast**: the shared
  lock (F5 L2) serializes the two paths. The WS path waits for
  the dispatcher's broadcast loop to complete (it's inside the
  lock); the operator's events come AFTER the peer's. No
  interleaving.

- **Per-message-id namespace conflict between dispatcher's
  broadcasted `replay-msg-N` ids and subsequent operator-typed
  `{session.id}-msg-N` ids**: disjoint by construction (codec
  uses one, `_parent_message_id_for` uses the other). The
  frontend groups by opaque parent_message_id; no collision.

- **The dispatcher broadcasts to a subscriber whose WebSocket is
  closing mid-broadcast**: `ws.send_json` raises; the inner
  catch in `broadcast_to_session` records it as dead and
  removes the subscriber. The dispatcher continues; subsequent
  events skip the now-removed subscriber on next iteration.
  Safe.

- **Subscribers added DURING the broadcast loop**: snapshot
  semantics of `subscribers_for` mean a mid-broadcast addition
  doesn't receive the in-flight event but receives subsequent
  events (the next iteration re-reads the snapshot). Documented
  behavior in `_broadcast.py:29-37`.

- **Broadcasting events that the codec emits for an EMPTY
  assistant content (msg.content == "")**: the codec's
  conditional `if msg.content:` at line 160 skips empty-content
  ASSISTANT events from being projected. If the only thing the
  assistant did was emit tool_calls, only the `tool_call` events
  fire. Correct behavior.

## Files Affected

- `the_one/db/codec.py` — `messages_to_ui_events` gains an
  `index_offset: int = 0` keyword-only parameter.
- `the_one/connectors/_inbound.py` — `dispatch_inbound` gains a
  per-message broadcast step after persistence; module-top imports
  for `messages_to_ui_events` and `broadcast_to_session`.
- `tests/test_connectors_inbound_broadcast.py` (new) — 6 unit
  tests covering the per-message-broadcast contract + multi-turn
  parent_message_id non-collision.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (`make test-unit`, `make lint` clean)
- [ ] Import-direction grep confirms no
      `the_one.connectors → the_one.interfaces` imports.
- [ ] Update flight-log.md with Leg 6 progress entry, including the
      note that the inbound-side live-broadcast visibility surface
      lands here (the WS-typed-path symmetric gap from F5 L5
      remains as documented).
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] Per the agentic-workflow protocol: do NOT commit until
      end-of-flight review.

## Citation Audit

8 citations verified against current code at leg design time:

- `the_one/connectors/_inbound.py:155-229` — `dispatch_inbound`'s
  per-session-lock block (verified).
- `the_one/connectors/_inbound.py:183` — `pre_step_len = len(agent.messages)`
  snapshot (verified).
- `the_one/connectors/_inbound.py:209` — `tag_post_step_visibility(...)`
  call (verified — F5 L3 output).
- `the_one/connectors/_inbound.py:225` — `await chat_repo.update(updated)`
  (verified).
- `the_one/connectors/_inbound.py:100-110` — function-local-import
  precedent for `db.repositories` / `encryption` / `config` (these
  have known cycle concerns; verified). The new imports in this
  leg do NOT follow this precedent — they go module-top alongside
  the existing `from the_one.sessions import session_locks` at
  line 40, because neither `db.codec` nor `the_one.sessions` has
  a known cycle with `connectors._inbound`.
- `the_one/sessions/_broadcast.py:40-60` — `broadcast_to_session`
  (verified — F5 L2 output; signature unchanged).
- `the_one/db/codec.py:114-187` — `messages_to_ui_events`
  (verified; visibility emitted at line 154 when non-None).
- `the_one/db/codec.py:126-137` — replay-id namespacing
  (verified — `"replay-msg-N"` form; disjoint from
  `f"{session.id}-msg-N"`).
