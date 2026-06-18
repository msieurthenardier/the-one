# Flight Log: Provider Capability Audit

**Mission**: [LLM Provider Layer Hardening](../../mission.md)
**Flight**: [Provider Capability Audit](./flight.md)

> Read-only recon flight. This log is the **deliverable**: the cross-provider
> capability matrix and the ratified gap backlog land in the sections below (DD1).

---

## Capability Matrix

### Rubric & Contract Inventory

> Frozen audit framework (leg `01-audit-rubric`). The four provider-audit legs
> score against THIS reference — they do not re-read the contract. Do not edit
> the inventory line citations without re-reading `the_one/llm/base.py`.

#### Capability list (matrix rows)

Each provider audit produces one row per capability below. The first ten are the
mission's named capabilities; the eleventh is a bounded catch-all.

1. **Extended thinking** (reasoning/thinking blocks — emit + replay)
2. **Prompt caching** (cache-control breakpoints + cache-read/creation usage)
3. **Structured outputs / JSON mode** (schema-constrained or JSON-forced responses)
4. **Vision / multimodal** (image inputs in a message)
5. **Reasoning-effort controls** (effort/verbosity knobs, e.g. OpenAI `reasoning_effort`)
6. **Document inputs** (PDF/file inputs as first-class content)
7. **Parallel tool calls** (multiple tool calls in one assistant turn + the toggle)
8. **Stop sequences** (`stop`/`stop_sequences` request param)
9. **Streaming events** (typed stream deltas: text, tool-call deltas, usage, lifecycle)
10. **Token counting** (pre-flight token-count / count-tokens endpoint or SDK helper)
11. **Per-SDK catch-all** — auditors add any *additional* capability the official
    SDK surfaces as a **first-class API parameter or object** (e.g. a dedicated
    request kwarg, a typed content block, a typed response field). **Bounded (leg
    Edge Case #2):** do NOT add raw transport details, HTTP headers, retry/timeout
    knobs, or undocumented fields — only capabilities the SDK models as first-class
    API surface. One row per such capability, same columns, same citation rule.

#### Three-axis rubric (DD4)

Each capability is scored per provider on three independent axes. Use the exact
decision rule; when a capability only partially satisfies an axis, score it
**Partial** and name the specific missing piece (leg Edge Case #1) rather than
forcing a binary.

- **SDK-exposed** — *Does the provider's official SDK surface this capability as a
  first-class API parameter/object?*
  - **Yes**: the SDK has a named request param, typed content block, or typed
    response field for it. Cite the symbol/path or doc URL (see citation convention).
  - **No**: not present in the SDK's public API surface.
  - **Partial**: surfaced but incomplete for our use (e.g. emit-only, no replay;
    one sub-field missing). Name the gap.
- **Contract-representable** — *Can the-one's `LLMProvider` contract carry this
  capability end-to-end — accept it as input AND round-trip it through persistence?*
  Scored against the **contract-surface inventory** below (the frozen reference).
  - **Yes**: an existing param on `complete()`/`stream()` accepts the input AND
    (if it produces durable state on a `Message`) an existing `Message`/`ToolCall`/
    `ToolResult`/`TokenUsage`/`StreamChunk` field carries it AND the codec
    (`the_one/db/codec.py`) round-trips that field. Round-trip is part of the axis,
    not just the dataclass field — see the persistence note in the inventory.
  - **No**: no param accepts it and/or no field can carry it (and/or the field
    exists but the codec drops it).
  - **Partial**: representable on one side only (e.g. `StreamChunk` carries usage
    but no field carries cache-read tokens). Name the missing field/param.
- **Wired-through** — *Does the-one's adapter for this provider actually build the
  param on the request and parse the capability off the response today?*
  - **Yes**: the provider adapter sets the request param AND reads it back into the
    contract objects. Cite the adapter file:line.
  - **No**: the adapter ignores it (param never set / response field never read).
  - **Partial**: half-wired (sent but not parsed back, or vice versa). Name which.

**Gap classification rule** (per gap, used by the synthesis leg's backlog):

- **contract-level** — closing the gap requires changing the contract in
  `base.py` (new param on `complete()`/`stream()`, new field on a dataclass,
  relaxing the `content`-is-`str` assert). **Implication:** any gap that adds a
  durable `Message`/`ToolCall`/`ToolResult`/`TokenUsage` field is contract-level
  AND **also implies a codec change** — the persistence round-trip is part of
  "contract-representable" (see inventory note + codec pointer below). Mark these
  so they aren't under-scoped.
- **adapter-only** — the contract already represents it; only the provider adapter
  (e.g. `anthropic_provider.py`) needs to set the request param / parse the response.
  No `base.py` or codec change.
- **none** — already fully wired-through; no gap.

#### Contract-surface inventory (frozen reference — `base.py` citations)

This is exactly what the contract can represent **today**. The "contract-representable"
axis is scored against this and nothing else.

| Surface | Location | What it can carry |
|---|---|---|
| `complete()` accepted params | `base.py:303-333` (sig `303-310`; `stream()` mirror `314-320`) | `messages`, `tools`, `temperature`, `max_tokens` — **and nothing else** |
| `Message` fields | `base.py:64-70` (full class `64-119`) | `role`, `content` (str), `tool_calls`, `tool_result`, `usage` (+ M10/M11 routing fields `visibility`/`peer_name`/`channel_id`/`channel_name`, `79-119`) |
| `ToolCall` | `base.py:21-25` | `id`, `name`, `arguments: dict` |
| `ToolResult` (normalize-to-`str`) | `base.py:28-56` (`__post_init__` `40-55`) | `tool_call_id`, `content` (widened input `str\|dict\|list` but **normalized to `str`** at construction, `54-55`), `is_error`, `metadata` |
| `TokenUsage` fields | `base.py:58-61` | `input_tokens`, `output_tokens` — **only these two** |
| `StreamChunk` fields | `base.py:228-243` (fields `239-243`) | `content` (delta), `is_final`, `tool_calls`, `usage`, `message` |
| `supports_tools()` hook | `base.py:335-345` | per-model tool-capability gate (default `True`) |
| `tool_schema()` hook | `base.py:347-360` | canonical tool-def → provider format (default OpenAI shape) |
| `_resolve_max_context_tokens()` hook | `base.py:276-301` (override `276-279`; lazy wrapper `281-301`) | per-model context-window resolution |

**Contract-visible gaps (already evident from `base.py` alone, no provider read needed):**

- **No thinking/reasoning field on `Message`** (`base.py:64-70`) — extended-thinking
  blocks cannot be stored or replayed. *contract-level.*
- **`content` is `str`-only AND assert-enforced** at construction
  (`base.py:135-137`) — a non-`str` `Message.content` raises `AssertionError`, so
  vision/multimodal content is **actively rejected, not merely unmodeled**. Closing
  this means relaxing the assert + widening the field. *contract-level.*
- **`TokenUsage` has no cache-read / cache-creation fields** (`base.py:58-61`, only
  `input_tokens`/`output_tokens`) — prompt-cache usage accounting cannot be
  represented. (cf. Flight 1's any-llm note: any-llm maps
  `cache_read_input_tokens`/`cache_creation_input_tokens`.) *contract-level.*
- **No `stop` / `response_format` / `reasoning_effort` params** on `complete()` /
  `stream()` (`base.py:303-310`, `314-320`) — stop sequences, structured-output/JSON
  mode, and reasoning-effort controls have no request-side entry point. *contract-level.*
- **No document/file content type** — same root as the multimodal gap: `content`
  is `str`. *contract-level.*

**Persistence round-trip note (codec pointer — leg AC #4):** "contract-representable"
includes round-trip through persistence, NOT just the presence of a field on a
dataclass. The `Message` persistence codec is **`the_one/db/codec.py`** —
`message_to_dict` (`codec.py:71`) / `message_from_dict` (`codec.py:105`), driven by
`encode_messages`/`decode_messages` (`codec.py:144`/`149`), with per-field helpers
(`_tool_call_to_dict`, `_tool_result_to_dict` `:54`, `_usage_to_dict` `:67`).
**Therefore any contract-level gap that adds a `Message`/`ToolCall`/`ToolResult`/
`TokenUsage` field ALSO requires a codec change** (a new emit-when-non-None key in
`*_to_dict` + a `d.get(...)` read in `*_from_dict`, matching the existing
`peer_name`/`channel_id` back-compat pattern). Auditors must not score such a gap
as adapter-only and must not under-scope it.

#### Matrix template (providers copy/fill this per provider — do NOT fill here)

One table per provider in that provider's leg artifact; one row per capability from
the list above (plus any catch-all rows). The synthesis leg consolidates them here.

| Capability | SDK-exposed | Contract-representable | Wired-through | Gap class (contract-level / adapter-only / none) | Citation | Notes |
|---|---|---|---|---|---|---|
| Extended thinking | | | | | | |
| Prompt caching | | | | | | |
| Structured outputs / JSON mode | | | | | | |
| Vision / multimodal | | | | | | |
| Reasoning-effort controls | | | | | | |
| Document inputs | | | | | | |
| Parallel tool calls | | | | | | |
| Stop sequences | | | | | | |
| Streaming events | | | | | | |
| Token counting | | | | | | |
| _(per-SDK catch-all: add rows)_ | | | | | | |

#### Citation convention (DD5)

- Every **SDK-exposed = Yes/Partial** cell MUST name a concrete source: an SDK
  symbol/path (e.g. `anthropic.types.ThinkingConfigParam`, or
  `anthropic SDK: messages.create(..., thinking=...)`) **or** a doc URL. A bare
  "Yes" with no citation is not acceptable.
- Every **Wired-through = Yes/Partial** cell SHOULD cite the-one adapter `file:line`.
- **Contract-representable** cells reference this inventory (cite the `base.py`
  line range and, for durable fields, the codec).
- Put the primary citation in the **Citation** column; use **Notes** for the
  Partial-reason or the specific missing field/param.

#### #122 / #105 cross-references (tracked in their owning flights — not re-derived here)

Per Flight 1's confirmed root causes (`../01-recon-root-cause-spike/flight-log.md`),
two known bugs touch the tool-calling rows. The audit **relates** them; it does not
re-investigate or re-derive them:

- **#122 — Anthropic tool `input_schema` rejection** (top-level `oneOf`/`allOf`/`anyOf`,
  and missing top-level `type`). Cross-reference against the **Parallel tool calls**
  row and any tool-calling notes for **Anthropic**. **Owned by Flight 2** (the new
  HIGH-priority `input_schema` compatibility flight). Auditors note "see #122 / F2",
  do not score a fix here. Root cause: verbatim schema passthrough at
  `anthropic_provider.py:210-215`.
- **#105 — Ollama/Gemma text-form tool calls** (model emits a ` ```tool ` fenced
  Python-call block; parser reads only structured `tool_calls`). Cross-reference
  against the **Parallel tool calls** row and tool-calling notes for **Ollama**.
  **Owned by Flight 3** (open-model tool-use robustness). Auditors note
  "see #105 / F3", do not score a fix here. Root cause: capability gate correctly
  drops tools (`ollama_provider.py:71-79`); parser ignores text-form calls
  (`ollama_provider.py:117-129`, `:197-228`).

### Consolidated Cross-Provider Matrix

> Synthesis leg (`06-synthesis-and-ratification`) consolidation of the four landed
> provider audits. Each cell = three-axis verdict shorthand (**SDK** / **Contract** /
> **Wired**, each Y/N/P) + gap class. Citations are NOT duplicated here — see the
> source leg (02 Anthropic, 03 OpenAI, 04 Ollama track-a, 05 OpenRouter) for the
> symbol/path and adapter file:line behind each cell. OpenRouter is a thin
> `OpenAIProvider` subclass (`openrouter_provider.py:46`); its inherited rows carry
> OpenAI's verdict (reconciled against 03), with its three genuine deltas flagged.
> "model-dep" = OpenRouter advertises this per-route via `/models`
> `supported_parameters` (see 05). Gap-class abbreviations: **CL** = contract-level,
> **CL+codec** = contract-level requiring a `db/codec.py` round-trip change, **AO** =
> adapter-only, **none** = fully wired, **N/A** = no provider-side surface to wire.

| Capability | Anthropic (see 02) | OpenAI (see 03) | Ollama track-a (see 04) | OpenRouter (see 05) |
|---|---|---|---|---|
| Extended thinking | SDK:Y / Contract:N / Wired:N — **CL+codec** | SDK:P (count, no replay via Chat) / Contract:N / Wired:N — **CL+codec** | SDK:Y (`/v1` `reasoning`, native `think`) / Contract:N / Wired:N — **CL+codec** | inherits OpenAI; model-dep — **CL+codec (inherited)** |
| Prompt caching | SDK:Y / Contract:P / Wired:N — **CL+codec** | SDK:Y (auto; usage `cached_tokens`) / Contract:P / Wired:N — **CL+codec** | SDK:N / Contract:N / Wired:N — **none (no provider cache)** | inherits OpenAI; model-dep — **CL+codec (inherited)** |
| Structured outputs / JSON mode | SDK:Y / Contract:N / Wired:N — **CL** | SDK:Y / Contract:N / Wired:N — **CL** | SDK:Y (`/v1` `response_format`; native `format`=schema) / Contract:N / Wired:N — **CL** | inherits OpenAI; model-dep — **CL (inherited)** |
| Vision / multimodal | SDK:Y / Contract:N / Wired:N — **CL+codec** | SDK:Y / Contract:N / Wired:N — **CL+codec** | SDK:Y (`/v1` base64 `image_url`; native `images`) / Contract:N / Wired:N — **CL+codec** | inherits OpenAI; model-dep — **CL+codec (inherited)** |
| Reasoning-effort controls | SDK:Y (`output_config.effort`) / Contract:N / Wired:N — **CL** | SDK:Y (`reasoning_effort`+`verbosity`) / Contract:N / Wired:N — **CL** | SDK:Y (`/v1` `reasoning_effort`) / Contract:N / Wired:N — **CL** | inherits OpenAI; model-dep — **CL (inherited)** |
| Document inputs | SDK:Y / Contract:N / Wired:N — **CL+codec** | SDK:Y (`file` content part) / Contract:N / Wired:N — **CL+codec** | SDK:N (only `images`) / Contract:N / Wired:N — **none (no provider surface)** | inherits OpenAI; model-dep — **CL+codec (inherited)** |
| Parallel tool calls | SDK:Y / Contract:P / Wired:P — **CL (toggle) / AO (parse done)** | SDK:P / Contract:P / Wired:P — **CL (toggle) / AO (parse done)** | SDK:P (multi-call yes; no toggle, no `tool_choice` on `/v1`) / Contract:P / Wired:P — **AO (parse) / no toggle surface** | inherits OpenAI parse+toggle gap; **delta:** live `supports_tools` per-route gate (`openrouter_provider.py:142-154`) — **AO delta** |
| Stop sequences | SDK:Y / Contract:N / Wired:N — **CL** | SDK:Y / Contract:N / Wired:N — **CL** | SDK:Y (`/v1` `stop`; native `options.stop`) / Contract:N / Wired:N — **CL** | inherits OpenAI; model-dep — **CL (inherited)** |
| Streaming events | SDK:Y / Contract:P / Wired:P — **AO (fidelity: interim usage is byte-heuristic, not raw events)** | SDK:Y / Contract:Y / Wired:Y — **none** | SDK:P (text+tool+usage deltas; no typed lifecycle) / Contract:Y / Wired:P — **AO** | inherits OpenAI `stream()` (Wired:Y) — **none (inherited)** |
| Token counting | SDK:Y (`messages.count_tokens`) / Contract:N / Wired:N — **CL (pre-flight helper)** | SDK:P (count is Responses-only; adapter on Chat) / Contract:n/a / Wired:N — **AO / →F5 (catalog)** | SDK:P (post-hoc usage only; no pre-flight endpoint) / Contract:P / Wired:P — **CL (pre-flight) / AO (post-hoc done)** | inherits OpenAI (no count endpoint); **delta:** interim bytes-per-token override (`openrouter_provider.py:134-140`, value-identical) — **AO delta** |
| _(catch-all)_ Citations | SDK:Y / Contract:N / Wired:N — **CL** | N/A | N/A | N/A |
| _(catch-all)_ Message Batches | SDK:Y / Contract:N / Wired:N — **out-of-scope (bulk workflow, not a per-call capability)** | N/A | N/A | N/A |
| _(catch-all)_ Server-side tools (web_search / code_execution / web_fetch) | SDK:Y / Contract:N / Wired:N — **CL (low priority)** | N/A | N/A | N/A |
| _(catch-all)_ Predicted Outputs | N/A | SDK:Y (`prediction` kwarg) / Contract:N / Wired:N — **CL** | N/A | N/A |
| _(catch-all)_ Audio in/out (modalities) | N/A | SDK:Y (`modalities`+`audio`) / Contract:N / Wired:N — **CL+codec** | N/A | N/A |
| _(catch-all)_ Model lifecycle / metadata (native `/api/tags`,`/ps`,`/show`,`/pull`,`/delete`, load/unload) | N/A | N/A | SDK:Y (native `/api/*`) / Contract:P (context-window only) / Wired:Y — **AO / out-of-contract** | N/A |
| _(catch-all)_ Context-window resolution (`_resolve_max_context_tokens` hook) | N/A (prefix-table, OpenAI shares) | N/A (hand-curated `OPENAI_MODEL_CONTEXT`, →F5) | (native `/api/show` `context_length`, wired via gate) | SDK:Y (`/models` `context_length`) / Contract:Y (hook) / Wired:Y — **delta, none (fully wired)** |
| _(catch-all)_ Per-model capability discovery (`/models` `supported_parameters`) | N/A | N/A | N/A | SDK:Y (first-class list) / Contract:n/a (discovery mechanism) / Wired:P (only `tools` gate consulted) — **AO (the lever for model-dep wiring)** |

> **Cross-provider reading.** The dominant pattern is **contract-level**: the contract
> carries only `messages`/`tools`/`temperature`/`max_tokens` (`base.py:303-310`), so
> nearly every capability that any provider's SDK exposes is blocked at the contract,
> not the adapter. Adapter-only gaps are the minority (streaming fidelity, wiring an
> already-representable knob, OpenRouter's `supported_parameters` consultation). The
> highest-leverage moves are therefore **shared contract-level enablers** that unblock
> several providers at once — see the backlog below.

## Gap Backlog (proposed → ratified)

> Synthesis leg proposal. Structured in three parts: **(A)** shared contract-level
> enablers (each unblocks multiple providers — highest leverage), **(B)** adapter-only
> gaps, **(C)** routed-elsewhere items (tracked in their owning flight, no fix proposed
> here). Priorities/efforts/risks below are **PROPOSED** — the operator ratifies (see
> the pending ratification block at the end of this section). Prioritization logic: a
> contract-level enabler that unblocks multiple providers at low/known effort ranks
> above any single-provider adapter tweak.

### (A) Shared contract-level enablers (highest leverage)

**A1 — Thinking/reasoning field on `Message` + codec round-trip.**
- Gap class: contract-level + codec (`base.py:64-70` has no thinking field; `db/codec.py` `message_to_dict`/`message_from_dict` round-trip).
- Affected providers: **Anthropic full** (SDK:Y signed `ThinkingBlock`, emit+replay); **OpenAI partial** (Chat surfaces only `reasoning_tokens` count, no replay block); **Ollama partial** (`/v1 reasoning` / native `think`; replay only on native `/api/chat`). OpenRouter inherits.
- Proposed priority: **High**.
- Effort: **M** — the *capture* side is de-risked by Flight 1 (`get_final_message` already carries signed thinking blocks); remaining work is the typed `Message` field + codec emit/read keys + Anthropic adapter parse. (OpenAI/Ollama replay is partial regardless of contract.)
- Risk: codec back-compat — must follow the existing emit-when-non-None / `d.get(...)` pattern (like `peer_name`/`channel_id`) so old persisted messages still decode.
- Rationale: unblocks Anthropic extended-thinking end-to-end (store+replay) and is the single most-cited contract-level gap; multi-provider.

**A2 — Widen `Message.content` off the str-assert for vision + document inputs.**
- Gap class: contract-level + codec (relax the assert at `base.py:135-137`, widen the field, codec round-trip).
- Affected providers: **Anthropic** (image + document/PDF blocks), **OpenAI** (image + `file` content part), **Ollama** (`/v1` base64 image / native `images`; no document surface). OpenRouter inherits.
- Proposed priority: **High**.
- Effort: **L** — content is `str`-only AND assert-enforced (actively rejects non-str today), so this touches construction, every adapter's `_to_api_message` projection, and the codec. Largest single-field blast radius.
- Risk: highest of the enablers — every adapter currently assumes `str` content; relaxing the assert without updating each projection would silently mis-serialize. Needs careful per-adapter content-list branches.
- Rationale: one root unblocks both Vision and Document inputs across three providers; both capabilities are blocked solely by this assert.

**A3 — `TokenUsage` cache-read / cache-creation fields + codec.**
- Gap class: contract-level + codec (`base.py:58-61` carries only `input_tokens`/`output_tokens`; `_usage_to_dict` `codec.py:67`).
- Affected providers: **Anthropic** (`cache_creation_input_tokens`/`cache_read_input_tokens`), **OpenAI** (`cached_tokens` prompt-cache accounting). Ollama N/A (no provider cache). OpenRouter inherits OpenAI.
- Proposed priority: **Medium**.
- Effort: **S** — two nullable int fields + codec emit/read; mirrors the any-llm mapping. Adapter parse is a few lines each.
- Risk: low. Purely additive accounting; no behavior change beyond richer usage.
- Rationale: enables prompt-cache cost accounting for the two providers that expose it; small, additive, low-risk.

**A4 — New request params on `complete()`/`stream()`: stop sequences, response_format/structured-outputs, reasoning_effort.**
- Gap class: contract-level, **no codec** (request-side params only, not durable state) — `base.py:303-310`, `314-320`.
- Affected providers: **all** — stop (Anthropic/OpenAI/Ollama; OpenRouter inherits), response_format (Anthropic `output_config`, OpenAI strong, Ollama `/v1 response_format`/native schema), reasoning_effort (Anthropic `output_config.effort`, OpenAI `reasoning_effort`+`verbosity`, Ollama `/v1`).
- Proposed priority: **High**.
- Effort: **M** — three new optional params plumbed through both `complete()`/`stream()` signatures and each adapter's request builder; no persistence, so no codec risk.
- Risk: low-moderate — signature change on the contract method touches every provider's `_build_kwargs`/request build, but each is a straightforward optional-param passthrough. Per-provider naming differs (e.g. Anthropic folds effort+format into `output_config`) so the adapter maps the canonical param to its SDK shape.
- Rationale: one signature change unblocks three named capabilities across all four providers; no codec, so cheaper than the durable-field enablers. Highest breadth-per-effort.

**A5 — Parallel-tool-call toggle (`tool_choice` / disable-parallel) on the contract + adapter-only parse-back.**
- Gap class: **contract-level** for the toggle param (no `tool_choice`/parallel param on `base.py:303-310`); **adapter-only** for parse-back — and note both providers already parse multiple `tool_calls` today, so the parse half is effectively done.
- Affected providers: **Anthropic** (`tool_choice.disable_parallel_tool_use`), **OpenAI** (`parallel_tool_calls` bool + `tool_choice`). Ollama: `/v1` has no toggle / no `tool_choice` (so toggle is un-exposable on track-a). OpenRouter inherits OpenAI's toggle gap (its own delta is the per-route `supports_tools` gate, which is already wired).
- Proposed priority: **Low**.
- Effort: **S** — one optional toggle param + adapter mapping; parse-back already wired for Anthropic/OpenAI/Ollama.
- Risk: low. Ollama can't honor the toggle on `/v1` (must no-op or document), so the param is best-effort per provider.
- Rationale: smaller payoff (control knob, not a new modality) and not honorable on Ollama track-a; ranks below the higher-breadth enablers.

### (B) Adapter-only gaps

**B1 — Anthropic streaming usage fidelity (raw-event iteration).**
- Gap class: adapter-only (no contract change). Affected: **Anthropic** only.
- Proposed priority: **Low**. Effort: **M**. Risk: moderate — swapping `text_stream`/`get_final_message` for raw `RawMessageStreamEvent` iteration is a stream-loop rewrite; current byte-heuristic interim usage works.
- Rationale: interim usage is an estimate, not real `message_delta` usage; cosmetic for accounting, not a capability gap.

**B2 — Ollama streaming lifecycle / typed-event fidelity.**
- Gap class: adapter-only. Affected: **Ollama** only.
- Proposed priority: **Low**. Effort: **S**. Risk: low.
- Rationale: text+tool+usage deltas are wired; only typed lifecycle taxonomy + a reasoning/thinking delta parse are missing. The thinking-delta parse becomes useful only once A1 lands.

**B3 — Anthropic pre-flight token counting (`messages.count_tokens`).**
- Gap class: contract-level for a *new contract method* (no count helper on `LLMProvider`), but no codec and no durable state — listed here as the lone provider with a real pre-flight endpoint. Affected: **Anthropic** (OpenAI's counter is Responses-only and unused; Ollama has none).
- Proposed priority: **Low**. Effort: **S**. Risk: low.
- Rationale: single-provider; nice-to-have pre-flight budgeting. Ranks low because only one provider exposes a true pre-flight endpoint.

**B4 — OpenRouter `supported_parameters` consultation for model-dependent wiring.**
- Gap class: adapter-only (the discovery surface exists; gate already reads it for `tools`). Affected: **OpenRouter** only (the lever; the *carried* capability still needs the A-series contract changes).
- Proposed priority: **Low**. Effort: **M**. Risk: low.
- Rationale: today only the `tools` gate consults `/models` `supported_parameters`; extending it to gate response_format/reasoning/stop per-route is adapter-only, but only valuable after the A4 params exist to gate.

### (C) Routed elsewhere (tracked there — no fix or priority proposed here)

- **#122 — Anthropic tool `input_schema` rejection** (top-level `oneOf`/`allOf`/`anyOf` + missing top-level `type`; verbatim passthrough `anthropic_provider.py:210-215`). **→ Flight 2 (tracked-there).** Surfaces against the Anthropic parallel-tool-calls row; not re-scoped here.
- **#105 — Ollama/Gemma text-form tool calls** (` ```tool ` fenced block never recovered; gate correctly drops tools, parser ignores text-form). **→ Flight 3 (tracked-there).** Surfaces against the Ollama parallel-tool-calls row.
- **Model-catalog / context-window sourcing** (OpenAI `/models` exposes no `context_length`, so `OPENAI_MODEL_CONTEXT` is hand-curated `openai_provider.py:46-59`; OpenRouter resolves live but the broader catalog story is cross-provider). **→ Flight 5 (tracked-there).**

### Operator Ratification (2026-06-17)

Operator ratified the proposed backlog via the Flight Director, with the following
dispositions:

- **High tier confirmed as-is** — A1 (thinking field), A2 (content-widening for
  vision + documents), and A4 (request params: stop / response_format /
  reasoning_effort) all **stay High**. The operator explicitly accepted that A2 —
  the heaviest, highest-risk enabler (relaxing the `content`-is-`str` assert at
  `base.py:135-137`, touching every adapter + codec) — is wanted alongside A1/A4
  rather than demoted.
- **A3** (`TokenUsage` cache fields) **Medium**, **A5** (parallel-tool-call toggle)
  **Low** — confirmed as proposed.
- **B1–B4** (adapter-only) **Low** — confirmed as proposed.
- **#122 / #105 / model-catalog** — confirmed routed to Flights 2 / 3 / 5; not
  prioritized here.

**Sequencing decision:** the **first capability flight** (sequenced *after* the
HIGH bug-fix flights — Flight 2 #122, Flight 3 #105) is **A1 — extended thinking**
(thinking field on `Message` + codec round-trip + Anthropic capture/replay). Chosen
over A4 and A2 because its capture side is already de-risked by Flight 1
(`get_final_message()` carries signed thinking blocks) and it closes the mission's
named extended-thinking success criteria. A4 and A2 remain High and follow per the
operator's later prioritization.

No proposed priority was overridden. This closes leg 06's final acceptance
criterion (operator ratification recorded).

---

## Mission Open-Question Disposition

> Synthesis leg disposition of the four still-open mission open questions. Each is
> marked **answerable-now** (with audit evidence) or **deferred-to-owning-flight**.

**OQ1 — Ollama official SDK vs raw `httpx`.** *Answerable-now (as scoped input, not a
decision).* Evidence: leg 04's track-b delta note. The official `ollama` SDK targets
the native `/api/*` surface (typed) and would add first-class `format` (schema),
`think` + `Message.thinking` (extended-thinking emit AND replay), `Message.images`,
typed `options`, `logprobs`/`top_logprobs` (note: `/v1` does not support logprobs),
typed `ChatResponse`/`Message`, and `embed`. Track-a uses the OpenAI-compatible `/v1`
surface (hand-built dicts) which also serves LM Studio / vLLM / llama.cpp. The
decision (migrate vs keep the broad `/v1` path) belongs to the owning flight; this
synthesis confirms the SDK's concrete delta as input.

**OQ2 — Model-catalog / context-window sourcing.** *Deferred to Flight 5.* Why: OpenAI's
`/models` exposes no `context_length`, so `OPENAI_MODEL_CONTEXT` is hand-curated
(`openai_provider.py:46-59`); Anthropic uses a prefix-table resolver; OpenRouter
already resolves live off `/models` `context_length` and Ollama off native
`/api/show`. The cross-provider catalog/context-window story is Flight 5's charter —
not re-scoped here (see backlog part C).

**OQ3 — Reasoning beyond Anthropic.** *Answerable-now (scoped).* Evidence: OpenAI
exposes `reasoning_effort` (`Literal["none","minimal","low","medium","high","xhigh"]`)
+ `verbosity` on Chat Completions (leg 03); Ollama exposes `/v1 reasoning_effort` and
native `think` (leg 04). So reasoning **controls** are an all-provider request-side
surface → covered by backlog **A4** (reasoning_effort request param, contract-level no
codec). Reasoning **replay/storage** (the thinking block itself) is partial off
Anthropic and is the separate **A1** enabler. Scope: A4 gives every provider the effort
knob; A1 gives durable thinking capture (full only on Anthropic + native Ollama).

**OQ4 — Thinking representation.** *Answerable-now (design input).* Evidence: this
synthesis's **A1** analysis — a typed thinking/reasoning field on `Message` + a
`db/codec.py` round-trip (emit-when-non-None / `d.get(...)`, mirroring
`peer_name`/`channel_id` back-compat). Capture is de-risked by Flight 1
(`get_final_message` carries signed `ThinkingBlock`s). This is the recommended
representation; ratification of A1's priority decides scheduling.

---

## Session Notes

_(chronological notes from work sessions)_

**2026-06-17 — Leg `01-audit-rubric` landed.** Froze the audit framework under
`## Capability Matrix → Rubric & Contract Inventory`: 10 mission capabilities + a
bounded per-SDK catch-all row, the DD4 three-axis rubric (SDK-exposed /
contract-representable / wired-through) with decision rules + contract-level-vs-
adapter-only gap classification, the contract-surface inventory with verbatim
`base.py` citations and the contract-visible gaps (no thinking field; `content`
str-only assert-enforced at `base.py:135-137`; `TokenUsage` lacks cache fields; no
stop/response_format/reasoning_effort params), the `Message` codec pointer
(`the_one/db/codec.py`) tying contract-representable to persistence round-trip, the
fillable matrix template + DD5 citation convention, and #122→F2 / #105→F3
cross-references. No provider rows filled; no source touched.

### Flight Director Notes

**2026-06-17 — Flight start.** Loaded leg-execution crew file (valid: Crew /
Interaction Protocol / Prompts present). Branch `flight/01b-provider-capability-audit`
created off `main`; flight `ready` → `in-flight`.

**Orchestration shape (read-only audit, recorded rationale).** This flight produces
a documentation deliverable, not code. Adaptations to the standard leg cycle:
- **Per-provider audits write to their own leg artifacts, not the shared flight
  log.** Legs `anthropic/openai/ollama/openrouter-audit` are mutually independent
  and would race on `flight-log.md` if run concurrently. Each stages its cited
  matrix rows in its own leg file; the `synthesis-and-ratification` leg consolidates
  them into the flight log's Capability Matrix (DD1). This lets the four audits run
  in parallel.
- **Design reviews batched.** `audit-rubric` reviewed on its own (it defines the
  rubric all others consume); the four provider-audit legs share one structural
  template, so they get a single shared design-review pass rather than four. Logged
  here as a deliberate Flight-Director call to cut spawn overhead without losing the
  design-validation gate.
- **Code review + commit deferred to flight end** per the workflow (single review of
  the whole deliverable).

**2026-06-17 — Design-review calls.** `audit-rubric` got its own design-review
agent. The four provider-audit legs (02–05) shared **one** design-review pass (same
structural template) — that review caught a HIGH issue: the SDK version pins were
stale (`anthropic 0.79.0`/`openai 2.32.0` from a stray user-site install) vs. the
authoritative project `.venv` (`0.97.0`/`2.33.0`). Fixed by switching every leg +
DD5 + Prerequisites to "read the exact installed version from `.venv` at audit
time." `synthesis-and-ratification` (leg 06) was **not** given a separate
design-review spawn — it mechanically consolidates four already-reviewed audits, and
its real validation is (a) operator ratification and (b) the end-of-flight Reviewer
pass over the whole deliverable. Logged as a deliberate FD call.

**2026-06-17 — Concurrency.** Legs 02–05 ran in parallel; each wrote its matrix to
its **own** leg artifact and made a single one-line append to this log's Session
Notes. A benign Session-Notes append race surfaced (as anticipated) and the agents
re-read/re-appended cleanly. No matrix-region contention.

**2026-06-17 — Flight close.** Operator ratified the backlog (High tier A1/A2/A4
confirmed as-is; A1 extended thinking = first capability flight after F2/F3); no
priority overridden. End-of-flight Reviewer returned `[HANDOFF:confirmed]` — zero
source files touched, deliverable complete, all spot-checked citations accurate.
Flight → landed. Debrief is a separate `/flight-debrief` step.

**2026-06-17 — openai-audit landed — 12 rows, see legs/03-openai-audit.md.**

**2026-06-17 — anthropic-audit landed — 13 rows, see legs/02-anthropic-audit.md.**

**2026-06-17 — openrouter-audit landed — 12 rows, see legs/05-openrouter-audit.md.**

**2026-06-17 — ollama-audit landed — 11 rows + track-b note, see legs/04-ollama-audit.md.**

**2026-06-17 — synthesis-and-ratification landed.** Consolidated the four audits into `## Capability Matrix → Consolidated Cross-Provider Matrix` (18 rows incl. all provider catch-alls), wrote the three-part Gap Backlog (5 shared contract-level enablers A1–A5, 4 adapter-only B1–B4, 3 routed-elsewhere #122→F2/#105→F3/catalog→F5) with proposed priority/effort/risk, added the Mission Open-Question Disposition (OQ1 SDK-delta answerable, OQ2→F5, OQ3 reasoning all-provider via A4+A1, OQ4 thinking-rep via A1), and left a pending Operator Ratification placeholder. No source touched; no commit.
