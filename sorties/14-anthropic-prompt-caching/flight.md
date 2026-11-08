# Sortie: Anthropic prompt caching

**Status**: landed

## Charter

### Outcome
Agents on Anthropic and on a Claude plan reuse a cached prompt prefix (tool schemas and system prompt), so each tool step in a turn uses less input quota and returns sooner.

### Why Now
Sortie 11's tool exposure sends every enabled tool schema on the first call when the toolset fits the budget, and Anthropic's large window means most agents fit. haiku's first-call input grew from 1044 to 2536 tokens for the bare eval agent and from 1556 to 3161 for all-on. Every tool step in a turn re-sends that same prefix, and `the_one/llm/` sets no `cache_control` anywhere, so plan quota pays for it each time. The sortie 11 debrief named this as recommendation 5.

### Success Criteria
- [ ] Once a turn's prompt reaches the model's cache minimum (4096 tokens on Claude Haiku 4.5; it differs by model), an Anthropic or Claude-plan agent's second and later model calls in that turn report cache reads covering the tool schemas and system prompt. *(Amended at flight design, 2026-11-07, with the operator: the original wording had no minimum, which Haiku 4.5's 4096-token floor makes unreachable for the small eval agents; see the flight log.)*
- [ ] Token telemetry counts cached input correctly: the context overlay and the stored `last_usage` neither double-count nor drop cache reads and writes.
- [ ] It covers the `anthropic`, `anthropic-plan` and `anthropic-plan-token` provider types.
- [ ] No change in agent behaviour: the s11 compare shows no gate failure for haiku.

### Constraints
- No platform prompt text changes. Caching changes only request metadata, so the prompt evals' size gates do not move.
- Secrets handling is unaffected: the provider request still carries placeholders only, never a secret value.
- No change to the frozen `the_one/agent/core.py` without the owner's approval.
- Out of scope: caching for other providers (OpenAI, OpenRouter, Ollama), and the conversation-history cache strategy beyond the stable prefix unless the design shows it is the same decision.

---

## Pre-Flight

### Objective
Turn on Anthropic prompt caching in the one request builder all three Claude provider types share, `AnthropicProvider._build_kwargs`. It uses an explicit breakpoint on the system prompt, which caches tools and system together, plus top-level automatic caching for the growing conversation within a turn. An endpoint or SDK that refuses either form degrades to no caching instead of failing.

The cache read and write counts are carried through `TokenUsage` without changing what `input_tokens` means to its consumers. The context overlay and `last_usage` therefore read the whole prompt size as before.

Verification:
- A committed live probe, run through the app's own agent factory, proves cache reads and the telemetry mapping on a real haiku 4.5 turn.
- A new model filter on `compare` lets the s11 compare check haiku alone, proving behaviour is unchanged.

### Open Questions
- [x] Where do the breakpoints go? → DD1
- [x] What does `TokenUsage.input_tokens` mean once caching is on? → DD2
- [x] Haiku 4.5's 4096-token minimum makes criterion 1 unreachable for the small eval agents; how is it proved? → DD4 (criterion amended)
- [x] Show cached tokens in the chat UI or the eval results? → DD3 (no, in both)
- [x] Does the plan (OAuth) endpoint accept `cache_control`? → yes, verified by a planning probe (DD5)
- [x] How does the s11 compare check haiku alone? → DD7 (`compare --models`)
- [x] HAT leg? → no (operator, 2026-11-07)

### Design Decisions

**DD1 — Breakpoints: one explicit marker on the system prompt plus top-level automatic caching** (operator choice, 2026-11-07)
- `_build_kwargs` sends `system` as a one-element list, `[{"type": "text", "text": <system_prompt>, "cache_control": {"type": "ephemeral"}}]`, instead of the bare string. It also sets the top-level `cache_control={"type": "ephemeral"}` on every request.
- Render order is tools → system → messages, so the system marker caches the tool schemas and the system prompt together. The automatic breakpoint follows the end of the conversation, so step N+1 of a turn reads everything step N sent, and so can the next user turn in the same chat if it starts within 5 minutes.
- Both use the default 5-minute TTL, via one module constant. Anthropic requires a longer-TTL entry to come before a shorter one, so a later edit that set `ttl: "1h"` on the top-level field alone, after a 5-minute system marker, would 400. A unit test pins that both carry the same value. No 1-hour TTL: its writes cost 2x and a turn's steps are seconds apart.
- With no system prompt, only the top-level field is sent. A request uses two of the four breakpoint slots, or one when there is no system prompt.
- Rationale: this is Anthropic's recommended agent-loop combination. The stable prefix gets a guaranteed read point however `messages` changes, and the tail caching is one more key in the same function. The charter allows the history strategy when it is the same decision, and here it is: both are breakpoint placement in `_build_kwargs`.
- Trade-off: each request pays the ~1.25x write premium on the newly appended tail, against roughly 0.1x reads of the whole earlier prompt on every later step.
- It applies to all three types by inheritance. `AnthropicPlanProvider` and `AnthropicPlanTokenProvider` override only `_build_client`, `_before_request`, `complete`/`stream` (error translation) and `_translate_plan_error`, never `_build_kwargs`.

