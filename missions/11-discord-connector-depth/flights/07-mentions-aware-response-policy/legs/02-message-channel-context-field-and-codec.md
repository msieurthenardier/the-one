# Leg: message-channel-context-field-and-codec

**Status**: completed
**Flight**: [Mentions-Aware Response Policy](../flight.md)

## Objective

Add `channel_name: str | None = None` and `channel_id: str | None = None` fields to the `Message` dataclass, extend `Message.user(...)` to accept them, and extend the codec (`message_to_dict` / `message_from_dict`) to round-trip them via the `message-additive-back-compat-via-emit-when-non-none` convention — so L3 can bind them post-step and L4 can project them into provider payloads.

## Context

- **Flight DD §5 (peer-name + channel-name LLM-side projection)** — `Message.channel_name` and `Message.channel_id` are new optional fields, codec-emitted only when non-None, decoded with `.get(...)` defaulting to None for legacy rows. The provider adapters (L4) prepend `[from {peer_name} in #{channel_name}]: ` to user-role content when these fields are set; the dispatcher (L3) binds them post-step the same way F6 L3 binds `peer_name`. L2 is the dataclass + codec slice of that ship.
- **`message-additive-back-compat-via-emit-when-non-none` convention** at `the_one/agents.md:309–340` — currently cites 3 sites (`tool_result.metadata`, `Message.visibility`, `Message.peer_name`). L2 adds 2 more sites (`Message.channel_name`, `Message.channel_id`), pushing the convention's citation count to n=5. The convention's implementation shape is unchanged; L2 mechanically follows it.
- **Atomic-leg-pattern boundary** — L2 is field + codec only. L3 wires the dispatcher binding (post-step mutator `bind_channel_context` lands in `post_step_metadata.py`, populated by L1 as the module home). L4 wires the provider projection (`_to_api_message` prefix). The codec is the DB serialization layer; the WS broadcast / Chat UI projection is a separate concern handled in L3.
- **Channel context is meaningful only on Role.USER messages** (the inbound user turn) — same shape as `peer_name`. Assistant / tool messages leave both fields at their default. L3 enforces this via the same `assert messages[pre_step_len].role == Role.USER` discipline `bind_peer_name` uses.

## Inputs

