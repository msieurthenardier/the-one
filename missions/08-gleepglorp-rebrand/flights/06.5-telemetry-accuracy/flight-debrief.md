# Flight Debrief: Telemetry Accuracy

**Date**: 2026-05-14
**Flight**: [Telemetry Accuracy](flight.md)
**Status**: landed
**Duration**: 2026-05-14 (planning + execution + HAT same-day)
**Legs Completed**: 4 of 3 planned (L04 inline-spawned during L03 HAT)

## Outcome Assessment

### Objectives Achieved

F6.5's stated objective — make the chat telemetry context-fill percent accurate before F7 (UI Performance Audit) tries to measure performance against it — is delivered:

- **L01** converted `LLMProvider.max_context_tokens` from class attribute to instance attribute resolved lazily on first `complete()`/`stream()`. Per-provider: Anthropic 200k class-default unchanged; Ollama `/api/show` family-suffix extraction; OpenAI `OPENAI_MODEL_CONTEXT` 12-entry table with longest-prefix-wins (defeats the `gpt-4-1106-preview → 8k` trap); OpenRouter `list_models` + new `get_model_context_length` helper. Failure-path caching via `_max_context_tokens_resolved` sentinel prevents retry storms.
- **L02** shipped a `@pytest.mark.live` cross-provider validation harness (`tests/test_input_tokens_cross_provider_live.py`) asserting monotonic `input_tokens` growth across 3-turn conversations. Skips silently for unavailable providers.
- **L03 HAT** verified L01 against the operator's real qwen2.5:7b agent (telemetry now reflects the real 32k window; 2% → 10% across 2 turns), validated Anthropic + OpenRouter agents through real chat usage, and ran the L02 harness against qwen2.5:7b explicitly — passes in 0.76s. F6 KI #2 (Ollama prompt_tokens undercount) **did not reproduce** under controlled testing.
- **L04 (inline-spawned during HAT, operator-requested)** extended `GET /api/providers/{id}/models` to return per-model `context_length`, added a "Max context" chip in the agent editor, and added a `max:` row in the chat telemetry overlay. Caught and fixed a related bug: `_process_and_broadcast` was capturing `max_context_tokens` at function entry BEFORE the L01 resolver fired, so the first chat message showed 128k. Fix: removed the capture, read live at usage-event emission.

### Mission Criteria Advanced

| Criterion | Status | Notes |
|-----------|--------|-------|
| Browser-side performance has been measured under realistic use ... no unbounded growth across normal interaction | **Unblocked** | Telemetry now meaningful; F7 can measure against accurate denominators |
| All existing functionality (M01–M07 capabilities) continues working — no regression | **Met** | broad 1669p/4s/374d, browser 315p/35s, pixel 12/12 — all preserved exactly |

## What Went Well

- **Cycle-1 design reviews caught real bugs before implementation.** Most impactful: L01's OpenAI prefix-collision trap (`gpt-4-1106-preview` would have resolved to 8k via the bare `gpt-4` entry). The fix — explicit entries for preview/32k/vision variants before bare `gpt-4` in longest-prefix-wins order — became a 17-row parametrized test that pins the trap explicitly. L02's `OLLAMA_BASE_URL → LIVE_OLLAMA_BASE_URL` namespace fix and the `@pytest.mark.asyncio`-is-redundant correction also landed at cycle-1.
- **Recon report classified items decisively.** All 16 source items from F6's flight log + mission KIs were classified at planning time as either in-scope, already-satisfied, or carry-forward. Zero stale items entered the leg-design phase.
- **Lazy-on-first-call resolver shape held up cleanly.** Cycle-1's reader-site enumeration (only `app.py:689` and `:752` read `max_context_tokens`, both AFTER agent.step()) was load-bearing. Zero call sites broke; the `_max_context_tokens_resolved` sentinel + try/except/finally in `base.py:114-124` correctly handles the failure-path retry-storm prevention.
- **L04 inline-spawn during HAT was net-positive.** Operator-requested polish that consumes L01's data (a "Max context" chip + `max:` overlay row) AND surfaced a latent bug (`_process_and_broadcast` capture-before-resolver-fire) that would have been hard to spot without the visualization. Pattern is sustainable when scope is genuinely discovered-not-imagined, bounded (~80 lines), and explicitly annotated in the flight log.
- **L02's `live`-marker reuse** instead of inventing `requires_real_llm` kept the test infrastructure consistent with `test_aiat.py`'s existing convention.

