# Leg: openai-audit

**Status**: landed
**Flight**: [Provider Capability Audit](../flight.md)

## Objective
Audit `openai_provider.py` against the installed `openai` SDK surface, producing one cited matrix row per capability (the frozen capability list from leg 01) scored on the three axes.

## Context
- Scores against the **frozen rubric + contract inventory** in `flight-log.md` (leg `01-audit-rubric`). Do NOT re-derive the contract surface.
- SDK is the official `openai` SDK installed in the project **`.venv`** (currently 2.33.0 — but **read the exact installed version from `.venv` and record it in the matrix header**; the pin is a floor `>=2.16`). Read its source for the "SDK-exposed" axis (DD5).
- Writes to its **own leg artifact**, not the shared flight log (concurrent with the other provider legs; leg 06 consolidates).
- **Model-catalog / context-window sourcing is owned by Flight 5** — the mission already records that OpenAI's `/models` exposes no `context_length` (so the hand-curated prefix table at `openai_provider.py:~37-59` is the current mechanism). Note this against the token-counting / catalog area as a cross-ref to Flight 5; do not re-derive or propose the fix here.

## Inputs
- `flight-log.md` → `### Rubric & Contract Inventory` (frozen reference).
- Installed `openai` SDK source in the project `.venv` (read the exact version; `~2.33.0`).
- `the_one/llm/openai_provider.py` (+ `_streaming.py`, `base.py` as needed).

## Outputs
- Filled matrix (one row per capability + catch-all rows) in this leg's `## Audit Result`, every SDK-exposed cell cited.

