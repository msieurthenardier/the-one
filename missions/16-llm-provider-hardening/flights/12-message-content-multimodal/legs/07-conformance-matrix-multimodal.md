# Leg: conformance-matrix-multimodal

**Status**: landed

> **FD note (2026-07-08):** design review intentionally skipped for this final,
> test-only, self-validating leg (it asserts against the already-landed, unit-tested
> L04–L06 projections; a wrong expected shape fails its own test). Test quality is
> covered by the Phase-2d batch code review.
**Flight**: [Multimodal Message.content (A2)](../flight.md)

## Objective

Extend the cross-provider conformance suite with an image-content projection matrix:
one canonical image-content USER `Message` projected through each provider's
`_to_api_message` to its correct native wire shape — with an explicit **OpenAI ≡
Ollama-`/v1` parity** assertion (the drift-catcher for the L05/L06 shared-mapping
duplication). Test-only, hermetic.

## Context

- **Depends on L04–L06** (all landed). The per-provider projections are already
  unit-tested; this leg is the systematic cross-provider proof + the parity net the
  L05/L06 forward-notes promised.
- **Direct `_to_api_message` matrix, not scripted transport** (design note): A2's
  projection is a **pure method** (`_to_api_message` — no network, deterministic
  from the input `Message`), so its output *is* the wire `messages`-array entry.
  Asserting `_to_api_message` output directly is equivalent to and simpler than
  driving `complete()` through the scripted transport (which A4-L05 needed only
  because config→wire required the full request assembly). This mirrors the A4-L05
  matrix *structure* (shared input, per-provider expected shape, OpenAI-compat
  grouping) applied to the projection method. *(If a reviewer prefers end-to-end
  through the transport, note it — but the pure-method assertion is the right bar
  here.)*
- **The wire shapes differ per provider** (like A4): Anthropic content blocks;
  OpenAI/OpenRouter/Ollama-`/v1` the shared OpenAI-compat parts; Ollama-native
  `content` + `images`; Mock has no `_to_api_message` (N/A).

## Inputs

- `tests/test_llm_provider_cross_provider_conformance.py` — the F4/A4 suite (the A4
  `A4_CONFIG` config→wire matrix is the structural precedent).
- The landed provider `_to_api_message` methods (L04–L06) + `mock.py` (no projection).
- `the_one/llm/base.py` — `Message.user`, `TextContent`, `ImageContent`.

## Outputs

- `tests/test_llm_provider_cross_provider_conformance.py` — an A2 image-projection
  matrix section (no production code).

## Acceptance Criteria

- [x] **Shared canonical input**: a module-level image-content USER message, e.g.
      `Message.user([TextContent("describe this"), ImageContent(media_type="image/png",
      data="AAA")])`.
- [x] **Anthropic**: `_to_api_message` → `{"role":"user","content":[{"type":"text",
      "text":"describe this"}, {"type":"image","source":{"type":"base64","media_type":
      "image/png","data":"AAA"}}]}`.
- [x] **OpenAI-compat providers parametrized** (openai, openrouter, ollama-`/v1`):
      each `_to_api_message` → `{"role":"user","content":[{"type":"text","text":…},
      {"type":"image_url","image_url":{"url":"data:image/png;base64,AAA"}}]}` — and
      an **explicit parity assertion** that openai, openrouter, and ollama-`/v1` emit
      the **identical** structure for the shared input (the L05/L06 duplication
      drift-catcher).
- [x] **Ollama native**: `_to_native_message` → `{"role":"user","content":"describe
      this","images":["AAA"]}` (joined text + base64 images array).
- [x] **Mock N/A**: documented (a comment or explicit skip — Mock has no
      `_to_api_message`/wire path).
- [x] **A `url`-image gap row** (optional but recommended): a `url`-only
      `ImageContent` projects natively on Anthropic/OpenAI/OpenRouter but is
      skipped+warned on both Ollama paths (asserts the DD5 documented gap
      cross-provider).
- [x] **No production code touched** — `git diff --stat` shows only the conformance
      test file (+ flight artifacts).
- [x] Full suite green: `PYTHON=.venv/bin/python bash scripts/run-tests.sh
      tests/test_llm_provider_cross_provider_conformance.py -x --timeout 30`; and
      `make test-unit` shows no regression.

## Verification Steps

- Run the conformance file — green, incl. the A2 matrix + parity assertion.
- `make test-unit` — no regression.
- `git diff --stat` — only the conformance test file (+ flight artifacts).
- Read the A2 section — confirm the parity assertion (openai ≡ openrouter ≡
  ollama-/v1) and the Anthropic/native/Mock distinctions.

## Implementation Guidance

1. Add an **A2 image-projection matrix** section near the A4 `A4_CONFIG` matrix.
   Define the shared input + the expected OpenAI-compat content-part list + the
   expected Anthropic block list + the expected Ollama-native `{content,images}`.
2. **Provider construction**: construct each provider directly (`AnthropicProvider(
   model="claude-test", api_key="x")`, `OpenAIProvider(...)`, `OpenRouterProvider(
   ...)`, `OllamaProvider(...)`) and call `_to_api_message`/`_to_native_message`
   with the shared message — no transport needed. (Follow the file's existing direct
   `_to_api_message`/`_build_kwargs` idiom.)
3. **Parity assertion**: assert `openai._to_api_message(m) == openrouter.
   _to_api_message(m) == ollama_v1._to_api_message(m)` for the shared base64 input —
   this is the L05/L06 drift net. If they ever diverge (someone edits one mapper),
   this fails loudly.
4. **Ollama native**: call `_to_native_message` (the native path) for the
   `{content, images}` shape; call `_to_api_message` for the `/v1` shape.
5. Note Mock N/A. Do NOT modify any `the_one/**` file — if a projection is wrong,
   STOP and surface it (the fix belongs to L04–L06, not this test-only leg).

## Edge Cases

- **Parity is the point**: if openai/openrouter/ollama-`/v1` diverge, the parity
  assertion is the intended failure — it means the deliberate duplication drifted
  and should be lifted to the shared helper (rule-of-three trigger).
- **url-gap cross-provider**: the optional url row proves the DD5 gap is consistent
  (native on Anthropic/OpenAI, skipped on Ollama) — a cross-provider record of the
  documented asymmetry.
- **Ollama `/v1` vs native divergence** is expected and asserted (different shapes) —
  not a drift, a genuine per-path difference.

## Files Affected

- `tests/test_llm_provider_cross_provider_conformance.py` — the A2 matrix.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (conformance file + `make test-unit` regression)
- [x] Update flight-log.md with a Leg Progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] **Last autonomous leg** — but do NOT set flight → landed or commit here: that
      is the post-L07 batch review + commit (Phase 2d), and only after L08 (optional
      HAT) is dispositioned.
- [x] Changes stay uncommitted — batch commit after review (do NOT commit)
