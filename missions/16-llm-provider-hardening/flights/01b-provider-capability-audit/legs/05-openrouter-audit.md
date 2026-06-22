# Leg: openrouter-audit

**Status**: landed
**Flight**: [Provider Capability Audit](../flight.md)

## Objective
Audit OpenRouter **standalone, with explicit inheritance markers** — one cited matrix row per capability scored on the three axes, each row marked either "inherits OpenAI adapter" (the common case, since `OpenRouterProvider` is a thin `OpenAIProvider` subclass) or an OpenRouter-specific delta — plus the OpenRouter `/models` `supported_parameters` surface. (Leg 06 reconciles the inheritance markers against the finished OpenAI audit.)

## Context
- Scores against the **frozen rubric + contract inventory** in `flight-log.md` (leg `01-audit-rubric`). Do NOT re-derive the contract.
- `openrouter_provider.py` is literally `class OpenRouterProvider(OpenAIProvider)` — it overrides only context-window resolution (live `/models` `context_length`), interim bytes-per-token, and `supports_tools` (live capability check), with a no-`super().__init__()` constructor. So most capability rows **inherit OpenAI's wiring** — the audit's value is the *delta*.
- OpenRouter is a router over many upstream models, so per-capability support is **model-dependent** and exposed via `/models` `supported_parameters` — that live surface is the distinctive thing to capture.
- Writes to its **own leg artifact**, not the shared flight log (leg 06 consolidates).
- This leg may be **folded into the openai-audit leg** per the flight's Adaptation Criteria — but as planned it stands alone for clean parallelism.

