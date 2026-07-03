# Leg: thinking-message-protocol

**Status**: completed
**Flight**: [Extended-Thinking / Reasoning Support (A1)](../flight.md)

## Objective

Add a structured, provider-agnostic `thinking` field to the `Message` protocol and
round-trip it through the persistence codec — modeled on `tool_calls` (a list with a
truthy emit guard), so signed thinking blocks persist and reload with signatures intact
while legacy rows decode byte-identically.

## Context

- **DD1 (structured, not scalar).** Criterion #1 requires the follow-up turn to replay
  thinking blocks *with their signatures*, and `redacted_thinking` blocks are opaque `data`
  with no text — a bare `str` cannot carry either. The field is therefore a **list of
  structured blocks**, round-tripped like `tool_calls`.
- **DD1 (outside the emit-when-non-none convention).** `thinking` is a `list` with
  `field(default_factory=list)`, a structural sibling of `tool_calls`
  (`base.py:68`, `codec.py:74`). The codec emits it with the **truthy guard** `if msg.thinking:`
  — NOT the `is not None` guard the `message-additive-back-compat-via-emit-when-non-none`
  convention (`agents.md:414–443`) mandates. An always-non-`None` empty list under an
  `is not None` guard would emit `"thinking": []` unconditionally and break the byte-identity
  tripwire. So this field joins `tool_calls` *outside* that convention. **Do NOT bump the
  `n=5` citation count** in `agents.md`'s emit-when-non-none block, and do NOT add `thinking`
  to the tripwire's expected-key list.
- **DD2 (no `StreamChunk` field).** Capture is from the final message (Leg 02), so no
  intermediate chunk carries thinking. `StreamChunk` is **not** touched in this leg.
- **Provider-agnostic.** Nothing enables or populates thinking yet — Leg 02 (Anthropic
  capture) is the first producer. This leg is pure protocol + codec + tests.
- The `Message.content`-is-always-`str` convention (`base.py:121–137` `__post_init__`
  str-assert) is **untouched** — `thinking` is a new field, not a widening of `content`.

## Inputs

What exists before this leg runs:
- `the_one/llm/base.py` — `Message` dataclass (`base.py:64–119`, fields end at
  `channel_name`); `ToolCall` (`base.py:21–25`); `field` already imported (`base.py:7`).
- `the_one/db/codec.py` — `message_to_dict` (`codec.py:71–102`, `tool_calls` emit at
  `:74`), `message_from_dict` (`codec.py:105–141`), `_tool_call_to_dict`
  (`codec.py:50–51`, the serializer template).
- `tests/test_db_codec.py` — `TestMessagePeerNameCodec` (`:479–533`, the round-trip test
  template) and the byte-identity tripwire
  `test_encode_emits_no_keys_when_all_optional_fields_default` (`:655–676`).
- Full test suite green at flight start.

## Outputs

What exists after this leg completes:
- `the_one/llm/base.py` — a new `ThinkingBlock` dataclass and a `thinking:
  list[ThinkingBlock] = field(default_factory=list)` field on `Message`; `Message.assistant`
  threads an optional `thinking` kwarg (mirrors how it threads `tool_calls`).
- `the_one/db/codec.py` — `_thinking_block_to_dict` / `_thinking_block_from_dict`
  serializers; `thinking` emitted (truthy guard) in `message_to_dict` and read
  (`d.get("thinking", [])`) in `message_from_dict`.
- `tests/test_db_codec.py` — a new `TestMessageThinkingCodec` class covering round-trip,
  back-compat (legacy rows → empty list), signature preservation, redacted-block round-trip,
  and an explicit assertion that the tripwire stays green (empty `thinking` not emitted).

## Acceptance Criteria

- [x] A `ThinkingBlock` dataclass exists in `the_one/llm/base.py` representing both Anthropic
      variants: `type="thinking"` (carries `thinking: str | None`, `signature: str | None`)
      and `type="redacted_thinking"` (carries `data: str | None`). Fields other than `type`
      default to `None`.
- [x] `Message` has a `thinking: list[ThinkingBlock] = field(default_factory=list)` field,
      declared alongside `tool_calls` (a structural sibling — truthy-guarded list, NOT an
      `is not None` optional).
- [x] `Message.assistant(...)` accepts an optional `thinking` kwarg and threads it into the
      constructor (mirroring `tool_calls or []`), so Leg 02 can synthesize a thinking-bearing
      assistant `Message` via the factory. Default (no kwarg) → empty list.
- [x] `message_to_dict` emits `"thinking"` **only when the list is non-empty** (`if
      msg.thinking:`), as a list of block dicts. Each block dict carries `type` plus only its
      set sub-keys (`thinking`/`signature` for thinking blocks, `data` for redacted) — i.e.
      the stored shape equals the Anthropic content-block shape, so Leg 03 replay can hand it
      back with no re-mapping.
