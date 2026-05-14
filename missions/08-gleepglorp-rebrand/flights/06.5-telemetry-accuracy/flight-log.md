# Flight Log: Telemetry Accuracy

**Flight**: [Telemetry Accuracy](flight.md)

## Summary

Brief overview of execution status and key outcomes. (Populated as legs land.)

---

## Reconnaissance Report

Performed during flight planning (2026-05-14). Source artifacts inspected: F6 flight log L06 HAT findings (`missions/08-gleepglorp-rebrand/flights/06-chat-polish/flight-log.md`); F6 close mission KIs added to `mission.md`; provider code state on `main` (post-F6 merge commit `1e34951`).

| # | Source | Item | Classification | Evidence | Recommendation |
|---|---|---|---|---|---|
| 1 | F6 KI: `max_context_tokens` hardcoded | Class-level default 128k everywhere except Anthropic | confirmed-live → L01 | `the_one/llm/base.py:87 — "max_context_tokens: int = 128_000"`; `the_one/llm/anthropic_provider.py:15 — "max_context_tokens = 200_000"`; no overrides in `openai_provider.py`, `ollama_provider.py`, `openrouter_provider.py` | Scope into F6.5 L01 (`max-context-per-model`) |
| 2 | F6 KI: Ollama `prompt_tokens` may undercount | Operator-observed flat ~1000 token count after multi-turn qwen convo | confirmed-live (symptom) / unverified (root cause) → L02 | `the_one/llm/ollama_provider.py:105,152,181 — "input_tokens=u.get('prompt_tokens', 0)"` reads what Ollama reports; agent sends full history (verified at F6 HAT investigation in `the_one/agent/core.py:172-173`) | Scope into F6.5 L02 (`input-tokens-cross-provider-validation`) for root-cause localization |
| 3 | F6 KI: Mid-stream `usage` event | Telemetry only updates at step completion, not during streaming | confirmed-live → OUT of F6.5 scope | `the_one/llm/openai_provider.py:121-125`, `ollama_provider.py:149-154` — `usage` only emitted on the final metadata chunk (when `choices` is empty) | Carry forward to F7 or polish flight; explicitly scoped OUT of F6.5 in flight spec |
| 4 | F6 KI: No stop button | No cancel affordance during active turn | NOT F6.5 scope | Feature work, not telemetry accuracy | Carry forward to dedicated reliability/agent-loop flight |
| 5 | F6 KI: qwen long-convo loops | Agent-loop behavior on local models | NOT F6.5 scope | Pairs with #4 | Carry forward to dedicated reliability flight |
| 6 | F6 HAT inline fixes | Smart-scroll, log-in copy edit, scroll-to-bottom on join | already-satisfied | All landed in F6 close commit `9f6b198` on flight/06-chat-polish (merged to main) | Retire — informational only |
| 7 | F6 design decisions | F5 codec round-trip + truncation alignment + Settings lazy + L03/L04/L05 polish | already-satisfied | Merged to main in commit `1e34951` (F6) | Retire — informational only |
| 8 | F6 unexercised: WS-reconnect mid-turn | F5 AI #5 defensive path remains unverified | NOT F6.5 scope | Reproducing the network drop is hard; F6 HAT skipped same as F5 | Carry forward — dedicated reliability flight or F7 |
| 9 | Per-agent `max_context_tokens` override field | Mentioned in F6 close as "optional / nice-to-have if HAT surfaces uncovered models" | NOT-yet-scope | Out-of-the-box defaults from L01 should be sufficient; revisit only if HAT fails | Carry forward to F6.5 HAT for re-evaluation; spawn an L04 if needed |
| 11 | Cycle-1 review: lazy resolution feasibility | Only `app.py:689` (`_broadcast_one`) and `app.py:752` (`_process_and_broadcast`) read `self.llm.max_context_tokens`; both fire AFTER first `complete()`/`stream()` | confirmed-safe → L01 | Architect verified live at design review | Risk retired — Adaptation Criteria divert path stays as future-proofing only |
| 12 | Cycle-1 review: Ollama `model_info` shape | Live `/api/show` for `qwen2.5:7b` shows `model_info.qwen2.context_length = 32768`; top-level keys follow `{family}.{field}` pattern | confirmed-correct → L01 | Architect verified against running Ollama | Use `.context_length` suffix match (NOT family-prefix); design decision updated |
| 13 | Cycle-1 review: OpenRouter resolver path | `get_model_capabilities` returns `frozenset[str]` of `supported_parameters`, NOT `OpenRouterModelEntry`. Need to call `list_models(base_url, api_key)` and walk for matching `entry.id` | confirmed-error → L01 design fix applied | Architect read `openrouter_api.py:169-208` | Design decision updated: L01 calls `list_models` directly OR adds a new `get_model_context_length` helper |
| 14 | Cycle-1 review: pytest `live` marker | Project already defines `live: marks tests that call real LLM APIs` in `pyproject.toml`; deselected by default | confirmed-existing → L02 | Architect verified `pyproject.toml` markers section | Use `@pytest.mark.live`; do NOT invent new `requires_real_llm` marker; test naming `tests/test_*_live.py` per project convention |
| 15 | Cycle-1 review: async __init__ feasibility | `factory.py:223` calls `get_provider(...)` from within an async method; making __init__ async is technically viable, not "infeasible" | partial-correction | Architect verified `agent/factory.py:186-229` | Design decision rationale updated to "surface-area minimization, not feasibility"; lazy-on-first-call choice stands |
| 16 | Cycle-1 review: failure-path caching | Without an instance "resolved" flag, every `complete()`/`stream()` call retries the failed fetch | confirmed-risk → L01 design fix applied | Architect raised as Question | Design decision updated: resolver sets `_max_context_tokens_resolved = True` regardless of fetch outcome; class-default stays if fetch fails |
| 10 | OpenAI model context-window table | New maintenance vector introduced by L01 | confirmed-live (forward) | Documented in L01 design as "manual maintenance, fall back to class default on unknown models" | Known-staleness call-out in code comment + agents.md note (deferred to L01 implementation) |

