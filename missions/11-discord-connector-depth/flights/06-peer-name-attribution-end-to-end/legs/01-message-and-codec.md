# Leg: message-and-codec

**Status**: completed
**Flight**: [Peer-name Attribution End-to-End (Bug C)](../flight.md)

## Objective

Add the `peer_name: str | None = None` field to the `Message` dataclass and extend the JSON codec's `message_to_dict` / `message_from_dict` to round-trip it with emit-when-non-None semantics, so connector-attached sessions can later persist the inbound peer's display name alongside the user-role message.

## Context

This is the first of four autonomous legs implementing M10 Bug C. It lands the wire-shape contract change — the new field on the dataclass and its JSON serialization — independently of the consumer code that will eventually read or write the field. The `messages_to_ui_events` projection is intentionally NOT in this leg (split into L2 per architect review — codec ↔ UI-event projection are unrelated wire-shape contracts).

Per `atomic-leg-pattern` (agents.md §Project-wide): this leg touches the Pydantic-equivalent dataclass + its codec ripple-sites together because they share the JSON-shape contract. UI-event projection consumes the dataclass shape but is a separate downstream wire format (the WebSocket event shape) and lives in L2.

Per Design Decision §3 (flight.md): back-compat for pre-F6 stored sessions is provided by the emit-when-non-None encode + `d.get("peer_name")` decode pattern — the exact precedent set by `visibility` at `the_one/db/codec.py:66-67` (encode) and `:100` (decode). Legacy stored JSON has no `peer_name` key; decoded `Message` instances get `peer_name=None`.

Per Design Decision §2 (flight.md): `peer_name` is consumed by UI/persistence paths only — provider adapters (`the_one/llm/openai_provider.py`, `anthropic_provider.py`, `ollama_provider.py`) explicitly project `{"role": msg.role.value, "content": msg.content}` and do NOT call `dataclasses.asdict(msg)`. The new field cannot leak into LLM prompt payloads — verified by architect audit at flight design time.

## Inputs

What exists before this leg runs:

- `the_one/llm/base.py:42` — `@dataclass class Message` with fields `role`, `content`, `tool_calls`, `tool_result`, `usage`, `visibility`. No `peer_name`.
- `the_one/llm/base.py:Message.user` — classmethod `(cls, content: str, *, visibility: str | None = None) -> Message`.
- `the_one/db/codec.py:message_to_dict` — at `codec.py:54-68`: emits `role`, `content`, optional `tool_calls`, `tool_result`, `usage`, and `visibility` (emit-when-non-None precedent at lines 66-67).
- `the_one/db/codec.py:message_from_dict` — at `codec.py:71-101`: reads each field including `visibility` (back-compat default at line 100: `visibility=d.get("visibility")`).
- `tests/test_db_codec.py` — `TestCodecRoundTrip` class (line 18) and `TestMessageVisibilityCodec` class (line 435) — established test shape for round-trip + emit-when-non-None + back-compat decode.

## Outputs

After this leg completes:

