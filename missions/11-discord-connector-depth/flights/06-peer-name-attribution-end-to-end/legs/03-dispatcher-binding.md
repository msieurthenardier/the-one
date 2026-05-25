# Leg: dispatcher-binding

**Status**: completed
**Flight**: [Peer-name Attribution End-to-End (Bug C)](../flight.md)

## Objective

Bind the inbound envelope's `peer_name` onto the dispatcher-appended user message inside the connector dispatcher's post-step block in `the_one/connectors/_inbound.py`, so that L1/L2's persistence + UI-event projection actually carry peer attribution end-to-end on every connector inbound turn.

## Context

L1 added `Message.peer_name` and codec round-trip. L2 added the user-event projection. L3 closes the gap between them and the live system: the dispatcher must write the envelope's `peer_name` onto the `Message.user` that `agent.step` appends, otherwise the field stays None forever and the rest of the pipeline carries nothing.

The hard mission constraint is preserved: `the_one/agent/core.py` and `the_one/agent/factory.py` are NOT modified. The dispatcher binds `peer_name` POST-step via a one-line mutation on `agent.messages[pre_step_len]`, mirroring the pattern that the existing `tag_post_step_visibility` (`the_one/connectors/visibility.py:38`) uses to back-fill metadata the agent loop doesn't know about.

Per flight Design Decision §5: the mutation site is inside the existing `session_locks[session_row.id]` lock (`_inbound.py:590`) and inside the existing `try` block (`_inbound.py:620`). Concurrency reasoning passes — the operator-typed concurrent path (`_process_and_broadcast` in `interfaces/web/app.py:322`) acquires the same per-session lock, so there is no race on `agent.messages[pre_step_len]`. Exception-path reasoning passes — on `agent.step` failure the mutation does not run; the partially-appended user message decodes with `peer_name=None` (codec back-compat handles it).

Per flight Design Decision §5 architect-confirmed: ordering relative to `tag_post_step_visibility(...)` (`_inbound.py:644`) is NOT load-bearing — the visibility helper explicitly `continue`s on `Role.USER` (`visibility.py:60`) so it never touches the user message and cannot compose-conflict with the peer_name mutation. The leg co-locates the two mutations for the "post-step metadata fill" idiom legibility but the call order is free.

Operator-typed path (`_process_and_broadcast`) is structurally unaffected: it does not construct a `Message` with `peer_name`; the live user_event it broadcasts is built directly from a `user_input` string at `interfaces/web/app.py:881-894` and has no peer_name source to draw from. A brief docstring/comment annotation marks this invariant; no new test is required beyond a positive negative-case assertion in the broadcast test (see Implementation Guidance §3).

## Inputs

What exists before this leg runs (post-L1+L2 state):

- `Message.peer_name: str | None = None` field on the dataclass (L1).
- `Message.user(content, *, visibility=..., peer_name=...)` kwarg-only signature (L1).
- Codec emit-when-non-None for `peer_name` (L1).
- `messages_to_ui_events` spreads `peer_name` onto Role.USER events when set (L2).
- `the_one/connectors/_inbound.py:dispatch_inbound` — at lines 618-644 in the current branch state:
  - line 618: `pre_step_len = len(agent.messages)` (snapshot before step)
  - line 619: `token = current_chat_session_id.set(session_row.id)`
  - line 620-622: `try:` block start with comment about Message.user
  - line 628-629: `async for _ in agent.step(working_envelope.text): pass`
  - line 631-644: `# F4 (M10) L4: post-step visibility tagging.` block + the `tag_post_step_visibility(agent.messages, pre_step_len)` call at line 644
  - line 675-681: live broadcast via `messages_to_ui_events(new_msgs, index_offset=pre_step_len)`
- `the_one/connectors/visibility.py:tag_post_step_visibility` (line 38) — established post-step Message-mutation precedent (mutates messages in-place; module-level helper).
- `tests/_connector_dispatch_helpers.py:_envelope` — fixture builds `InboundEnvelope` with `peer_name="Alice"` baked in (line 190).
- `tests/test_connectors_inbound.py:test_dispatch_inbound_persists_inbound_with_visibility_none` (line 567) — established test shape for "persisted user message has expected field value."
- `tests/test_connectors_inbound_broadcast.py:test_dispatch_inbound_broadcasts_carry_visibility` (line 220) — established test shape for "broadcast event carries expected key/value, omits when absent."

