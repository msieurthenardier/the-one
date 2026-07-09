# Leg: ollama-image-projection

**Status**: landed
**Flight**: [Multimodal Message.content (A2)](../flight.md)

## Objective

Fork **both** Ollama USER-turn projections into content-list paths: the `/v1`
(OpenAI-compat) path maps to `image_url` content parts (base64 data-URI **only** —
no remote URL), and the native `/api/chat` path maps to a message-level
`images: [base64]` array plus a text `content` — with the `str` path byte-identical
and `url`-bearing images a documented per-provider gap.

## Context

- **Depends on L01**; follows L02/L03; independent of L04/L05. Ollama has **two**
  projection methods (recon): `_to_api_message` (`/v1`) and `_to_native_message`
  (native `/api/chat`) — both fall through to `build_user_message_content(msg)`.
- **`/v1` path** = OpenAI-compat `image_url` content part, **base64 data-URI only**
  (Ollama's `/v1` layer has **no remote-URL support**, per L01 doc-gate). Same
  mapping as OpenAI (L05) — keep a **local** mapper with a forward-note (A4
  rule-of-two; L07 asserts `/v1`↔OpenAI parity).
- **Native path** is DIFFERENT — not content parts. The native `/api/chat` user
  message carries a text `content` string **plus** a message-level `images: [base64,
  …]` array. So native maps: `TextContent` → joined into `content`; `ImageContent`
  → base64 appended to `images` (**base64 only**; `url` → documented gap).
- **DD5 gap**: a `url`-bearing `ImageContent` on either Ollama path has no native
  target (base64-only) — **documented no-op/skip + a warning**, not fetched
  ("Acceptable variation"). base64 is the universal path (L08's producer base64-
  encodes).

## Inputs

- `the_one/llm/base.py` — content-block types + `build_user_message_content` (L01).
- `the_one/llm/ollama_provider.py` — `_to_api_message` (`/v1`), `_to_native_message`
  (native). The native message shape (`content` + `images`) per the L01 doc-gate.
- `tests/test_ollama_native_provider.py` + `tests/test_ollama_provider_*.py`.

## Acceptance Criteria

- [x] **`/v1` fork** (`_to_api_message`): `list` → OpenAI-compat content parts
      (`{type:text}` / `{type:image_url,image_url:{url: data-URI}}`); **base64 only**
      — a `url`-only `ImageContent` is skipped with a `logger.warning` (no remote-URL
      on Ollama `/v1`). `str` path byte-identical.
- [x] **native fork** (`_to_native_message`): `list` → a native user message with
      `content` = the `TextContent` texts joined (single space) **and** `images` =
      `[b.data for ImageContent if b.data]`; a `url`-only image skipped +
      `logger.warning`. `images` key omitted when no base64 image present. `str` path
      byte-identical.
- [x] **Prefix block**: the DD4 prefix `TextContent` folds into the text on both
      paths (a leading text part on `/v1`; part of the joined `content` on native).
- [x] **`url`-only image documented gap**: both paths skip it + warn (not fetched);
      a test asserts the warning + omission.
- [x] **No other provider / base.py / codec change**; `git diff --stat` shows only
      `ollama_provider.py` + Ollama test file(s) (+ flight artifacts).
- [x] Targeted tests green: `PYTHON=.venv/bin/python bash scripts/run-tests.sh
      tests/test_ollama_native_provider.py tests/test_ollama_provider_auth.py
      tests/test_ollama_provider_recovery.py tests/test_ollama_degraded_roundtrip.py
      tests/test_ollama_provider_a4_request_params.py -x --timeout 30` (the last two
      also exercise `_to_api_message`/`_native_body` → str-byte-identical regression
      net, per the L06 review).

## Implementation Guidance

0. **Add module-level logging** (design-review [medium]): `ollama_provider.py` has
   **no `logger`** today (unlike `anthropic_provider.py`/`openai_provider.py`). Add
   `import logging` and `logger = logging.getLogger(__name__)` at module level
   (matching `openai_provider.py`'s pattern) — the `logger.warning(...)` calls below
   `NameError` otherwise. Also add `TextContent`, `ImageContent`, `ContentBlock` to
   the existing `from the_one.llm.base import (...)` (not currently imported).

1. **`/v1` `_content_block_to_api`** on `OllamaProvider` — same as OpenAI's L05
   mapper BUT skip `url`-only images (base64 data-URI only): if `b.data` →
   `{"type":"image_url","image_url":{"url": f"data:{b.media_type};base64,{b.data}"}}`;
   elif `b.url` → `logger.warning("ollama /v1: remote image URL not supported; skipping")`
   and omit. Forward-note: shared OpenAI-compat mapping (L05); lift at rule-of-three.
   Fork `_to_api_message`'s USER fallthrough on `isinstance(projected, list)`.
2. **native** — fork `_to_native_message`'s USER fallthrough:
   ```python
   projected = build_user_message_content(msg)
   if isinstance(projected, list):
       texts, images = [], []
       for b in projected:
           if isinstance(b, TextContent):
               texts.append(b.text)
           elif b.data is not None:
               images.append(b.data)
           else:
               logger.warning("ollama native: remote image URL not supported; skipping")
       out = {"role": msg.role.value, "content": " ".join(texts)}
       if images:
           out["images"] = images
       return out
   # ... existing str path ...
   ```
3. **Tests**: `/v1` list projection (base64 data-URI, url-skipped+warn, prefix
   block) + str byte-identical; native list projection (content join + images array,
   url-skipped+warn, images omitted when none) + str byte-identical. Use the Ollama
   test idioms (`_to_api_message`/`_to_native_message` direct calls, `caplog` for the
   warning).

## Edge Cases

- **`url`-only image** → skipped + warned on BOTH paths (documented DD5 gap). Tested.
- **Image-only native** → `content: ""` + `images:[…]`. That Ollama accepts an
  empty `content` alongside `images` is an **inferred** assumption (parallel to
  Anthropic/OpenAI image-only acceptance), NOT pinned by the L01 doc-gate — flag as
  **HAT-confirm** if L08 is promoted. `/v1` `image_url` branch: use explicit `b.data
  is not None` (not a bare truthiness), matching the native fork.
- **Empty list** → `/v1` `content: []`; native `content: ""` (no `images`). No
  producer emits `[]`.
- **`/v1`↔OpenAI parity** for base64 → asserted in L07 (the mappers must match on the
  base64 case).

## Files Affected

- `the_one/llm/ollama_provider.py` — `/v1` `_content_block_to_api` + native fork;
  both USER fallthroughs.
- Ollama test file(s) — projection tests.

---

## Post-Completion Checklist

- [ ] All acceptance criteria verified
- [ ] Tests passing
- [ ] Update flight-log.md with a Leg Progress entry
- [ ] Set this leg's status to `completed`
- [ ] Check off this leg in flight.md
- [ ] Changes stay uncommitted — batch commit after L07