- `Message` dataclass has `peer_name: str | None = None` field, declared with explanatory comment citing M11 F6 (Bug C, mission criterion #13).
- `Message.user` classmethod accepts a kwarg-only `peer_name: str | None = None` parameter and threads it into the constructor.
- `message_to_dict` emits `"peer_name": msg.peer_name` only when non-None (mirrors visibility pattern).
- `message_from_dict` reads `d.get("peer_name")` — None on legacy rows without the key.
- Tests in `tests/test_db_codec.py` pin: dataclass field default, `Message.user` kwarg, encode emit-when-non-None, decode back-compat, full round-trip with/without `peer_name`.
- No other consumer code is touched in this leg (L2 handles `messages_to_ui_events`; L3 handles dispatcher binding).

## Acceptance Criteria

- [ ] `Message` dataclass at `the_one/llm/base.py:42` has a new field `peer_name: str | None = None`, declared AFTER the existing `visibility` field for visual grouping of "M10/M11 connector-related optional fields" with a comment explaining the field (cites M11 F6 / Bug C / criterion #13).
- [ ] `Message.user` classmethod signature is `(cls, content: str, *, visibility: str | None = None, peer_name: str | None = None) -> Message` and threads `peer_name` into the constructor. Other classmethods (`system`, `assistant`, `tool`) are unchanged (peer_name is meaningful only on user-role messages; their `Message` constructor calls leave the field at its default None).
- [ ] `message_to_dict` at `the_one/db/codec.py:54` emits `d["peer_name"] = msg.peer_name` only when `msg.peer_name is not None` (placed alongside or after the existing visibility emit at lines 66-67).
- [ ] `message_from_dict` at `the_one/db/codec.py:71` populates `peer_name=d.get("peer_name")` on the constructed Message (placed alongside the existing visibility read at line 100).
- [ ] `tests/test_db_codec.py` gains a new test class `TestMessagePeerNameCodec` placed after `TestMessageVisibilityCodec` (line 472) with these tests:
  - [ ] `test_message_to_dict_emits_peer_name_when_non_none` — `Message(role=Role.USER, content="hi", peer_name="alice")` encodes with `d["peer_name"] == "alice"`.
  - [ ] `test_message_to_dict_omits_peer_name_when_none` — `Message(role=Role.USER, content="hi", peer_name=None)` encodes without the `peer_name` key.
  - [ ] `test_message_from_dict_restores_peer_name` — `{"role": "user", "content": "hi", "peer_name": "alice"}` decodes with `msg.peer_name == "alice"`.
  - [ ] `test_message_from_dict_back_compat_no_peer_name_key` — `{"role": "user", "content": "hi"}` decodes with `msg.peer_name is None`.
  - [ ] `test_full_round_trip_with_peer_name` — `Message.user("hi", peer_name="alice")` round-trips through `decode_messages(encode_messages(...))` preserving `peer_name == "alice"`.
  - [ ] `test_full_round_trip_without_peer_name` — `Message.user("hi")` round-trips with `peer_name is None`.
  - [ ] `test_message_user_default_peer_name_is_none` — `Message.user("hi").peer_name is None` (locks the kwarg-only default).
  - [ ] `test_message_user_kwarg_sets_peer_name` — `Message.user("hi", peer_name="alice").peer_name == "alice"` (locks the kwarg-only contract).
  - [ ] `test_round_trip_with_peer_name_and_visibility` — both new fields compose: `Message.user("hi", peer_name="alice", visibility="operator")` round-trips with both values preserved (cross-cutting back-compat check — neither field interferes with the other's encode/decode site).
- [ ] All pre-existing tests in `tests/test_db_codec.py` pass without modification (the change is purely additive — no existing message shape's encoded output changes byte-for-byte because the new key is omitted when None, which is the default).
- [ ] Pre-existing `Message.user(text)` call sites continue to compile and behave identically (kwarg-only default means existing positional calls are unaffected). Verified by running the touched test files; broader suite run is L4's responsibility.

## Verification Steps

Run from the project root inside the dev container. Pattern follows the `leg-execution.md` prompt: `docker exec the-one pytest -x --timeout 30 <path>`.

1. **Targeted test file passes** (post-implementation):
   ```
   docker exec the-one pytest -x --timeout 30 tests/test_db_codec.py
   ```
   Expected: all tests pass, including the 9 new tests in `TestMessagePeerNameCodec`.

2. **Smoke-check the dataclass field** (interactive verification):
   ```
   docker exec the-one python -c "from the_one.llm.base import Message; m = Message.user('hi', peer_name='alice'); print(m.peer_name)"
   ```
   Expected: `alice`.

3. **Smoke-check codec back-compat** (legacy JSON shape):
   ```
   docker exec the-one python -c "from the_one.db.codec import message_from_dict; m = message_from_dict({'role': 'user', 'content': 'hi'}); print(m.peer_name)"
   ```
   Expected: `None`.

4. **Smoke-check codec emit-when-non-None**:
   ```
   docker exec the-one python -c "from the_one.db.codec import message_to_dict; from the_one.llm.base import Message; print(message_to_dict(Message.user('hi')))"
   docker exec the-one python -c "from the_one.db.codec import message_to_dict; from the_one.llm.base import Message; print(message_to_dict(Message.user('hi', peer_name='alice')))"
   ```
   Expected: first prints `{'role': 'user', 'content': 'hi'}` (no peer_name key). Second prints `{'role': 'user', 'content': 'hi', 'peer_name': 'alice'}`.

5. **Verify no consumer regressions** in adjacent test files that load encoded messages:
   ```
   docker exec the-one pytest -x --timeout 30 tests/test_db_codec.py tests/test_session_lifecycle.py
   ```
   Expected: all pass. (Broader connector test run is L3's verification step.)

## Implementation Guidance

1. **Edit `the_one/llm/base.py`**

   Add the `peer_name` field to the `Message` dataclass immediately after the `visibility` field (lines 48-56). Use the same comment shape (cite mission/flight/leg + intent):

   ```python
   # M11 F06 L01: peer_name attribution for connector-attached sessions.
   # None = no peer attribution (operator-typed, agent-internal, or
   # non-connector session — the default for every Message constructed
   # without an explicit peer_name kwarg). When non-None, this is the
   # platform's display name for the peer who sent the inbound message
   # (e.g. a Discord username); the Chat UI renders it as the bubble's
   # attribution. The codec emits the key only when non-None — pre-F6
   # rows decode with peer_name=None unchanged. Meaningful only on
   # Role.USER messages; assistant/tool messages leave it at the default.
   peer_name: str | None = None
   ```

   Then update `Message.user` classmethod (current line 62-64) to thread the kwarg:

   ```python
   @classmethod
   def user(
       cls,
       content: str,
       *,
       visibility: str | None = None,
       peer_name: str | None = None,
   ) -> Message:
       return cls(
           role=Role.USER,
           content=content,
           visibility=visibility,
           peer_name=peer_name,
       )
   ```

   Do NOT modify `Message.system`, `Message.assistant`, `Message.tool` — peer_name is only meaningful on user-role messages; their `Message` constructor calls leave the field at its default None.

2. **Edit `the_one/db/codec.py:message_to_dict`** (current lines 54-68)

   After the visibility emit (lines 66-67), add a sibling emit for peer_name:

   ```python
   # M11 F06 L01: emit peer_name only when non-None. Pre-F6 rows had no
   # peer_name key; preserve that shape for back-compat and storage
   # efficiency. Mirrors the visibility pattern above and the
   # tool_result.metadata pattern in _tool_result_to_dict.
   if msg.peer_name is not None:
       d["peer_name"] = msg.peer_name
   ```

3. **Edit `the_one/db/codec.py:message_from_dict`** (current lines 71-101)

   In the `Message(...)` constructor call at the end (lines 93-101), add a sibling kwarg for peer_name after the visibility line:

   ```python
   return Message(
       role=Role(d["role"]),
       content=d.get("content", ""),
       tool_calls=tool_calls,
       tool_result=tool_result,
       usage=usage,
       # M10 F03 L02: visibility — None on legacy rows without the key.
       visibility=d.get("visibility"),
       # M11 F06 L01: peer_name — None on pre-F6 rows without the key.
       peer_name=d.get("peer_name"),
   )
   ```

4. **Edit `tests/test_db_codec.py`**

   Add a new test class `TestMessagePeerNameCodec` after `TestMessageVisibilityCodec` (which ends at line 472) and BEFORE the `TestMessagesToUiEventsVisibility` class. Mirror the visibility test class structure (line 435 onward) one-to-one — same docstring pattern, same test-shape, swap "visibility" for "peer_name" and swap `"operator"` for `"alice"`. Add the cross-cutting `test_round_trip_with_peer_name_and_visibility` test at the end of the class.

   Example shape (matching the precedent):

   ```python
   class TestMessagePeerNameCodec:
       """``Message.peer_name`` round-trips through ``message_to_dict`` ↔
       ``message_from_dict``: the key is emitted only when non-None,
       deserialization defaults to None when the key is absent (back-compat
       with every pre-F6 session row).
       """

       def test_message_to_dict_emits_peer_name_when_non_none(self) -> None:
           msg = Message(role=Role.USER, content="hi", peer_name="alice")
           d = message_to_dict(msg)
           assert d["peer_name"] == "alice"

       def test_message_to_dict_omits_peer_name_when_none(self) -> None:
           msg = Message(role=Role.USER, content="hi", peer_name=None)
           d = message_to_dict(msg)
           assert "peer_name" not in d

       # ... etc, mirroring the visibility class structure
   ```

5. **Update leg status to in-flight** at the start of implementation; update to `landed` when implementation + tests pass. Do NOT commit (per agentic-workflow protocol, commit is deferred to flight-end).

6. **Update flight-log.md** with a Leg Progress entry under `## Leg Progress` describing what landed. Per the `leg-execution.md` Implement prompt: "Update flight log with outcomes. Propagate changes to artifacts (flight, mission, leg)... as needed."

## Edge Cases

- **Empty-string peer_name**: technically truthy-different-from-None in Python; would be emitted as `"peer_name": ""` in JSON. The dispatcher (L3) always reads from `working_envelope.peer_name` which the Discord plugin populates as `display_name or str(user.id)` (`_discord.py:218`) — `display_name` is never empty (falls back to user.id), so the dispatcher cannot produce `peer_name=""`. Test data should use `"alice"` consistently; no explicit empty-string handling needed in L1. Document the invariant in the dataclass comment for future readers.
- **Unicode/emoji peer names** (e.g. `"😎alice"`): JSON serialization handles Unicode natively via `json.dumps` default behavior (no `ensure_ascii` argument); round-trip is byte-clean. Not tested explicitly in L1 (covered by Python stdlib semantics); L5 HAT may exercise emoji peer names against the real Discord client.
- **Pre-F6 sessions read post-F6**: a stored session row whose JSON has no `peer_name` key decodes with `peer_name=None` via `d.get("peer_name")`. Subsequent encode is byte-identical to pre-F6 because the codec emit-when-non-None omits the key when None. No storage churn for unchanged messages.
- **Message constructed without `Message.user` factory** (e.g. `Message(role=Role.USER, content="x")`): the field default `None` applies; no constructor-call site change needed. Existing call sites in tests (e.g. `tests/test_openrouter_provider.py:281`: `Message(role=Role.USER, content="hi")`) remain valid.
- **Compose with visibility**: both fields default to None and both are emitted-when-non-None independently. Cross-cutting test (`test_round_trip_with_peer_name_and_visibility`) pins composition.
- **No `Message.system`/`Message.assistant`/`Message.tool` kwarg**: intentional. peer_name is meaningful only on user-role messages. If a future need arises (e.g. attributing an agent reply to a specific multi-agent identity), it's an additive extension — not in scope here.

## Files Affected

- `the_one/llm/base.py` — `Message` dataclass + `Message.user` classmethod
- `the_one/db/codec.py` — `message_to_dict` + `message_from_dict`
- `tests/test_db_codec.py` — new `TestMessagePeerNameCodec` test class
- `missions/11-discord-connector-depth/flights/06-peer-name-attribution-end-to-end/flight-log.md` — Leg Progress entry
- `missions/11-discord-connector-depth/flights/06-peer-name-attribution-end-to-end/legs/01-message-and-codec.md` — status transitions (planning → in-flight → landed)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]` (per agentic-workflow protocol; do NOT commit — commit is deferred to flight-end):**

- [ ] All acceptance criteria verified
- [ ] Targeted test file passes (`docker exec the-one pytest -x --timeout 30 tests/test_db_codec.py`)
- [ ] Adjacent test files smoke-pass (`tests/test_session_lifecycle.py`)
- [ ] Update flight-log.md with leg progress entry under `## Leg Progress`
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Check off this leg in flight.md (`message-and-codec` checkbox in the Legs list)
- [ ] Do NOT commit — agentic-workflow defers commit to flight-end (after L4 review)
- [ ] Do NOT update flight.md status to `landed` — that happens after the final leg (L5)

---

## Citation Audit

10 citations verified against current code at leg design time:

- `the_one/llm/base.py:42` (Message dataclass) — verified at design time via Read of base.py lines 41-91.
- `the_one/llm/base.py:Message.user` (current line 62-64 with `*, visibility: str | None = None`) — verified at design time.
- `the_one/db/codec.py:54-68` (message_to_dict) — verified via Read of codec.py.
- `the_one/db/codec.py:66-67` (visibility emit precedent) — verified.
- `the_one/db/codec.py:71-101` (message_from_dict) — verified.
- `the_one/db/codec.py:100` (visibility back-compat read precedent) — verified.
- `tests/test_db_codec.py:18` (TestCodecRoundTrip class start) — verified.
- `tests/test_db_codec.py:435` (TestMessageVisibilityCodec class start) — verified.
- `tests/test_db_codec.py:472` (last test of TestMessageVisibilityCodec) — verified (line 471 is `assert rt[0].visibility is None` per Read at design time; new test class lands at next blank line).
- `the_one/connectors/_discord.py:218` (peer_name population fallback to user.id) — verified at recon time during flight design.
