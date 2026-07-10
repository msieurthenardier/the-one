# Leg: codec-content-round-trip

**Status**: landed
**Flight**: [Multimodal Message.content (A2)](../flight.md)

## Objective

Make `list[ContentBlock]` message content round-trip the persistence codec — add a
`_content_block_to_dict`/`_from_dict` pair and wire it into
`message_to_dict`/`message_from_dict` — mirroring the `ThinkingBlock` codec
precedent, with the `str`-content path byte-identical.

## Context

- **Depends on L01** (landed): `TextContent`/`ImageContent`/`ContentBlock` in
  `base.py`. Nothing produces `list` content at runtime yet (recon: zero producers),
  so this leg is proven hermetically by constructing list-content `Message`s in tests
  and round-tripping them.
- **The DD2 fork**: dataclass content blocks are NOT JSON-serializable, so the codec's
  opaque `content` passthrough breaks on a list (`json.dumps(ContentBlock)` →
  `TypeError`). This leg is exactly the codec cost DD2 accepted (vs raw dicts, which
  would have round-tripped free). Small and well-precedented.
- **Precedent — encode mirrors, decode deliberately departs.** The **encode** side
  mirrors `_thinking_block_to_dict` (`codec.py:61`) — non-None field emission.
  The **decode** side does **not** mirror `_thinking_block_from_dict` (`:79`), which
  is *permissive* (constructs `ThinkingBlock(type=d["type"], …)` for ANY type, so an
  unknown thinking type round-trips — `test_db_codec.py::test_unknown_future_type_round_trips`).
  `_content_block_from_dict` instead **raises on an unknown type** — a deliberate,
  stricter departure: content blocks are **user data** selecting between **distinct
  dataclasses** with no safe default target, so silently dropping one loses input
  (worse than a display-only thinking type). `message_to_dict` emits content opaquely
  at `:107`; `message_from_dict` decodes at `:173`.
- **Anti-pattern to avoid** (F10 Rec 5, the `thinking_display_text:208` *filter*):
  never silently drop an unrecognized block — hence the raise above.
- **UI-events deferral has an expiry (tracked).** `messages_to_ui_events`
  (`codec.py:298-309`, USER branch) passes `msg.content` into the event `"content"`
  opaquely — a list would flow through unmodified. **Safe this flight only because
  there is no producer** (recon: zero). The moment a producer ships (L08), that path
  breaks — so **hardening `messages_to_ui_events` is a prerequisite of L08 / the
  frontend follow-up**, now recorded in the flight's Out-of-Scope. L02 itself leaves
  it untouched (correctly), but flags the expiry.

## Inputs

- `the_one/llm/base.py` — `TextContent`/`ImageContent`/`ContentBlock` (L01).
- `the_one/db/codec.py` — `_thinking_block_to_dict`/`_from_dict`, `message_to_dict`
  (`:105`), `message_from_dict` (`:146`), `encode_messages`/`decode_messages`.
- The existing codec tests (the file that round-trips `Message`/`ThinkingBlock` — the
  implementer locates it; mirror its idiom).

## Outputs

- `the_one/db/codec.py` — `_content_block_to_dict`/`_content_block_from_dict` +
  content-aware `message_to_dict`/`message_from_dict`.
- Codec tests — structured-content round-trip.
- **No** `base.py`/provider/consumer change; the **UI-events projection**
  (`messages_to_ui_events`, `:302`) is **out of scope** (frontend rendering of list
  content is the deferred L08 follow-up — no producer feeds it this flight).

## Acceptance Criteria