## What Could Be Improved

### Process

- **Wire-test pinning convention** surfaced as a deviation during L01 implementation. Two pre-existing test files (`test_openrouter_wire_level.py`, `test_ollama_provider_auth.py`) pinned `captured[0]` for the chat-completion request, which broke when the new resolver fires `/models` or `/api/show` BEFORE chat completion. Fix landed inline (`_find_chat_request` helper, ~50 lines net across the 2 files), but a forward-looking note in L01's "Files Affected" — "wire-level tests pinning `captured[0]` will need updating" — would have set expectations and avoided the in-flight reroute.
- **Pre-first-turn telemetry shows zeros.** No `usage` event fires before the first user message, so `max:` reads 0 even though L04's endpoint could provide it. Operator noted; scope-creep'd out of the HAT (eager-resolve-at-session-join OR client-side fetch via `/api/providers/{id}/models` are both reasonable F7 micro-tasks).

### Technical

- **OpenRouter's "skip `super().__init__()`" carve-out is a tripwire.** `OpenRouterProvider.__init__` deliberately skips super to avoid the OpenAI SDK env-var leak, so it has to manually mirror every instance attribute the parent sets. Today that's `_max_context_tokens_resolved = False`, with a comment. Any future state added to `LLMProvider.__init__` will silently break OpenRouter until a runtime `AttributeError`. Architect-flagged as the flight's most actionable structural concern.
- **Anthropic 200k literal at `anthropic_provider.py:15` is a latent staleness vector.** No resolver override, no table, no docstring pointer. When Anthropic ships Claude 5 with a different context window, this becomes a perception bug identical to F6 KI #1. Architect recommends a one-line docstring pointing to the Anthropic docs and the OpenAI table as the migration template.
- **`OPENAI_MODEL_CONTEXT` is a known-staleness vector.** Documented in its docstring with a canonical-reference link to `https://platform.openai.com/docs/models`, but no operational reminder. Drift will be user-reported, not system-detected.
- **The L04 `_process_and_broadcast` live-read fix has no direct unit test.** The bug (capture-before-resolver-fire) is the kind of regression invisible until someone resurrects the eager-capture pattern. Operator-verified only.

### Documentation

- **`make rebuild` wipes Playwright Chromium** — F6.5 HAT hit this pattern twice (once during L03 HAT, once during the final regression smoke), each time requiring `make _ensure-playwright` to recover. Documented inline in flight logs since F5/F6; promoting to `agents.md` or making `make rebuild` idempotent w.r.t. Chromium would eliminate the operator footgun.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| L01 added `_find_chat_request` helper to two pre-existing wire-level test files | New resolver fires `/models` or `/api/show` BEFORE chat completion; tests pinned `captured[0]` | Yes — codify in test conventions if a third place needs it. Below rule-of-three for now. |
| L04 inline-spawned during L03 HAT (not in original plan) | Operator requested "show max in agent editor"; consumed L01's data + caught a latent bug | Pattern is sustainable when discovered-not-imagined, bounded, and flight-log-annotated. Watch for HAT-cycle scope creep on future flights. |
| `_process_and_broadcast` reads `max_context_tokens` live at usage emission instead of capturing | L01 resolver fires inside `agent.step()`; pre-step capture would lag by one turn | Yes — pattern: when a value is lazily resolved, NEVER pre-capture across the resolver boundary. |
| Cycle-2 design reviews skipped on both L01 and L02 | All cycle-1 fixes were content-level corrections, not structural pivots | Yes — the skill protocol's "skip if only minor/cosmetic" guidance held up cleanly in this flight. |

## Key Learnings

1. **Cycle-1 reviews catch hand-maintained-table prefix traps and helper-shape mismatches.** The OpenAI prefix-collision and the OpenRouter `get_model_capabilities`-returns-frozenset-not-Entry catches were both pre-implementation saves.
2. **Lazy-on-first-call is a viable pattern WHEN reader-site enumeration is done at design time.** The cycle-1 reader-audit (only 2 readers, both post-step) made the choice safe. Generalizing without that audit would be risky.
3. **Operator-requested HAT-cycle scope additions can be net-positive when they consume already-delivered backend data.** L04's chip + overlay row built on L01's resolved values — zero new backend work, frontend integration only, plus the bug surfaced by the visualization. Bounded scope (~80 lines) and flight-log annotation kept it from sprawling.
4. **Wrong-denominator perception bugs masquerade as data bugs.** F6 KI #2 (Ollama undercount) didn't reproduce in any controlled test or real chat usage post-L01. The original symptom — flat ~1000 tokens — was the wrong-denominator effect: 1k → 2k growth against 128k denominator displays as 0.8% → 1.6%, visually "stuck." With the real 32k denominator, the same growth shows as 3% → 6% — clearly moving.