**Summary**: 2 items in F6.5 scope (KI #1 → L01, KI #2 → L02), 3 items already-satisfied by F6, 4 items carry-forward to future flights, 1 forward-looking maintenance note. Operator confirmed at F6 close: F6.5 is the bridging flight; F7 starts after F6.5.

**Open for operator confirmation**:
- Anthropic stays at class-default 200k (no per-model table). All current Claude models are 200k; revisit only if Anthropic ships a different-size model.
- Mid-stream `usage` (KI #5) explicitly deferred to F7 / polish-flight. Confirm this isn't a blocker for F7 itself.

---

## Flight Director Notes

### 2026-05-14 — Flight start

- Branch `flight/06.5-telemetry-accuracy` created from `main` (commit `1e34951`)
- Flight status updated to `in-flight`
- Phase file loaded: `the-one/.flightops/agent-crews/leg-execution.md` (project-owned) — Developer = Sonnet, Reviewer = Haiku

### 2026-05-14 — L01 design + design review cycle 1

- L01 (`max-context-per-model`) drafted per flight spec design decisions
- Cycle-1 spawn: general-purpose Developer for design review
- Findings: 1 high, 2 medium, 3 low + 2 suggestions
  - **[high]** OpenAI prefix-match table had a real bug: `gpt-4-1106-preview` (128k actual context) would prefix-match `gpt-4` (8k entry) → resolve to 8k. Same trap for `gpt-4-0125-preview`, `gpt-4-vision-preview` (all 128k → 8k), and `gpt-4-32k` (32k → 8k). **Fix applied**: expanded `OPENAI_MODEL_CONTEXT` with explicit entries for the tricky variants (`gpt-4-32k`, `gpt-4-vision-preview`, `gpt-4-0125-preview`, `gpt-4-1106-preview`) BEFORE bare `gpt-4`; longest-prefix-wins ordering resolves correctly. Also added `gpt-3.5-turbo-instruct` (4k) and `gpt-3.5-turbo-16k` (16k) for completeness. Added canonical-reference link to https://platform.openai.com/docs/models in the docstring.
  - **[medium]** Acceptance criterion's OpenAI test matrix was sparse — only covered `gpt-4o-2024-05-13` and `my-finetune`. **Fix applied**: expanded the test case list to lock in the previously-trapped models: `gpt-4-1106-preview` → 128k, `gpt-4-0125-preview` → 128k, `gpt-4-vision-preview` → 128k, `gpt-4-32k-0613` → 32k, `gpt-4-0613` → 8k (legacy default), `gpt-3.5-turbo-instruct` → 4k, `gpt-3.5-turbo-16k` → 16k.
  - **[medium]** Edge-case wording about test doubles was reversed. The original claimed "resolver call is the FIRST line of complete/stream so it WILL run" for MockProvider — that's WRONG since MockProvider/FakeLLM define their OWN complete/stream that don't call super. The leg only inserts the resolver call into the four REAL providers' complete/stream methods. **Fix applied**: rewrote the Edge Case to correctly state that the resolver wrapper never fires for the five test-side subclasses (`MockProvider`, `FakeLLM`, `_CompleteOnlyProvider`, `_MultiIterLLM`, `_DummyProvider`).
  - **[low]** Per-call overhead trade-off (one `await` per complete/stream call when sentinel is True). **Fix applied**: documented in Edge Cases as sub-microsecond noise; async for symmetry with truly-async underlying resolvers (Ollama/OpenRouter).
  - **[low]** Test subclass enumeration was incomplete (leg listed only "MockProvider / FakeLLM"). **Fix applied**: enumerated all five test subclasses with file:line refs in Edge Cases.
  - **[low]** Note about base `LLMProvider.stream()` default impl not being modified. **Fix applied**: explicit note in Edge Cases.
  - **Suggestions noted (no change)**: putting resolver in base.stream() default impl was deferred (keeps blast radius smaller); regex matcher for OpenAI was deferred (explicit entries are clearer for hand-maintained table).
- **Cycle-2 decision**: skipped per skill protocol — all fixes are content corrections (additions to the OpenAI table, wording corrections in Edge Cases, expansion of test matrix). No change to design conclusion, leg shape, files affected, or acceptance criteria structure.
- L01 status → `ready`

### 2026-05-14 — L01 implementation landed

- Spawned general-purpose Developer (Sonnet) to implement L01
- Result: 7 production files + 3 test files touched (1 new + 2 fixed). +ish 200 lines total. **`gpt-4-1106-preview` smoke verified**: resolver returns 128000 (NOT 8192). Cycle-1 OpenAI table fix held.
- Broad pytest 1669p/4s/370d exit 0 in 93.52s — L05-baseline 1627 + 42 new unit tests. Browser suite 315p/35s preserved
- 2 pre-existing wire-level tests (`test_openrouter_wire_level.py`, `test_ollama_provider_auth.py`) needed `_find_chat_request` helper because new resolver fires `/models` or `/api/show` BEFORE chat-completion. Fixed in scope (~50 lines net across the 2 files); same contract, more precise about which on-wire request is pinned. Documented in flight-log Deviations.
- L01 status → `landed`. NOT committed per agentic-workflow batched-review protocol

### 2026-05-14 — L02 design + design review cycle 1

- L02 (`input-tokens-cross-provider-validation`) drafted: ships `@pytest.mark.live` test harness in `tests/test_input_tokens_cross_provider_live.py` with 4 tests (one per real provider); diagnostic only — no inline fix to Ollama undercount in this leg (categorization at L03 HAT)
- Cycle-1 spawn: general-purpose Developer for design review
- Findings: 0 high, 2 medium, 2 low + 2 suggestions
  - **[medium]** `@pytest.mark.asyncio` decorations are REDUNDANT — project sets `asyncio_mode = "auto"` in `pyproject.toml:52`; L01's `tests/test_llm_max_context.py` doesn't use the explicit decoration. **Fix applied**: dropped `@pytest.mark.asyncio` from all 4 example tests; only `@pytest.mark.live` remains.
  - **[medium]** `OLLAMA_BASE_URL` is NOT a project-recognized env var — production uses `THE_ONE_LLM_BASE_URL` via factory (`docker-compose.yml:53`). The leg invented `OLLAMA_BASE_URL` which would collide if production ever decides to honor it. **Fix applied**: renamed to `LIVE_OLLAMA_BASE_URL` throughout (explicit test-only namespace, no collision risk).
  - **[low]** Anthropic key-family mismatch (a Sonnet-only key against the default `claude-haiku-4-5-20251001` model would raise `PermissionDeniedError`, not skip). **Fix applied**: added Edge Case bullet describing the `try/except` pattern + skip-on-permission-error with hint to set `LIVE_ANTHROPIC_MODEL`.
  - **[low]** AC about prompt-caching was over-claiming "`input_tokens` reports FULL prompt size regardless." Anthropic actually splits `input_tokens` (non-cached) from `cache_read_input_tokens` (cached). **Fix applied**: softened the AC to acknowledge the split; argued the monotonic-non-decreasing assertion still holds for short 3-turn conversations under the 1024-token cache threshold.
  - **Suggestions accepted**:
    - Client teardown — added to Edge Cases as a try/finally pattern recommendation (warnings, not failures).
    - Verify live-marker count empirically via `pytest --collect-only -m live -q` rather than assuming `6 → 10`. **AC updated** to require empirical verification.
  - **Reviewer-confirmed (no change needed)**:
    - `Message.user(...)` / `Message.assistant(...)` exist as classmethods (`base.py:42-65`); appending the response Message directly to messages list IS correct.
    - OpenRouter `_NO_KEY_PLACEHOLDER` means construction won't raise without a key — skip-before-construct guard catches no-key case correctly.
- **Cycle-2 decision**: skipped per skill protocol — all fixes are AC clarifications, env-var rename, and Edge Cases additions; no structural change to test shape, file paths, or design conclusion. The OpenAI-table-style high-severity bug pattern from L01 doesn't reappear here.
- L02 status → `ready`

---

## Leg Progress

### 2026-05-14 — L01 landed: max-context-per-model

**Status**: `landed` (not yet checked off in flight.md — that happens during the post-L02 commit batch per agentic-workflow protocol).

**Files changed** (line counts via `git diff --stat` against `1e34951`):
- `the_one/llm/base.py` — +37 / -0 (logger import, `LLMProvider.__init__`, no-op `_resolve_max_context_tokens`, lazy wrapper `_resolve_max_context_tokens_if_needed`)
- `the_one/llm/anthropic_provider.py` — +3 / -0 (`super().__init__()`, resolver call at top of `complete` + `stream`)
- `the_one/llm/openai_provider.py` — +40 / -0 (module-scope `OPENAI_MODEL_CONTEXT` dict, `_resolve_max_context_tokens` override, `super().__init__()`, resolver call at top of `complete` + `stream`)
- `the_one/llm/ollama_api.py` — +20 / -0 (`extract_ollama_context_length` module-scope helper)
- `the_one/llm/ollama_provider.py` — +15 / -0 (`_resolve_max_context_tokens` override, `super().__init__()`, resolver call at top of `complete` + `stream`)
- `the_one/llm/openrouter_api.py` — +30 / -0 (`get_model_context_length` module-scope helper)
- `the_one/llm/openrouter_provider.py` — +21 / -0 (`_resolve_max_context_tokens` override, manual `_max_context_tokens_resolved = False` init since `super().__init__()` is intentionally skipped)
- `tests/test_llm_max_context.py` — NEW, 325 lines total (42 unit tests across `TestExtractOllamaContextLength`, `TestOpenAIPrefixLookup`, `TestOllamaResolver`, `TestOpenRouterResolver`, `TestAnthropicDefault`)
- `tests/test_openrouter_wire_level.py` — +25 / -4 (added `_find_chat_request` helper; switched the 4 wire pins from `captured[0]` to `_find_chat_request(captured)` since the resolver now fires `/models` before `/chat/completions`)
- `tests/test_ollama_provider_auth.py` — +29 / -5 (added `_find_chat_request` helper + handler now returns `{"model_info": {}}` for `/api/show` resolver probe; switched the 4 auth-header pins from `captured[0]` to `_find_chat_request(captured)`)

**Test results**:
- Targeted: `tests/test_llm_max_context.py` — 42 passed (new).
- Targeted regression check: `tests/test_streaming.py tests/test_llm_registry.py` — 21 passed (no breakage from the new `LLMProvider.__init__`; test subclasses that don't call `super().__init__()` are unaffected because they also don't call the resolver wrapper).
- Targeted reader-site check: `tests/test_auto_load.py tests/test_app_websocket_pause_resume.py` — 14 passed.
- Broad pytest: `docker exec the-one pytest --timeout 30` — **1669 passed, 4 skipped, 370 deselected in 93.52s**. Exit 0. Baseline was 1627p/4s/370d at F6 close → +42 from the new test file, no regressions.
- Browser suite: `docker exec the-one pytest -m browser --timeout 60 --tb=line` — **315 passed, 35 skipped, 1693 deselected in 261.19s**. Unchanged from baseline.

**Smoke verification**: `docker exec the-one python -c "import asyncio; from the_one.llm.openai_provider import OpenAIProvider; p = OpenAIProvider(model='gpt-4-1106-preview', api_key='x'); asyncio.run(p._resolve_max_context_tokens_if_needed()); print(p.max_context_tokens)"` printed `128000` (would have been `8192` without the explicit `gpt-4-1106-preview` entry that defeats the `gpt-4` prefix collision). Resolver fires on a real provider end-to-end.

**Acceptance criteria**: all 18 checkboxes verified.

---

### 2026-05-14 — L02 landed: input-tokens-cross-provider-validation

**Status**: `landed` (not yet checked off in flight.md — that happens during the post-L02 commit batch per agentic-workflow protocol).

**Files changed**:
- `tests/test_input_tokens_cross_provider_live.py` — NEW, 250 lines (4 tests + 3 helpers + module docstring). One `@pytest.mark.live` test per provider (`test_anthropic_input_tokens_monotonic`, `test_openai_input_tokens_monotonic`, `test_ollama_input_tokens_monotonic`, `test_openrouter_input_tokens_monotonic`). Shared `_run_three_turn_conversation` driver + `_assert_monotonic_growth` + `_skip_on_auth_error` + `_aclose_provider_client` teardown helper. Auth/permission errors translate to `pytest.skip` (not failure) with hint pointing at `LIVE_{PROVIDER}_MODEL` override. Ollama base URL via `LIVE_OLLAMA_BASE_URL` env var (avoids colliding with the production `OLLAMA_BASE_URL` config namespace); strips trailing `/v1` so the same env value works for both bare-host and OpenAI-compat targets.
- `pyproject.toml` — `live=6` → `live=10` (and `total=308` → `total=312`) in the per-marker deselect-math comment at line 59. Verified empirically via `pytest --collect-only -m live -q | tail -3` before AND after — went from `6/2043 collected (2037 deselected)` to `10/2047 collected (2037 deselected)`.

**Test results**:
- Targeted collection (`pytest --collect-only -m live tests/test_input_tokens_cross_provider_live.py -q`): 4 tests collected. Default-CI collection (`pytest --collect-only tests/test_input_tokens_cross_provider_live.py -q` without `-m live`): 4 deselected (correctly excluded by default `addopts`).
- Skip-behavior verification (`pytest -m live tests/test_input_tokens_cross_provider_live.py -v` with no credentials in env): 3 skipped (anthropic, openai, openrouter — credentials absent) **+ 1 passed (ollama)** — `host.docker.internal:11434` was reachable from inside the dev container during the run, so the Ollama test ran end-to-end against the operator's local Ollama and the monotonic-growth assertion held. Not a leg defect; the test is functioning correctly (zero env vars → still does its diagnostic job for any locally-reachable provider). Documented for transparency.
- Broad pytest (`pytest -x --timeout 30`): **1669 passed, 4 skipped, 374 deselected in 92.32s**. Exit 0. Pass count UNCHANGED from L01 (1669); deselect count +4 (was 370, now 374) — new live tests deselected by default `addopts`.
- Browser suite (`pytest -m browser --timeout 60 --tb=line`): **315 passed, 35 skipped, 1697 deselected in 257.20s**. Unchanged.

**Anomaly**: Ollama test passed (rather than skipped) during the no-env-vars skip-behavior run. The expected baseline was "4 skipped" because no provider credentials were set; however, `LIVE_OLLAMA_BASE_URL`'s default falls back to `host.docker.internal:11434/v1` which IS reachable from inside this container, and the local Ollama instance has models loaded. Test correctly probed, picked an available model, ran 3 turns, and asserted monotonic growth — all green. This validates the harness end-to-end on the most accessible provider; for the L03 HAT cycle the operator can still explicitly target qwen2.5:7b via `LIVE_OLLAMA_MODEL=qwen2.5:7b` to reproduce the F6 KI #2 scenario. No leg defect — recorded here so the "1 passed, 3 skipped" reading isn't mistaken for a regression.

**Acceptance criteria**: all 12 checkboxes verified.

---

## Decisions

Runtime decisions not in original plan.

---

## Deviations

Departures from planned approach.

### 2026-05-14 — L01: wire-test fixups outside leg's planned "Files Affected"

The leg spec's "Files Affected" listed 8 files (the seven `the_one/llm/*` files + `tests/test_llm_max_context.py`). During the broad pytest run, two pre-existing wire-level test files broke because the new resolver fires a metadata request (`/models` for OpenRouter, `/api/show` for Ollama) before the chat-completion request — and those tests asserted on `captured[0]` assuming the chat-completion was the first request on the wire.

**Files touched outside the planned list**:
- `tests/test_openrouter_wire_level.py` — added `_find_chat_request` helper; 4 assertions switched from `captured[0]` to `_find_chat_request(captured)`.
- `tests/test_ollama_provider_auth.py` — added `_find_chat_request` helper + extended the mock handler to return `{"model_info": {}}` for the new `/api/show` resolver probe; 4 assertions switched the same way.

This is a pure test-suite adjustment (no production-code semantics changed): the wire-level pins still pin the same OpenRouter/Ollama auth + ranking-header contracts, just on the chat-completion request specifically rather than "whichever request is first on the wire". The new behaviour — a `/models` or `/api/show` precedes the chat completion — is the intended L01 design (lazy resolver fires at top of `complete()`/`stream()`), so the test pin needs to be more specific. Documented for future readers.

---

## Anomalies

Unexpected issues encountered.

---

## Session Notes

Chronological notes from work sessions.

### 2026-05-14 — Architect design-review cycle 1

Spawned Architect (Opus, project-crew default) against the F6.5 draft spec. Result: **approve with changes**. 1 high + 2 medium + 4 suggestions + 2 questions.

**Cycle-1 changes incorporated**:

- **[high]** OpenRouter resolver premise was wrong — `get_model_capabilities(base_url, api_key, model)` returns `frozenset[str] | None` of `supported_parameters`, NOT an `OpenRouterModelEntry` with `context_length`. **Fix applied**: rewrote the OpenRouter Design Decision to use `list_models` directly OR a new sibling `get_model_context_length` helper. Also noted `api_key` is required positional (not just `(base_url, model)`).
- **[medium]** Lazy-resolution rationale overstated the "async __init__ would ripple" argument — `factory.py:223` is in an async method and `await get_provider(...)` would be a 1-line change. **Fix applied**: rewrote rationale to acknowledge async __init__ is technically viable; choosing lazy for surface-area minimization (provider registry's `get_provider` signature, test fixtures), not feasibility.
- **[medium]** Pytest marker — project already defines `live` in `pyproject.toml`. **Fix applied**: L02 now uses `@pytest.mark.live` (existing convention), test path `tests/test_input_tokens_cross_provider_live.py`.
- **Suggestion accepted**: Ollama `model_info.{family}.context_length` — Architect verified live API shape (`qwen2.5:7b` returns `model_info.qwen2.context_length = 32768`). **Fix applied**: switched from family-prefix match to `.context_length` suffix match (safer against multi-segment future family prefixes).
- **Suggestion accepted**: documented lazy-resolution feasibility verification in flight-log recon (rows 11-16 added).
- **Suggestion accepted**: pre-committed OpenAI table location to `the_one/llm/openai_provider.py` (module-scope dict, not separate module).
- **Suggestion accepted**: referenced `OllamaProvider.supports_tools` (`ollama_provider.py:48-50`) as the async-helper-with-cache pattern to mirror in `_resolve_max_context_tokens`.
- **Question 2 resolved (failure-path caching)**: design now requires `_max_context_tokens_resolved = True` regardless of fetch outcome — prevents retry storm on every `complete()`/`stream()` call when metadata fetch fails. Class-default stays when fetch fails.

**Cycle-2 decision**: skipped per skill protocol "skip if only minor/cosmetic fixes were applied" — the high-severity fix is a Design Decision wording correction (not a structural pivot), and the mediums + suggestions are language tightening. No leg-breakdown change; L01 still sized appropriately per Architect.

**Sign-off**: ready for crew sign-off. F6.5 status → `ready` pending user confirmation.

### 2026-05-14 — Flight planning

- F6 merged as `1e34951` on main; PR #52 closed
- F6.5 scope locked to telemetry accuracy: per-model `max_context_tokens` resolution + cross-provider `input_tokens` validation
- 3-leg breakdown: L01 (max-context-per-model), L02 (input-tokens-cross-provider-validation), L03 (telemetry-accuracy-hat)
- KI #5 (mid-stream usage) explicitly out of scope — defer to F7 or polish flight
- KI #3 + #4 (no stop button, qwen loops) — feature work; dedicated flight; out of scope here
- Reconnaissance report compiled (see above)
- Design decisions pre-committed: lazy resolution at first LLM call (avoids async __init__), Ollama family-key wildcard match, OpenAI manual table, OpenRouter via existing model cache, Anthropic unchanged
