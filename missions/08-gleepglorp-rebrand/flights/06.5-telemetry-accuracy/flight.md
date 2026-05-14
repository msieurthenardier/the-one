# Flight: Telemetry Accuracy

**Status**: completed
**Mission**: [GleepGlorp AI Rebrand & UX Polish](../../mission.md)

## Contributing to Criteria

- [ ] Browser-side performance has been measured under realistic use (long chat sessions, many agents, repeated area switching) and meets an established memory and responsiveness budget — no unbounded growth across normal interaction, no blocking work that freezes the UI *(unblocks F7 by making the telemetry that F7 measures against actually accurate)*
- [ ] All existing functionality (M01–M07 capabilities) continues working — no regression in chat persistence, provider management, etc.

---

## Pre-Flight

### Objective

Make the chat telemetry overlay's context-fill percent accurate before Flight 7 (UI Performance Audit) tries to measure performance against it. F6 L06 HAT surfaced two bugs in the telemetry path:

1. **`max_context_tokens` is hardcoded class-level**, not per-model. `the_one/llm/base.py:87` defaults to 128,000 for all providers; only `anthropic_provider.py:15` overrides (to 200,000). Effect: qwen-via-ollama (real 32k window) is shown against 128k → percent severely understates fill; warn/crit thresholds (70%/90%) fire late or never.
2. **Ollama `prompt_tokens` may undercount** for some models. F6 operator observed `last_input ≈ 1000` after a multi-turn conversation against qwen — implausibly low for cumulative history.