## Inputs
- `flight-log.md` → `### Rubric & Contract Inventory` (frozen reference).
- `the_one/llm/openrouter_provider.py` and `the_one/llm/openrouter_api.py` (the `/models` `supported_parameters` + `context_length` surface).
- The `openai` SDK in the project `.venv` (OpenRouter has no dedicated SDK — it uses the `openai` client pointed at OpenRouter's base URL, so the "SDK-exposed" surface reduces to OpenAI's SDK plus OpenRouter's HTTP `/models` metadata).
- **Expected under parallel execution: `03-openai-audit.md` will NOT yet be filled.** So audit OpenRouter standalone and mark inherited rows explicitly as "inherits OpenAI adapter (reconcile vs 03)" — do not block or poll waiting for leg 03.

## Outputs
- Filled matrix (one row per capability + catch-all) in this leg's `## Audit Result`, each row stating either "inherits OpenAI (see 03)" or the OpenRouter-specific delta, with citations; plus a note on the `supported_parameters` model-dependent capability surface.

## Acceptance Criteria
- [ ] Every frozen-list capability has a row; rows that are pure inheritance from OpenAI say so explicitly (and need no separate SDK citation beyond the inheritance pointer), while rows where OpenRouter differs cite `openrouter_provider.py:line` / `openrouter_api.py:line`.
- [ ] The three OpenRouter overrides (context-window via `/models`, interim bytes-per-token, live `supports_tools`) are reflected in the relevant rows.
- [ ] The `/models` `supported_parameters` surface is captured as the mechanism by which OpenRouter advertises per-model capability (cite `openrouter_api.py`), noted against the catch-all or a dedicated note — this is OpenRouter's distinctive capability-discovery surface.
- [ ] Each gap carries a proposed gap class consistent with the inventory. (Most OpenRouter gaps will be adapter-only or "inherits OpenAI's gap.")

## Verification Steps
- Confirm one row per frozen-list capability, each marked inherited-or-delta.
- Confirm `openrouter_provider.py` is verified as an `OpenAIProvider` subclass (cite the class line).
- Spot-check 2 citations (an override in `openrouter_provider.py`; the `supported_parameters`/`context_length` read in `openrouter_api.py`).

## Implementation Guidance
1. Read the frozen rubric/inventory in `flight-log.md`.
2. Read `openrouter_provider.py` and `openrouter_api.py` fully. Confirm the subclass relationship and enumerate exactly what is overridden.
3. Audit standalone: for each capability, score the row and mark it either "inherits OpenAI adapter (reconcile vs 03)" or an OpenRouter-specific delta with a `openrouter_provider.py`/`openrouter_api.py` citation. (Do not wait for leg 03 — it runs concurrently. Leg 06 reconciles inheritance markers against the finished OpenAI audit.)
4. Capture the `/models` `supported_parameters` model-dependent capability surface as OpenRouter's distinctive trait.
5. Fill the matrix rows in `## Audit Result`. Set leg status `landed`; one-line flight-log Session Notes append. Do NOT commit. Do NOT touch source.

## Edge Cases
- **Model-dependent support**: a capability OpenRouter "supports" depends on the routed upstream model. Score SDK-exposed as "via `/models` `supported_parameters`, model-dependent" rather than a flat Yes — and note that wiring would mean consulting that surface (like `supports_tools` already does).
- **OpenRouter has no dedicated SDK**: it uses the `openai` SDK pointed at OpenRouter's base URL. "SDK-exposed" therefore reduces to OpenAI's SDK surface plus OpenRouter's HTTP `/models` metadata — say so.

## Files Affected
- This leg artifact only. No source code.

---

## Audit Result

### Subclass confirmation & override inventory (frozen-reference, not re-derived)

`OpenRouterProvider` is **literally a thin `OpenAIProvider` subclass** — confirmed at
`openrouter_provider.py:46` (`class OpenRouterProvider(OpenAIProvider):`). Its
constructor (`openrouter_provider.py:65-118`) **deliberately does NOT call
`super().__init__()`** (cited comment `:74-76`: "Override constructor entirely — do
NOT call super().__init__() — so the parent's OPENAI_API_KEY env-var fallback does
not leak to OpenRouter"); it still ends by calling `self._init_provider_state()`
(`:118`) to inherit any provider state added on the base class. It overrides
**exactly three** behaviors, all model-dependent live lookups via the `/models`
listing:

1. **`_resolve_max_context_tokens`** (`openrouter_provider.py:120-132`) — reads the
   per-model `context_length` directly off `/models` via
   `openrouter_api.get_model_context_length` (`:124-128`) instead of the OpenAI
   prefix-table resolver; falls back to the class-default 128k on `None`.
2. **`_bytes_per_token_for_interim`** (`openrouter_provider.py:134-140`) — returns
   `BYTES_PER_TOKEN_OPENROUTER = 4.0` (`:29`); identical density to the OpenAI
   default (cl100k_base) but exposed separately for future per-route tuning.
3. **`supports_tools`** (`openrouter_provider.py:142-154`) — live capability check via
   `openrouter_api.get_model_capabilities` (`:149-153`); returns `False` only when the
   routed model's `supported_parameters` lacks `"tools"`, fail-open (`True`) when caps
   can't be determined.

Everything else — `complete()`, `stream()`, request construction, response parsing,
`tool_schema()` — is **inherited unmodified from `OpenAIProvider`**, so those rows
inherit the OpenAI adapter's scores (reconcile vs leg 03).

### SDK-exposed axis — what it means for OpenRouter

**OpenRouter has NO dedicated SDK.** The adapter uses the `openai` client
(`openai.AsyncOpenAI`, `openrouter_provider.py:99`) pointed at
`https://openrouter.ai/api/v1` (`:69`). So the "SDK-exposed" axis here reduces to
**OpenAI's SDK surface** (the `openai` package in `.venv`) **PLUS OpenRouter's HTTP
`/models` metadata** (`supported_parameters`). Crucially, OpenRouter is a router over
many upstream models, so per-capability support is **model-dependent**, advertised
per-model via `/models` `supported_parameters`
(`openrouter_api.OpenRouterModelEntry.supported_parameters`,
`openrouter_api.py:46`; read by `get_model_capabilities`, `:195-234`). Cells that
depend on the routed model are scored **"model-dependent, via `/models`
`supported_parameters`"** rather than a flat Yes; wiring such a capability would mean
consulting that surface the way `supports_tools` already does.

### Capability matrix (7-column, standalone — inheritance markers reconciled by leg 06)

| Capability | SDK-exposed | Contract-representable | Wired-through | Gap class | Citation | Notes |
|---|---|---|---|---|---|---|
| Extended thinking | Inherits OpenAI SDK surface; on OpenRouter, model-dependent via `/models` `supported_parameters` (e.g. `reasoning`/`include_reasoning`) | No — no thinking field on `Message` (`base.py:64-70`) | No | inherits OpenAI's gap (contract-level) | inherits OpenAI adapter (reconcile vs 03); `openrouter_api.py:46,195-234` for the per-model surface | Storage/replay gap is contract-level and shared with OpenAI; even where a route advertises reasoning, the contract can't carry it. |
| Prompt caching | Inherits OpenAI SDK surface; model/route-dependent via `/models` `supported_parameters` | Partial — no cache-read/creation fields on `TokenUsage` (`base.py:58-61`) | No | inherits OpenAI's gap (contract-level + codec) | inherits OpenAI adapter (reconcile vs 03) | Shared with OpenAI; usage-accounting fields missing AND codec round-trip (`db/codec.py:67`) would need them. |
| Structured outputs / JSON mode | Inherits OpenAI SDK (`response_format`); model-dependent via `/models` `supported_parameters` (`response_format`/`structured_outputs`) | No — no `response_format` param on `complete()`/`stream()` (`base.py:303-310,314-320`) | No | inherits OpenAI's gap (contract-level) | inherits OpenAI adapter (reconcile vs 03); `openrouter_api.py:46` | No request-side entry point in the contract; OpenRouter advertises support per-route. |
| Vision / multimodal | Inherits OpenAI SDK (image content parts); model-dependent via `/models` `supported_parameters` | No — `content` is `str`-only AND assert-enforced (`base.py:135-137`) | No | inherits OpenAI's gap (contract-level) | inherits OpenAI adapter (reconcile vs 03) | Actively rejected at construction (assert), not merely unmodeled; shared root with OpenAI. |
| Reasoning-effort controls | Inherits OpenAI SDK (`reasoning_effort`); model-dependent via `/models` `supported_parameters` (`reasoning`) | No — no `reasoning_effort` param (`base.py:303-310`) | No | inherits OpenAI's gap (contract-level) | inherits OpenAI adapter (reconcile vs 03); `openrouter_api.py:46` | OpenRouter normalizes a `reasoning` knob across routes, but the contract has no param to carry it. |
| Document inputs | Inherits OpenAI SDK (file content parts); model-dependent via `/models` `supported_parameters` | No — same root as multimodal: `content` is `str` (`base.py:135-137`) | No | inherits OpenAI's gap (contract-level) | inherits OpenAI adapter (reconcile vs 03) | Shared `content`-is-`str` root gap with OpenAI. |
| Parallel tool calls | Inherits OpenAI SDK (`parallel_tool_calls` toggle + multiple `tool_calls`); model-dependent via `/models` `supported_parameters` (`tools`) | Partial — `Message.tool_calls` carries multiple (`base.py:64-70`), but no `parallel_tool_calls` toggle param (`base.py:303-310`) | Inherits OpenAI adapter's wiring (multiple tool_calls parsed; toggle not sent) — **reconcile vs 03** | inherits OpenAI's gap (contract-level for the toggle; calls themselves adapter-representable) | inherits OpenAI adapter (reconcile vs 03); OpenRouter delta: `supports_tools` override (`openrouter_provider.py:142-154`) gates tools per-route via `get_model_capabilities` (`openrouter_api.py:195-234`) | **OpenRouter-specific delta:** the live `supports_tools` override drops `tools` for routes that don't advertise them. No #122/#105 equivalent here. |
| Stop sequences | Inherits OpenAI SDK (`stop`); model-dependent via `/models` `supported_parameters` (`stop`) | No — no `stop` param on `complete()`/`stream()` (`base.py:303-310`) | No | inherits OpenAI's gap (contract-level) | inherits OpenAI adapter (reconcile vs 03); `openrouter_api.py:46` | OpenRouter advertises `stop` support per-route; contract has no entry point. |
| Streaming events | Inherits OpenAI SDK (typed stream deltas); OpenRouter streams the same OpenAI-compatible SSE | Partial — `StreamChunk` carries `content`/`tool_calls`/`usage`/`message`/`is_final` (`base.py:228-243`) | Inherits OpenAI adapter's `stream()` wiring — **reconcile vs 03** | inherits OpenAI's status (likely none/partial) | inherits OpenAI adapter (reconcile vs 03) | `stream()` is inherited unmodified; whatever OpenAI parses, OpenRouter parses. |
| Token counting | Inherits OpenAI SDK (no count-tokens endpoint — OpenAI has none; usage on response only) | Partial — `TokenUsage.input_tokens`/`output_tokens` only (`base.py:58-61`) | Inherits OpenAI adapter's post-hoc usage parse — **reconcile vs 03**. **OpenRouter delta on the interim byte-heuristic**: `_bytes_per_token_for_interim=4.0` (`openrouter_provider.py:134-140,29`) | inherits OpenAI's status | inherits OpenAI adapter (reconcile vs 03); OpenRouter delta `openrouter_provider.py:134-140` | No pre-flight counting endpoint (same as OpenAI). **Delta:** OpenRouter overrides the mid-stream bytes-per-token density constant (value-identical to OpenAI's default, but its own override point). |
| **Context-window resolution** (catch-all — `_resolve_max_context_tokens` hook, `base.py:276-301`) | OpenRouter-specific: `context_length` is a first-class field on `/models` (`OpenRouterModelEntry.context_length`, `openrouter_api.py:47`) | Yes — contract has the `_resolve_max_context_tokens()` hook (`base.py:276-301`) | **Yes — OpenRouter delta**: override resolves live via `/models` `context_length` (`openrouter_provider.py:120-132`, helper `openrouter_api.py:165-192`) | adapter-only — already wired (effectively **none**) | `openrouter_provider.py:120-132`; `openrouter_api.py:165-192` | **OpenRouter-specific delta vs OpenAI's prefix-table resolver.** Fully wired; no gap. |
| **Per-model capability discovery** (catch-all — OpenRouter's distinctive surface) | OpenRouter-specific: `supported_parameters` is a first-class list field on `/models` (`OpenRouterModelEntry.supported_parameters`, `openrouter_api.py:46`) | n/a (a discovery mechanism, not a per-message capability) — but it IS the lever any future per-route wiring would pull | **Partial today**: read only for the `supports_tools` gate (`openrouter_provider.py:142-154` via `get_model_capabilities`, `openrouter_api.py:195-234`); not consulted for any other capability | adapter-only (the surface exists; wiring more capabilities off it needs no contract change for the *gate*, though carrying the capability still needs the contract-level changes above) | `openrouter_api.py:46,195-234`; `openrouter_provider.py:142-154` | **OpenRouter's distinctive capability-discovery surface.** `/models` `supported_parameters` advertises per-model support for `tools`, `response_format`, `reasoning`, `stop`, etc. Today only `tools` is consulted; it's the wiring point for model-dependent scoring of every "model-dependent via `/models`" cell above. |

### Notes / reconciliation pointers for leg 06

- **Inherited rows** (extended thinking, prompt caching, structured outputs, vision,
  reasoning-effort, document inputs, stop sequences, streaming events, and the
  inherited halves of parallel-tool-calls / token-counting) carry **OpenAI's scores
  verbatim** — leg 06 reconciles these against the finished `03-openai-audit.md`. No
  separate OpenAI-SDK citation is given per row beyond the inheritance pointer, per
  AC #1.
- **Three genuine OpenRouter deltas** (over and above inheritance):
  1. live `context_length` resolution (catch-all row 1) — **fully wired, no gap**;
  2. live `supports_tools` gate off `supported_parameters` (parallel-tool-calls row) —
     adapter-only, route-aware;
  3. the interim bytes-per-token override (token-counting row) — value-identical to
     OpenAI today, but OpenRouter's own override seam.
- **`supported_parameters` surface** (catch-all row 2) is OpenRouter's distinctive
  capability-discovery mechanism and the single lever for converting any
  "model-dependent via `/models`" cell from advertised to wired. Currently consulted
  only for the tools gate.
- Most gaps are **"inherits OpenAI's gap" (contract-level)** — closing them requires
  `base.py`/codec changes that benefit OpenAI and OpenRouter alike, not an
  OpenRouter-specific fix. OpenRouter's own deltas are all **adapter-only / none**.
