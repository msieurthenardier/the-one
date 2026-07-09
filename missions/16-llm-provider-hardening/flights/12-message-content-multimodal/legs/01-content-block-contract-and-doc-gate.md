# Leg: content-block-contract-and-doc-gate

**Status**: landed
**Flight**: [Multimodal Message.content (A2)](../flight.md)

## Objective

Land the canonical provider-neutral content-block union (`TextContent` +
`ImageContent`), widen `Message.content` (and the `Message.user()` factory) to
`str | list[ContentBlock]` behind a conditional assert, make
`build_user_message_content` shape-aware, and record the per-provider image
wire-format premise — with the `str` path byte-identical and **no** provider request
path or codec touched.

## Context

- **Foundational leg**: L02 (codec), L03 (consumers), L04–L06 (provider projection),
  L07 (conformance) all depend on this contract. Nothing produces `list` content yet
  (recon: zero ingestion producers), so widening the type + assert cannot break any
  runtime path — the `str`-assuming consumers (L03) and codec (L02) are hardened
  before any producer (optional L08) exists.
- **Mirror the `ThinkingBlock` precedent** (`base.py`): a provider-neutral dataclass
  the codec serializes and each provider maps to native. `Message.thinking:
  list[ThinkingBlock]` (`base.py:98`) is the exact structural template.