- `the_one/llm/base.py:42–69` — `Message` dataclass with fields ending in `peer_name: str | None = None` (M11 F6 L1 addition). New fields append after `peer_name`.
- `the_one/llm/base.py:76–88` — `Message.user(...)` classmethod with kwargs `visibility`, `peer_name`. L2 extends to add `channel_name`, `channel_id`.
- `the_one/db/codec.py:54–74` — `message_to_dict` with emit-when-non-None blocks for `visibility` (lines 65–67) and `peer_name` (lines 68–73). L2 appends two symmetric blocks for channel_name + channel_id.
- `the_one/db/codec.py:77–109` — `message_from_dict` reading `.get("visibility")` (line 100) and `.get("peer_name")` (line 108). L2 adds two more `.get(...)` reads in the Message constructor call.
- `tests/test_db_codec.py:479–534` — `TestMessagePeerNameCodec` test class with the canonical 3-test pattern: full round-trip, back-compat (no key in legacy JSON), and composition with another optional field. L2 mirrors this for channel_name + channel_id.
- `the_one/agents.md:309–340` — `message-additive-back-compat-via-emit-when-non-none` convention block with n=3 citations.
- L1 status — landed; the post-step module home exists at `the_one/connectors/post_step_metadata.py`. L2 does NOT touch it (channel binding is L3's job).

## Outputs

- `the_one/llm/base.py` (Message dataclass):
  - New `channel_id: str | None = None` field appended immediately after `peer_name`, with an explanatory comment block. The `channel_id` is the platform-native channel identifier string (e.g. a Discord channel snowflake; the convention is plugin-agnostic — non-Discord plugins supply their own platform-native id string). Goes first because it is the canonical key from which `channel_name` is resolved.
  - New `channel_name: str | None = None` field appended immediately after `channel_id`, with an explanatory comment block mirroring the `peer_name` comment in shape (cite M11 F7 L2 origin, name the codec emit-when-non-None pattern, name the L3 dispatcher-binding + L4 provider-projection consumers, note meaningfulness limited to Role.USER messages, name the F3 discoverable-entities cache as the resolution source).
- `the_one/llm/base.py` (Message.user classmethod):
  - Signature extended with two keyword-only optional parameters: `channel_id: str | None = None`, `channel_name: str | None = None` (in this order, matching the dataclass field order).
  - Body passes both new kwargs through to the `cls(...)` call.
- `the_one/db/codec.py:message_to_dict`:
  - Two new emit-when-non-None blocks appended after the peer_name block (which ends at line 73):
    ```python
    # M11 F07 L02: emit channel_id only when non-None. Pre-F7 rows
    # had no channel_id key; preserve byte-identical legacy shape.
    if msg.channel_id is not None:
        d["channel_id"] = msg.channel_id
    # M11 F07 L02: emit channel_name only when non-None. Same back-compat
    # discipline as channel_id above; the pair travels together but each
    # independently emits when set (cold-pool case: id resolved but name
    # not yet cached).
    if msg.channel_name is not None:
        d["channel_name"] = msg.channel_name
    ```
- `the_one/db/codec.py:message_from_dict`:
  - Two new keyword args appended to the Message constructor call (after the peer_name=...), in id-then-name order:
    ```python
    # M11 F07 L02: channel_id — None on pre-F7 rows without the key.
    channel_id=d.get("channel_id"),
    # M11 F07 L02: channel_name — None on pre-F7 rows without the key.
    channel_name=d.get("channel_name"),
    ```
- `the_one/agents.md`:
  - In the `message-additive-back-compat-via-emit-when-non-none` convention block at lines 309–340:
    - Citations list grows from n=3 → n=5: append two new lines:
      - `Message.channel_name (M11 F7 L2)` — `the_one/db/codec.py:<new_encode_line>, <new_decode_line>` (encode + decode).
      - `Message.channel_id (M11 F7 L2)` — `the_one/db/codec.py:<new_encode_line>, <new_decode_line>` (encode + decode).
    - Update the "(n=3 — pattern is well past codification threshold)" parenthetical to `(n=5 — pattern is well past codification threshold)`.
    - The convention's implementation shape (code example at ~lines 316–329) is unchanged.
- `tests/test_db_codec.py`:
  - New `TestMessageChannelIdCodec` class with four tests (mirroring `TestMessagePeerNameCodec` shape):
    - `test_full_round_trip_with_channel_id` — `Message.user("hi", channel_id="123456789")` → encode → decode → asserts `channel_id == "123456789"`.
    - `test_message_from_dict_back_compat_no_channel_id_key` — legacy JSON `{"role": "user", "content": "hi"}` → decode → asserts `channel_id is None`.
    - `test_message_user_default_channel_id_is_none` — `Message.user("hi").channel_id is None`, pinning the classmethod's default contract that L3 will rely on when constructing user messages.
    - `test_round_trip_with_channel_id_and_peer_name` — both set together → both round-trip independently.
  - New `TestMessageChannelNameCodec` class with four tests (same four patterns for `channel_name`).
  - New `TestMessageChannelContextCompositionCodec` class with two cross-cutting composition tests:
    - `test_round_trip_with_all_optional_fields` — `Message.user("hi", visibility="operator", peer_name="alice", channel_id="123456789", channel_name="general")` → all four round-trip independently.
    - `test_encode_emits_no_keys_when_all_optional_fields_default` — `Message.user("hi")` → encode → JSON contains only `role` and `content` keys (no `visibility`, `peer_name`, `channel_id`, or `channel_name` keys). This pins the back-compat invariant: a Message with no optional fields set encodes byte-identical to pre-F7 (and pre-F6, and pre-M10-F3). **The test body MUST include a comment naming this invariant explicitly and noting that any new optional Message field requires a conscious update to the expected-key-list in the same edit that adds it to the agents.md `n=` citation count — otherwise the tripwire degrades into a maintenance nuisance rather than a regression net.**

## Acceptance Criteria

- [ ] `the_one/llm/base.py:Message` dataclass has `channel_name: str | None = None` and `channel_id: str | None = None` fields appended after `peer_name`, each with an explanatory comment block following the existing peer_name comment pattern (M11 F7 L2 attribution, codec emit-when-non-None reference, L3 + L4 consumer mention, Role.USER-only meaningfulness note).
- [ ] `the_one/llm/base.py:Message.user(...)` accepts `channel_name: str | None = None` and `channel_id: str | None = None` as keyword-only kwargs and passes them through to the constructor.
- [ ] `the_one/db/codec.py:message_to_dict` has two new `if msg.channel_name is not None` / `if msg.channel_id is not None` emit blocks appended after the peer_name block, with M11 F7 L2 attribution comments.
- [ ] `the_one/db/codec.py:message_from_dict` includes `channel_name=d.get("channel_name")` and `channel_id=d.get("channel_id")` in the Message constructor call.
- [ ] `the_one/agents.md`'s `message-additive-back-compat-via-emit-when-non-none` convention citation count is updated to n=5, with two new lines citing `Message.channel_name` and `Message.channel_id`.
- [ ] `tests/test_db_codec.py` has `TestMessageChannelIdCodec` (4 tests), `TestMessageChannelNameCodec` (4 tests), and `TestMessageChannelContextCompositionCodec` (2 tests) — 10 new tests total.
- [ ] The composition test `test_encode_emits_no_keys_when_all_optional_fields_default` passes — pinning the back-compat invariant that a default Message encodes to `{"role": "...", "content": "..."}` only.
- [ ] `docker exec the-one pytest tests/test_db_codec.py -x --timeout 30` passes (existing + new tests, all green).
- [ ] Full suite at leg-end: `docker exec the-one pytest -x --timeout 60` — no L2-introduced regressions.
- [ ] Flight log L2 entry under `## Leg Progress` documents the leg; leg checked off in `flight.md` under `### Legs`.

## Verification Steps

- `python -c "from the_one.llm.base import Message; m = Message.user('hi', channel_name='general', channel_id='123'); print(m.channel_name, m.channel_id)"` prints `general 123`.
- `python -c "from the_one.llm.base import Message; m = Message.user('hi'); print(m.channel_name, m.channel_id)"` prints `None None`.
- `python -c "from the_one.db.codec import message_to_dict, message_from_dict; from the_one.llm.base import Message; d = message_to_dict(Message.user('hi')); print(sorted(d.keys()))"` prints `['content', 'role']` — no optional keys emitted.
- `python -c "from the_one.db.codec import message_to_dict, message_from_dict; from the_one.llm.base import Message; d = message_to_dict(Message.user('hi', channel_name='general', channel_id='123')); print(sorted(d.keys()))"` prints `['channel_id', 'channel_name', 'content', 'role']`.
- `python -c "from the_one.db.codec import message_from_dict; m = message_from_dict({'role': 'user', 'content': 'hi'}); print(m.channel_name, m.channel_id)"` prints `None None` (legacy decode).
- `grep -n "channel_name" the_one/agents.md` returns at least one citation match in the convention block.
- `grep -c "M11 F07 L02" the_one/llm/base.py the_one/db/codec.py` returns ≥6 matches total (≥2 per field-comment block × 2 fields + ≥2 codec attribution comments).
- Targeted test command: `docker exec the-one pytest tests/test_db_codec.py -x --timeout 30` — all green.
- Full suite: `docker exec the-one pytest -x --timeout 60` — all green.

## Implementation Guidance

1. **Update `the_one/llm/base.py:Message` dataclass.** Append after the existing `peer_name: str | None = None` line (id first since it is the canonical key from which the name is resolved):
   ```python
   # M11 F07 L02: channel_id — platform-native channel identifier string
   # (e.g. a Discord channel snowflake; the convention is plugin-agnostic
   # and any connector plugin supplies its own platform-native id string).
   # The canonical key; the channel_name field below is the human-readable
   # label resolved from this id via the F3 discoverable-entities cache.
   # The pair travels together because the L4 provider projection uses the
   # name for the LLM prefix while the dispatcher's routing audit and the
   # F9 audit-log inspector use the id. The codec emits the key only when
   # non-None — pre-F7 rows decode with channel_id=None unchanged.
   # Meaningful only on Role.USER messages; assistant/tool messages leave
   # it at the default.
   channel_id: str | None = None
   # M11 F07 L02: channel_name — platform-resolved human-readable channel
   # label (e.g. a Discord channel name like "general"). Resolved from
   # channel_id via the F3 discoverable-entities cache by L3's
   # bind_channel_context; the L4 provider adapters project it as
   # `[from {peer_name} in #{channel_name}]: ...` on user-role content so
   # the engaged agent sees multi-user context naturally. Same back-compat
   # discipline as channel_id above (emit-when-non-None; legacy rows
   # decode to None). May be present without channel_id only in
   # corner-case malformed envelopes — the standard flow binds both
   # together; either may be absent independently (cold-pool case: id
   # resolved but name not yet cached).
   channel_name: str | None = None
   ```

2. **Update `the_one/llm/base.py:Message.user(...)` classmethod.** Extend the signature (id first, then name — matches dataclass field order):
   ```python
   @classmethod
   def user(
       cls,
       content: str,
       *,
       visibility: str | None = None,
       peer_name: str | None = None,
       channel_id: str | None = None,
       channel_name: str | None = None,
   ) -> Message:
       return cls(
           role=Role.USER,
           content=content,
           visibility=visibility,
           peer_name=peer_name,
           channel_id=channel_id,
           channel_name=channel_name,
       )
   ```

3. **Update `the_one/db/codec.py:message_to_dict`.** After the existing peer_name emit block (which ends at line 73), append (id first, matching dataclass field order):
   ```python
   # M11 F07 L02: emit channel_id only when non-None. Pre-F7 rows had
   # no channel_id key; preserve byte-identical legacy shape. Mirrors
   # the peer_name pattern above.
   if msg.channel_id is not None:
       d["channel_id"] = msg.channel_id
   # M11 F07 L02: emit channel_name only when non-None. Same back-compat
   # discipline as channel_id above; the pair travels together but each
   # independently emits only when set (cold-pool case: id resolved but
   # name not yet cached).
   if msg.channel_name is not None:
       d["channel_name"] = msg.channel_name
   ```

4. **Update `the_one/db/codec.py:message_from_dict`.** In the Message constructor call (around lines 100–108), after `peer_name=d.get("peer_name")`, append (id first):
   ```python
   # M11 F07 L02: channel_id — None on pre-F7 rows without the key.
   channel_id=d.get("channel_id"),
   # M11 F07 L02: channel_name — None on pre-F7 rows without the key.
   channel_name=d.get("channel_name"),
   ```

5. **Update `the_one/agents.md`.** In the `message-additive-back-compat-via-emit-when-non-none` block (lines 309–340):
   - Change the Citations parenthetical from `(n=3 — pattern is well past codification threshold)` to `(n=5 — pattern is well past codification threshold)`.
   - Append two new bullet lines after the `Message.peer_name` citation, in the same shape:
     ```
     - `Message.channel_name` (M11 F7 L2) — `the_one/db/codec.py:<encode_line>, <decode_line>` (encode + decode).
     - `Message.channel_id` (M11 F7 L2) — `the_one/db/codec.py:<encode_line>, <decode_line>` (encode + decode).
     ```
   - Resolve the `<encode_line>` and `<decode_line>` line numbers from the actual file after the codec edits — these will be a few lines below the peer_name citations.

6. **Add tests in `tests/test_db_codec.py`.** Mirror `TestMessagePeerNameCodec` (lines 479–534) for the new fields:
   - `TestMessageChannelIdCodec` — four tests: `test_full_round_trip_with_channel_id`, `test_message_from_dict_back_compat_no_channel_id_key`, `test_message_user_default_channel_id_is_none`, `test_round_trip_with_channel_id_and_peer_name`. Each test follows the existing test class's body shape. Use `Message.user("hi", channel_id="123456789")` for construction.
   - `TestMessageChannelNameCodec` — four tests in the same four patterns for `channel_name`. Use `Message.user("hi", channel_name="general")` for construction.
   - `TestMessageChannelContextCompositionCodec` — two cross-cutting composition tests:
     - `test_round_trip_with_all_optional_fields` — Message with all four optional fields set; verify all four round-trip.
     - `test_encode_emits_no_keys_when_all_optional_fields_default` — `Message.user("hi")` → encode → assert `sorted(d.keys()) == ["content", "role"]` (no optional keys). This pins the back-compat invariant globally for all four optional fields, not just channel_id/channel_name. The test body MUST carry a comment:
       ```python
       # TRIPWIRE: any new optional Message field added via the
       # message-additive-back-compat-via-emit-when-non-none convention
       # MUST update this expected-key-list in the same edit that bumps
       # the n=N citation count in agents.md. Do NOT "fix" the failing
       # test by adding the new field to the expected list silently —
       # that defeats the back-compat tripwire.
       ```

7. **Run tests** per Verification Steps. Update flight log under `## Leg Progress` with a `### L2 — message-channel-context-field-and-codec` subsection. Check off the leg in `flight.md`. Set L2 status to `landed` in the leg artifact header. Do NOT commit (F7 flight-level commit ordering — see L1's Flight Director Notes).

## Edge Cases

- **`channel_name=""` (empty string)** vs. `channel_name=None`: per the convention's bold guidance ("Use `is not None` for the emit guard, NOT truthy"), an empty-string channel_name MUST round-trip (i.e. emit the empty string and decode it back). This matches the peer_name precedent. Tests do not need to pin this explicitly — the `is not None` guard is structural — but a non-blocking suggestion: add a `test_round_trip_with_empty_string_channel_name` if doing so doesn't bloat the suite. Default: omit; the structural guard makes it unnecessary.
- **`channel_id="0"` (string zero)** similarly: emit + decode correctly; the structural `is not None` guard already covers this.
- **Channel_id without channel_name** (or vice versa): both fields independently emit-when-non-None, so an envelope that has a resolvable channel_id but no cached channel_name (cold pool, non-Discord plugin) will store `{"role": "user", "content": "...", "channel_id": "..."}` with no channel_name key. L3's `bind_channel_context` will set both together when both are available; L2's codec must independently support either-or. The composition test confirms this implicitly (no special-case test needed) — but note it in the channel_id comment block.
- **Pre-F7 rows during forward-compat** — legacy rows lack both keys; `.get(...)` returns None for both; the decoded Message has `channel_name=None, channel_id=None`. No migration script needed.
- **Forward-compat with future fields** — the convention is well-established; new optional fields after L2 follow the same pattern. The convention's citation count is the indirect monitor of this discipline.
- **WS broadcast / Chat UI** — explicitly out of L2 scope. L3 wires `messages_to_ui_events` (replay path) and `_broadcast_one` (live path) to project the new fields onto WS events. L2's codec is DB-only.

## Files Affected

- `the_one/llm/base.py` — Message dataclass + `Message.user(...)` classmethod.
- `the_one/db/codec.py` — `message_to_dict` + `message_from_dict`.
- `the_one/agents.md` — convention block citation list (n=3 → n=5).
- `tests/test_db_codec.py` — three new test classes (8 new tests total).
- `missions/11-discord-connector-depth/flights/07-mentions-aware-response-policy/flight-log.md` — APPEND `## Leg Progress` entry.
- `missions/11-discord-connector-depth/flights/07-mentions-aware-response-policy/flight.md` — CHECK OFF leg.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (targeted + full suite)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] If final leg of flight: NOT applicable (L2 is mid-flight)
- [ ] Commit all changes together (code + artifacts) — DEFERRED in F7 per `/agentic-workflow` flight-level commit ordering; do NOT commit per leg.

## Citation Audit

10 code-location citations in this leg were verified against current code at design time via the F7 L2 reconnaissance pass:

- `the_one/llm/base.py:42–69` — Message dataclass (verified).
- `the_one/llm/base.py:76–88` — Message.user(...) classmethod (verified).
- `the_one/db/codec.py:54–74` — message_to_dict with peer_name emit at 68–73 (verified).
- `the_one/db/codec.py:77–109` — message_from_dict with peer_name decode at 108 (verified).
- `the_one/agents.md:309–340` — message-additive-back-compat convention block (verified).
- `tests/test_db_codec.py:479–534` — TestMessagePeerNameCodec template class (verified).
- `the_one/agents.md:316–329` — implementation shape code example within the convention block (verified).

No drift detected. All citations verified clean. L1 added `the_one/connectors/post_step_metadata.py` which L2 does not touch (L3's domain).