**DD2 — `TokenUsage.input_tokens` keeps meaning "the whole prompt"; the cache counts are new fields**
- Once caching is on, Anthropic's `usage.input_tokens` is only the uncached remainder. The total prompt is `input_tokens + cache_creation_input_tokens + cache_read_input_tokens`; the planning probe saw `input_tokens=3` for an 8954-token prompt.
- Every consumer reads `TokenUsage.input_tokens` as the prompt size, and none sums the cache counts:
  - the overlay's `context_tokens`, the last step's `input_tokens` (`app.py`);
  - the stored `last_usage`;
  - the informational eval `model_counts` (`evals/tokens.py::first_call_input_tokens`, `evals/outcomes.py::usage_totals`).
  - The eval `size:*` gates are separate: they compare tiktoken counts from `measure-prompt`, never provider usage, so they are untouched by construction.
- One private helper in `anthropic_provider.py` maps an SDK `usage` to `TokenUsage` and replaces the two duplicate mapping sites in `complete` and `_stream_inner`:
  - `TokenUsage.input_tokens` = `input + cache_creation + cache_read`.
  - Two new dataclass fields, `cache_read_tokens: int = 0` and `cache_write_tokens: int = 0`, are appended after `output_tokens`, so positional `TokenUsage(a, b)` callers (e.g. `evals/scripted.py`) keep working.
  - A cache field counts only when it is an `int`: `None`, missing, or a non-int such as a test `MagicMock` (`tests/test_streaming.py:188`) counts as 0.
- `db/codec.py` emits the two keys only when non-zero and decodes them with `.get(..., 0)`. Rows without them decode as before, and a non-caching message encodes byte-identically to today.
- Rationale: nothing downstream double-counts or drops anything. The overlay and `last_usage` read the totals they read before caching, which is what criterion 2 requires.
- Trade-off: `input_tokens` no longer means "billed at full price" for Anthropic. Anyone who needs the billing split reads the new fields.

**DD3 — No UI change, and no change to the eval scoring files** (operator choices, 2026-11-07)
- The chat telemetry readout, the WebSocket usage frames and `last_usage` keep their current keys and values. The cache counts are stored on the assistant message (DD2) and nowhere else.
- `evals/outcomes.py`, `harness.py`, `checks.py` and `judge.py` are untouched; `tests/test_evals_freeze.py::SCORING_DIGESTS` pins them. The probe (DD4) reads the counts directly from the turn trace's messages.
- Rationale: keeps the sortie to one decision cluster, with no browser lanes, no mockup gate and no eval methodology change.