## Acceptance Criteria
- [ ] Each of the ten named frozen-list capabilities, plus any per-SDK catch-all rows, has a row scored on all three axes (Yes/No/Partial, missing piece named).
- [ ] Every "SDK-exposed: Yes/Partial" cell cites an `openai` SDK symbol/path (e.g. `chat.completions.create` params like `response_format`, `reasoning_effort`, `parallel_tool_calls`, `stop`; the Responses API if relevant; usage fields) or a doc URL.
- [ ] Every "Wired-through" cell cites `openai_provider.py:line` (or `_streaming.py:line`).
- [ ] Each gap carries a proposed gap class (contract-level / adapter-only / none) consistent with the inventory.
- [ ] The structured-outputs and reasoning-effort rows are scored explicitly (these are OpenAI's strong surfaces); the catalog/context-window observation cross-refs Flight 5.

## Verification Steps
- Confirm one row per frozen-list capability, all three axes scored.
- Spot-check 2 SDK citations resolve to a real symbol in the installed `openai` package.
- Spot-check 2 wiring citations resolve to the cited `openai_provider.py` lines.

## Implementation Guidance
1. Read the frozen rubric/inventory in `flight-log.md`.
2. Read `the_one/llm/openai_provider.py` fully (+ `_streaming.py`). Note per-capability wiring; note the hand-curated context table location for the Flight 5 cross-ref (do not propose a fix).
3. Read the installed `openai` SDK surface (`chat.completions.create` and, if present, the Responses API; params for `response_format`/`json_schema`, `reasoning_effort`, `parallel_tool_calls`, `stop`, `stream_options`; usage fields incl. any cached-token fields). Cite real symbols.
4. Fill the matrix rows in `## Audit Result`. Partial honestly; name the missing piece.
5. Set leg status `landed`; one-line flight-log Session Notes append. Do NOT commit. Do NOT touch source.

## Edge Cases
- **Two API shapes**: if the installed SDK exposes both Chat Completions and the Responses API, note which the-one uses and which capability each shape gates (e.g. reasoning effort may differ across them). Cite the one the adapter actually calls for "wired-through."
- **Cached-token usage**: if the SDK surfaces prompt-cache token fields in usage, that's SDK-exposed Yes for prompt caching even if cache control is automatic — note the accounting gap against `TokenUsage` (contract-level).

## Files Affected
- This leg artifact only. No source code.

---

## Audit Result

**SDK**: `openai` **2.33.0** (read from `.venv/bin/python -c "import openai; print(openai.__version__)"`; pin floor `>=2.16`).
**API shape used by the adapter**: **Chat Completions** — `self.client.chat.completions.create(...)` at `openai_provider.py:132` (`complete`) and `:184` (`stream`). The SDK also ships the **Responses API** (`.venv/.../openai/resources/responses/responses.py`, `responses.create`) and a Responses-only token-counter (`responses.input_tokens.count`, `.venv/.../openai/resources/responses/input_tokens.py:46`), but **the-one never calls Responses** — every "wired-through" verdict below is judged against the Chat Completions path. Citations are to the installed SDK source under `.venv/lib/python3.12/site-packages/openai/`.

| Capability | SDK-exposed | Contract-representable | Wired-through | Gap class | Citation | Notes |
|---|---|---|---|---|---|---|
| Extended thinking | **Partial** | **No** | **No** | **contract-level** (+codec) | SDK: `completion_usage.py:22` `CompletionTokensDetails.reasoning_tokens` (usage-side only); reasoning *content* not on `ChatCompletionMessage` (`chat_completion_message.py:57`, no reasoning field) — replay lives in Responses API, not Chat Completions | Chat Completions surfaces reasoning only as a token *count*, never as a replayable thinking block. Contract has no thinking field on `Message` (`base.py:64-70`). SDK=Partial (count, no replay block via Chat path). |
| Prompt caching | **Yes** | **Partial** | **No** | **contract-level** (+codec) | SDK: `completion_usage.py:40` `PromptTokensDetails.cached_tokens` (cache control is automatic — no breakpoint param, by design) | Caching is automatic server-side; SDK *exposes* it via usage accounting (=Yes per Edge Case #2). `TokenUsage` has only `input/output_tokens` (`base.py:58-61`) → cannot carry `cached_tokens`; adapter reads only `prompt_tokens`/`completion_tokens` (`openai_provider.py:150-152`, `:199-202`). Accounting gap = contract-level (new `TokenUsage` field + codec `_usage_to_dict` `codec.py:67`). |
| Structured outputs / JSON mode | **Yes** | **No** | **No** | **contract-level** | SDK: `chat.completions.create(response_format=...)` `completions.py:97`, `:214` (`_type_to_response_format`); supports json_schema / json_object / Pydantic type | **OpenAI strong surface.** No `response_format` param on `complete()`/`stream()` (`base.py:303-310`, `:314-320`); adapter never sets it (`openai_provider.py:123-130`). Contract-level (new request param). |
| Vision / multimodal | **Yes** | **No** | **No** | **contract-level** (+codec) | SDK: `ChatCompletionContentPartImageParam` (`chat_completion_content_part_image_param.py:22`, `image_url`/`detail`); part union `chat_completion_content_part_param.py:12` | Contract `Message.content` is `str`-only AND assert-enforced (`base.py:135-137`) → image content actively *rejected*. Adapter sends only `str` content (`openai_provider.py:263`). Contract-level: relax assert + widen field + codec. |
| Reasoning-effort controls | **Yes** | **No** | **No** | **contract-level** | SDK: `chat.completions.create(reasoning_effort=...)` `completions.py:113`, `:213`; `ReasoningEffort` = `Literal["none","minimal","low","medium","high","xhigh"]` (`types/shared/reasoning_effort.py`). Also `verbosity` `Literal["low","medium","high"]` (`completions.py:126`) | **OpenAI strong surface.** No `reasoning_effort`/`verbosity` param on `complete()`/`stream()` (`base.py:303-310`); adapter never sets either (`openai_provider.py:123-130`). Contract-level (new request param). |
| Document inputs | **Yes** | **No** | **No** | **contract-level** (+codec) | SDK: `File`/`FileFile` content part — `chat_completion_content_part_param.py:29` (`type:"file"`, `file_data` base64 / `file_id` / `filename`) | First-class file/PDF content part exists in Chat Completions. Same root as vision: `content` is `str` (`base.py:135-137`). Contract-level: widen content + codec. |
| Parallel tool calls | **Partial** | **Partial** | **Partial** | **contract-level** (toggle) / adapter-only (parse) | SDK: `chat.completions.create(parallel_tool_calls=bool)` `completions.py:108`, `:208`; `tool_choice` `completions.py:121` | Adapter parses *multiple* `tool_calls` off the response (`openai_provider.py:136-145` non-stream; `:211-225`+accumulator stream) and sends tool defs (`:130`), so multi-call parse is wired. But the **toggle** (`parallel_tool_calls`) and `tool_choice` are never set (no param on `base.py:303-310`). Partial: parse=yes, toggle=no. Toggle gap = contract-level (new param); no #122/#105 cross-ref applies to OpenAI. |
| Stop sequences | **Yes** | **No** | **No** | **contract-level** | SDK: `chat.completions.create(stop=Union[str, SequenceNotStr[str], None])` `completions.py:117`, `:215` | No `stop` param on `complete()`/`stream()` (`base.py:303-310`); adapter never sets it (`openai_provider.py:123-130`). Contract-level (new request param). |
| Streaming events | **Yes** | **Yes** | **Yes** | **none** | SDK: `chat.completions.create(stream=True, stream_options={"include_usage":True})` `completions.py:119` / `chat_completion_stream_options_param.py` (`include_usage`); typed delta chunks | Adapter streams text deltas, accumulates tool-call deltas by index, and reads the final usage-only chunk (`openai_provider.py:184`, `:195-225`, `:228-234`). `StreamChunk` carries content/tool_calls/usage/message (`base.py:239-243`). Fully wired. (Usage delta still drops cached/reasoning sub-fields — tracked under Prompt caching / Extended thinking rows, not double-counted here.) |
| Token counting | **Partial** | n/a (req-side helper) | **No** | adapter-only (would need Responses) / cross-ref F5 | SDK: `responses.input_tokens.count` (`resources/responses/input_tokens.py:46`) — **Responses API only**; no count-tokens on `chat.completions`; no local tokenizer | the-one uses Chat Completions, which has **no** pre-flight token-count endpoint; the SDK's only counter is on the Responses API the adapter doesn't call. the-one instead does post-hoc usage + a hand-curated context-window prefix table (`OPENAI_MODEL_CONTEXT`, `openai_provider.py:46-59`) because OpenAI `/models` exposes no `context_length`. **Model-catalog / context-window sourcing → cross-ref Flight 5 (do not fix here).** |
| _(catch-all)_ Predicted Outputs | **Yes** | **No** | **No** | **contract-level** | SDK: `chat.completions.create(prediction=ChatCompletionPredictionContentParam)` `completions.py:109`; usage `accepted_prediction_tokens`/`rejected_prediction_tokens` (`completion_usage.py:13`,`:25`) | First-class Chat Completions request kwarg (latency optimization). No contract param; not wired. Bounded catch-all per leg Edge Case #2 (real API surface, not transport). |
| _(catch-all)_ Audio in/out (modalities) | **Yes** | **No** | **No** | **contract-level** (+codec) | SDK: `modalities=["text","audio"]` (`completions.py:106`), `audio` param (`:96`), `ChatCompletionContentPartInputAudioParam`; usage `audio_tokens` (`completion_usage.py:19`,`:37`) | First-class multimodal-audio surface in Chat Completions. Same `content`-str root + no `audio` request param. Listed as a distinct first-class capability; contract-level. |

### Gap summary (for synthesis leg)
- **contract-level (request param only, no codec):** Structured outputs, Reasoning-effort/verbosity, Stop sequences, Parallel-tool-calls toggle. Each = new param on `complete()`/`stream()` (`base.py:303-320`).
- **contract-level + codec:** Prompt-caching accounting (`TokenUsage.cached_tokens`), Extended-thinking (`Message` reasoning field + `reasoning_tokens`), Vision, Document inputs, Audio. Each adds a durable field → also a `the_one/db/codec.py` change (Vision/Document/Audio share the relax-`content`-str-assert root at `base.py:135-137`).
- **none:** Streaming events (fully wired).
- **adapter-only / cross-ref:** Token counting — the SDK counter is Responses-only and the-one uses Chat Completions; context-window sourcing belongs to **Flight 5** (hand-curated `OPENAI_MODEL_CONTEXT`, `openai_provider.py:46-59`).
- **Catch-all rows added:** Predicted Outputs; Audio in/out (modalities). No OpenAI #122/#105 tool-schema cross-ref (those are Anthropic/Ollama).