- **DD2**: canonical union — **`TextContent`** (load-bearing: content is `str` XOR
  `list`, so a user's typed text becomes a block when an image is present) +
  **`ImageContent`**. Not raw dicts (keeps the `provider-shape-portability`
  invariant).
- **DD3**: `list` content is legitimate **only on `Role.USER`** — the assert
  enforces it.
- **DD4**: `build_user_message_content` becomes shape-aware; for `list` input it
  returns the list with a **separate prepended `TextContent`** carrying the
  peer/channel prefix (not merged into the user's text block).
- **DD5 doc-gate** (F10-Rec-1 / A4-DD4 pattern): pin each provider's accepted image
  wire shape + base64/URL support before any wiring (L04–L06 depend on it).

## Inputs

- `the_one/llm/base.py`: `ThinkingBlock` (dataclass precedent); `Message` dataclass
  (`content: str = ""` at `:84`); `__post_init__` assert (`:151-167`); the
  `Message.user()` factory (`:173-190`); `build_user_message_content` (`:221-257`).
- `the_one/agents.md`: the `provider-shape-portability` convention (the "assert
  content is str" invariant this leg makes conditional).
- Pinned SDK stubs (`.venv/…/anthropic` 0.97.0, `openai` 2.33.0) — the doc-gate
  authority for image wire shapes (recon already located them).

## Outputs

- `the_one/llm/base.py` — `TextContent` + `ImageContent` dataclasses + a
  `ContentBlock` type alias; `Message.content` + `Message.user()` widened;
  conditional assert; shape-aware `build_user_message_content`.
- `the_one/agents.md` — `provider-shape-portability` convention updated (assert now
  conditional; canonical `ContentBlock`).
- **flight-log.md** — a recorded `## Wire-Format Premise` (image shapes per provider).
- `tests/test_llm_base.py` (or a focused sibling) — contract + helper unit tests.
- **No** provider request path, **no** codec change (those are L04–L06 / L02).

## Acceptance Criteria

- [x] **`TextContent` + `ImageContent` dataclasses** exist in `base.py`, mirroring
      `ThinkingBlock`: `TextContent(text: str)`; `ImageContent(media_type: str,
      data: str | None = None, url: str | None = None)` with a light `__post_init__`
      guard that at least one of `data`/`url` is set. A `ContentBlock = TextContent
      | ImageContent` type alias is defined. (Import from `base` per the
      `ThinkingBlock` precedent — not added to `llm/__init__.py.__all__` unless the
      reviewer prefers.)
- [x] **`Message.content` widened** to `str | list[ContentBlock]` (default `""`);
      **`Message.user()` factory** `content` param widened to `str |
      list[ContentBlock]`. SYSTEM/ASSISTANT/TOOL factories stay `str` (DD3).
- [x] **Conditional assert** in `Message.__post_init__`: `str` content passes; a
      `list` of `ContentBlock`s passes **only when `role == Role.USER`** (DD3); a
      bare non-str/non-list, or a list containing a non-`ContentBlock`, or `list`
      content on a non-USER role, still raises `AssertionError` with a clear message.
- [x] **`build_user_message_content` shape-aware** (DD4): `str` content → **exactly
      today's behavior** (native-ready `str` with the peer/channel bracket prefix,
      byte-identical); `list[ContentBlock]` content → returns the `list` with a
      **separate prepended `TextContent`** carrying the same bracket prefix **iff**
      peer/channel are set (no prefix block when neither is set); return type
      `str | list[ContentBlock]`. Non-USER role → returns `msg.content` unchanged
      (existing safety branch).
- [x] **`str` path byte-identical**: every existing `str`-content behavior (assert,
      factory, helper output) is unchanged — existing tests pass unmodified; no
      persisted-session migration (legacy `str` rows still decode + assert clean).
- [x] **Wire-Format Premise recorded** in flight-log.md: per provider (Anthropic /
      OpenAI / OpenRouter / Ollama `/v1` + native) the accepted **image** wire shape
      + base64-vs-URL support + per-model acceptance, cited to the pinned SDK stubs
      and/or first-party docs. Anything unverifiable flagged **HAT-confirm**. This is
      the L04–L06 gate; no provider is wired on an assumed shape.
- [x] **`agents.md` convention updated**: `provider-shape-portability` reflects that
      `Message.content` is `str | list[ContentBlock]`, the assert is conditional
      (str, or USER-only block list), and `ContentBlock` is the canonical
      provider-neutral type each provider maps to native.
- [x] **No provider request path or codec touched** — `git diff --stat` shows only
      `base.py`, `agents.md`, the test file, and flight artifacts.
- [x] Targeted tests green: `PYTHON=.venv/bin/python bash scripts/run-tests.sh
      tests/test_llm_base.py -x --timeout 30` (+ the block-contract tests).

## Verification Steps

- Run `tests/test_llm_base.py` (+ new tests) — green, incl. assert-rejects cases and
  the `build_user_message_content` str-byte-identical + list-prefix-block cases.
- `git diff --stat` — only `base.py`, `agents.md`, test file, flight artifacts.
- Read the flight-log Wire-Format Premise — every provider×image cell has a cited
  shape or a HAT-confirm flag.
- `grep -n "ContentBlock\|TextContent\|ImageContent" the_one/llm/base.py` — types present.

## Implementation Guidance

1. **Doc-gate first** (record before code): from the pinned SDK stubs, confirm the
   image wire shapes (recon located them): Anthropic `ImageBlockParam`
   (`source: base64 {media_type,data} | url {url}`); OpenAI
   `ChatCompletionContentPartImageParam` (`{type:"image_url", image_url:{url}}`,
   base64 data-URL or URL); Ollama native message-level `images:[base64]`, `/v1`
   base64 `image_url` (no remote URL). Record per-model acceptance from first-party
   docs; flag HAT-confirm where docs don't settle it. Append `## Wire-Format Premise`
   to flight-log.md.
2. **Content-block types** (in `base.py`, near `ThinkingBlock`):
   ```python
   @dataclass
   class TextContent:
       text: str

   @dataclass
   class ImageContent:
       media_type: str            # e.g. "image/png", "image/jpeg"
       data: str | None = None    # base64 (universal path)
       url: str | None = None     # native on Anthropic/OpenAI; Ollama = documented gap (DD5)
       def __post_init__(self) -> None:
           assert self.data is not None or self.url is not None, (
               "ImageContent requires one of data (base64) or url"
           )

   ContentBlock = TextContent | ImageContent
   ```
   (Match the module's dataclass style. Keep fields simple/JSON-friendly for L02.)
3. **Widen `Message.content`** → `str | list[ContentBlock] = ""` and the
   `Message.user()` `content` param → `str | list[ContentBlock]`.
4. **Conditional assert** — replace the unconditional str-assert. **Use explicit
   `raise` for BOTH invalid cases** (not a plain `assert` for the role guard — the
   reviewer's [medium]: a plain `assert` is stripped under `python -O`, so a
   non-USER block-list would silently pass; the invariant must always hold):
   ```python
   c = self.content
   if isinstance(c, str):
       pass
   elif isinstance(c, list) and all(isinstance(b, (TextContent, ImageContent)) for b in c):
       if self.role != Role.USER:
           raise AssertionError(
               f"list[ContentBlock] content is only valid on USER messages, got {self.role}"
           )
   else:
       raise AssertionError(
           f"Message.content must be str or list[ContentBlock], got {type(c).__name__}"
       )
   ```
   Keep the docstring; note the widening + the DD3 USER-only rule + the
   `agents.md` pointer. *(This makes the whole invariant `-O`-robust — a slight
   strengthening over the old plain `assert isinstance`, and correct.)*
5. **`build_user_message_content`** — hoist the peer/ch lookups once, then add a
   `list` branch BEFORE the str prefix logic. When no prefix applies, return a
   **copy** (`list(msg.content)`) — not the same reference — so a downstream provider
   (L04–L06) can't mutate the caller's list (the str path is aliasing-immune; the
   list path must be too):
   ```python
   if msg.role != Role.USER:
       return msg.content
   peer, ch = msg.peer_name, msg.channel_name
   if isinstance(msg.content, list):
       prefix = None
       if peer is not None and ch is not None:
           prefix = f"[from {peer} in #{ch}]:"
       elif peer is not None:
           prefix = f"[from {peer}]:"
       elif ch is not None:
           prefix = f"[in #{ch}]:"
       return [TextContent(text=prefix), *msg.content] if prefix else list(msg.content)
   # ... existing str prefix logic below, now using the hoisted peer/ch ...
   ```
   Update the return annotation to `str | list[ContentBlock]` and the docstring.
6. **`agents.md`** — update the `provider-shape-portability` convention prose (assert
   now conditional; `str | list[ContentBlock]`; USER-only block list; `ContentBlock`
   canonical). Do not restructure other content.
7. **Tests** (`tests/test_llm_base.py` or sibling): block construction (incl.
   ImageContent one-of-data/url guard); `Message.user([...])` accepts a block list;
   assert accepts str + USER block-list, rejects non-USER block-list + list-of-junk +
   non-str-non-list; `build_user_message_content` str output byte-identical to today
   (all four peer/ch combos) + list output prepends the prefix `TextContent` (and
   omits it when neither peer nor ch set). No provider construction, no persistence.

## Edge Cases

- **`list` content on SYSTEM/ASSISTANT/TOOL** → assert raises (DD3). Tested.
- **Empty `list` content** (`[]`) on USER → **allowed by design** (passes the assert
  vacuously). Rationale (resolves the review's question): the assert validates
  *shape + role*, not content *semantics* — exactly as bare `""` str content is
  allowed today; forbidding `[]` would special-case the contract for no real gain
  (no producer emits `[]`; L08's producer always includes at least the user's text
  block). Lenient-by-design, mirroring the empty-str precedent.
  `build_user_message_content` returns `[]` or `[prefix]`. Tested.
- **`ImageContent` with both `data` and `url`** → allowed (guard is "at least one");
  provider mapping prefers `data` (base64 universal) — documented, decided in L04–L06.
- **Codec/persistence of `list` content** → NOT handled here (L02). L01 tests never
  persist list content; str persistence is unchanged.
- **Anti-pattern to avoid** (F10 Rec 5): do NOT hardcode a block `type` string filter
  anywhere — dispatch by `isinstance`, so a future block type doesn't silently
  vanish (the `thinking_display_text` `type=="thinking"` trap).

## Files Affected

- `the_one/llm/base.py` — content-block types; widened `Message.content` + `user()`;
  conditional assert; shape-aware `build_user_message_content`.
- `the_one/agents.md` — `provider-shape-portability` convention update.
- `tests/test_llm_base.py` (or sibling) — contract + helper tests.
- flight-log.md — `## Wire-Format Premise`.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (`tests/test_llm_base.py` + new)
- [x] Update flight-log.md (Leg Progress entry + Wire-Format Premise)
- [x] Set this leg's status to `landed` (in this file's header) — per the
      Developer role's batch-commit instructions, `landed` not `completed`;
      `completed` is reserved for the batch-review/commit pass after L07
- [ ] Check off this leg in flight.md — deferred per the Flight Director's
      batch-commit instructions (not done at individual-leg end)
- [ ] (Not final leg — no flight/mission status change)
- [x] Changes stay uncommitted — batch commit after L07 (do NOT commit at leg end)
