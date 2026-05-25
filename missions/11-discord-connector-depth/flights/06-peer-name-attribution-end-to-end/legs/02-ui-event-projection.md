# Leg: ui-event-projection

**Status**: completed
**Flight**: [Peer-name Attribution End-to-End (Bug C)](../flight.md)

## Objective

Extend `messages_to_ui_events`'s `Role.USER` branch to spread `peer_name` onto the projected user event when `msg.peer_name is not None`, mirroring the visibility spread pattern, so the WebSocket-broadcast and replay paths carry peer attribution end-to-end downstream of L1's dataclass+codec contract.

## Context

L1 landed the `Message.peer_name` field + JSON codec round-trip. L2 closes the downstream wire-format gap: the WebSocket event shape consumed by the Chat UI must carry `peer_name` on user events when present. Without L2, the codec persists `peer_name` to disk but the Chat UI never sees it on replay or live broadcast.

Per architect review (recorded in `flight.md` Adaptation Criteria and `flight-log.md` Architect cycle 1 notes): L2 is split from L1 because codec JSON shape and WebSocket-event shape are unrelated wire-format contracts. L1's tests pin the JSON shape; L2's tests pin the event shape.

The existing `visibility` projection pattern (`codec.py:178-181` in the pre-L1 state, now shifted by L1's edits — see Implementation Guidance) is the precedent: a per-message `{key: msg.<field>}` dict is built when the field is non-None, then spread (`**vis`) into each derived event. L2 follows the same idiom for `peer_name`, but only on the `Role.USER` branch (peer_name is meaningful only on user-role messages — assistant/tool messages have `peer_name=None` by construction).

The corresponding test class `TestMessagesToUiEventsVisibility` (currently at `tests/test_db_codec.py:536`) demonstrates the test shape: per-event-type assertions that the key is present-and-correct on tagged messages, absent on untagged. L2's new test class mirrors it for peer_name, but with a much smaller surface — only the user-event branch.

## Inputs

What exists before this leg runs (post-L1 state):

- `the_one/llm/base.py:Message` — has `peer_name: str | None = None` field (L1).
- `the_one/llm/base.py:Message.user` — accepts kwarg-only `peer_name: str | None = None` (L1).
- `the_one/db/codec.py:messages_to_ui_events` — at the `Role.USER` branch (approx lines 182-185 in current code, possibly shifted by L1's adjacent edits), emits `{"type": "user", "content": msg.content, "source": "restored", **vis}` where `vis = {"visibility": msg.visibility} if msg.visibility is not None else {}`. No peer_name spread.
- `tests/test_db_codec.py` — `TestMessagesToUiEventsVisibility` class (currently around line 536) — established test shape for per-event-type spread; ends at approximately line 627.
- `TestMessageVisibilityClassmethodKwargs` class (currently around line 629) follows immediately after — L2's new test class lands BETWEEN these two.

## Outputs

After this leg completes:

- `messages_to_ui_events` `Role.USER` branch emits `{"type": "user", "content": ..., "source": "restored", peer_name (when set), visibility (when set)}` — both optional fields are independently spread; the event omits each key when its source field is None.
- New test class `TestMessagesToUiEventsPeerName` in `tests/test_db_codec.py` pins the user-event peer_name projection (present, absent, compose-with-visibility).
- No other branches in `messages_to_ui_events` are touched — assistant/tool/tool_call/tool_result branches do NOT spread peer_name because the source `Message.peer_name` is None on those roles by construction.

## Acceptance Criteria

- [ ] `messages_to_ui_events` in `the_one/db/codec.py` builds a per-message `peer = {"peer_name": msg.peer_name} if msg.peer_name is not None else {}` dict alongside the existing `vis` dict, and spreads `**peer` into the `Role.USER` event dict (and ONLY the `Role.USER` event dict — assistant/tool/tool_call/tool_result branches are unchanged).
- [ ] The Role.USER event with peer_name set emits `{"type": "user", "content": ..., "source": "restored", "peer_name": "alice", "visibility"?: ...}` (visibility key conditional on `msg.visibility`).
- [ ] The Role.USER event without peer_name (None) omits the `peer_name` key from the event dict — frontends treat absent === no peer attribution (operator-typed or non-connector session).
- [ ] No assistant/tool event acquires a `peer_name` key under any input — even if a future test constructs `Message.assistant("hi")` with the peer_name field somehow set, the projection ignores it (because the per-message `peer` dict is only spread into the Role.USER branch).
- [ ] `tests/test_db_codec.py` gains a new test class `TestMessagesToUiEventsPeerName` placed AFTER `TestMessagesToUiEventsVisibility` (currently ends near line 627) and BEFORE `TestMessageVisibilityClassmethodKwargs` (currently line 629), with these tests:
  - [ ] `test_projects_peer_name_on_user_message` — `Message.user("hi", peer_name="alice")` projects to event with `peer_name == "alice"`.
  - [ ] `test_omits_peer_name_on_user_message_without_peer_name` — `Message.user("hi")` projects to event without the `peer_name` key.
  - [ ] `test_does_not_project_peer_name_on_assistant_event` — assistant message (even if peer_name were set via direct constructor — for paranoia coverage) does NOT carry peer_name on its event. Use `Message(role=Role.ASSISTANT, content="hi there", peer_name="alice")` for the test fixture; assert the projected assistant event does not contain `peer_name`.
  - [ ] `test_does_not_project_peer_name_on_tool_call_event` — assistant-with-tool_calls projection: even if peer_name were set on the source message, the tool_call event does NOT carry peer_name. Mirror the visibility test pattern at `TestMessagesToUiEventsVisibility::test_projects_visibility_on_tool_call_event` (around line 499 in pre-L1 layout) for shape; assert peer_name is absent on every tool_call event.
  - [ ] `test_does_not_project_peer_name_on_tool_result_event` — Tool message: peer_name absent on tool_result event.
  - [ ] `test_user_event_carries_both_peer_name_and_visibility` — `Message.user("hi", peer_name="alice", visibility="operator")` projects to event with BOTH keys present. Cross-cutting compose-with-visibility check.
  - [ ] `test_mixed_user_messages_in_session` — list of three user messages: (a) no peer_name no visibility, (b) peer_name="alice" only, (c) peer_name="alice" + visibility="operator". The projection produces three events with the keys present/absent independently per message — mirrors the visibility class's `test_mixed_visibility_session` test (around line 524 pre-L1).
- [ ] All pre-existing tests in `tests/test_db_codec.py` pass without modification. In particular: the pre-existing `TestMessagesToUIEvents::test_user_message` at line 101 asserts `events[0] == {"type": "user", "content": "hello", "source": "restored"}` for a `Message.user("hello")` — peer_name is None by default so the event remains byte-identical and the equality assertion still passes.
- [ ] All L1 tests (`TestMessagePeerNameCodec`) continue to pass without modification.

## Verification Steps

Run from the project root inside the dev container.

1. **Targeted test file passes** (post-implementation):
   ```
   docker exec the-one pytest -x --timeout 30 tests/test_db_codec.py
   ```
   Expected: all tests pass — pre-existing + L1's 9 + L2's 7 (or 8 depending on exact test split) new tests.

2. **Smoke-check the user-event projection**:
   ```
   docker exec the-one python -c "from the_one.db.codec import messages_to_ui_events; from the_one.llm.base import Message; print(messages_to_ui_events([Message.user('hi', peer_name='alice')]))"
   ```
   Expected: `[{'type': 'user', 'content': 'hi', 'source': 'restored', 'peer_name': 'alice'}]`.

3. **Smoke-check assistant/tool event absence**:
   ```
   docker exec the-one python -c "from the_one.db.codec import messages_to_ui_events; from the_one.llm.base import Message, Role; m = Message(role=Role.ASSISTANT, content='hi', peer_name='alice'); print(messages_to_ui_events([m]))"
   ```
   Expected: `[{'type': 'assistant', 'content': 'hi'}]` — no peer_name key on the assistant event (the projection is gated to the USER branch only).

4. **Smoke-check compose-with-visibility**:
   ```
   docker exec the-one python -c "from the_one.db.codec import messages_to_ui_events; from the_one.llm.base import Message; print(messages_to_ui_events([Message.user('hi', peer_name='alice', visibility='operator')]))"
   ```
   Expected: both `peer_name` and `visibility` keys present on the projected event.

5. **Verify no consumer regressions** in adjacent test files that exercise the projection:
   ```
   docker exec the-one pytest -x --timeout 30 tests/test_db_codec.py tests/test_app_websocket_pause_resume.py
   ```
   Expected: all pass.

## Implementation Guidance

1. **Edit `the_one/db/codec.py:messages_to_ui_events`** — find the per-iteration `vis` dict construction (the line currently reading `vis = {"visibility": msg.visibility} if msg.visibility is not None else {}`). Add a sibling `peer` dict immediately after it:

   ```python
   # M10 F03 L02: visibility tag flows into every event derived from
   # this message. Absent key when source visibility is None — frontends
   # treat absent === platform-visible.
   vis = {"visibility": msg.visibility} if msg.visibility is not None else {}
   # M11 F06 L02: peer_name flows ONLY into Role.USER events (peer_name
   # is meaningful only on user-role messages — assistant/tool messages
   # leave the field at its default None by construction). Absent key
   # when source peer_name is None — frontends treat absent === no peer
   # attribution (operator-typed or non-connector session).
   peer = {"peer_name": msg.peer_name} if msg.peer_name is not None else {}
   ```

   Then in the `Role.USER` branch, append `**peer` to the event-dict spread:

   ```python
   if msg.role == Role.USER:
       events.append(
           {"type": "user", "content": msg.content, "source": "restored", **vis, **peer}
       )
   ```

   Do NOT add `**peer` to the assistant, tool_call, or tool_result branches. Keep the per-message `peer` variable construction OUTSIDE the role branching (defensive — costs ~one dict-build per message, negligible).

2. **Edit `tests/test_db_codec.py`** — locate the end of `TestMessagesToUiEventsVisibility` class (it ends near line 627 in the current layout with a `test_assistant_visibility_in_complex_session` or similar tail). Insert a new test class immediately after it and before `TestMessageVisibilityClassmethodKwargs` (currently at line 629). Use the same docstring pattern as `TestMessagesToUiEventsVisibility`:

   ```python
   class TestMessagesToUiEventsPeerName:
       """``messages_to_ui_events`` projects ``peer_name`` ONLY onto user-role
       events. Assistant/tool branches are unaffected — peer_name is
       meaningful only on user-role messages, and the projection's per-branch
       spread is gated accordingly. Composes cleanly with the visibility
       projection (both keys spread independently from per-message dicts).
       """

       def test_projects_peer_name_on_user_message(self) -> None:
           msgs = [Message.user("hi", peer_name="alice")]
           events = messages_to_ui_events(msgs)
           assert events[0]["peer_name"] == "alice"

       def test_omits_peer_name_on_user_message_without_peer_name(self) -> None:
           msgs = [Message.user("hi")]
           events = messages_to_ui_events(msgs)
           assert "peer_name" not in events[0]

       def test_does_not_project_peer_name_on_assistant_event(self) -> None:
           # Direct constructor — paranoia: even if peer_name is somehow set
           # on a non-USER message, the projection MUST NOT propagate it.
           msgs = [Message(role=Role.ASSISTANT, content="hi there", peer_name="alice")]
           events = messages_to_ui_events(msgs)
           assert len(events) == 1
           assert events[0]["type"] == "assistant"
           assert "peer_name" not in events[0]

       def test_does_not_project_peer_name_on_tool_call_event(self) -> None:
           tc1 = ToolCall(id="tc-1", name="read_file", arguments={"path": "/x"})
           msgs = [Message(role=Role.ASSISTANT, content="", tool_calls=[tc1], peer_name="alice")]
           events = messages_to_ui_events(msgs)
           tc_events = [e for e in events if e["type"] == "tool_call"]
           assert len(tc_events) == 1
           assert "peer_name" not in tc_events[0]

       def test_does_not_project_peer_name_on_tool_result_event(self) -> None:
           tr = ToolResult(tool_call_id="tc-1", content="done")
           msgs = [Message(role=Role.TOOL, content="done", tool_result=tr, peer_name="alice")]
           events = messages_to_ui_events(msgs)
           assert len(events) == 1
           assert events[0]["type"] == "tool_result"
           assert "peer_name" not in events[0]

       def test_user_event_carries_both_peer_name_and_visibility(self) -> None:
           msgs = [Message.user("hi", peer_name="alice", visibility="operator")]
           events = messages_to_ui_events(msgs)
           assert events[0]["peer_name"] == "alice"
           assert events[0]["visibility"] == "operator"

       def test_mixed_user_messages_in_session(self) -> None:
           """Three user messages with different (peer_name, visibility) combos:
           keys present/absent independently per message."""
           msgs = [
               Message.user("plain"),
               Message.user("from-alice", peer_name="alice"),
               Message.user("operator-and-alice", peer_name="alice", visibility="operator"),
           ]
           events = messages_to_ui_events(msgs)
           assert len(events) == 3
           assert "peer_name" not in events[0]
           assert "visibility" not in events[0]
           assert events[1]["peer_name"] == "alice"
           assert "visibility" not in events[1]
           assert events[2]["peer_name"] == "alice"
           assert events[2]["visibility"] == "operator"
   ```

3. **Update leg status to `in-flight`** at the start of implementation; update to `landed` when implementation + tests pass.

4. **Update flight-log.md** with a Leg Progress entry under `## Leg Progress`. Check off the `ui-event-projection` checkbox in `flight.md`'s Legs list. Do NOT commit (deferred to flight-end).

## Edge Cases

- **Assistant message with peer_name accidentally set**: the per-branch spread ensures peer_name is never propagated to non-USER events. Paranoia tests (`test_does_not_project_peer_name_on_assistant_event`, `..._on_tool_call_event`, `..._on_tool_result_event`) lock this invariant.
- **Empty-string peer_name**: per L1's edge-case analysis, this cannot happen in practice (Discord plugin populates `display_name or str(user.id)` at `_discord.py:218`). If it did appear (e.g. test fixture sets `peer_name=""`), the truthy-check `if msg.peer_name is not None` would still emit `{"peer_name": ""}` — non-issue, the UI's `data.peer_name || 'You'` fallback (L4) would render `'You'` for empty strings. No special handling needed.
- **None visibility + None peer_name** on user message: both keys absent from event — byte-identical to pre-F6 projection. Pre-existing `TestMessagesToUIEvents::test_user_message` (line 101) at the start of the file relies on this exact-equality assertion; the test must continue to pass without modification (verified by AC).
- **Non-None visibility + None peer_name** on user message: visibility key present, peer_name absent. The pre-existing `TestMessagesToUiEventsVisibility::test_projects_visibility_on_tagged_user_message` (around line 482) MUST continue to pass — peer_name is None by default and the new spread does not add the key.
- **`index_offset` interaction**: `messages_to_ui_events` accepts an `index_offset` kwarg used by the dispatcher for live broadcasts (`_inbound.py:678`). The peer_name spread is independent of `index_offset` — it's a per-message field, not a per-position projection. No interaction; no new tests needed for `index_offset + peer_name` composition.

## Files Affected

- `the_one/db/codec.py` — `messages_to_ui_events` user-event spread
- `tests/test_db_codec.py` — new `TestMessagesToUiEventsPeerName` test class
- `missions/11-discord-connector-depth/flights/06-peer-name-attribution-end-to-end/flight-log.md` — Leg Progress entry
- `missions/11-discord-connector-depth/flights/06-peer-name-attribution-end-to-end/legs/02-ui-event-projection.md` — status transitions (planning → in-flight → landed)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]` (per agentic-workflow protocol; do NOT commit — commit is deferred to flight-end):**

- [ ] All acceptance criteria verified
- [ ] Targeted test file passes (`docker exec the-one pytest -x --timeout 30 tests/test_db_codec.py`)
- [ ] Adjacent test files smoke-pass (`tests/test_app_websocket_pause_resume.py`)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed`
- [ ] Check off `ui-event-projection` in flight.md
- [ ] Do NOT commit — agentic-workflow defers commit to flight-end
- [ ] Do NOT update flight.md status to `landed`

---

## Citation Audit

Citations verified against current code (post-L1 state) at leg design time:

- `the_one/db/codec.py:messages_to_ui_events` — verified at design time. Note: L1's edits to adjacent functions (`message_to_dict`, `message_from_dict`) may have shifted line numbers in `messages_to_ui_events`; the leg uses symbol-form citations (`messages_to_ui_events`, `Role.USER` branch, `vis` dict construction) which are drift-resistant. The implementing agent re-locates the exact lines via the cited snippet `vis = {"visibility": msg.visibility} if msg.visibility is not None else {}`.
- `tests/test_db_codec.py:101` (`TestMessagesToUIEvents::test_user_message`) — verified at design time (the exact-equality assertion that L2 must not break).
- `tests/test_db_codec.py:482` (`TestMessagesToUiEventsVisibility::test_projects_visibility_on_tagged_user_message`) — verified at design time; pre-L1 line numbers, may have shifted by ~60 lines post-L1's TestMessagePeerNameCodec insertion.
- `tests/test_db_codec.py:536` (`TestMessagesToUiEventsVisibility` class start) — verified post-L1 layout via grep (`^class Test`).
- `tests/test_db_codec.py:629` (`TestMessageVisibilityClassmethodKwargs` class start) — verified post-L1 layout via grep.
- `the_one/connectors/_inbound.py:678` (`messages_to_ui_events(new_msgs, index_offset=pre_step_len)` — the dispatcher broadcast call site for live connector inbound) — verified at flight design time.
- `the_one/connectors/_discord.py:218` (peer_name population fallback) — verified at flight design time.

7 citations verified; line-number drift acknowledged for the codec function body (L1 added ~6 lines in adjacent functions); symbol-form citations protect against the drift. The implementing agent re-locates exact lines via grep on the snippet.
