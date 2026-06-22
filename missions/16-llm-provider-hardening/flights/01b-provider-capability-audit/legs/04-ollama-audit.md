# Leg: ollama-audit

**Status**: landed
**Flight**: [Provider Capability Audit](../flight.md)

## Objective
Audit Ollama on two tracks — the current raw-`httpx` OpenAI-compatible path (`ollama_provider.py` + `ollama_api.py`) and the official `ollama` SDK delta (docs; SDK not installed) — producing one cited matrix row per capability scored on the three axes, plus a track-b note feeding the mission's Ollama-SDK open question.

## Context
- Scores against the **frozen rubric + contract inventory** in `flight-log.md` (leg `01-audit-rubric`). Do NOT re-derive the contract.
- The `ollama` SDK is **not installed** (confirmed at flight planning) → track b reads official docs, not local source.
- Writes to its **own leg artifact**, not the shared flight log (leg 06 consolidates).
- #105 (open models emit tool calls as fenced text never recovered; `supports_tools()` correctly gates) is owned by Flight 3 — note against the tool-calling row, do not re-derive (Flight 1 already confirmed it).

## Inputs
- `flight-log.md` → `### Rubric & Contract Inventory` (frozen reference).
- `the_one/llm/ollama_provider.py` and `the_one/llm/ollama_api.py` (raw-`httpx` path; `/api/show` capability gate; `/api/tags`/`/api/show` model metadata).
- Official `ollama` Python SDK docs (track b — what the SDK would add over the raw path).

## Outputs
- Filled matrix (one row per capability + catch-all) in this leg's `## Audit Result`, plus a short **track-b delta note** (what the official SDK exposes that the raw path doesn't, feeding the mission's Ollama-SDK open question).

## Acceptance Criteria
- [ ] Each of the ten named frozen-list capabilities, plus any per-SDK catch-all rows, has a row scored on all three axes for **track a (raw `httpx` path)**, with `ollama_provider.py:line` / `ollama_api.py:line` wiring citations.
- [ ] Every "SDK-exposed" judgment names whether it's via the OpenAI-compatible `/v1/chat/completions` surface the raw path uses, or the native `/api/*` surface, with a doc citation.
- [ ] A **track-b delta note** records what the official `ollama` SDK exposes that track a does not (cite official docs), framed as input to the mission open question "official SDK vs raw `httpx`" — NOT a decision (that belongs to the owning flight).
- [ ] Each gap carries a proposed gap class consistent with the inventory.
- [ ] The tool-calling row notes #105 → Flight 3 (cross-ref), and that `supports_tools()` correctly gates non-tool-capable models (per Flight 1).

## Verification Steps
- Confirm one row per frozen-list capability scored for track a.
- Spot-check 2 wiring citations resolve to the cited `ollama_provider.py` / `ollama_api.py` lines.
- Confirm the track-b delta note is present with a doc citation and is framed as input, not decision.

## Implementation Guidance
1. Read the frozen rubric/inventory in `flight-log.md`.
2. Read `ollama_provider.py` and `ollama_api.py` fully — note the raw-`httpx` request building, the `supports_tools()`/`/api/show` gate, streaming parse, and model-metadata calls. These are the track-a wiring citations.
3. For SDK-exposed: track a is judged against the OpenAI-compatible `/v1` surface Ollama serves + the native `/api/*` endpoints (cite Ollama docs). For track b, read the official `ollama` Python SDK docs and note the delta.
4. Fill the matrix rows + write the track-b delta note in `## Audit Result`. Partial honestly.
5. Set leg status `landed`; one-line flight-log Session Notes append. Do NOT commit. Do NOT touch source.

## Edge Cases
- **OpenAI-compatible vs native**: a capability may be absent on `/v1` but present on native `/api/chat` (e.g. structured outputs via `format`). Score track a against what the adapter actually calls, but note in the row if the native surface would expose more — that informs track b.
- **No live calls required**: judge from code + docs. If a capability can only be confirmed by probing a live `/api/show`, tag the cell with a consistent `[live-unverified]` marker (so leg 06 can find them) rather than blocking.