**DD4 — Criterion 1 (and criterion 2's live half) is proved by a committed live probe through the real factory** (operator choice, 2026-11-07)
- A new developer tool `evals/cache_probe.py`, run with `make eval ARGS="cache-probe"`, a new subcommand in `evals/__main__.py`.
- **Setup.** It reuses the eval entry points as they are, following the pattern of `tokens.measure_prompt`, with no edits to `harness.py`:
  1. `evals.env.startup(StartupOptions(run_dir=evals/runs/cache-probe-<time>, need_token=True, ...))`.
  2. `models.load_presets` / `select_presets(..., ["haiku"])`.
  3. `Harness(env, {"haiku": preset})` and `await harness.setup()`.
  4. The scenario from `scenario.parse_scenario` of the probe's TOML.
  5. `await harness.run_once(RunSpec(...))`.
  6. The per-call usage from `attempt.trace.turns[0].messages`, plus `attempt.exposure`, `attempt.effective["thinking"]`, `attempt.exc` and `attempt.model_failure`.
  7. `harness.close()` and `env.shutdown`.

  The agent loop streams, so the live proof exercises `_stream_inner`'s usage mapping; unit tests cover `complete`. Through `startup` it inherits:
  - the scratch data directory and home;
  - the data-directory guard, so production and port 8484 are never touched;
  - plan-token handling and redaction;
  - `evals/env.py::check_pinned_env`, which refuses if `THE_ONE_ANTHROPIC_EXTENDED_THINKING` or `THE_ONE_TOOL_EXPOSURE_*` is set, so the shipped defaults apply.
- **The turn.**
  - It builds a `haiku` agent whose persona is padded so the system prompt and tools pass 4096 tokens.
  - The padding lives in the persona only, in its own scenario TOML under `evals/cache_probe_data/` (never `evals/scenarios/`; named apart from the module so it can never shadow it). The platform prompt and the scenarios fingerprint are unchanged.
  - It runs one turn whose user message asks for the current time, so the agent calls `current_time`, which every agent has.
  - The user message is padded with a few hundred tokens of filler, so the system marker alone and the automatic tail are told apart by a wide margin.
- **Output.** For each model call it prints:
  - `input_tokens` (as mapped), `cache_read_tokens` and `cache_write_tokens`;
  - the agent's `tool_exposure` and the provider's effective thinking setting;
  - whether a cache strip fired (DD5), from the `the_one.llm.anthropic_provider` warnings captured during the run.
- **Exit codes:**
  - **0, pass**, when all of these hold, with `margin = 32`:
    - On call 1 and call 2, the uncached remainder `input_tokens − cache_read_tokens − cache_write_tokens <= margin`. The automatic breakpoint covered the whole request, user message included; with only the system marker, the padded user message stays uncached.
    - Call 2's `cache_read_tokens >= call1.input_tokens − margin`. Call 2 read everything call 1 sent, user message included, so the tail entry was read and not only the system marker.
    - On every call, `input_tokens >= cache_read_tokens + cache_write_tokens`. That is the DD2 mapping; without it `input_tokens` collapses to a handful.
    - Call 2's `input_tokens >= call1.input_tokens`, because the prompt only grows within a turn.
    - No cache strip fired.
  - **1, fail**, when the preconditions hold but an assertion does not.
  - **2, refused**, through `_err` like the other subcommands: a startup refusal (`EvalRefusalError`, `PresetError`, a missing token).
  - **3, inconclusive** (not a failure), when a precondition fails: fewer than two model calls, no tool call, or call 1's total prompt at or below 4096 + 256 tokens.
  - **4, run error**: `attempt.exc` or `attempt.model_failure` is set, for example a plan 429 or an escaped 400. It is kept apart from 3 so that a persistent provider error never reads as "inconclusive".
  - Codes 0, 1 and 2 match the existing subcommands; 3 and 4 are new and unused today.
- It is not a scenario, because a scenario would change the baselined `s11` set and force a re-baseline. Like every eval tool, it stays out of CI and the test gate. Offline unit tests cover the pass, fail and inconclusive logic against hand-built traces, plus the argument handling.
- Rationale: the probe exercises the app's real path (factory → provider → `_build_kwargs` → usage mapping), so it proves criteria 1 and 2 live for `anthropic-plan-token`. The `anthropic` and `anthropic-plan` types share the request builder; unit tests on `_build_kwargs` per provider class cover them (criterion 3).
- Trade-off: a few thousand plan-quota tokens per run.

**DD5 — Endpoint support is verified; refusal degrades to no caching, and the existing retries compose**
- **Planning probe** (2026-11-07, scratch script, plan token, `claude-haiku-4-5-20251001`, a ~8.9k-token system block carrying the explicit marker plus top-level `cache_control`, one tool, two calls):
  - call 0: `input=3 cache_write=8951 cache_read=0`
  - call 1: `input=3 cache_write=323 cache_read=8628`

  The OAuth bearer endpoint accepts both forms, and the stable prefix was read. The second call's user message differed, so the probe proved the system marker only; DD4's pass rule covers the tail. The installed SDK is 0.96.0 (`uv.lock`), and `AsyncMessages.create` and `.stream` both take `cache_control`.
- **Two refusals degrade gracefully:**
  - *An older SDK.* The project allows `anthropic>=0.40,<0.97`. An SDK without the top-level parameter raises `TypeError: unexpected keyword argument 'cache_control'`, which the existing squawk-0009 net strips.
  - *A refusing endpoint.* A proxy behind the environment-supplied `ANTHROPIC_BASE_URL`, which the SDK honours, or an endpoint that stops accepting the field, returns a `BadRequestError` whose message names `cache_control`. A new check strips both markers (the top-level key, and `system` back to the bare string) and retries once, like the temperature retry.
- **The retries must compose.** Today a retry inside `except TypeError` that then hits a `temperature` 400 is never given the temperature retry. Without caching that path never ran; with this change it would fail every turn on such an SDK and model.
  - `complete` and `stream` are restructured so each strip (temperature, a named unexpected kwarg, cache markers) removes its key and re-runs the whole attempt, under a small bounded loop with one strip per key.
  - A strip fires only while its key is still in kwargs. A repeat 400 or `TypeError` that names an already-stripped key falls through to the `tools.N` mapping or the re-raise. Today the temperature path pops without checking.
  - The cache-marker strip restores `system` from `kwargs["system"][0]["text"]`, and does nothing to `system` when none was sent.
  - On the first cache refusal, a per-instance flag (`self._cache_disabled`) is set so that `_build_kwargs` stops adding markers for that provider instance. A refusing proxy then costs one failed round trip per agent, not one per model call. The flag is never persisted; a rebuilt agent tries again.
  - `stream` keeps its `yielded_any` gate: no retry once a chunk has been emitted.
  - The `tools.N` → tool-name mapping keeps applying to the final 400.
  - Unit tests pin each strip, the TypeError-then-temperature combination and the bound.
- **Per-leg re-verify:** the plan token and endpoint behaviour are external. Leg 2's probe run is the re-check, and it runs first in that leg.

**DD6 — Known cache-invalidating events stay as they are**
- Each of these legitimately misses the cache from the change onward:
  - `search_tools` discovery adds a tool mid-turn: the `tools` array changes, and tools render first.
  - A self-configuration revision replaces `messages[0]` at a turn settle.
  - The OAuth sign-in resume path drops the auth-required placeholder tool messages from history (`core.py`, resume).
  - The date line changes on a reload after midnight.
  - The degraded tool-free path swaps the system prompt.
- None is fixed here; each is correct behaviour.
- Nothing toggles thinking mid-turn, because no caller passes `enable_thinking`. Tool order is already deterministic (registry order).
- Rationale: the charter's outcome is reuse within a turn on a stable prefix. Chasing these edge cases would be a second cluster of decisions.

**DD7 — `compare --models` checks a subset of the baseline's models** (operator choice, 2026-11-07)
- `compare` gains `--models NAME[,NAME...]`, in `evals/baseline.py` and `evals/__main__.py`, neither of which `SCORING_DIGESTS` pins.
  - The models fingerprint check recomputes the baseline's digest from the stored `models.{name}.{preset, effective, model_info}`, restricted to the selected names, through the same `fingerprint.models_fingerprint`. It compares that with the run's own digest.
  - The cell loop compares only the selected models' cells.
  - The header states the subset, so a filtered compare can never pass for a full one.
- **The run side is filtered once, at the start of `compare`.** `runset.records` is restricted to the selected models, so the run's fingerprint, `aggregate`, `exposure_counts` and `decided_mismatches` all see the same subset. A run that holds more models than selected is filtered quietly, and the header states the selection.
- The model-independent `size:*` gates still run and print, and the subset header says so.
- Without `--models`, `compare` behaves exactly as today, using the stored digest by construction.
- **Refusals**, each with a plain message:
  - a name the baseline lacks;
  - a selected model with no records in the run (today that surfaces as a confusing "models fingerprints differ").
- **Pinned by unit tests:**
  - an unfiltered digest equal to today's;
  - a filtered digest equal to a haiku-only run's;
  - unselected models' cells absent;
  - an unknown name refused.
- Rationale: criterion 4 is about haiku; caching cannot affect Ollama models. A filter costs only haiku quota, puts no load on the local models, and serves any future Claude-only change.
- Trade-off: one small feature in the eval tool. It is verification apparatus, not a second product decision.

### Citation Audit

Verified against the working tree at `baf9f8c3`, then re-checked by the Architect review:

| Citation | Status |
|---|---|
| `the_one/llm/anthropic_provider.py::AnthropicProvider._build_kwargs`: builds `system` as a bare string from the last `Role.SYSTEM` message, `tools` via `_to_anthropic_tool`, returns the kwargs dict used by both `complete` and `stream` | verified |
| `the_one/llm/anthropic_provider.py::AnthropicProvider.complete` / `_stream_inner`: map `usage.input_tokens`/`output_tokens` into `TokenUsage`, two sites | verified |
| `the_one/llm/anthropic_provider.py::complete`/`stream`: temperature retry inside `except BadRequestError`; squawk-0009 strip-and-retry inside `except TypeError`, only when the named key is in `kwargs`; the retry inside `except TypeError` does not get the temperature retry | verified |
| `the_one/llm/anthropic_plan_provider.py::AnthropicPlanProvider`, `AnthropicPlanTokenProvider`: override `_build_client`, `_before_request`, `complete`/`stream` (error translation only), `_translate_plan_error`; never `_build_kwargs` | verified |
| `the_one/llm/base.py::TokenUsage`: dataclass with `input_tokens: int = 0`, `output_tokens: int = 0` only | verified |
| `the_one/db/codec.py::_usage_to_dict` / usage decode: two keys, `.get(..., 0)` on decode | verified |
| `the_one/interfaces/web/app.py` (~2362, ~2572, ~2634, ~2965): `context_tokens` = last step's `usage.input_tokens`; `input_tokens` summed | verified |
| `evals/tokens.py::first_call_input_tokens`, `evals/outcomes.py::usage_totals`: read `usage.input_tokens`; they feed the informational `model_counts`, not the `size:*` gates | verified |
| `evals/baseline.py::check_comparable`: refuses on differing scenarios, models or prompt fingerprints (`--same-prompt` for an equal prompt); `compare` loops over every baseline model's cells | verified |
| `evals/report.py` `RunSet.models_fingerprint` → `evals/fingerprint.py::models_fingerprint(presets, effective, model_info)`; `s11-platform.json` stores `models.{haiku,lfm3,qwen3-4b}.{preset,effective,model_info}` | verified |
| `tests/test_evals_freeze.py::SCORING_DIGESTS`: pins `outcomes.py`, `harness.py`, `checks.py`, `judge.py` (not `baseline.py`, `__main__.py`) | verified |
| `evals/env.py::check_pinned_env`: refuses when a provider-shaping variable is set | verified |
| `the_one/agent/core.py::Agent.__init__`: `messages = [Message.system(system_prompt)]`; the system prompt is built once per agent | verified |
| `the_one/time_zones.py::render_date_line`: date only, "as of when this conversation was last loaded"; no clock time | verified |
| `anthropic` 0.96.0 (`uv.lock`): `create`/`stream` take `cache_control`; `Usage` has `cache_creation_input_tokens`, `cache_read_input_tokens` | verified (introspected) |
| `pyproject.toml`: `anthropic>=0.40,<0.97` | verified |
| `evals/models.toml [haiku]`: `anthropic-plan-token`, `claude-haiku-4-5-20251001` | verified |
| No existing test asserts `kwargs["system"]` as a string (`test_llm_provider_cross_provider_history.py:263/326` assert `_to_api_message` output, not kwargs) | verified (Architect grep) |

### Prerequisites
- [x] Plan token at `~/.config/the-one-evals/plan-token` is valid and the endpoint accepts `cache_control` (planning probe, DD5). Leg 2's probe run re-verifies it.
- [x] Baseline `evals/baselines/s11-platform.json` exists and stores per-model presets, effective settings and model info (DD7).
- [x] The `[evals]` extra (tiktoken) is installed in `.venv`, for `measure-prompt --json` in leg 2: tiktoken 0.14.0, re-checked at leg 2.
- [x] Ollama is not needed: leg 2 runs and compares `haiku` only (DD7).

### Pre-Flight Checklist
- [x] All open questions resolved
- [x] Design decisions documented
- [x] Citation Audit complete — every code-asserting design decision verified
- [x] Prerequisites verified (the `[evals]` extra is re-checked at leg 2)
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach
- **Provider (`anthropic_provider.py`)**:
  - The breakpoints in `_build_kwargs` (DD1).
  - The usage helper (DD2).
  - The composed strip-and-retry in `complete` and `stream` (DD5).
  - No change to the plan subclasses.
- **Usage type (`base.py`)**: two new `TokenUsage` fields with defaults (DD2).
- **Persistence (`db/codec.py`)**: emit the cache keys when non-zero, and decode them with defaults (DD2).
- **Evals**:
  - `evals/cache_probe.py`, its scenario TOML under `evals/cache_probe_data/`, and the `cache-probe` subcommand (DD4).
  - `compare --models` in `baseline.py` and `__main__.py` (DD7).
  - `evals/README.md` documents both, and that provider `input_tokens` is the whole prompt.
  - No edit to any `SCORING_DIGESTS` file.
- **Docs**:
  - `the_one/agents.md` gets an "Anthropic prompt caching (sortie 14)" block: the breakpoints and TTL rule, the `input_tokens` contract, the strip-and-retry ladder, and the invalidating events in DD6.
  - `CLAUDE.md` gets a one-paragraph pointer under the LLM layer, and the Prompt evals paragraph mentions `cache-probe` and `compare --models`.
  - `SECURITY-MODEL.md` needs nothing: the cache holds the same request bytes the API already receives, and secrets stay placeholders.
- **Tests** (unit tier, offline). None of the existing tests asserts `kwargs["system"]` as a string, so these are all new assertions.
  - `tests/test_anthropic_provider.py`:
    - `system` is the marked list and top-level `cache_control` is present;
    - with no system prompt, only the top-level field is sent;
    - both TTLs are equal;
    - usage mapping sums correctly, and `None`, missing or non-int cache fields count as 0;
    - each strip retries once: temperature, a `TypeError` naming `cache_control`, a 400 naming `cache_control` (back to the bare-string `system`);
    - the TypeError-then-temperature combination succeeds;
    - the retry bound holds, and a strip fires only while its key is present;
    - after a cache refusal, the instance stops sending markers (`_cache_disabled`);
    - `stream` does not retry after a yielded chunk;
    - the plan and plan-token providers produce the same kwargs.
  - `tests/test_db_codec.py`: a round trip with cache counts, and byte-identity without them.
  - An app-level test: a `TokenUsage` carrying cache fields yields the same usage-frame keys and values (`app.py` usage frames and `last_usage`).
  - `tests/test_evals_cache_probe.py`: pass, fail and inconclusive on hand-built traces, and the argument handling.
  - `tests/test_evals_compare*.py` (or the existing compare test file): the DD7 pins, the run-side filter, and both refusals.

### Checkpoints
- [x] Leg 1 implemented, unit tier green, reviewed and committed before any quota-heavy run (sortie 11 DD14).
- [x] Live probe exits 0 on haiku 4.5 (criteria 1, 2 live half, 3 for plan-token).
- [x] `compare --models haiku` against `s11-platform.json` shows no gate failure (criterion 4). It ran without `--same-prompt`, because the current prompt postdates the baseline; see the flight log, Deviations.

### Adaptation Criteria

**Divert if**:
- The plan endpoint rejects `cache_control` (the probe shows no cache reads because the strip path fired). Stop and ask the operator.
- The probe fails its DD2 assertions: the telemetry contract is broken.
- The haiku compare shows a gate failure that repeats on a re-run: behaviour moved, which caching must not do.

**Acceptable variations**:
- The probe's persona padding, prompt wording and margin.
- The helper's name and placement.
- The retry loop's exact shape, provided each strip runs once and the `yielded_any` gate holds.
- Extra unit tests.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `prompt-caching`: breakpoints and the composed retries in the provider, the `TokenUsage` cache fields through provider and codec, the `cache-probe` tool, `compare --models`, unit tests and docs. Autonomous; reviewed and committed before leg 2.
- [x] `cache-verification`: run by the Flight Director. Quota-heavy; no code changes unless a defect is found. Steps, in order:
  1. `make eval ARGS="cache-probe"`.
  2. `make eval ARGS="run --models haiku"`.
  3. `make eval ARGS="measure-prompt --json <run-dir>/measure.json"`.
  4. `make eval ARGS="compare <run-dir> --baseline evals/baselines/s11-platform.json --same-prompt --models haiku"`.
  5. Record the readings against criteria 1, 2 and 4.

---

## Post-Flight

### Completion Checklist
- [x] All legs completed
- [ ] Code merged
- [x] Tests passing
- [x] Documentation updated

### Verification
- `make test-unit` green (offline; no network), including `tests/test_evals_freeze.py` with unchanged digests.
- `make eval ARGS="cache-probe"` exits 0: call 2 reads at least what call 1 read and wrote, and `input_tokens` covers the cache counts on every call.
- The haiku-only compare against `s11-platform.json` (`--same-prompt --models haiku`): no gate failure.