## Outputs

After this leg completes:

- `the_one/connectors/_inbound.py:dispatch_inbound` mutates `agent.messages[pre_step_len].peer_name = working_envelope.peer_name` immediately after `agent.step` returns, before the per-session lock releases, alongside the existing `tag_post_step_visibility` call. A defensive `assert agent.messages[pre_step_len].role == Role.USER` documents the invariant.
- A short comment block explains why the mutation lives outside `agent.step` (mission constraint: agent loop not modified) and cites the parallel `tag_post_step_visibility` pattern.
- `the_one/interfaces/web/app.py:_process_and_broadcast` gains a one-sentence annotation (comment only — no behavior change) noting that the operator-typed user_event carries no peer_name by construction (no peer to attribute).
- `tests/test_connectors_inbound.py` gains a new test `test_dispatch_inbound_persists_inbound_with_peer_name_from_envelope` in the "Visibility defaults" section near the existing visibility tests — pins that the dispatched user message's `peer_name == "Alice"` matches the envelope fixture.
- `tests/test_connectors_inbound_broadcast.py` gains a new test `test_dispatch_inbound_broadcasts_carry_peer_name` mirroring the existing visibility broadcast test — pins that the live `user` broadcast event carries `peer_name == "Alice"`, and that follow-on assistant/tool events do NOT carry `peer_name`.
- All pre-existing dispatcher + broadcast tests pass unchanged (the change is purely additive; existing assertions on user-message fields and event payloads do not break because peer_name was previously None and now becomes the envelope's `peer_name` value — pre-existing tests using `_envelope()` already had `peer_name="Alice"` in the envelope but did not assert on it).

## Acceptance Criteria

- [ ] `the_one/connectors/_inbound.py:dispatch_inbound` mutates `agent.messages[pre_step_len].peer_name = working_envelope.peer_name` after `agent.step` returns and before the function exits the `try` block. The mutation is co-located with the `tag_post_step_visibility(...)` call (immediately before or after — both are acceptable per Design Decision §5; the leg writes "immediately after" for code-narrative consistency, but the implementing agent may choose either order).
- [ ] A defensive `assert agent.messages[pre_step_len].role == Role.USER, "agent.step must append a Role.USER message at pre_step_len"` documents the invariant. Used as a documentation assert (not load-bearing for correctness, since `agent/core.py:144` structurally guarantees this — the assert is a tripwire for any future agent-loop refactor that violates the invariant).
- [ ] A comment block above the mutation cites: (a) the M11 F6 / Bug C / criterion #13 origin, (b) the agent-loop-NOT-modified constraint, (c) the `tag_post_step_visibility` parallel.
- [ ] `the_one/interfaces/web/app.py:_process_and_broadcast` gains a one-line comment near the `user_event` construction (`app.py:881-894`) noting that the operator-typed path carries no peer_name by construction. Comment only — no behavior change.
- [ ] `tests/test_connectors_inbound.py` gains `test_dispatch_inbound_persists_inbound_with_peer_name_from_envelope` in the "Visibility defaults" section after `test_dispatch_inbound_persists_inbound_with_visibility_none` (after line ~591):
  - Dispatches a stub-platform envelope (which uses the helper's default `peer_name="Alice"`).
  - Decodes the persisted session messages.
  - Asserts the first USER message's `peer_name == "Alice"`.
- [ ] `tests/test_connectors_inbound.py` gains a sibling negative test `test_dispatch_inbound_persists_user_message_role_invariant`:
  - Asserts `agent.messages[pre_step_len].role == Role.USER` after dispatch. This is a separate test pinning the structural invariant the production assert relies on (so a refactor that breaks the invariant fails a regular unit test, not just the production assert).
- [ ] `tests/test_connectors_inbound_broadcast.py` gains `test_dispatch_inbound_broadcasts_carry_peer_name`:
  - Mirrors the structure of `test_dispatch_inbound_broadcasts_carry_visibility` (lines 220-295).
  - Dispatches with the default `_envelope()` (peer_name="Alice").
  - Drives the same assistant-with-tool_call + final-assistant scripted response chain used by the visibility test for parity.
  - Asserts the `user` broadcast event carries `peer_name == "Alice"`.
  - Asserts the `tool_call`, `tool_result`, and final `assistant` broadcast events do NOT carry a `peer_name` key (per L2's branch-gated projection).
- [ ] All pre-existing tests in `tests/test_connectors_inbound.py`, `tests/test_connectors_inbound_broadcast.py`, `tests/test_connectors_session.py`, and `tests/test_db_codec.py` pass without modification.

## Verification Steps

Run from the project root inside the dev container.

1. **Targeted dispatcher tests pass**:
   ```
   docker exec the-one pytest -x --timeout 30 tests/test_connectors_inbound.py
   ```
   Expected: all existing tests pass plus the two new tests.

2. **Targeted broadcast tests pass**:
   ```
   docker exec the-one pytest -x --timeout 30 tests/test_connectors_inbound_broadcast.py
   ```
   Expected: all existing tests pass plus the new peer_name broadcast test.

3. **Cross-cutting connector suite**:
   ```
   docker exec the-one pytest -x --timeout 60 tests/test_connectors_inbound.py tests/test_connectors_inbound_broadcast.py tests/test_connectors_session.py tests/test_db_codec.py
   ```
   Expected: all pass. (Higher per-test timeout because some integration tests in this set are slower than codec unit tests.)

4. **Smoke-check the dispatcher binding** via a manual driver script (optional — covered by tests but useful for visual confirmation):
   ```
   docker exec the-one python -c "
   import asyncio
   from tests._connector_dispatch_helpers import _envelope, _make_factory, _seed_provider_and_agent, _seed_stub_account
   from the_one.connectors._inbound import dispatch_inbound
   from the_one.connectors._stub import StubPlugin
   from the_one.connectors.registry import register_for_test
   from the_one.db.connection import get_connection
   from the_one.db.repositories import ChatSessionRepository
   from the_one.db.codec import decode_messages
   async def main():
       # ... seeded test setup omitted for brevity
       pass
   "
   ```
   (Skip if the targeted tests pass.)

## Implementation Guidance

1. **Edit `the_one/connectors/_inbound.py:dispatch_inbound`** — locate the post-step block (currently at lines 631-644 with the comment `# F4 (M10) L4: post-step visibility tagging.` and the `tag_post_step_visibility(agent.messages, pre_step_len)` call). Add the peer_name binding immediately before or after that call (the implementing agent may choose; for code-narrative consistency, prefer "immediately after" to keep the existing block as-is):

   ```python
   # F4 (M10) L4: post-step visibility tagging.
   # ... existing block ...
   tag_post_step_visibility(agent.messages, pre_step_len)

   # M11 F06 L03: post-step peer_name binding.
   # The Discord plugin's gateway translator populates
   # ``InboundEnvelope.peer_name`` (the_one/connectors/_discord_translate.py:125)
   # but ``Agent.step`` constructs ``Message.user(working_envelope.text)``
   # at agent/core.py:144 with no peer_name. The M11 mission constraint
   # forbids modifying ``agent/core.py`` and ``agent/factory.py``, so the
   # dispatcher binds peer_name here POST-step on the appended user
   # message, mirroring the ``tag_post_step_visibility`` pattern just
   # above (same idiom: fill in the metadata the agent loop doesn't
   # know about). The mutation is inside the per-session lock
   # (session_locks[session_row.id]) and inside the try block, so it
   # composes correctly with concurrent operator-typed turns and is
   # skipped on agent.step exceptions. Closes M10 debrief Bug C
   # (peer_name data-model gap, 6 surfaces) / M11 criterion #13.
   assert agent.messages[pre_step_len].role == Role.USER, (
       "agent.step must append a Role.USER message at pre_step_len"
   )
   agent.messages[pre_step_len].peer_name = working_envelope.peer_name
   ```

   Use `working_envelope.peer_name` (not `envelope.peer_name`) because pairing handling earlier in `dispatch_inbound` may have replaced `envelope` with a stripped-text version (`working_envelope = replace(envelope, text=cleaned)` at line 320); `peer_name` is preserved through that replacement (the `replace()` keeps all fields except the named ones).

2. **Edit `the_one/interfaces/web/app.py:_process_and_broadcast`** — locate the `user_event` construction block (currently at lines 881-894). Add a brief one-line comment near the existing visibility-conditional block explaining the peer_name invariant:

   ```python
   user_event: dict[str, Any] = {"type": "user", "content": user_input, "source": source}
   # M10 F06 L6: connector-attached operator-typed turns carry the
   # operator-only visibility tag (operator typed, agent reply is
   # operator-only by F04 L4). M11 F06 L03: this path does NOT acquire
   # a peer_name key — the operator IS the source; there is no peer
   # to attribute. Peer-attributed user events flow via the dispatcher
   # path (connectors/_inbound.py) where the codec spreads peer_name
   # from the Message.peer_name field.
   if session.platform is not None:
       user_event["visibility"] = OPERATOR_VISIBILITY
   ```

3. **Edit `tests/test_connectors_inbound.py`** — locate the "Visibility defaults" section (header comment at line 564, then `test_dispatch_inbound_persists_inbound_with_visibility_none` at line 567 and `test_dispatch_inbound_persists_agent_reply_with_visibility_operator` at line 593). Insert TWO new tests after the visibility-none test and before the visibility-operator test (or at the end of the section — implementing agent's choice):

   ```python
   async def test_dispatch_inbound_persists_inbound_with_peer_name_from_envelope(
       isolated_db,
   ) -> None:
       """The persisted user message's ``peer_name`` equals the inbound
       envelope's ``peer_name`` — the dispatcher's post-step binding
       writes the envelope value onto ``agent.messages[pre_step_len]``
       after ``agent.step`` returns.

       M11 F6 L3: closes the Message-side half of Bug C (peer_name
       data-model gap). The helper ``_envelope()`` defaults to
       ``peer_name="Alice"``.
       """
       await _seed_provider_and_agent()
       await _seed_stub_account()
       register_for_test("stub", StubPlugin)
       factory = await _make_factory()

       envelope = _envelope()
       await dispatch_inbound("acct-test", envelope, factory=factory)

       conn = await get_connection()
       chat_repo = ChatSessionRepository(conn)
       sessions = await chat_repo.list()
       history = decode_messages(sessions[0].messages)
       user_msgs = [m for m in history if m.role == Role.USER]
       assert user_msgs[0].peer_name == "Alice"


   async def test_dispatch_inbound_persists_user_message_role_invariant(
       isolated_db,
   ) -> None:
       """Production code at the L3 binding site contains a defensive
       ``assert agent.messages[pre_step_len].role == Role.USER``. This
       test pins the same invariant as a regular unit-test assertion so
       a future agent-loop refactor that violates it fails a normal test
       run, not just a runtime assert in production.

       M11 F6 L3.
       """
       await _seed_provider_and_agent()
       await _seed_stub_account()
       register_for_test("stub", StubPlugin)
       factory = await _make_factory()

       envelope = _envelope()
       await dispatch_inbound("acct-test", envelope, factory=factory)

       conn = await get_connection()
       chat_repo = ChatSessionRepository(conn)
       sessions = await chat_repo.list()
       history = decode_messages(sessions[0].messages)
       non_system = [m for m in history if m.role != Role.SYSTEM]
       # The first non-system message in the persisted history is the
       # dispatcher-appended user turn (agent.step prepends nothing in
       # the connector path — the freshly-built agent's system message
       # was kept and non-system stored messages were appended; on the
       # first inbound there are no prior non-system stored messages).
       assert non_system[0].role == Role.USER
   ```

4. **Edit `tests/test_connectors_inbound_broadcast.py`** — locate `test_dispatch_inbound_broadcasts_carry_visibility` (lines 220-295). Add a sibling test immediately after it (before the next section header at line 298):

   ```python
   # ─── Test: peer_name carried on broadcast events ─────────────────────────


   async def test_dispatch_inbound_broadcasts_carry_peer_name(
       isolated_db, monkeypatch
   ) -> None:
       """The inbound envelope's ``peer_name`` propagates through the
       dispatcher's post-step binding (M11 F6 L3) into the persisted
       USER message, then through the codec's ``messages_to_ui_events``
       Role.USER spread (M11 F6 L2) into the live broadcast event.

       Branch coverage:
       - USER event: carries ``peer_name == "Alice"`` (the envelope
         helper's default value).
       - TOOL_CALL, TOOL_RESULT, ASSISTANT events: do NOT carry a
         ``peer_name`` key — L2's projection is gated to the USER branch.

       Composes with the visibility test above — the same scripted
       response chain (assistant-with-tool_call + final assistant)
       drives all four event types.
       """
       await _seed_provider_and_agent(connector_account_ids=["acct-test"])
       await _seed_stub_account()
       register_for_test("stub", StubPlugin)

       tc = ToolCall(
           id="tc-send-1",
           name="send_to_platform_channel",
           arguments={
               "target": {"account_id": "acct-test", "channel_id": "ch-1"},
               "content": "hello peer",
           },
       )
       responses = [
           Message.assistant(content="", tool_calls=[tc]),
           Message.assistant(content="done"),
       ]
       factory = await _make_scripted_factory(
           responses, monkeypatch, connector_account_ids=["acct-test"]
       )

       _, fake_ws = await _dispatch_and_collect(factory=factory)

       types = [p["type"] for p in fake_ws.payloads]
       assert types == ["user", "tool_call", "tool_result", "assistant"], (
           f"unexpected event sequence: {types}"
       )

       user_event, tool_call_event, tool_result_event, assistant_event = (
           fake_ws.payloads
       )

       # USER: peer_name from the envelope.
       assert user_event["peer_name"] == "Alice"

       # Non-USER branches: peer_name absent (per L2 branch-gating).
       assert "peer_name" not in tool_call_event
       assert "peer_name" not in tool_result_event
       assert "peer_name" not in assistant_event
   ```

5. **Update leg status to `in-flight`** at the start of implementation; update to `landed` when implementation + tests pass.

6. **Update flight-log.md** with a Leg Progress entry. Check off `dispatcher-binding` in `flight.md`'s Legs list. Do NOT commit (deferred to flight-end).

## Edge Cases

- **Empty `agent.messages` somehow** (impossible in current flow, but for defensive reasoning): the `assert agent.messages[pre_step_len].role == Role.USER` would fail with IndexError before reaching the role check. This is the correct failure mode — a degenerate state that should crash visibly, not silently skip.
- **`pre_step_len` past end of `agent.messages`** (also impossible — `agent.step` always appends at least the user message at agent/core.py:144): same IndexError-then-crash semantics. Acceptable.
- **Pairing flow with text replacement**: `working_envelope = replace(envelope, text=cleaned)` at line 320 strips the `PAIR <code>` prefix but preserves `peer_name`. Use `working_envelope.peer_name` to ensure consistency with `working_envelope.text` passed to `agent.step`.
- **Command path**: the slash-command surface (`/agents`, `/talk_to`, etc.) returns early via `return` statements before reaching the post-step block (e.g. `_inbound.py:548` in the plugin-command-response path, line 575 in the built-in-command path). Those paths do NOT go through `agent.step` and do NOT need peer_name binding — slash-command responses are dispatcher-emitted, not agent-stepped, and have no `Message.user` to mutate. The existing visibility-tagging post-step block is also skipped on those paths; the symmetry holds.
- **`agent.step` raises**: the `try` block at line 620 contains the step call AND the existing visibility-tagging call. The peer_name mutation must land inside the same `try` block so it's also skipped on exception. If `agent.step` raises, the partially-appended `Message.user` (from `agent/core.py:144`'s first line) has `peer_name=None` and decodes back as such — codec back-compat handles it. Acceptable.
- **Operator-typed concurrent turn**: per Design Decision §5 architect-confirmed, the WS-path operator-typed turn handler acquires the same per-session lock (`app.py:322 session_locks[session.id]`) before invoking `_process_and_broadcast`, as the dispatcher (`_inbound.py:590`). Serialized — no race on `agent.messages[pre_step_len]`. (The non-WS HTTP path at `app.py:1312` is out of scope — it has no peer_name source by construction.)
- **Pre-F6 connector sessions revived after F6**: the first F6-era inbound mutates `agent.messages[pre_step_len].peer_name` correctly; older messages in the same session's history continue to decode with `peer_name=None` (L1 back-compat). The session's history is heterogeneous (some messages with peer_name, some without) — this is correct and intentional. Pre-F6 turns don't gain attribution retroactively (Design Decision §3).

## Files Affected

- `the_one/connectors/_inbound.py` — post-step peer_name binding + comment block
- `the_one/interfaces/web/app.py` — comment annotation only (no behavior change)
- `tests/test_connectors_inbound.py` — two new dispatcher tests
- `tests/test_connectors_inbound_broadcast.py` — one new broadcast test
- `missions/11-discord-connector-depth/flights/06-peer-name-attribution-end-to-end/flight-log.md` — Leg Progress entry
- `missions/11-discord-connector-depth/flights/06-peer-name-attribution-end-to-end/legs/03-dispatcher-binding.md` — status transitions (planning → in-flight → landed)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]` (per agentic-workflow protocol; do NOT commit):**

- [ ] All acceptance criteria verified
- [ ] Targeted dispatcher tests pass (`docker exec the-one pytest -x --timeout 30 tests/test_connectors_inbound.py`)
- [ ] Targeted broadcast tests pass (`docker exec the-one pytest -x --timeout 30 tests/test_connectors_inbound_broadcast.py`)
- [ ] Cross-cutting connector suite passes (`docker exec the-one pytest -x --timeout 60 tests/test_connectors_inbound.py tests/test_connectors_inbound_broadcast.py tests/test_connectors_session.py tests/test_db_codec.py`)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed`
- [ ] Check off `dispatcher-binding` in flight.md
- [ ] Do NOT commit
- [ ] Do NOT update flight.md status to `landed`
- [ ] Constraint check: `the_one/agent/core.py` and `the_one/agent/factory.py` are NOT in the diff for this leg

---

## Citation Audit

Citations verified against current code (post-L1+L2 state) at leg design time:

- `the_one/connectors/_inbound.py:618` (`pre_step_len = len(agent.messages)`) — verified via grep at design time.
- `the_one/connectors/_inbound.py:628` (`async for _ in agent.step(working_envelope.text):`) — verified.
- `the_one/connectors/_inbound.py:644` (`tag_post_step_visibility(agent.messages, pre_step_len)`) — verified.
- `the_one/connectors/_inbound.py:675-681` (live broadcast block with `messages_to_ui_events(new_msgs, index_offset=pre_step_len)`) — verified.
- `the_one/connectors/_inbound.py:590` (`async with session_locks[session_row.id]:`) — verified.
- `the_one/connectors/_inbound.py:320` (`working_envelope = replace(envelope, text=cleaned)`) — verified.
- `the_one/connectors/visibility.py:38` (`tag_post_step_visibility`) — verified.
- `the_one/connectors/visibility.py:60` (`if msg.role == Role.USER: continue`) — verified at flight-design time.
- `the_one/agent/core.py:144` (`self.messages.append(Message.user(user_input))`) — verified at flight-design time.
- `the_one/interfaces/web/app.py:258` (`session_locks[session.id]`) — verified at flight-design time.
- `the_one/interfaces/web/app.py:881-894` (`user_event` construction block) — verified at flight-design time.
- `tests/_connector_dispatch_helpers.py:190` (`peer_name="Alice"` envelope fixture default) — verified.
- `tests/test_connectors_inbound.py:567` (`test_dispatch_inbound_persists_inbound_with_visibility_none`) — verified.
- `tests/test_connectors_inbound.py:593` (`test_dispatch_inbound_persists_agent_reply_with_visibility_operator`) — verified.
- `tests/test_connectors_inbound_broadcast.py:220` (`test_dispatch_inbound_broadcasts_carry_visibility`) — verified.

15 citations verified. The line numbers in `_inbound.py` may have shifted minimally if any uncommitted L1/L2 churn touched the file, but L1/L2 did not edit `_inbound.py` (only `llm/base.py`, `db/codec.py`, and `tests/test_db_codec.py`), so the cited line numbers are stable.
