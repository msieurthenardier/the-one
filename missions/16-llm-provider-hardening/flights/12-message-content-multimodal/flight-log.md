# Flight Log: Multimodal `Message.content` — vision (image) inputs (A2)

**Flight**: [Multimodal Message.content (A2)](flight.md)

## Summary

Planning. Flight scoped to backlog **A2** — widen `Message.content` to
`str | list[ContentBlock]` for **image inputs**, mapped to each provider's native
multimodal wire shape, proven hermetically. Capability + wire only, images-first
(operator best-judgment 2026-07-08, adjustable at review); a canonical
`ContentBlock` dataclass (not raw dicts); a live ingestion producer + Anthropic
vision HAT are an optional promotable leg (L08). Split from A4 (Flight 11, landed).
Not yet in-flight.

---

## Leg Progress

### L01 — content-block-contract-and-doc-gate (landed, 2026-07-08)

Landed the canonical `TextContent`/`ImageContent` union in `the_one/llm/base.py`
(mirrors `ThinkingBlock`), widened `Message.content` and the `Message.user()`
factory to `str | list[ContentBlock]`, replaced the unconditional str-assert with
a conditional one (`str` OK; `list[ContentBlock]` OK only on `Role.USER`; both
invalid branches use an explicit `raise AssertionError` — not a bare `assert` —
so the role guard survives `python -O`), and made `build_user_message_content`
shape-aware (DD4: the `list` branch prepends a separate `TextContent` prefix
block, never merges into the user's own blocks; returns a fresh `list(msg.content)`
copy — not the same reference — when no prefix applies). `agents.md`'s
`provider-shape-portability` convention updated to describe the conditional
assert + the canonical `ContentBlock` union. Added 22 new tests to
`tests/test_llm_base.py` (block construction incl. the `ImageContent`
data-or-url guard, `Message.user([...])` accepting a block list, the assert's
accept/reject matrix, and the `build_user_message_content` str-byte-identical +
list-prefix + empty-list cases) — 27/27 green. Confirmed no regression:
`tests/test_anthropic_provider.py` (63 tests) and
`tests/test_llm_provider_cross_provider_conformance.py` (40 tests) green — the
widened `build_user_message_content` return annotation doesn't break any str
call site. `ruff check`/`ruff format --check` clean on touched files.
`git diff --stat` shows only `base.py`, `agents.md`, `tests/test_llm_base.py` (+
flight artifacts) — no codec, consumer, or provider-request-path change (L02–L06
untouched, per DD5/atomic-leg scoping). See the Wire-Format Premise below (the
L04–L06 gate).

### L02 — codec-content-round-trip (landed, 2026-07-08)

Widened the persistence codec (`the_one/db/codec.py`) to round-trip
`list[ContentBlock]` message content — the DD2 fork the codec pays for (dataclass
blocks aren't JSON-serializable, so the prior opaque `content` passthrough would
`TypeError` on `json.dumps`). Added `_content_block_to_dict`/`_content_block_from_dict`
next to the `ThinkingBlock` codec pair: encode mirrors `_thinking_block_to_dict`'s
non-None-field-emission style (`TextContent` → `{"type":"text","text"}`;
`ImageContent` → `{"type":"image","media_type"}` plus `data`/`url` only when set).
Decode deliberately departs from `_thinking_block_from_dict`'s permissive any-type
construction — an unrecognized block `type` **raises** `ValueError` rather than
being silently dropped (F10 Rec 5 anti-pattern: content blocks are user data
selecting between distinct dataclasses with no safe default target). Made
`message_to_dict`/`message_from_dict` content-aware via an `isinstance` branch:
`str` content is emitted/decoded byte-identically (unchanged code path); `list`
content routes through the new block codec. `messages_to_ui_events`, `base.py`,
and provider paths untouched (per leg scope — UI-events hardening for a live list
producer is flagged as an L08 prerequisite, not this leg's job). Added
`TestContentBlockCodec` to `tests/test_db_codec.py` (14 new tests) mirroring
`TestMessageThinkingCodec`'s idiom: all-three-block-shapes round-trip (`TextContent`
+ `ImageContent(data=…)` + `ImageContent(url=…)`) through both the direct
`message_to_dict`/`message_from_dict` path and the full `encode_messages`/
`decode_messages` JSON boundary, str byte-identical, empty-list round-trip,
data-only/url-only/both-set `ImageContent` variants, unknown-type raises (both at
the block-helper level and propagated through `message_from_dict`), legacy-str and
legacy-missing-key decode, and a persisted list-content-on-non-USER-role case that
raises via `Message.__post_init__`'s role guard (documents the codec relies on the
dataclass invariant, not its own role check) — 119/119 green in `test_db_codec.py`.
Confirmed no regression: `tests/test_llm_base.py` (27 tests) green — the codec
change doesn't touch `base.py`. `ruff check`/`ruff format --check` clean on touched
files. `git diff --stat` (scoped to this leg's own edits, isolating out L01's
already-landed-but-uncommitted `base.py`/`agents.md`/`tests/test_llm_base.py`
changes) shows only `the_one/db/codec.py` + `tests/test_db_codec.py` (+ flight
artifacts) — no `messages_to_ui_events`, `base.py`, or provider-path change.