## Files Affected
- This leg artifact only. No source code.

---

## Audit Result

**Provider**: Ollama — **TRACK A** = current raw-`httpx` adapter (`ollama_provider.py` + `ollama_api.py`) over the **OpenAI-compatible `/v1/chat/completions`** surface, with native `/api/show` used only for the capability gate + context-length resolution.

**Surface key**:
- **`/v1`** = OpenAI-compatible endpoint the adapter actually POSTs to ([`/v1/chat/completions` compat doc](https://docs.ollama.com/api/openai-compatibility)).
- **`/api`** = native Ollama REST surface ([`/api/chat`, `/api/generate`, `/api/show` doc](https://github.com/ollama/ollama/blob/main/docs/api.md)). The adapter touches native only via `show_model`/`get_model_capabilities` (`/api/show`), never `/api/chat`.

Scored against the frozen rubric + contract-surface inventory in `flight-log.md`. **SDK-exposed** axis = "does the surface Ollama serves expose it" (per leg IG #3: `/v1` the adapter uses + native `/api/*`). Contract-representable cells reference the frozen `base.py`/`codec.py` inventory.

| Capability | SDK-exposed | Contract-representable | Wired-through | Gap class | Citation | Notes |
|---|---|---|---|---|---|---|
| Extended thinking | Yes (`/v1` `reasoning_effort`/`reasoning`; native `/api/chat` `think`) | No | No | contract-level | `/v1`: [openai-compat "Reasoning/thinking control"](https://docs.ollama.com/api/openai-compatibility); native: [`/api/chat` `think`](https://github.com/ollama/ollama/blob/main/docs/api.md) | Adapter never sets `reasoning_effort`/`think` (request build `ollama_provider.py:90-98`,`:161-169`) nor reads a reasoning/thinking field off the response (`:114-143`, `:189-223`). Contract has no thinking field on `Message` (`base.py:64-70`) + codec round-trip needed (`codec.py:71`/`:105`). |
| Prompt caching | No | No | No | none (no provider-side cache to wire) | n/a — not in [openai-compat fields](https://docs.ollama.com/api/openai-compatibility) nor [native API](https://github.com/ollama/ollama/blob/main/docs/api.md) | Ollama has no cache-control breakpoints / cache-read-creation usage concept. `keep_alive` is VRAM model-residency, NOT prompt caching — out of scope for this row. No SDK surface ⇒ no gap to wire. |
| Structured outputs / JSON mode | Yes (`/v1` `response_format`; native `/api/chat` `format` = `"json"` or JSON schema) | No | No | contract-level | `/v1`: [openai-compat "JSON mode" + `response_format`](https://docs.ollama.com/api/openai-compatibility); native: [`/api/chat` `format`](https://github.com/ollama/ollama/blob/main/docs/api.md) | Adapter sets no `response_format` (`ollama_provider.py:90-98`). Native `/api/chat` `format` accepts a full JSON **schema** (richer than the `/v1` json-mode the adapter would call) — informs track b. No `response_format` param on `complete()`/`stream()` (`base.py:303-310`,`:314-320`). |
| Vision / multimodal | Yes (`/v1` base64 `image_url` content; native `/api/chat` message `images`) | No | No | contract-level | `/v1`: [openai-compat "Vision" — base64 only, image URL unsupported](https://docs.ollama.com/api/openai-compatibility); native: [`/api/chat` message `images`](https://github.com/ollama/ollama/blob/main/docs/api.md) | Adapter builds text-only message content (`_to_api_message` `ollama_provider.py:239-266`); `build_user_message_content` projects a string prefix only. Contract **actively rejects** non-`str` content via assert (`base.py:135-137`). |
| Reasoning-effort controls | Yes (`/v1` `reasoning_effort`) | No | No | contract-level | [openai-compat `reasoning_effort` + `reasoning`](https://docs.ollama.com/api/openai-compatibility) | Same root as Extended thinking: no `reasoning_effort` param on `complete()`/`stream()` (`base.py:303-310`); adapter never sets it (`ollama_provider.py:90-98`). |
| Document inputs | No | No | No | none (no provider-side surface) | n/a — not in [openai-compat](https://docs.ollama.com/api/openai-compatibility) nor [native API](https://github.com/ollama/ollama/blob/main/docs/api.md) | Ollama models no first-class PDF/file content type (only `images`). No SDK surface ⇒ no gap to wire; if ever added it would share the `content`-is-`str` contract-level root (`base.py:135-137`). |
| Parallel tool calls | Partial — `tools` supported on `/v1`; multiple tool calls returned in one turn, but **no `parallel_tool_calls` toggle** and `tool_choice` unsupported on `/v1` | Partial | Partial | adapter-only (parsing); see notes | SDK: [openai-compat "Tools" supported; `tool_choice` unsupported](https://docs.ollama.com/api/openai-compatibility); wired: `ollama_provider.py:97-98`,`:117-129`,`:197-228`; gate `:71-79` → `ollama_api.py:199-225` | **Partial (SDK)**: no parallel toggle, no `tool_choice` on `/v1`. **Partial (wired)**: adapter sends `tools` + parses a list of structured `tool_calls` (multiple supported by index in stream accumulator `:197-228`), but ignores **text-form** tool calls — **see #105 → Flight 3** (` ```tool ` fenced blocks never recovered; not re-derived here). `supports_tools()` (`:71-79`) **correctly gates** non-tool models (Gemma rejects `tools` with 400) — confirmed by Flight 1. Contract carries `tools` param + `ToolCall` (`base.py:303-310`,`:21-25`) but no parallel-toggle param ⇒ Partial. |
| Stop sequences | Yes (`/v1` `stop`; native `options.stop`) | No | No | contract-level | `/v1`: [openai-compat `stop`](https://docs.ollama.com/api/openai-compatibility); native: [`options.stop`](https://github.com/ollama/ollama/blob/main/docs/api.md) | Adapter never sets `stop` (request build `ollama_provider.py:90-98`,`:161-169`). No `stop`/`stop_sequences` param on `complete()`/`stream()` (`base.py:303-310`). |
| Streaming events | Partial — text + tool-call deltas + usage wired; **no typed lifecycle events** (raw SSE dicts, not typed deltas) | Yes | Partial | adapter-only | SDK: [openai-compat streaming + `stream_options`](https://docs.ollama.com/api/openai-compatibility); wired: `ollama_provider.py:145-237`, `ollama_api.chat_stream` `ollama_api.py:228-272` | Adapter streams text deltas (`:191-193`), accumulates tool-call deltas by index (`:197-215`), emits usage via `stream_options.include_usage` (`:166`,`:182-223`), and a final `StreamChunk` with `message` (`:230-237`). Contract `StreamChunk` carries content/is_final/tool_calls/usage/message (`base.py:228-243`) — fully representable. **Partial (wired)**: no thinking/reasoning delta parsed; lifecycle is start/final only, no typed event taxonomy. |
| Token counting | Partial — usage returned **post-response** (`prompt_tokens`/`completion_tokens` on `/v1`; `prompt_eval_count`/`eval_count` native); **no pre-flight count-tokens endpoint** | Partial | Partial | contract-level (pre-flight) / adapter (post-hoc done) | SDK: [openai-compat usage](https://docs.ollama.com/api/openai-compatibility), [native `eval_count`/`prompt_eval_count`](https://github.com/ollama/ollama/blob/main/docs/api.md); wired: `ollama_provider.py:131-137`,`:182-223` | **Partial (SDK)**: Ollama exposes **usage accounting**, not a dedicated pre-flight count-tokens endpoint (cf. Anthropic `count_tokens`). Adapter parses post-response usage into `TokenUsage` (`:131-137`,`:218-223`). Note the byte-heuristic interim-usage path (`BYTES_PER_TOKEN_OLLAMA`, `_StreamAccumulator`, `:175`,`:194`) is an *estimate*, not a server count. `TokenUsage` carries only input/output (`base.py:58-61`) — sufficient here; pre-flight counting has no contract entry point. |
| _(catch-all)_ Model lifecycle / metadata (native `/api/tags`, `/api/ps`, `/api/show`, `/api/pull`, `/api/delete`, `/api/generate` load/unload) | Yes (native `/api/*`) | Partial (context-window only) | Yes | adapter-only / out-of-contract | wired: `ollama_api.py:88-105`(`tags`),`:108-124`(`ps`),`:127-161`(`show`),`:199-225`(capabilities),`:275-302`(`pull`),`:305-319`(`delete`),`:322-378`(load/unload); context resolve `ollama_provider.py:59-69` | Native-only surface the SDK models as first-class; raw path already wires it. First-class catch-all because `supports_tools()` (`base.py:335-345`) and `_resolve_max_context_tokens()` (`base.py:276-301`) hooks consume `/api/show` (`capabilities`, `model_info.*.context_length` via `extract_ollama_context_length` `ollama_api.py:164-181`). Bounded per leg Edge Case #2 — these are first-class API objects, not transport details. `[live-unverified]`: the actual `capabilities` list + `model_info.*.context_length` values are only confirmable against a live `/api/show`; code path is wired but per-model contents unverified offline. |

**`[live-unverified]` tags**: only the per-model `/api/show` payload contents (capabilities list values, `context_length`) in the catch-all row — the code path is confirmed wired; the runtime values require a live probe (no live call made, per leg Edge Case #2).

### Track-B Delta Note (official `ollama` Python SDK — INPUT to mission open question "official SDK vs raw `httpx`", NOT a decision)

The official `ollama` Python SDK is **not installed** (confirmed at flight planning); this is read from its public types/docs only. Source: [`ollama-python` `_types.py`](https://github.com/ollama/ollama-python/blob/main/ollama/_types.py), [`ollama-python` README](https://github.com/ollama/ollama-python). The SDK targets the **native `/api/*`** surface (typed), whereas track a targets the **OpenAI-compatible `/v1`** surface (hand-built dicts). What the SDK exposes as first-class typed params/objects that track a does **not** wire today:

- **`format`** on `ChatRequest` — native structured outputs accepting a full JSON **schema** (not just `/v1` json-mode). Richer than the `response_format` the `/v1` path would use.
- **`think`** request param + **`Message.thinking`** typed response field — first-class extended-thinking emit AND replay surface. Track a has neither.
- **`Message.images`** — typed multimodal input on the native message (vs. the adapter's text-only `/v1` projection).
- **`options`** — typed catch-all for Modelfile params (`stop`, `temperature`, `num_ctx`, etc.) on the native surface; track a only passes `temperature`/`max_tokens`/`stop`(absent) as flat `/v1` fields.
- **`keep_alive`** — typed VRAM-residency control on the chat/generate request (track a sets it only on the *separate* native load/unload helpers, not on chat).
- **`logprobs` / `top_logprobs`** — typed on `ChatRequest`; note `/v1` openai-compat **does not** support logprobs, so this is a native-SDK-only gain.
- **Typed `ChatResponse` / `Message`** objects (`tool_calls`, `tool_name`, `eval_count`/`prompt_eval_count`) and typed helpers (`chat`, `generate`, `embed`, `ps`, `show`, `list`, `pull`, `create`, `delete`) — replaces the raw-dict parsing + the bespoke `ollama_api.py` wrappers track a maintains.
- **`embed` / `EmbedRequest`** (`input`, `dimensions`, `truncate`) — embeddings as a first-class typed call; track a has no embeddings path.

**Frame**: this delta is evidence for the mission open question, not a recommendation. Adopting the SDK would mean a `/v1`→native-`/api/*` migration and trading hand-built dicts for typed objects; whether that is worth it (vs. keeping the broad OpenAI-compatible path that also serves LM Studio / vLLM / llama.cpp per `ollama_provider.py:31-35`) is a decision for the owning flight.