- [x] **`_content_block_to_dict(block) -> dict`** dispatches by `isinstance`:
      `TextContent` → `{"type":"text","text":...}`; `ImageContent` →
      `{"type":"image","media_type":...}` plus `data` and/or `url` **only when
      non-None** (mirrors `_thinking_block_to_dict`'s non-None field emission).
- [x] **`_content_block_from_dict(d) -> ContentBlock`** reads `d["type"]`: `"text"` →
      `TextContent`; `"image"` → `ImageContent(media_type, data=d.get("data"),
      url=d.get("url"))`; **an unknown `type` raises** (ValueError/KeyError — NOT a
      silent skip; F10 Rec 5).
- [x] **`message_to_dict` content-aware**: `str` content emitted unchanged
      (byte-identical); `list` content → `[_content_block_to_dict(b) for b in
      content]`.
- [x] **`message_from_dict` content-aware**: a `str` decoded value → `str`
      (unchanged); a `list` decoded value → `[_content_block_from_dict(b) for b in
      raw]`. Legacy rows (str content, no blocks) decode byte-identically.
- [x] **Round-trip tests**: a USER `Message` with `[TextContent, ImageContent(data=…),
      ImageContent(url=…)]` content survives `message_to_dict` → `json.dumps` →
      `json.loads` → `message_from_dict` **equal** to the original; a `str`-content
      message round-trips byte-identically (existing behavior); an unknown block
      `type` on decode raises; a legacy dict with plain `str` content decodes.
- [x] **`str` path byte-identical**; existing codec tests pass unmodified; no
      persisted-session migration.
- [x] **Scope**: `git diff --stat` shows only `codec.py` + the codec test file (+
      flight artifacts). `messages_to_ui_events` untouched (deferred).
- [x] Targeted tests green: `PYTHON=.venv/bin/python bash scripts/run-tests.sh
      <codec-test-file> -x --timeout 30`.

## Verification Steps

- Run the codec test file — green, incl. the list-content round-trip + unknown-type-raises + legacy-str cases.
- `git diff --stat` — only `codec.py` + codec test file (+ flight artifacts).
- Read the `message_to_dict`/`message_from_dict` diffs — confirm the `str` branch is untouched and the `list` branch is additive.

## Implementation Guidance

1. **`_content_block_to_dict`/`_from_dict`** next to `_thinking_block_to_dict`
   (`codec.py:61-84`), same style:
   ```python
   def _content_block_to_dict(b: ContentBlock) -> dict[str, Any]:
       if isinstance(b, TextContent):
           return {"type": "text", "text": b.text}
       d: dict[str, Any] = {"type": "image", "media_type": b.media_type}
       if b.data is not None:
           d["data"] = b.data
       if b.url is not None:
           d["url"] = b.url
       return d

   def _content_block_from_dict(d: dict[str, Any]) -> ContentBlock:
       t = d.get("type")
       if t == "text":
           return TextContent(text=d["text"])
       if t == "image":
           return ImageContent(media_type=d["media_type"], data=d.get("data"), url=d.get("url"))
       raise ValueError(f"unknown content block type: {t!r}")   # do NOT silently skip (F10 Rec 5)
   ```
   Import `TextContent`/`ImageContent`/`ContentBlock` from `the_one.llm.base`.
2. **`message_to_dict`** (`:107`): replace `"content": msg.content` with
   `"content": ([_content_block_to_dict(b) for b in msg.content]
   if isinstance(msg.content, list) else msg.content)`.
3. **`message_from_dict`** (`:173`): `raw = d.get("content", "")`;
   `content = [_content_block_from_dict(b) for b in raw] if isinstance(raw, list)
   else raw`; pass `content=content`.
4. **Tests** (`tests/test_db_codec.py`): add a `TestContentBlockCodec` class mirroring
   `TestMessageThinkingCodec` (`:787-908`) — its idiom: encode-only assertions via
   `message_to_dict`, decode via `decode_messages(encode_messages(...))`, a
   dedicated unknown-type case, a legacy back-compat case, a mixed-field case. Cover:
   list-content USER message equality round-trip (all three block shapes:
   `TextContent`, `ImageContent(data=…)`, `ImageContent(url=…)`), str byte-identical,
   unknown-type **raises**, legacy-str decodes. Plus one test that a persisted
   list-content dict on a **non-USER** role raises via `Message.__post_init__`'s
   role-guard on decode (documents that the codec relies on the dataclass invariant,
   not its own role check).
5. Do **not** touch `messages_to_ui_events` / provider paths / `base.py`.

## Edge Cases

- **`str` content with a `list`-looking value?** No — `str` and `list` are distinct
  `isinstance` branches; a JSON string decodes to `str`, a JSON array to `list`. No
  ambiguity.
- **Empty list content** (`[]`) → encodes to `[]`, decodes to `[]` — round-trips
  (matches L01's lenient empty-list).
- **`ImageContent` with both data+url** → both emitted, both decoded — round-trips.
- **Unknown block type on decode** → raises (a corrupt/forward-version row surfaces
  loudly rather than silently dropping content).

## Files Affected

- `the_one/db/codec.py` — content-block encoder/decoder + content-aware
  `message_to_dict`/`message_from_dict`.
- The codec test file — round-trip tests.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (codec test file)
- [x] Update flight-log.md with a Leg Progress entry
- [x] Set this leg's status to `landed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] (Not final leg — no flight/mission status change)
- [x] Changes stay uncommitted — batch commit after L07 (do NOT commit at leg end)