## Test Metrics

Captured at debrief time (post-L04, post-HAT, post-commit `eb454c6`):

| Suite | Pass | Skip | Deselect | Time |
|-------|------|------|----------|------|
| Broad pytest | **1669** | 4 | 374 | **94.10s** |
| Browser (`-m browser`) | **315** | 35 | 1697 | **263.95s** |
| Pixel (`-m pixel`) | **12** | 0 | 2035 | **18.34s** |

**Comparison vs prior debriefs**:

- F5 (Chat Response Trace) baseline: 1622p/4s broad in 98.90s, 315p/35s browser in 271.01s, 12/0 pixel in 18.96s.
- F6 (Chat Polish) baseline at close: 1627p/4s broad, 315p/35s browser, 12/0 pixel.
- F6.5 close: **1669p/4s** broad (+42 from F6, the new `test_llm_max_context.py` mocked unit tests; +47 vs F5). Browser **-7s vs F5**, **identical pass/skip counts**. Pixel **-0.6s vs F5**, **identical pass/skip counts**.

No failing tests, no new skips, no flakes observed. The +42 broad-pytest growth is exactly the L01 unit-test contribution (L02's 4 `live` tests are deselected by default). Browser and pixel baselines preserved exactly — no UI semantics regressed across L04's chip + telemetry-overlay row additions.

**Two pre-existing warnings** observed but not introduced by F6.5: `test_provider_api::test_ollama_models` emits two `AsyncMock` coroutine-never-awaited warnings. Carry-forward to a future MCP/test-cleanup flight; not in scope here.

## Recommendations

1. **Refactor OpenRouter's "skip super" carve-out into an `_init_provider_state()` hook on `LLMProvider`.** Defuses the tripwire identified by the architect. Any future state added to base.py is then automatically inherited. ~30 minutes. Candidate for an opportunistic maintenance flight or fold into a future provider-touching flight.
2. **Add an explicit no-op `_resolve_max_context_tokens` override on `AnthropicProvider`** with a docstring pointing to the migration template (the OpenAI table). Makes intent legible. ~5 minutes. Stays at 200k until Anthropic ships a non-200k model.
3. **Add a unit test for the `_process_and_broadcast` live-read fix.** Mock an `LLMProvider` whose `max_context_tokens` is set post-construction; assert the broadcast `usage` event reflects the post-construction value. ~20 lines. Pins the L04 HAT-cycle inline bug against regression.
4. **F7 UI Performance Audit must anchor against the L01-resolved `max_context_tokens`.** F7's perf-budget code must NOT fall back to the 128k class default in any measurement code path; if it does, the budget is wrong. Carry-forward note: F6.5 made the denominator meaningful — F7 has to consume it correctly.
5. **Carry-forward to F7**: eager-resolve-at-session-join or client-side fetch via `/api/providers/{id}/models` to fix the pre-first-turn-telemetry-zero observation. The L04 endpoint already returns the data; client-side fetch is the lower-risk path.
6. **`make rebuild` wipes Playwright Chromium** — document in `agents.md` or make `make rebuild` idempotent w.r.t. Chromium. Surfaced in F5, F6, F6.5; recurring operator footgun.

## Action Items

- [ ] Refactor OpenRouter `__init__` to use a base-class `_init_provider_state()` hook (or equivalent) — defuse the "skip super" tripwire
- [ ] Add an explicit `_resolve_max_context_tokens` no-op override on `AnthropicProvider` with a migration-template docstring
- [ ] Add a unit test for `_process_and_broadcast` live-read of `max_context_tokens`
- [ ] F7 design phase: anchor measurement code paths against the resolved `max_context_tokens`; reject any fallback to class default in perf-critical paths
- [ ] F7 (or polish flight): eager-resolve-at-session-join OR client-side fetch via `/api/providers/{id}/models` to surface `max:` in the telemetry overlay BEFORE the first user message
- [ ] Document `make rebuild` Chromium wipe in `agents.md` or make rebuild idempotent
- [ ] Investigate pre-existing `test_provider_api::test_ollama_models` AsyncMock warnings as part of the next MCP-touching flight