Resolution: move `max_context_tokens` to an instance attribute resolved at construction time from provider model metadata (Ollama `/api/show` exposes `model_info.{family}.context_length`; OpenRouter's existing model cache already has `context_length`; OpenAI uses a hardcoded per-model table; Anthropic stays at 200k class default — correct for all current Claude models). Then add a cross-provider validation test that asserts `usage.input_tokens` grows with conversation length to catch Ollama-side undercount (or confirm it's our request shape that's at fault). Closes with an operator HAT exercising real providers.

Out of scope (deferred to F7 or later):
- Mid-stream `usage` event emission (KI #5) — `usage` emits only at step completion today; mid-stream estimation requires chunk-byte→tokens heuristic. Polish, not accuracy.
- Per-agent `max_context_tokens` override field in Studio Agent editor — nice-to-have; not needed if model-resolved defaults are right. Revisit if HAT surfaces models where resolution fails.

### Open Questions

- [x] **Ollama context-length field location** → Resolved: `/api/show` returns `model_info` keyed by model family (e.g., `qwen2.context_length`, `llama.context_length`). L01 extracts via a small helper that finds the first `*.context_length` key in `model_info`. Fallback to class default (128k) when absent. See Design Decisions.
- [x] **OpenAI per-model lookup table** → Resolved: hardcoded `OPENAI_MODEL_CONTEXT` dict in `openai_provider.py` covering common models (gpt-4o: 128k, gpt-4-turbo: 128k, gpt-4: 8k, gpt-3.5-turbo: 16k, o1: 200k, o3-mini: 200k). Fallback to class default. See Design Decisions.
- [x] **Class attribute vs instance attribute** → Resolved: convert `LLMProvider.max_context_tokens` from class attribute to INSTANCE attribute set in `__init__`. Class attribute stays as a default fallback. Existing call sites that read `self.llm.max_context_tokens` continue working unchanged (attribute lookup falls through to class default if instance never set). See Design Decisions.
- [x] **OpenRouter wiring** → Resolved: `OpenRouterProvider` inherits from `OpenAIProvider`. Resolve via `get_model_capabilities(base_url, model)` which already returns the `OpenRouterModelEntry` with `context_length`. Cache hits are free (5min TTL). On miss/error: class default. See Design Decisions.
- [x] **Should resolution be sync or async?** → Resolved: provider `__init__` is sync today; making it async is invasive. Use a lazy-load pattern — `max_context_tokens` becomes a property that triggers async resolution on first access, with caching. OR: leave as instance attribute set during the first `complete()` / `stream()` call. The latter is simpler — call `_resolve_max_context_tokens()` at the top of `complete`/`stream` (idempotent, caches via instance attribute). See Design Decisions.
- [x] **Ollama undercount root cause** → Open until L02 validation. Hypotheses: (a) Ollama's tokenizer reports differently for some models (Ollama-side issue), (b) our request body strips history somehow (verify against Anthropic/OpenAI to localize). L02 ships the test harness; root cause categorization happens there.
- [x] **Closing HAT** → Resolved: included. Operator validates with qwen-via-ollama (the original bug-report scenario) + at least one other provider.

### Design Decisions

**`max_context_tokens` is an instance attribute, resolved lazily on first LLM call**

- Choice: convert `max_context_tokens` from class attribute (`the_one/llm/base.py:87`) to instance attribute. The class attribute STAYS as the fallback default (128k). Each provider implements `_resolve_max_context_tokens()` that queries model metadata and sets `self.max_context_tokens` to the resolved value. The resolver runs lazily at the top of `complete()` and `stream()` (idempotent — short-circuits if already resolved).
- Rationale: cycle-1 review confirmed that making `__init__` async is technically viable — `agent/factory.py:186-229`'s `AgentFactory.create()` is already async and `get_provider(...)` is called there at line 223 (not awaited today, but `await get_provider(...)` would be a one-line change). So this isn't an infeasibility argument; it's a surface-area argument. Lazy-on-first-call keeps the provider registry's `get_provider` signature sync (consumed in places that aren't easy to audit exhaustively), avoids touching every test fixture that instantiates providers directly, and limits the new code path to the provider classes themselves. The first user message triggers a one-time metadata fetch (Ollama: ~10-50ms; OpenRouter: free if list-models cache is warm; OpenAI/Anthropic: pure dict lookup). Subsequent calls short-circuit. The trade-off — telemetry shows the class-default denominator until the first message arrives — is acceptable because nobody reads telemetry before the first turn (the overlay is hidden until then).
- Existing call sites that read `self.llm.max_context_tokens` continue working unchanged: cycle-1 review confirmed only two reader sites exist — `the_one/interfaces/web/app.py:689` (`_broadcast_one`) and `the_one/interfaces/web/app.py:752` (`_process_and_broadcast`) — both fire AFTER `agent.step()` triggers the first `complete()`/`stream()`. No pre-call readers. The lazy-resolution divert path in Adaptation Criteria below is documented for future-proofing but won't trigger with the current codebase.

**Ollama `model_info.*.context_length` resolution**

- Choice: helper `extract_ollama_context_length(show_response: dict) -> int | None` walks `model_info` (a dict) and returns the first value at a key ENDING in `.context_length`. Ollama nests context_length under a family-namespaced key (cycle-1 verified against live `/api/show` for `qwen2.5:7b`: `model_info.qwen2.context_length = 32768`; top-level keys are `{family}.{field}` pattern e.g. `qwen2.attention.head_count`, `qwen2.block_count`).
- Rationale: families vary (`qwen2`, `llama`, `mistral`, etc.); no single literal key works. Suffix match (`.context_length`) is safer than prefix match (the family prefix can be multi-segment in future model variants). Return None on missing → caller falls back to class default (128k).
- Trade-off: brittle to Ollama API shape changes; defensive logging in case a future Ollama version moves the field.
- **Pattern reference**: mirror `OllamaProvider.supports_tools` at `ollama_provider.py:48-50` which already uses the async-helper-with-cache pattern via `get_model_capabilities`. The new `_resolve_max_context_tokens` follows the same shape.

**OpenAI per-model hardcoded lookup table**

- Choice: `OPENAI_MODEL_CONTEXT: dict[str, int]` lives at module scope in `the_one/llm/openai_provider.py` (not a separate `openai_models.py` — too small a payload to justify a new module; co-located with the provider that consumes it). Maps common model name prefixes → context size. Match by prefix (e.g., `gpt-4o-2024-05-13` matches `gpt-4o`). Fallback to class default.
- Initial table:
  - `gpt-4o` → 128_000
  - `gpt-4-turbo` → 128_000
  - `gpt-4` → 8_192
  - `gpt-3.5-turbo` → 16_385
  - `o1` → 200_000
  - `o3-mini` → 200_000
- Rationale: OpenAI doesn't expose context size via API. Manual maintenance is acceptable for a small set of well-known models; unknowns fall back. Operators can override per-agent later if F6.5 HAT surfaces models we don't cover.
- Trade-off: drifts as OpenAI ships new models; documented as a known-staleness vector in the dict's docstring.

**OpenRouter resolution via `list_models` + match-by-id**

- Choice: `OpenRouterProvider` overrides `_resolve_max_context_tokens()` to call `openrouter_api.list_models(base_url, api_key)` (existing helper, 300s LRU cache), then walks the returned list to find the entry where `entry.id == self.model`, then reads `entry.context_length`. On cache miss + API failure OR model-not-found: class default.
- Rationale: cycle-1 review surfaced that `get_model_capabilities(base_url, api_key, model)` returns `frozenset[str] | None` of `supported_parameters`, NOT an `OpenRouterModelEntry` — so it doesn't expose `context_length`. The `context_length` field IS on `OpenRouterModelEntry` (`openrouter_api.py:47`) but is only reachable via `list_models`. L01 either calls `list_models` directly OR adds a sibling helper `get_model_context_length(base_url, api_key, model) -> int | None` next to `get_model_capabilities` (recommended — single-purpose accessor, mirrors `get_model_capabilities`'s fail-open semantics).
- Trade-off: depends on OpenRouter API availability — a transient outage during the resolver call leaves the value at class default for that session. Acceptable.
- **Note**: `list_models` requires `api_key`. The provider has its api_key from `__init__`; pass it through.

**Anthropic stays at class-default 200k for now**

- Choice: don't add per-model resolution for Anthropic in F6.5. All current Claude models (Claude 4.x family) have 200k context windows; the class override at `anthropic_provider.py:15` is correct.
- Rationale: zero ROI to add a model-name table when 100% of in-use models hit the same value. Revisit if Anthropic ships a model with a different window.
- Trade-off: latent code-debt if Anthropic ships a Claude 5 with 1M context (the hardcoded 200k would understate fill). The fix would be a one-line table addition.

**Cross-provider `input_tokens` validation as a test harness, not a runtime assertion**

- Choice: L02 ships a pytest test gated by `@pytest.mark.live` (cycle-1 verified the marker already exists in `pyproject.toml` — "marks tests that call real LLM APIs", deselected by default per the project's existing addopts marker list). The test runs a 3-turn conversation against each enabled provider; mocking defeats the purpose since the goal is to catch the Ollama prompt_tokens undercount in real traffic.
- Rationale: catching the Ollama undercount requires real Ollama, real qwen model, real conversation. Mocking defeats the purpose. The test harness becomes a regression net: an operator runs it before each release to confirm telemetry is still accurate across providers.
- Trade-off: not exercised in default CI. Documented in the test's docstring + a "how to run" entry in agents.md (or wherever the project keeps test invocation docs).

**Mid-stream `usage` emission deferred to F7**

- Choice: KI #5 (telemetry only updates after step, not during streaming) is OUT of scope for F6.5.
- Rationale: F6.5 is "make the math right." Mid-stream emission is a smoothness improvement on the rendering side that depends on a chunk-byte→tokens heuristic (provider-specific). Best tackled when F7's perf-audit work can also exercise it. Keeping F6.5 tight is the priority — bridging flight.

### Prerequisites

- [ ] F6 merged to main (✓ — commit `1e34951`)
- [ ] Broad pytest reliably exits with code 0 (✓ — verified at F6 close: 1627 passed, 4 skipped, 370 deselected)
- [ ] Browser suite baseline 315p/35s (✓ — verified at F6 close)
- [ ] Container `the-one` running and reachable via `docker exec`
- [ ] `make rebuild` available on host
- [ ] An Ollama instance with at least one model loaded (for L02/L03 real-LLM validation) — typically running on host, accessible from the container at `http://host.docker.internal:11434` or similar. **Operator-controlled**: HAT scenarios assume operator has qwen or another local model installed.

### Pre-Flight Checklist

- [ ] All open questions resolved (the Ollama-undercount-root-cause one is open by design — L02 ships the diagnostic and resolves at HAT)
- [ ] Design decisions documented
- [ ] Prerequisites verified
- [ ] Validation approach defined (per-leg unit tests for the resolvers; L02 real-LLM cross-provider harness; L03 operator HAT)
- [ ] Legs defined

---

## In-Flight

### Technical Approach

**Phase 1 — Per-model `max_context_tokens` resolution (L01).** Convert `max_context_tokens` from class attribute to instance attribute. Implement `_resolve_max_context_tokens()` per provider:

- **AnthropicProvider**: no change (class default 200k stays — covers all current Claude models)
- **OllamaProvider**: query `ollama_api.show_model(base_url, model)`; extract `model_info.{family}.context_length` via new helper; set `self.max_context_tokens` to the value or class default
- **OpenAIProvider**: lookup against `OPENAI_MODEL_CONTEXT` dict by model-name prefix; set `self.max_context_tokens` to the matched value or class default
- **OpenRouterProvider**: call `openrouter_api.get_model_capabilities(base_url, model)`; read `entry.context_length` if available; set `self.max_context_tokens` to the value or class default

Resolver is invoked lazily at the top of `complete()` and `stream()` (idempotent — short-circuits if already resolved). Failure-path caching: if the metadata fetch fails (network error, model not found, malformed response), the resolver MUST still mark the provider as "resolved" with the class-default value — otherwise every subsequent `complete()`/`stream()` call would re-attempt the failed fetch (retry storm). Pattern: set an instance flag `_max_context_tokens_resolved = True` regardless of fetch outcome; the `max_context_tokens` instance attribute either gets the fetched value or stays at the class default. Add unit tests per provider with mocked metadata responses, including the failure path.

**Phase 2 — Cross-provider `input_tokens` validation (L02).** Create a pytest-marked test (`@pytest.mark.requires_real_llm` or similar) that:

1. For each provider config present in the environment (Ollama, OpenAI, Anthropic, OpenRouter — skip silently if creds/server unavailable):
2. Runs a 3-turn conversation: turn 1 short message, turn 2 longer message, turn 3 even longer
3. Captures `msg.usage.input_tokens` after each turn
4. Asserts the sequence is MONOTONICALLY NON-DECREASING (token count grows turn-over-turn)
5. If any provider's sequence is flat or decreasing, log the symptom with provider name + model + token deltas

This test ships in `tests/test_input_tokens_cross_provider_live.py` (top-level `tests/` directory, `_live.py` suffix matching the marker — verify against existing `live`-marked test naming convention at L02 design time). It is NOT part of default CI (gated by `-m live`) but is documented as "run before release" and "run when adding a new provider" in agents.md.

The L02 leg also captures the root-cause categorization for the Ollama undercount — once the test runs against real qwen-via-ollama, the data localizes the issue:

- **If Ollama prompt_tokens grows correctly across turns with a different model (e.g., llama3)**: Ollama-side qwen-specific issue → external; document and move on
- **If Ollama prompt_tokens is flat across all tested models**: our request shape is wrong → investigate the chat completions body construction in `ollama_provider.py` and fix inline if scope allows

**Phase 3 — Operator HAT (L03).** Operator validates against real providers:

- Configure a qwen-via-ollama agent (or whichever model triggered the original F6 report)
- Send a few turns; observe the telemetry overlay percent — it should now reflect ACTUAL fill of the model's REAL context window (e.g., qwen's 32k)
- Push toward 70% / 90% to verify warn/crit fire at realistic fill levels
- Repeat for at least one other provider (Anthropic OR OpenAI OR OpenRouter — whatever the operator has credentials for)
- Run the L02 cross-provider test against the operator's available providers; verify it passes (or surfaces the Ollama-side undercount cleanly)
- Pixel + broad + browser suite regression smoke (same cadence as F6)

### Checkpoints

- [ ] L01: per-model `max_context_tokens` resolution lands; resolver runs idempotently per provider; unit tests pass for each provider with mocked metadata; broad pytest still exits 0
- [ ] L02: cross-provider validation harness lands; documented as operator-runnable; root cause of Ollama undercount categorized (external Ollama issue OR our request shape) — recommendation captured in flight log
- [ ] L03: HAT — operator validates real-provider telemetry against expected model context windows; warn/crit fires at correct thresholds; no regression in broad/browser suites

### Adaptation Criteria

**Divert if**:
- L01 reveals that lazy resolution breaks an existing call site that reads `self.llm.max_context_tokens` BEFORE the first `complete()` / `stream()` call. Investigate the call site; either move the read after-first-LLM-call OR switch to a property-based resolver. (Property is more invasive but safer; lazy-on-first-call is simpler and probably sufficient.)
- L02's cross-provider test reveals our request shape IS wrong (history is being dropped before send). Then the fix becomes ESSENTIAL in-scope work; the Ollama undercount is OURS to fix.
- HAT operator finds models we don't cover in the OpenAI table → scope down: ship F6.5 with the partial table + add a "log as future addition" note rather than chasing every model variant.

**Acceptable variations**:
- The exact list of OpenAI models in the lookup table can grow during L01 as operator preferences surface; not pre-committed
- L02's test may be skipped for providers the operator doesn't have credentials for; document which providers were exercised
- L03 pixel-baseline regeneration is OPTIONAL (no new visual changes in F6.5 — accuracy fix is data-only). Re-run pixel suite to confirm 12/12 unchanged; regenerate only if needed.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `max-context-per-model` — per-model `max_context_tokens` resolution for all four providers (Anthropic stays 200k; Ollama `/api/show`; OpenAI table; OpenRouter cache); resolver runs lazily on first LLM call; unit tests with mocked metadata
- [x] `input-tokens-cross-provider-validation` — pytest-marked integration test that runs 3-turn conversations across enabled providers and asserts `input_tokens` grows; localize Ollama undercount (external vs ours); inline fix if it's ours
- [x] `telemetry-accuracy-hat` — operator HAT against real providers; verify warn/crit thresholds fire at realistic context fill; broad + browser suite regression smoke
- [x] `max-context-display` (L04, inline-spawned during L03 HAT) — `GET /api/providers/{id}/models` returns per-model `context_length` (Ollama via `/api/show`, OpenAI via `OPENAI_MODEL_CONTEXT` prefix lookup, Anthropic class-default 200k, OpenRouter via existing `list_models` field); agent editor displays a `Max context` chip; telemetry overlay gains a `max:` row; bug fix: `_process_and_broadcast` now reads `max_context_tokens` LIVE at usage-event emission (was captured pre-resolver-fire → first turn showed 128k default).

---

## Post-Flight

### Completion Checklist

- [ ] All legs completed
- [ ] Code merged to main
- [ ] Broad pytest exits code 0 with no new failures or skips
- [ ] Browser suite ≥ 315 passing / ≤ 37 skipped (F6 baseline ± 2 new-skip cap)
- [ ] Pixel suite 12/12 on clean rerun (no new visual changes expected)
- [ ] Ollama undercount root cause documented in flight log (external vs ours) with link to upstream issue if external
- [ ] Mission KIs #1, #2 marked resolved (closes the F6 HAT findings); KI #5 (mid-stream usage) explicitly carried forward to F7

### Verification

How to confirm the flight achieved its objective:

1. **Per-model resolution lands**: send a chat turn with a qwen-via-ollama agent; inspect telemetry overlay — percent reflects 32k denominator (or whatever qwen's actual context is), NOT 128k
2. **Test harness passes**: `docker exec the-one pytest -m requires_real_llm tests/integration/test_input_tokens_cross_provider.py` runs to completion for the operator's available providers; all enabled providers show monotonic `input_tokens` growth
3. **Ollama undercount disposition**: flight log captures the root cause + decision (external Ollama issue with link → close as KI; OR our request shape → inline fix already landed)
4. **No regression in M01–M07**: broad pytest exit 0; browser suite preserved; pixel suite 12/12 clean
5. **F7 unblocked**: with telemetry now accurate, F7 (UI Performance Audit) can proceed to measure performance against meaningful fill thresholds

---

## Known Issues (carried forward)

From F6 mission KIs, F6.5 addresses #1 and #2 below; #3, #4, #5 stay carried-forward:

- **F6 KI #1** `max_context_tokens` hardcoded → **F6.5 L01 resolves**
- **F6 KI #2** Ollama `prompt_tokens` undercount → **F6.5 L02 categorizes + resolves if ours**
- **F6 KI #3** No stop / cancel button → out of scope (dedicated reliability flight)
- **F6 KI #4** Long-convo loops on qwen → out of scope (pairs with #3 in dedicated flight)
- **F6 KI #5** Mid-stream `usage` emission → out of scope (defer to F7 or polish flight)