### L03 — str-consumer-hardening (landed, 2026-07-08)

Added `content_to_text(content: str | list[ContentBlock]) -> str` to
`the_one/llm/base.py` (next to `build_user_message_content`): `str` → unchanged;
`list` → `TextContent` texts joined by a single space, each `ImageContent` → a
`"[image]"` placeholder (mirrors the MCP layer's image→placeholder flattening),
dispatch by `isinstance` (F10 Rec 5 no-hardcoded-type-filter discipline) — the
union is closed so the chain is exhaustive; empty list → `""`. Hardened the one
genuine USER-content reader confirmed in-scope, `_inference.py::_render_history_for_prompt`
— `content = m.content` → `content = content_to_text(m.content)` before the
`[operator]`-prefix wrap; everything else (role-label, prefix, join) is untouched,
so the str path is byte-identical. Added a one-line comment at the call site
pointing future readers at the DD3-safe / tracked-deferral sites. Independently
re-verified the recon's "exactly one" claim by grepping every `.content` read
across `the_one/` (excluding `ToolResult.content`/`response.content` false
positives): the only other USER-role reader is `db/codec.py::messages_to_ui_events`
(already tracked as an L08/frontend prerequisite, out of L03's scope) — no new
blocking site found, so no `[BLOCKED:...]` needed. Left the documented DD3-safe
sites (`agent/core.py`, the `_inference.py` classifier-output parse,
`post_step_metadata.py`, `interfaces/cli.py`, `interfaces/web/app.py`),
providers, codec, and `messages_to_ui_events` untouched. Added
`TestContentToText` to `tests/test_llm_base.py` (6 new tests: str passthrough,
empty-str passthrough, text-only list join, image→placeholder, mixed
text+image ordering preserved, empty list → `""`) and 3 new tests to
`tests/test_connectors_inference.py` (str-content byte-identical render;
list-content USER message with no operator prefix — flattened text with no
stray double space; list-content USER message WITH the operator prefix, applied
after flattening since the raw-content read means `content_to_text` only sees
the user's own blocks) — 61/61 green across both files. `ruff check`/
`ruff format --check` clean on touched files. `git diff --stat` (scoped to this
leg's own edits, isolating out L01/L02's already-landed-but-uncommitted
`base.py`/`agents.md`/`db/codec.py`/`test_db_codec.py` changes) shows only
`the_one/llm/base.py` + `the_one/connectors/_inference.py` +
`tests/test_llm_base.py` + `tests/test_connectors_inference.py` (+ flight
artifacts) — no provider/codec/other-consumer change.

### L04–L06 — provider image projection (landed, 2026-07-08)

The three provider-projection legs were designed + design-reviewed + implemented
**in parallel** (independent files; each implementer scoped to its own provider +
test files and its own leg status, the Flight Director writing the shared
flight-log/flight.md to avoid write races). Design reviews (Sonnet): L04 **approve**,
L05 **approve**, L06 **approve-with-changes** (folded). Each forks its provider's
USER-turn `_to_api_message` fallthrough on
`isinstance(build_user_message_content(msg), list)` — the `str` path stays
byte-identical everywhere.

- **L04 Anthropic** (`anthropic_provider.py`): `_content_block_to_api` →
  `{type:text}` / `{type:image, source: base64{media_type,data} preferred else
  url{url}}`; superseded the old "would NOT call `build_user_message_content`"
  forward-comment (DD4). SYSTEM never reaches the list branch. **68 passed** (5 new).
- **L05 OpenAI/OpenRouter** (`openai_provider.py`): `_content_block_to_api` →
  `{type:image_url, image_url:{url}}` (url = `data:{media_type};base64,{data}` base64-
  preferred, else the plain url); forward-note (shared OpenAI-compat mapping w/
  Ollama-`/v1`, lift at rule-of-three). **OpenRouter code untouched** — an inheritance
  smoke asserts the same shape. **57 passed**.
- **L06 Ollama** (`ollama_provider.py`): added the module-level `logger` it lacked
  (review [medium]); `/v1` fork = OpenAI-compat parts (base64 data-URI **only**,
  `url` skipped+warn); native fork = joined `content` + a message-level
  `images:[base64]` array (`url` skipped+warn; `images` omitted when none). New
  `tests/test_ollama_content_projection.py` (9) + suite **68 passed**.

Combined smoke (3 provider suites + cross-provider conformance): **182 passed**.
Provider diffs: anthropic +39 / openai +32 / ollama +60; `openrouter_provider.py`
unchanged (inherits). `url`-on-Ollama is a documented DD5 gap. Uncommitted
(batch-commit after L07).

### L07 — conformance-matrix-multimodal (landed, 2026-07-08)

Test-only. Extended `tests/test_llm_provider_cross_provider_conformance.py` with an
A2 image-projection matrix (+158 lines): a shared image-content USER message
(`[TextContent, ImageContent(data=…)]`) projected through each provider's
`_to_api_message` to its native shape — Anthropic content blocks
(`{type:image,source:base64}`), the OpenAI-compat parts
(`{type:image_url,image_url:{url:data-URI}}`) with an explicit **openai ≡ openrouter
≡ ollama-`/v1` parity assertion** (the L05/L06 duplication drift-catcher), Ollama
native `{content, images:[base64]}`, and a cross-provider `url`-gap row
(native on Anthropic/OpenAI, skipped on both Ollama paths — the DD5 asymmetry). Mock
documented N/A (no `_to_api_message`). **Design review intentionally skipped** (FD
decision): final, test-only, self-validating leg asserting against the already-unit-
tested L04–L06 projections — Phase-2d batch review covers test quality.

Conformance file **45 passed** (was 40 → +5 A2 tests). Diff test-only (no
`the_one/**`). Full `make test-unit` regression run by the FD as the pre-batch gate.
All 7 autonomous legs landed; L08 (ingestion + vision HAT) remains optional/deferred.
Next: Phase-2d batch code review + single commit + draft PR.

### L08 — image ingestion producer + live vision HAT (2026-07-09/10)

**Promoted from optional** at operator request ("might as well send an image…
looking forward to doing it myself"). Built the minimal image-ingestion producer +
the `content_to_text` event-projection fix, then ran a live Anthropic vision HAT.

**Build** (recon-mapped 4 touch points + 1 shared fix): `chat.js` file-attach
control → `images` on the WS payload; `app.py` builds `[TextContent(text),
*ImageContent(...)]` (text present) or `[ImageContent(...)]` (image-only — **no
empty `TextContent`**, which Anthropic 400s) + widened `_process_and_broadcast`/
`_spawn_message_processing` hints; `Agent.step` hint widened (body unchanged —
`Message.user` is polymorphic); **`content_to_text(user_input)` at the live-broadcast
`user_event` site (`app.py`) AND the `messages_to_ui_events` USER branch
(`codec.py`)** — this single fix closes **two latent bugs any image message would
trigger**: (a) `json.dumps` `TypeError` on list content → **kills the WS on
replay/join** and desyncs the sender on the first live send; (b) `Session.add_event`
title-slice corrupting the `str`-typed `session.title`. Design review (Sonnet:
approve-with-changes) caught the source-scan→**Playwright browser test** correction
(the repo HAS a `tests/browser/` suite) + the image-only 400 risk — both folded.
New tests: `test_process_and_broadcast_image_content.py`, `test_ws_build_user_content.py`,
`tests/browser/test_flow_chat_image_attach.py`. Verified: hermetic 129, browser 5,
**full `make test-unit` 3976 passed / 10 skipped**, ruff clean.

**HAT (operator-driven, live Anthropic, `claude-sonnet-4-6` on :8485 rebuilt from
this branch): PASS.** Vision confirmed end-to-end — Claude answered grounded in the
attached image. Two inline UX fixes during the HAT (operator feedback): (1) the
attach was **silent** → added a staged-image indicator; (2) moved it to a
**chicklet row above the input** + **multi-image** support (each attach appends a
removable chicklet; `multiple` file input) — the wire path already supported N
images. A real bug caught+fixed in the multi-image work: a live `FileList` reference
collapsed when the input `.value` was cleared (snapshotted to fix). Final browser
suite **5 passed** + `test_ui_guards` 14. Deferred (recorded): the user's own image
**thumbnail in the sent bubble** (shows text + `[image]` today), attach-while-busy,
documents/PDF, client-side size limits.

---

## Decisions

### Scope: capability + native-wire mapping, images-first (DD1)
**Context**: A2 was split from A4 as a "flight-class protocol migration with no
in-scope ingestion surface." Recon §6 confirmed **zero ingestion producers** today.
**Decision**: widen the contract + map to native wire shapes + prove hermetically;
documents/PDF and a live producer deferred (producer = optional L08).
**Impact**: image support is real + wire-proven but has no user entry point unless
L08 is promoted. Mission criterion #3 advanced (with A2 done, only the A3/A5/B1–B4
deferral sweep remains).

### Canonical `ContentBlock` dataclass, not raw dicts (DD2)
**Context**: recon fork — raw-dict blocks round-trip the codec free; a dataclass
needs an encoder/decoder but matches the `provider-shape-portability` convention +
the `ThinkingBlock` precedent.
**Decision**: canonical provider-neutral `ContentBlock` dataclass; the codec gains a
`_content_block_to_dict`/`_from_dict` pair (L02).
**Impact**: type-safe + convention-aligned; L02 exists because of this. Overridable
at review (raw-dict would collapse L02).

### Content blocks only on USER-role messages (DD3)
**Context**: images/documents are inputs; recon confirmed assistant/tool-side
`str`-consumers stay valid if content-widening is user-turn-scoped.
**Decision**: `list[ContentBlock]` legitimate only on `Role.USER`; SYSTEM/ASSISTANT/
TOOL stay str; the assert enforces it.
**Impact**: blast radius shrinks to the USER-turn projection + ~6 user-content
readers (L03).

---

## Deviations

_(none yet)_

---

## Anomalies

_(none yet)_

---

## Reconnaissance Report

Blast-radius recon (2026-07-08) against `the_one/` at mission-16 HEAD (`cf68f81`).
Source item: A2 from the Flight 1B audit backlog. Full detail in the planning
session; summary of the load-bearing findings:

| Area | Finding | Leg |
|------|---------|-----|
| Contract site | `Message.content: str = ""` (`base.py:84`); hard **assert** `isinstance(content,str)` (`base.py:165`) — not a normalize-guard (that's `ToolResult`); `build_user_message_content()->str` (`base.py:221`) is str-in/str-out (f-string interp — silently corrupts a list) | L01 |
| Blast radius (str-assuming `.content` consumers) | **~6 real sites**: `agent/core.py:328` (`.strip()`), `connectors/_inference.py:135` (history f-string) + `:283/343` (classifier parse, assistant-side), `connectors/post_step_metadata.py:119` (`.startswith`), `interfaces/cli.py:79` (`Markdown()`), `interfaces/web/app.py:1920` (`str.join`). Everything else opaque-safe (truthy/dict-passthrough/equality) or assistant/tool-side | L03 |
| False positives (NOT `Message.content`) | Discord SDK `.content`, MCP SDK `CallToolResult.content` (already flattens image blocks to text placeholders — the gap A2 closes), `httpx.Response.content`, `ToolResult.content` (self-normalizing), Anthropic SDK `response.content` | — |
| Provider projection | 3 `_to_api_message` (Anthropic `:462-508`, OpenAI `:262-289`, Ollama TWO: `/v1` `:645-668` + native `_to_native_message` `:540-557`); all fall through to `build_user_message_content`. **OpenRouter inherits OpenAI** (no override). Anthropic ASSISTANT branch `:479-497` already builds a list-of-blocks — the target shape. Mock has no projection | L04–L06 |
| Persistence codec | `message_to_dict:107` + `message_from_dict:175` = opaque passthrough. **dict blocks round-trip FREE; dataclass blocks need `_content_block_to_dict`/`_from_dict`** (mirror `_thinking_block_to_dict` `codec.py:60-75`) — the DD2 fork | L02 |
| Native wire shapes (pinned SDKs) | Anthropic 0.97.0 `ImageBlockParam` (base64/url source) + `DocumentBlockParam`; OpenAI 2.33.0 `ChatCompletionContentPartImageParam` (`image_url`), content field already `str \| list[part]`; Ollama native `images:[base64]` (unwired), `/v1` base64 `image_url` only | L01/L04–L06 |
| Ingestion producers | **ZERO** — `Agent.step(user_input: str)` (`core.py:196`), WS `payload.get("message","")` (`app.py:2163`), no chat file-upload anywhere. Live vision un-HAT-able without a producer | L08 (optional) |
| F10-Rec-5 type-filter risk | `thinking_display_text` (`codec.py:199`) hardcodes `type=="thinking"` — the failure template A2's content-block type dispatch must NOT repeat (provider-neutral canonicalization) | L01/L03 |

---

## Wire-Format Premise

Recorded 2026-07-08 by L01 (the DD5 / F10-Rec-1 doc-gate for L04–L06 — no provider
is wired on an assumed shape). Authority: pinned SDK stubs under `.venv/`
(anthropic 0.97.0, openai 2.33.0) for the wire shape; first-party provider docs
for per-model acceptance (SDK stubs don't encode model-capability tables).

| Provider | Accepted image wire shape | base64 support | URL support | Per-model acceptance | Source |
|---|---|---|---|---|---|
| **Anthropic** (Messages API) | `content: list[ContentBlockParam]` where an image block is `{"type": "image", "source": {...}}`. `Source = Base64ImageSourceParam \| URLImageSourceParam` (`anthropic.types.image_block_param.ImageBlockParam`, `.venv/…/anthropic/types/image_block_param.py`). | Yes — `{"type": "base64", "media_type": "image/jpeg" \| "image/png" \| "image/gif" \| "image/webp", "data": <b64 str>}` (`base64_image_source_param.py`; `media_type` is a closed `Literal` of exactly those 4 MIME types — the SDK stub itself is the authority for L04's `ImageContent.media_type` validation surface, if any is added). | Yes — `{"type": "url", "url": <str>}` (`url_image_source_param.py`). | **All current Claude models accept image input** per the first-party vision guide (`platform.claude.com/docs/en/build-with-claude/vision`, fetched 2026-07-08) — vision is a blanket model-family capability, not a per-model opt-in on the current lineup (this project's default `claude-sonnet-4-6`, `the_one/llm/anthropic_provider.py:131`, is in the vision-capable family). Format support: JPEG/PNG/GIF/WebP only (first frame of animations). Request limits: 100 images/request for 200k-context models, 600 otherwise; ≤10MB base64-encoded per image (Claude API direct). Bedrock/Vertex: **base64-only, no `url` source** — flagged **HAT-confirm** if/when a non-direct-API deployment target is in scope (out of scope for this project's provider set today, which calls the Claude API directly). | SDK stub (shape); `platform.claude.com/docs/en/build-with-claude/vision` (per-model + format + limits), fetched 2026-07-08. |
| **OpenAI** (Chat Completions) | `content: str \| list[ChatCompletionContentPartParam]`; an image part is `ChatCompletionContentPartImageParam` = `{"type": "image_url", "image_url": {"url": <str>, "detail"?: "auto"\|"low"\|"high"}}` (`.venv/…/openai/types/chat/chat_completion_content_part_image_param.py`). | Yes — via a base64 **data URL** in the same `url` field: `"url": "data:image/jpeg;base64,<b64 str>"` (no separate base64 field — base64 and remote URL share the one `url` string, distinguished by the `data:` scheme prefix). | Yes — a plain `https://…` URL in `url`. | Vision-enabled per first-party docs (`developers.openai.com/api/docs/guides/images-vision`, fetched 2026-07-08): GPT-4o family, GPT-4.1 family, o-series reasoning models, and the current GPT-5 family all accept image input; this project's default `gpt-4o` (`the_one/llm/openai_provider.py:56`) is in the vision-capable set. Supported formats: PNG, JPEG, WEBP, non-animated GIF. | SDK stub (shape); `developers.openai.com/api/docs/guides/images-vision`, fetched 2026-07-08. |
| **OpenRouter** | Inherits `OpenAIProvider._to_api_message` verbatim (recon: no override) — same `image_url` part shape as OpenAI. | Same as OpenAI (data-URL). | Same as OpenAI. | **HAT-confirm** — OpenRouter proxies to many backing models with heterogeneous vision support; the request shape is OpenAI-compatible (confirmed structurally by inheritance), but whether a *given* OpenRouter-routed model accepts an image part is model-specific and not resolvable from the OpenAI SDK stub or OpenAI's own docs. L05 (or a HAT) must confirm per configured OpenRouter model at wiring time. | Structural: OpenAI SDK stub + `the_one/llm/openrouter_provider.py` (no `_to_api_message` override). Per-model acceptance: HAT-confirm. |
| **Ollama — native** (`/api/chat`, `/api/generate`) | Message-level `images: list[str]` sibling key (NOT a content-part union like Anthropic/OpenAI — Ollama's native shape is flatter: text goes in `content: str`, images go in a separate `images` array on the same message object). | Yes — each list element is a bare base64 string (no `data:` URI prefix, no wrapping object): `"images": ["<b64 str>", ...]`. | **No** — the native API has no URL-source option; only base64. | Vision-capable models must be explicitly multimodal-tagged (e.g. `llava`, `llama3.2-vision`, `qwen2.5vl`, `bakllava`, `moondream`, `gemma3`); a non-vision model silently ignores or errors on the `images` key (per-model behavior on ignore-vs-error not settled by docs — **HAT-confirm** if a non-vision default model is ever sent image content, since this project has no ingestion producer yet — recon confirms zero producers, so this can't diverge from any live default until L08). | `github.com/ollama/ollama/blob/main/docs/api.md` (fetched 2026-07-08, via research fetch — confirms `images: [base64, ...]` shape at both `/api/generate` and `/api/chat`, no URL support); `ollama.com/blog/vision-models` (model list). |
| **Ollama — `/v1` (OpenAI-compat)** | Same `ChatCompletionContentPartImageParam` shape as OpenAI (`{"type": "image_url", "image_url": {"url": ...}}`) — this project's `OllamaProvider` (`the_one/llm/ollama_provider.py`) talks to `/v1/chat/completions` by default (`base_url="http://localhost:11434/v1"`, line ~158). | Yes — data URL, same as OpenAI's `/v1` shape. | **Documented gap (DD5)** — Ollama's `/v1` compat layer does not fetch remote URLs; only base64 data URLs are honored in practice (recon + this doc-gate concur: Ollama's own docs describe only the base64 `images` shape for its native API, and the `/v1` shim is a compatibility layer over that native base64-only backend — a remote `url` would need to be fetched server-side, which Ollama does not do). Flagged **HAT-confirm** at L06 wiring time against the operator's actual Ollama version, since this is inferred from the native-API gap rather than stated explicitly for the `/v1` shim. | Same per-model caveat as native — vision-tagged models only. | Structural inference from `github.com/ollama/ollama/blob/main/docs/api.md` (native gap) + `the_one/llm/ollama_provider.py` (default `/v1` base_url); direct `/v1`-endpoint URL-support documentation not found — **HAT-confirm**. |

**L04–L06 gate takeaway**: `data` (base64) is the universal path across all four
provider adapters — safe to always populate. `url` is native and free on
Anthropic direct-API and OpenAI/OpenRouter; **Ollama (both native and `/v1`) has
no remote-URL path** — an `ImageContent` with only `url` set (no `data`) will need
either a fetch-and-inline step or a documented capability gap at the Ollama
adapter (L06's call). Per-model image acceptance is a blanket family capability
for Anthropic/OpenAI's current default models (`claude-sonnet-4-6`, `gpt-4o`);
OpenRouter and Ollama per-model acceptance are correctly deferred to
HAT-confirm at their respective wiring legs (L05/L06) since no first-party doc
or pinned SDK stub settles it generically.

---

## Session Notes

**2026-07-08 — Flight planned (A2).** Scoped from mission criterion #3 + the Flight
1B backlog. Split from A4 (Flight 11, landed). Blast-radius recon run (see above) —
narrower than feared (~6 str-assumers; OpenRouter inherits; codec free for dicts).
Design decisions: capability+wire images-first (DD1), canonical `ContentBlock`
dataclass (DD2), USER-turn-only (DD3), shared shape-aware `build_user_message_content`
(DD4), doc-gate-first (DD5), hermetic + optional HAT (DD6). Operator away at the
decision point — DD1/DD2 taken as best-judgment defaults, flagged overridable at
review. Next: Phase-5b Architect design review, then operator walk-through.

**2026-07-08 — Phase-5b design review incorporated (Architect/Opus: approve with
changes).** All recon load-bearing claims validated against the tree; confirmed no
persisted-session migration needed (legacy `content` decodes as str → passes the
conditional assert), no token-budget/streaming concern, and DD3's USER-turn-only
scoping has no hole (every `Message.user(...)` site passes a str; the classifier
builds a str history). Blast radius is even smaller than the recon's ~6 — under DD3
only `_inference.py` history-render genuinely reads USER content; the rest are
assistant/tool-side (L03 mostly defensive). Changes folded in: **[high]** DD2/L01
now define **both** `TextContent` and `ImageContent` (content is str XOR list, so a
user's text must be a block when an image is present); **[high]** L08 re-scoped to
the **send path + model-receives-image + grounded HAT**, with frontend image-bubble
display + `messages_to_ui_events` projection + list-content replay made an explicit
follow-up (frontend renders via `textContent` → a list would coerce to
`[object Object]`); **[medium]** `Message.user()` factory signature widening added to
L01; **[medium]** DD4/DD5 spell out the `isinstance`-fork contract + that the
prefix `TextContent` block is native-mapped too. Questions resolved: base64 is the
universal image path, `url` best-effort (Ollama no-URL = documented gap, no fetch)
(DD5); the F11 schema-normalizer was mis-scoped to A2 → moved to the structured-
output deferral, not bundled here; peer/channel prefix is a **separate** prepended
`TextContent` block (DD4). Affirmed: DD2 dataclass over raw dicts (keeps the
provider-shape-portability invariant), L02/L03-before-L04–L06 ordering, doc-gate as
a hard gate. Single review cycle; changes were spec tightenings + question
resolutions, no structural rethink → no second cycle. Awaiting operator sign-off.

**2026-07-08 — Operator sign-off; flight → `ready`.** Spec approved as presented:
**L08 kept optional** (not promoted — capability wire-proven hermetically; image-
upload UI + live vision HAT deferred), **dataclass content blocks confirmed** (DD2).
Operator directed immediate execution via `/agentic-workflow`. Autonomous legs
L01–L07; L08 optional/operator-guided.

---

### Flight Director Notes

**2026-07-08 — Flight started via `/agentic-workflow`; → `in-flight`.** Branch
`flight/12-message-content-multimodal` cut from `main` (`56e6114`). Per-leg design
review, then batch code-review + single commit after the last autonomous leg
(L01–L07). L08 (ingestion + vision HAT) is operator-guided/optional. Beginning
Leg 01 design (`content-block-contract-and-doc-gate`).

**2026-07-08 — L01 designed + design-reviewed (Developer/Sonnet: approve with
changes) → `ready`.** Scope: canonical `TextContent`+`ImageContent` dataclasses +
widen `Message.content`/`Message.user()` + conditional assert (str, or USER-only
block-list) + shape-aware `build_user_message_content` (separate prepended prefix
`TextContent`) + wire-format doc-gate + `agents.md` convention update; no codec/
provider/consumer bleed. Review verified every citation, confirmed DD3 has no hole
(all `Message(...)` sites pass str), and that widening `build_user_message_content`'s
return type is safe at all 3 provider call sites (they return `dict[str,Any]`, str
path unbroken). Folded: **[medium]** the USER-only guard uses an explicit `raise`
(not a plain `assert`, `-O`-strippable) so the invariant always holds;
**[suggestions]** return a copy `list(msg.content)` in the no-prefix list branch
(no aliasing) + hoist the peer/ch lookups; **[question]** empty-`[]`-on-USER
allowed-by-design (validates shape+role not semantics, mirrors empty-str). Single
cycle → no second cycle. Proceeding to implementation.