- [x] `message_from_dict` reads `d.get("thinking", [])` and reconstructs `ThinkingBlock`s;
      signatures and `data` survive the round-trip verbatim.
- [x] A single `Message` carrying `content` + `thinking` + `tool_calls` simultaneously (the
      criterion-#1 turn shape) round-trips all three independently — each field emits on its
      own guard with no cross-interference.
- [x] The byte-identity tripwire `test_encode_emits_no_keys_when_all_optional_fields_default`
      (`test_db_codec.py:655–676`) **passes UNCHANGED** — `Message.user("hi")` still encodes
      to exactly `["content", "role"]` (an empty `thinking` list is not emitted). The test is
      NOT edited; its expected-key list is NOT extended.
- [x] The `agents.md` `message-additive-back-compat-via-emit-when-non-none` `n=5` citation
      count is **NOT** bumped (this field is outside that convention). No `agents.md` edit is
      required in this leg (the thinking-field convention is documented in Leg 06).
- [x] `StreamChunk` (`the_one/llm/base.py`) is unchanged — no `thinking` field added to it.
- [x] New `TestMessageThinkingCodec` tests pass and the full codec suite is green; no existing
      codec test regresses.

## Verification Steps

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_db_codec.py -x --timeout 30`
  — the new `TestMessageThinkingCodec` passes AND
  `test_encode_emits_no_keys_when_all_optional_fields_default` passes unchanged.
- `git diff tests/test_db_codec.py` — confirm the tripwire test body is untouched (only a new
  test class was added).
- `git diff the_one/agents.md` — confirm empty (no citation-count bump this leg).
- `grep -n "thinking" the_one/llm/base.py` — confirm `StreamChunk` has no thinking field
  (only `Message` + the new `ThinkingBlock`).
- Round-trip a redacted block manually or via test:
  `decode_messages(encode_messages([Message.assistant("hi", thinking=[ThinkingBlock(type="redacted_thinking", data="abc")])]))`
  preserves `data="abc"`.

## Implementation Guidance

1. **Add the `ThinkingBlock` dataclass** in `the_one/llm/base.py`, near `ToolCall`
   (`base.py:21–25`). Discriminated by a `type: str` field; variant-specific fields default
   to `None`:

   ```python
   @dataclass
   class ThinkingBlock:
       """A single extended-thinking block from a provider response.

       Mirrors Anthropic's two content-block variants (anthropic SDK 0.79.0):
         - type="thinking": `thinking` (reasoning text) + `signature` (opaque,
           server-issued; MUST be replayed verbatim or the follow-up turn 400s).
         - type="redacted_thinking": `data` (opaque; no text).
       Provider-agnostic — Ollama/OpenAI adapters may populate this later (DD5).
       """
       type: str
       thinking: str | None = None
       signature: str | None = None
       data: str | None = None
   ```

2. **Add the field to `Message`** alongside `tool_calls` (`base.py:68`), NOT among the
   `is not None` optionals:

   ```python
   thinking: list[ThinkingBlock] = field(default_factory=list)
   ```

   Place it directly after `tool_calls` so the structural sibling relationship is visible in
   the source. Add a short comment citing DD1/DD2: structured (carries signatures), truthy
   emit guard like `tool_calls`, outside the emit-when-non-none convention.

3. **Thread it into `Message.assistant`** (`base.py:162–177`) as an optional kwarg, mirroring
   `tool_calls`:

   ```python
   @classmethod
   def assistant(
       cls,
       content: str,
       tool_calls: list[ToolCall] | None = None,
       usage: TokenUsage | None = None,
       *,
       visibility: str | None = None,
       thinking: list[ThinkingBlock] | None = None,
   ) -> Message:
       return cls(
           role=Role.ASSISTANT,
           content=content,
           tool_calls=tool_calls or [],
           usage=usage,
           visibility=visibility,
           thinking=thinking or [],
       )
   ```

4. **Add codec serializers** in `the_one/db/codec.py`, next to `_tool_call_to_dict`
   (`codec.py:50–51`). Emit only set sub-keys so the stored dict equals the API block shape:

   ```python
   def _thinking_block_to_dict(tb: ThinkingBlock) -> dict[str, Any]:
       # Two-level guard (do NOT "harmonize"): the FIELD-level emit in
       # message_to_dict uses a TRUTHY guard (`if msg.thinking:`) to keep the
       # byte-identity tripwire green (empty list → no key). The SUB-KEY guards
       # here use `is not None` so a legitimately-empty-but-present value (e.g. an
       # empty-string signature) round-trips verbatim and the stored dict equals
       # the Anthropic content-block shape for Leg 03 replay. Flattening either
       # guard breaks one of those two invariants.
       d: dict[str, Any] = {"type": tb.type}
       if tb.thinking is not None:
           d["thinking"] = tb.thinking
       if tb.signature is not None:
           d["signature"] = tb.signature
       if tb.data is not None:
           d["data"] = tb.data
       return d

   def _thinking_block_from_dict(d: dict[str, Any]) -> ThinkingBlock:
       return ThinkingBlock(
           type=d["type"],
           thinking=d.get("thinking"),
           signature=d.get("signature"),
           data=d.get("data"),
       )
   ```

   Import `ThinkingBlock` from `the_one.llm.base` (extend the existing import at
   `codec.py:9`).

5. **Emit in `message_to_dict`** (`codec.py:71–102`) with the **truthy** guard, modeled on the
   `tool_calls` emit at `codec.py:74` — NOT the `is not None` blocks below it:

   ```python
   if msg.thinking:
       d["thinking"] = [_thinking_block_to_dict(tb) for tb in msg.thinking]
   ```

   Put it adjacent to the `tool_calls` emit so the sibling pattern is obvious.

6. **Read in `message_from_dict`** (`codec.py:105–141`), modeled on the `tool_calls`
   reconstruction at `codec.py:107–110`:

   ```python
   thinking = [_thinking_block_from_dict(tb) for tb in d.get("thinking", [])]
   ```

   and pass `thinking=thinking` to the `Message(...)` constructor.

7. **Add `TestMessageThinkingCodec`** in `tests/test_db_codec.py`, modeled on
   `TestMessagePeerNameCodec` (`:479–533`). Cover, at minimum:
   - emit-when-non-empty: a message with one thinking block encodes a `"thinking"` key;
   - omit-when-empty: `Message.assistant("hi")` (empty thinking) has no `"thinking"` key;
   - signature preservation: round-trip a `type="thinking"` block with `thinking` +
     `signature` and assert both survive verbatim;
   - redacted round-trip: a `type="redacted_thinking"` block preserves `data` and leaves
     `thinking`/`signature` at `None`;
   - back-compat: `message_from_dict({"role": "assistant", "content": "hi"})` yields
     `thinking == []` (legacy rows have no key);
   - full `decode_messages(encode_messages(...))` round-trip through the list codec;
   - **mixed content** (the criterion-#1 turn shape): a single `Message` carrying `content`
     + `thinking` + `tool_calls` simultaneously round-trips all three, each emitting on its
     own independent guard — none interferes with another (template:
     `TestMessagePeerNameCodec::test_round_trip_with_peer_name_and_visibility` at
     `test_db_codec.py:525–533`);
   - **unknown-future-type forward-compat**: a block with an unrecognized `type` (e.g.
     `type="some_future_kind"` plus arbitrary set sub-fields) round-trips its `type` + set
     sub-fields without dropping — locks in the free-`str` `type` property;
   - a guard test asserting the tripwire's invariant still holds for a thinking-bearing
     message class (belt-and-suspenders; the real tripwire at `:655–676` stays untouched).

8. **Do NOT** touch `agents.md`, `StreamChunk`, the `__post_init__` str-assert, or the
   tripwire test body. Run the full unit suite once at leg end
   (`make test-unit` or the codec file plus a broad pass) to confirm no cross-suite regression.

## Edge Cases

- **Empty list vs. `None`.** The field default is `[]` (never `None`). The truthy guard
  `if msg.thinking:` treats empty-list and (defensively) `None` alike as "omit" — but the
  dataclass default guarantees a list, so downstream consumers can iterate without a `None`
  check, exactly like `tool_calls`.
- **Redacted block has no text/signature.** `type="redacted_thinking"` carries only `data`;
  `thinking` and `signature` stay `None` and are omitted from the stored dict. Replay (Leg 03)
  must send it back as `{"type": "redacted_thinking", "data": ...}` — the stored shape already
  matches.
- **Unknown future block type.** `type` is a free `str`, not an enum — an unrecognized type
  round-trips its `type` + whatever sub-fields are set, so a future provider variant doesn't
  silently drop. Leg 02/03 decide which types they produce/replay.
- **Mixed content.** A message may carry `content` (answer text) AND `thinking` AND
  `tool_calls` simultaneously (the criterion-#1 turn). The three fields are independent; the
  codec emits each on its own guard.

## Files Affected

- `the_one/llm/base.py` — new `ThinkingBlock` dataclass; `Message.thinking` field;
  `Message.assistant` thinking kwarg.
- `the_one/db/codec.py` — `_thinking_block_to_dict` / `_thinking_block_from_dict`; emit +
  read in `message_to_dict` / `message_from_dict`; extend the `base` import.
- `tests/test_db_codec.py` — new `TestMessageThinkingCodec` class (additive; no existing test
  edited).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (new codec tests + full unit suite green; tripwire unchanged)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] If final leg of flight: (N/A — Leg 01 of 6)
- [ ] Commit — deferred to Phase 2d flight review per `/agentic-workflow` (do NOT commit
      per-leg on this flight)
