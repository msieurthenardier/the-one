# Leg: openai-openrouter-image-projection

**Status**: landed
**Flight**: [Multimodal Message.content (A2)](../flight.md)

## Objective

Fork the OpenAI `_to_api_message` USER-turn projection into a content-list path
mapping blocks to OpenAI content parts (`{type:text}` / `{type:image_url,
image_url:{url}}`, base64 as a `data:` URI or a plain URL) — with OpenRouter
inheriting it for free (no override) — and the `str` path byte-identical.

## Context

- **Depends on L01** (types + shape-aware `build_user_message_content`); follows
  L02/L03. Independent of L04/L06.
- **Projection site** — `openai_provider.py::_to_api_message`, the USER/SYSTEM
  fallthrough: `return {"role": msg.role.value, "content":
  build_user_message_content(msg)}`. Fork on `isinstance(projected, list)`.
- **OpenRouter** (`OpenRouterProvider(OpenAIProvider)`) overrides neither
  `_to_api_message` nor `complete`/`stream` — it **inherits** the fix (recon +
  Flight 11 confirmed). A smoke test confirms inheritance; no OpenRouter code change.
- **Wire shape (L01 doc-gate)**: OpenAI content part =
  `{"type":"image_url","image_url":{"url": <str>}}` where `url` is a base64 data-URI
  (`data:{media_type};base64,{data}`) **or** a plain URL. Text part =
  `{"type":"text","text":…}`. OpenAI's `content` field is natively
  `str | list[part]`, so the widened shape maps directly.
- **Shared-mapping note (A4 precedent)**: the OpenAI-compat content-part mapping is
  the same one Ollama `/v1` needs (L06). Per the A4 rule-of-two decision, keep a
  **local** `_content_block_to_api` on each provider with a forward-note to a future
  `to_openai_compat_content(...)` shared helper (lift at rule-of-three); L07's
  conformance matrix asserts OpenAI and Ollama-`/v1` emit identical shapes, catching
  drift.

## Inputs

- `the_one/llm/base.py` — content-block types + `build_user_message_content` (L01).
- `the_one/llm/openai_provider.py` — `_to_api_message` (USER fallthrough).
- `the_one/llm/openrouter_provider.py` — confirm no `_to_api_message` override.
- `tests/test_openai_provider.py` (created in Flight 11) — test home.

## Acceptance Criteria

- [x] **`_content_block_to_api(block) -> dict`** on `OpenAIProvider`: `TextContent` →
      `{"type":"text","text":…}`; `ImageContent` → `{"type":"image_url","image_url":
      {"url": f"data:{media_type};base64,{data}"}}` when `data` set (preferred),
      else `{"type":"image_url","image_url":{"url": url}}`.
- [x] **Fallthrough forked**: `list` → `{"role":…, "content":[map(b) …]}`; `str` →
      unchanged (byte-identical).
- [x] **Prefix block mapped**: peer/channel-set list-content USER message → leading
      `{"type":"text","text":"[from …]:"}` part.
- [x] **base64 preferred over url** when both set (DD5).
- [x] **OpenRouter inherits** — a smoke test constructs `OpenRouterProvider` and
      asserts `_to_api_message(Message.user([TextContent, ImageContent]))` produces
      the same content-part shape (no OpenRouter code change).
- [x] **No other provider / base.py / codec change**; `git diff --stat` shows only
      `openai_provider.py` + `tests/test_openai_provider.py` (+ flight artifacts).
- [x] Targeted tests green: `PYTHON=.venv/bin/python bash scripts/run-tests.sh
      tests/test_openai_provider.py tests/test_openrouter_provider.py -x --timeout 30`.

## Implementation Guidance

1. **`_content_block_to_api`** on `OpenAIProvider`:
   ```python
   def _content_block_to_api(self, b: ContentBlock) -> dict[str, Any]:
       if isinstance(b, TextContent):
           return {"type": "text", "text": b.text}
       url = f"data:{b.media_type};base64,{b.data}" if b.data is not None else b.url
       return {"type": "image_url", "image_url": {"url": url}}
   ```
   Add a forward-note comment: identical OpenAI-compat mapping to Ollama `/v1`
   (`ollama_provider.py`); lift to a shared `to_openai_compat_content` at
   rule-of-three (L07 asserts parity).
2. **Fork the fallthrough** (mirror L04): `projected =
   build_user_message_content(msg)`; `list` → map; `str` → unchanged.
3. **Tests** (`tests/test_openai_provider.py`): image-projection (base64 → data-URI,
   url → passthrough, base64-preferred-when-both); prefix-block; str byte-identical;
   an OpenRouter inheritance smoke (in `tests/test_openrouter_provider.py` or
   alongside).

## Edge Cases

- **Image-only / url-only / empty list** — as L04 (OpenAI accepts image-only user
  turns; empty list not produced).
- **base64 data-URI format** — `data:{media_type};base64,{data}` exactly (no spaces);
  test asserts the literal prefix.

## Files Affected

- `the_one/llm/openai_provider.py` — `_content_block_to_api` + forked fallthrough.
- `tests/test_openai_provider.py` (+ maybe `tests/test_openrouter_provider.py`) —
  tests.

---

## Post-Completion Checklist

- [x] All acceptance criteria verified
- [x] Tests passing
- [ ] Update flight-log.md with a Leg Progress entry (deferred — orchestrator scope, not Developer)
- [ ] Set this leg's status to `completed` (this leg is `landed`; `completed` deferred to review/orchestrator)
- [ ] Check off this leg in flight.md (deferred — orchestrator scope, not Developer)
- [x] Changes stay uncommitted — batch commit after L07
