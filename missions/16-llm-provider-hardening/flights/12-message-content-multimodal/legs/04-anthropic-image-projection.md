# Leg: anthropic-image-projection

**Status**: landed
**Flight**: [Multimodal Message.content (A2)](../flight.md)

## Objective

Fork the Anthropic `_to_api_message` USER-turn projection into a content-list path:
when `build_user_message_content` returns `list[ContentBlock]`, map each block to
Anthropic's native content-block shape (`{type:text}` / `{type:image, source:…}`),
mirroring the list-of-blocks shape the ASSISTANT branch already builds — with the
`str` path byte-identical.

## Context

- **Depends on L01** (types + shape-aware `build_user_message_content`) and follows
  L02/L03 (landed). Provider legs L04–L06 are independent; OpenRouter inherits L05.
- **The projection site** — `anthropic_provider.py::_to_api_message`, the USER/SYSTEM
  fallthrough (`:508`): `return {"role": msg.role.value, "content":
  build_user_message_content(msg)}`. `build_user_message_content` now returns
  `str | list[ContentBlock]` (L01/DD4) — for `list` it already prepends the DD4
  prefix `TextContent`. So the fork is: `str` → today's behavior; `list` → map every
  block (prefix + user text + images) to native Anthropic blocks.
- **Target shape already exists** — the ASSISTANT branch (`:482-498`) builds
  `content: list[dict]` with `{type:text}`/`{type:tool_use}` blocks. The USER image
  path is the same list-of-blocks idea with `{type:image, source:…}` added.
- **Supersede the forward-comment** (`:503-507`): it said a future multimodal branch
  "would NOT call `build_user_message_content`." DD4 reverses that — the helper is now
  shape-aware and IS called; update/remove the comment.
- **Wire shape (L01 doc-gate premise)**: Anthropic image block =
  `{"type":"image","source": {"type":"base64","media_type":…,"data":…}}` **or**
  `{"type":"image","source":{"type":"url","url":…}}`. Prefer **base64** when both are
  present (DD5 universal path).
- **DD3**: only USER carries list content; SYSTEM (str-only, extracted to the `system`
  param elsewhere) and ASSISTANT/TOOL are unaffected.

## Inputs

- `the_one/llm/base.py` — `TextContent`/`ImageContent`/`ContentBlock`,
  `build_user_message_content` (L01).
- `the_one/llm/anthropic_provider.py` — `_to_api_message` (`:463`), the fallthrough
  (`:508`), the ASSISTANT list-of-blocks branch (`:482-498`, style reference).
- flight-log `## Wire-Format Premise` (the image shape).

## Outputs

- `the_one/llm/anthropic_provider.py` — a `_content_block_to_api` mapper + the
  forked fallthrough; the superseded forward-comment updated.
- `tests/test_anthropic_provider.py` — image-projection fixtured tests.

## Acceptance Criteria

- [x] **`_content_block_to_api(block) -> dict`** (on `AnthropicProvider`): `TextContent`
      → `{"type":"text","text":block.text}`; `ImageContent` → `{"type":"image",
      "source": {"type":"base64","media_type":…,"data":…}}` when `data` is set
      (preferred), else `{"type":"image","source":{"type":"url","url":…}}`.
- [x] **Fallthrough forked**: `projected = build_user_message_content(msg)`; when
      `isinstance(projected, list)` → `{"role": msg.role.value, "content":
      [self._content_block_to_api(b) for b in projected]}`; else the existing
      `{"role": msg.role.value, "content": projected}` (str). **str path
      byte-identical**.
- [x] **Prefix block mapped natively**: with `peer_name`/`channel_name` set on a
      list-content USER message, the projected `content` begins with a
      `{"type":"text","text":"[from …]:"}` block (the DD4 prefix `TextContent` → native
      text block), followed by the user's own blocks.
- [x] **base64 preferred over url** when an `ImageContent` carries both (DD5).
- [x] **Forward-comment updated** (`:503-507`): reflect that
      `build_user_message_content` is now shape-aware and the multimodal branch maps
      its list output (no longer "would NOT call" it).
- [x] **No other provider / codec / base.py change**; `git diff --stat` shows only
      `anthropic_provider.py` + `tests/test_anthropic_provider.py` (+ flight artifacts).
- [x] Targeted tests green: `PYTHON=.venv/bin/python bash scripts/run-tests.sh
      tests/test_anthropic_provider.py -x --timeout 30`.

## Verification Steps

- Run `tests/test_anthropic_provider.py` — green, incl. image-projection + str-byte-identical + prefix-block cases.
- Read the `_to_api_message` diff — confirm the str branch is untouched and the list branch is additive.
- `git diff --stat` — only `anthropic_provider.py` + its test file (+ flight artifacts).

## Implementation Guidance

1. **`_content_block_to_api`** on `AnthropicProvider` (near `_to_api_message`):
   ```python
   def _content_block_to_api(self, b: ContentBlock) -> dict[str, Any]:
       if isinstance(b, TextContent):
           return {"type": "text", "text": b.text}
       # ImageContent — base64 preferred (DD5 universal path)
       if b.data is not None:
           source = {"type": "base64", "media_type": b.media_type, "data": b.data}
       else:
           source = {"type": "url", "url": b.url}
       return {"type": "image", "source": source}
   ```
   Import `ContentBlock`/`TextContent`/`ImageContent` from `the_one.llm.base`.
2. **Fork the fallthrough** (`:508`):
   ```python
   projected = build_user_message_content(msg)
   if isinstance(projected, list):
       return {"role": msg.role.value, "content": [self._content_block_to_api(b) for b in projected]}
   return {"role": msg.role.value, "content": projected}
   ```
3. **Update the forward-comment** (`:503-507`) to reflect DD4 (helper is shape-aware;
   the multimodal branch maps its list output).
4. **Tests** (`tests/test_anthropic_provider.py`, near the existing `_to_api_message`/
   `_build_kwargs` tests): construct `AnthropicProvider(model="claude-test",
   api_key="x")`; call `prov._to_api_message(Message.user([TextContent("hi"),
   ImageContent(media_type="image/png", data="BASE64"), ImageContent(
   media_type="image/jpeg", url="https://x/y.jpg")]))` and assert the native block
   list; a base64-preferred-over-both case; the prefix-block case
   (`Message.user([...], peer_name="alice", channel_name="general")` → leading text
   block `"[from alice in #general]:"`); and a str-content case byte-identical to
   today. Follow the file's `_to_api_message` test idiom (or `Message.user(...)`
   direct construction).

## Edge Cases

- **Image-only list** (no `TextContent`) on USER → `content` = `[{type:image,…}]`;
  Anthropic accepts an image-only user turn. Fine.
- **`ImageContent` with only `url`** → `{type:image, source:{type:url,url}}`; valid on
  Anthropic (per L01 doc-gate). Ollama differs (L06).
- **Empty list** on USER → `content: []` — Anthropic may reject an empty content
  array, but no producer emits `[]` (L01 lenient at the contract layer; the provider
  doesn't special-case it — documented, not forced).
- **SYSTEM with list content** — impossible (DD3 assert forbids it); the list branch
  only ever sees USER.

## Files Affected

- `the_one/llm/anthropic_provider.py` — `_content_block_to_api` + forked fallthrough +
  comment update.
- `tests/test_anthropic_provider.py` — image-projection tests.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (`tests/test_anthropic_provider.py`)
- [ ] Update flight-log.md with a Leg Progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] (Not final leg — no flight/mission status change)
- [ ] Changes stay uncommitted — batch commit after L07 (do NOT commit at leg end)
