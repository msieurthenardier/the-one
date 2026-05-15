# Flight Log: UI Performance Audit

**Flight**: [UI Performance Audit](flight.md)

## Summary

Brief overview of execution status and key outcomes. (Populated as legs land.)

---

## Reconnaissance Report

Performed during flight planning (2026-05-14). Source artifacts inspected: F6.5 flight-debrief Action Items + Recommendations; F6 close mission KIs in `mission.md` (post-F6.5-merge state); F3-F6 flight debriefs for routing-defect carry-forwards; current code state on `main` (post-F6.5 merge commit `95ae1f7`).

| # | Source | Item | Classification | Evidence | Recommendation |
|---|---|---|---|---|---|
| 1 | F6.5 debrief AI #1 | Refactor OpenRouter "skip super" carve-out into base-class `_init_provider_state()` hook | confirmed-live → L05 | `the_one/llm/openrouter_provider.py:63-65` "Override constructor entirely — do NOT call super().__init__()"; line 105 manually sets `self._max_context_tokens_resolved: bool = False` | Scope into F7 L05 (`carry-forward-cleanup-and-routing-triage`) |
| 2 | F6.5 debrief AI #2 | Explicit no-op `_resolve_max_context_tokens` override on `AnthropicProvider` with migration-template docstring | confirmed-live → L05 | `the_one/llm/anthropic_provider.py:15 — "max_context_tokens = 200_000"`; no resolver override exists | Scope into F7 L05 |
| 3 | F6.5 debrief AI #3 | Unit test for `_process_and_broadcast` live-read of `max_context_tokens` | confirmed-live → L05 | `the_one/interfaces/web/app.py:752-756` has the fix (no capture; live-read) but no test pins the contract; grep `live-read` in tests/ returns empty | Scope into F7 L05 |
| 4 | F6.5 debrief AI #4 | F7 must anchor measurement against resolved `max_context_tokens` | architectural anchor → L01 | F6.5 made denominator meaningful; F7 perf-budget code must consume it correctly | Anchor in L01 design — perf-budget calculations use `self.llm.max_context_tokens` (instance), NOT the class default |
| 5 | F6.5 debrief AI #5 | Eager-resolve max_context_tokens at session join OR client-side fetch via `/api/providers/{id}/models` | confirmed-live → L04 | F6.5 L04 endpoint at `the_one/interfaces/web/api.py:2381-2525` returns per-model context_length; chat.js session_joined handler at `chat.js:727-754` does NOT fetch it | Scope into F7 L04 (`mid-stream-usage-and-eager-resolve`); use client-side fetch path (lower-risk per F6.5 architect) |
| 6 | F6.5 debrief AI #6 | `make rebuild` Chromium wipe documented in `agents.md` (currently only in flight logs since F5) | confirmed-live → L05 | Recurring operator footgun across F5/F6/F6.5 HATs; no agents.md note | Scope into F7 L05 |
| 7 | F6 KI #5 | Mid-stream `usage` event emission (currently only fires at step completion) | confirmed-live → L04 | `the_one/llm/openai_provider.py:160-165` emits usage on final metadata chunk only (when `choices` is empty); same pattern in `ollama_provider.py:149-154` | Scope into F7 L04 |
| 8 | F6 KI #3 | No stop / cancel button | confirmed-live → NOT F7 scope | Feature work, not perf | Carry forward to dedicated reliability/agent-loop flight |
| 9 | F6 KI #4 | Long-convo loops on qwen | confirmed-live → NOT F7 scope | Pairs with #8 | Same future flight as #8 |
| 10 | F6 KI #8 | WS-reconnect mid-turn defensive path unexercised | confirmed-live → NOT F7 scope | `chat.js:407-424` `getOrCreateTrace` self-heal still unverified; HAT skipped in F6 again | Carry forward to dedicated reliability flight |
| 11 | Mission criterion: routing | Per-area routing and navigation correctness | partial → L05 (verify-only) | F3-F6 flight-debrief Action Items contain ZERO open routing defects; F6 L06 Scenario 9 PASSED with one inline fix (scroll-to-bottom on session-join); F4 / F3 don't carry forward open items | L05 routing pass is verification-only; fix inline if defects surface, KI otherwise |
| 12 | Mission spec: pixel baseline final regen | "Closes with the final local visual-snapshot baseline regeneration for the mission" | confirmed-live → L06 HAT | Pixel baselines are gitignored; last regen was F6 HAT; F6.5 added 2 visual elements (agent-editor chip + telemetry max: row) that may drift | Scope into F7 L06 HAT |
| 13 | Mission F6 KI #10 (native `<select>` popup) | Operator-skipped at F4 | NOT F7 scope | No chat-surface consumer | Carry forward — revisit when real dropdown UX need surfaces |
| 14 | Mission F6 KI: F4 L07 deferred Studio tests | Studio surface investigation | NOT F7 scope | Studio test-suite cleanup, not perf | Carry forward to dedicated Studio-cleanup flight |
| 15 | Mission F6 KI: agent rename stale PTY keys | Agent-loop concern | NOT F7 scope | Pairs with #8/#9 | Same future flight |
| 16 | F6.5 debrief carry: `OPENAI_MODEL_CONTEXT` drift watch | Hand-maintained table; no operational reminder | NOT F7 scope | Docstring-only documentation today | Carry forward to maintenance-flight checklist |
| 17 | Performance instrumentation in codebase | NONE exists today | confirmed-greenfield → L01 | `grep -r 'performance\.mark\|performance\.measure\|performance\.now\|console\.time' the_one/interfaces/web/static/` returns empty | L01 builds `App.perf` from scratch |
| 18 | Area lifecycle: deactivate cleanup | All three areas' `deactivate()` do NO cleanup | confirmed-live → L02 | `chat.js:941-943` "// Keep WS alive" but no closure-state release; `studio.js:1987` empty `function () {}`; `admin.js:756` empty `function () {}` | Primary suspect for L02 leak audit |

**Summary**: 6 items in F7 scope (AIs #1-6 → L05, mid-stream usage → L04, eager-resolve → L04, pixel regen → L06, methodology → L01, area-switch leaks → L02), 7 items carry-forward to future flights, 1 routing-verification item (L05), 1 mission-spec-required L06 HAT close. Operator confirmed at F6.5 close: F7 is the next flight; reliability + Studio cleanup are separate future flights.

**Open for operator confirmation**:
- Budget thresholds in flight spec are working defaults (≤20% heap growth across 50 area-switches; ≤50ms session-join block; ≤16ms keystroke-to-paint). Revise after L01 baselines land.
- L04 mid-stream usage emission uses approximate chunk-byte → tokens heuristic; provider-reported final usage still authoritative. Accept the approximation or push back?

---

## Flight Director Notes

### 2026-05-15 — L05 carry-forward-cleanup landed

Closed all four F6.5 debrief carry-forward Action Items in a single small leg. Status → `landed`. No architectural pivots; no source-code behaviour changes other than the explicit Anthropic resolver no-op (which is documentation-as-code).

**AI #1 — OpenRouter init hook (state-mirror tripwire defused)**:
- `LLMProvider._init_provider_state(self)` added in `the_one/llm/base.py` as the single-source-of-truth seam for per-instance provider state. `LLMProvider.__init__` calls it; subclasses that skip `super().__init__()` (OpenRouter) MUST call `self._init_provider_state()` directly.
- `OpenRouterProvider.__init__` replaces the manual `self._max_context_tokens_resolved = False` line with `self._init_provider_state()`. Future state added to the base hook is inherited automatically.

**AI #2 — Anthropic explicit no-op override**:
- `AnthropicProvider._resolve_max_context_tokens` added as a documented no-op. Docstring is a migration template pointing future maintainers at the `OPENAI_MODEL_CONTEXT` per-model table pattern (or an `openrouter_api`-style live lookup) for the day Anthropic ships a non-200k Claude model. No runtime behaviour change — L01's lazy-wrapper short-circuits regardless.

**AI #3 — live-read unit test**:
- `tests/test_process_and_broadcast_live_read.py` (NEW, ~165 LOC). Pins the F6.5 L04 HAT-cycle fix: `_process_and_broadcast` MUST read `session.agent.llm.max_context_tokens` LIVE at usage-event emission, not pre-capture at function entry. Test mutates `agent.llm.max_context_tokens` from 128k (class default) → 32k (resolved) inside the stub `step()` and asserts the broadcast usage event carries 32k.
- **Sanity-check evidence**: temporarily re-introduced the eager-capture regression (`max_context_eager = session.agent.llm.max_context_tokens` at function entry, both usage-event sites swapped to read it). Test failed with the expected diagnostic: `AssertionError: ... eager-capture at function entry would emit 128000 instead of 32000. Got: ... 'max_context_tokens': 128000`. Restored the live-read fix; test passes.

**AI #6 — `make rebuild` Chromium-wipe note**:
- Added `### make rebuild wipes Playwright Chromium` section to `the_one/agents.md` (under the Performance Measurement / Operator Notes area). Documents the symptom (hundreds of `Executable doesn't exist` errors), the cause (image rebuild wipes `/root/.cache/ms-playwright/`), and the recovery (`make _ensure-playwright`). Surfaced as a recurring operator footgun in F5/F6/F6.5/F7.

**Files changed**:
- `the_one/llm/base.py` (+17/-5): `_init_provider_state` hook + docstring
- `the_one/llm/openrouter_provider.py` (+6/-5): manual sentinel replaced with `self._init_provider_state()`
- `the_one/llm/anthropic_provider.py` (+19/-0): explicit no-op `_resolve_max_context_tokens` override + migration-template docstring
- `the_one/agents.md` (+11/-0 for the L05 section, the rest of the diff is L01's Performance Measurement section already on the branch)
- `tests/test_process_and_broadcast_live_read.py` (NEW, ~165 LOC): live-read regression test

**Test results**:
- New unit test: `tests/test_process_and_broadcast_live_read.py` passes (1 passed).
- `tests/test_llm_max_context.py`: `42 passed` — Anthropic + OpenRouter resolver paths unchanged.
- Broad pytest: `1679 passed, 4 skipped, 375 deselected` — exactly L04 baseline (1678) + 1 new live-read test. Matches expectation.
- Browser suite: `316 passed, 35 skipped` — preserved exactly at L04 baseline.

**Not committed** — per leg instructions, Flight Director batches commits after L05 (Reviewer spawned next).

### 2026-05-15 — L04 mid-stream-usage-and-eager-resolve implemented

Two-track leg landed (status → `landed`). Both Track A (mid-stream usage) and Track B (eager-resolve) acceptance criteria met.

**Track A — mid-stream usage**:
- `Agent.step` widened with optional `on_usage: Callable[[TokenUsage], Awaitable[None]] | None = None` parameter. Back-compat preserved — existing callers (tests, web layer) unchanged.
- Interim-only emission contract: `on_usage` fires when `chunk.usage is not None AND not chunk.is_final`. Final-chunk usage stays on the existing `_process_and_broadcast` final-usage broadcast path at app.py to avoid double-emission (cycle-1 [high] correction).
- `_process_and_broadcast` defines `_broadcast_usage` coro that emits `{"type":"usage", ..., "is_interim": True}` and passes it as `on_usage=` to `agent.step`. Frontend's last-write-wins on the cumulative fields handles interim vs final transparently; `is_interim` is informational.
- All four providers emit interim usage via the uniform cumulative-byte heuristic (cycle-1 correction — Anthropic's high-level `client.messages.stream()` + `text_stream` iterator doesn't expose `RawMessageDeltaEvent`; refactor to raw events deferred). Per-provider constants: `BYTES_PER_TOKEN_OPENAI=4.0`, `BYTES_PER_TOKEN_OPENROUTER=4.0` (override on subclass), `BYTES_PER_TOKEN_OLLAMA=3.5`, `BYTES_PER_TOKEN_ANTHROPIC=3.7`. Threshold = 200 cumulative bytes (≈50 OpenAI tokens; ~one update every 2.5s at 20 tok/s).
- `accumulated_bytes` is CUMULATIVE — never reset; emits when `accumulated_bytes - last_emitted_bytes >= 200`; output_tokens is cumulative `int(accumulated_bytes / BYTES_PER_TOKEN)` (cycle-1 correction over the original delta-reset pattern).

**Track B — eager-resolve**:
- New `GET /api/agents/{name}/context-window` route in `the_one/interfaces/web/api.py`. Constructs `AgentFactory(store=SQLiteAgentStore(...))` (NOT bare `AgentFactory()` — that path 404s every named agent because the `_load_config` fallback only resolves "default"; matches the live app's startup-time factory construction). Calls `await agent.llm._resolve_max_context_tokens_if_needed()` (L01 lazy resolver) and returns `{"max_context_tokens": agent.llm.max_context_tokens}`.
- Error mapping: 404 on `KeyError`/`AgentNotFoundError` (agent doesn't exist), 400 on `ProviderNotConfiguredError` and `ProviderNotFoundError`. NOTE: `ProviderNotFoundError` subclasses `KeyError` so its `except` clause MUST precede the bare-KeyError clause — otherwise dangling-provider cases 404 instead of 400.
- `chat.js` `session_joined` handler fetches the endpoint AFTER `showChrome()` (overlay element must exist before `App.chat.updateTelemetry` mutates it). Fire-and-forget on failure.

**Files changed**:
- `the_one/agent/core.py` (+30/-3): widened `step` + `_run_iterations` signatures; interim-only callback gate
- `the_one/interfaces/web/app.py` (+24/-1): `_broadcast_usage` nested coro + `on_usage=` plumbing
- `the_one/llm/openai_provider.py` (+47/-1): module constants, `_bytes_per_token_for_interim` helper, cumulative byte accumulator
- `the_one/llm/openrouter_provider.py` (+15/-0): `BYTES_PER_TOKEN_OPENROUTER` + override helper
- `the_one/llm/ollama_provider.py` (+25/-1): constants + cumulative byte accumulator
- `the_one/llm/anthropic_provider.py` (+34/-1): constants + cumulative byte accumulator in `_stream_inner`
- `the_one/interfaces/web/api.py` (+58/-0): new `GET /api/agents/{name}/context-window` route
- `the_one/interfaces/web/static/js/areas/chat.js` (+17/-0): `session_joined` eager-fetch + telemetry seed
- `tests/test_agent_step_on_usage.py` (NEW, 130 LOC): 4 tests covering on_usage callback contract
- `tests/test_api_context_window.py` (NEW, 130 LOC): 5 tests covering endpoint paths
- `tests/test_app_websocket_pause_resume.py` (+1/-0): widened StubAgent.step signature with `on_usage` kw
- `tests/test_tool_result_truncation_alignment.py` (+1/-0): widened StubAgent.step signature with `on_usage` kw

**Test results**:
- Broad pytest: `1678 passed, 4 skipped, 375 deselected` (1669 baseline + 9 new = 1678; matches expectation).
- Browser suite: `316 passed, 35 skipped, 1706 deselected` (preserved L03 baseline exactly).

**Smoke verification (curl against live container)**:
- `GET /api/agents/Generic%20Agent/context-window` → `{"max_context_tokens":262144}` HTTP 200 (OpenRouter-routed `arcee-ai/trinity-large-thinking:free`)
- `GET /api/agents/no-such-agent/context-window` → `{"detail":"Agent not found: no-such-agent"}` HTTP 404

**Cycle-1 corrections applied** (per FD prompt):
1. `on_usage` callback is interim-only — gated on `chunk.usage is not None AND not chunk.is_final`
2. `accumulated_bytes` is cumulative, tracked alongside `last_emitted_bytes`; emits at 200-byte boundaries; output_tokens is cumulative
3. Anthropic uses the byte heuristic uniformly (not `message_delta`) — refactor to raw events deferred
4. New endpoint uses `AgentFactory().create(name)` with proper `store=` wiring + `KeyError`/`ProviderNotConfiguredError`/`ProviderNotFoundError` error mapping (correct subclass ordering)

**Not committed** — per leg instructions, FD batches commits after L05.

### 2026-05-14 — Flight start

- Branch `flight/07-ui-performance-audit` created from `main` (commit `95ae1f7` post-F6.5)
- Flight status `ready` → `in-flight`
- Phase file loaded: `the-one/.flightops/agent-crews/leg-execution.md` (project-owned); Developer = Sonnet, Reviewer = Haiku
- Chrome DevTools MCP confirmed connected via `mcp__chrome-devtools__list_pages` (returned `about:blank` attached page)

### 2026-05-14 — L01 design + design review (2 cycles)

- L01 (`perf-methodology-baselines`) drafted: `App.perf` module gated by `?perf=1`/localStorage; `performance.mark` hooks at area switching, session_joined, addMsg, telemetry update; `the_one/agents.md` MCP-driven recipes for 4 scenarios; baseline capture
- **Cycle-1 review**: needs rework — 4 highs (agents.md path wrong, MCP scope mismatch FD vs Developer, defensive-guard inconsistency, rAF measure timing) + 5 mediums + 2 lows
  - Fixes applied: path corrected to `the_one/agents.md` throughout; MCP-scope split — Developer ships instrumentation + TBD-placeholder template, Flight Director runs MCP and fills baselines as small follow-up; defensive guards dropped (load-order from index.html is the guarantee); rAF measure timing clarified — measure() must be INSIDE rAF closure
  - Line-drift fixes: `addMsg` at chat.js:116 (was cited as 102); `updateTelemetry` at telemetry-overlay.js:68 (was cited as 67)
  - Scenario 1 scale reconciled to 200 transitions (50 loops × 4 per loop) — stronger leak signal than original 50
  - New `App.perf.summary()` aggregator added (returns p50/p95/max per measure name) — addresses 100-event addMsg replay inflation
  - Heap-availability Edge Case expanded with empirical-verification requirement
- **Cycle-2 review**: approve with changes — 3 residual highs (citation audit still had old line numbers, AC #10/#11 collision on "populated vs TBD", AC #4 captureHeap ownership ambiguity) + 1 medium + 1 low
  - Fixes applied: Citation Audit + Implementation Guidance step 4 corrected to current line numbers; AC #10 reworded to "template rows with TBD placeholders" (Developer scope) vs AC #11 "FD runs MCP + fills" (FD scope); AC #4 split into [Developer] code-implementation + [Flight Director] empirical-verification
  - Verification step "Baseline numbers recorded" reassigned to FD-owned with explicit `[Flight Director]` tag
- **Max-cycles check**: cycle-2 changes are mechanical wording / ownership-tagging corrections — no design pivot. Per protocol "Max 2 design review cycles" boundary respected; proceeding to implementation.
- L01 status → `ready`

### 2026-05-15 — L01 implementation landed + FD baseline capture

- Developer agent shipped `perf.js` (121 LOC), instrumented `app.js`/`chat.js`/`telemetry-overlay.js`, added `the_one/agents.md` `## Performance Measurement (F7)` section with 4 scenario templates. API connection dropped before delivering the final report but all files verified post-hoc; broad pytest 1669p/4s/374d unchanged.
- **FD baseline capture via Chrome DevTools MCP** (post-Developer-landed):
  - `App.perf` smoke: `enabled=true`, all 7 API methods present, `performance.memory` IS available (returned numeric heap values — not null). Heap-availability Edge Case resolved positive.
  - **Scenario 1 (area-switch cycles)**: 50 loops × 3 effective hashchanges = 150 area-switches. **Heap delta +30.88% (+505KB) — EXCEEDS the 20% budget**. p50/p95 `area-switch.full` both sub-millisecond (0.10ms / 0.20ms). This is the L02 confirmed-live investigation target. Filed in agents.md.
  - **Scenarios 2/3/4**: degenerate captures because operator's app state was empty (no sessions, no agents visible). Captured what was observable (heap-idle baseline ~2.24 MB) and explicitly tagged each scenario with "Operator-task during L06 HAT: re-run with seeded state." The capture procedures themselves verified working.
- L01 status → `landed` (per agentic-workflow batched-review protocol)
- **Key carry-forward into L02**: Scenario 1's +30.88% heap delta confirms a real leak signature across area-switch cycles. L02 investigates via DevTools heap-diff procedure documented in agents.md.

### 2026-05-15 — L02 design + design review cycle 1

- L02 (`memory-audit-area-switching`) drafted as investigative-only: Developer ships code-reading-based hypothesis table; FD validates via MCP heap-diff
- Cycle-1 spawn: general-purpose Developer agent (Sonnet) for design review
- Findings: GO with 3 sharpenings (no high/medium issues)
  - **Suggestion accepted**: add explicit grep-for-negative-evidence technique to Implementation Guidance (grep `removeEventListener` against `addEventListener` callsites; absence = statically-confirmed leak candidate)
  - **Suggestion accepted**: add 2 hypothesis surfaces — detached DOM nodes (classic SPA leak from closure-captured querySelector results) and perf.js mark-buffer accumulation (instrumentation can become the leak)
  - **Suggestion accepted**: tier hypotheses as `statically-confirmed` (grep-validated) vs `requires-heap-diff` (needs FD's MCP run); soften "at least 5" to "5+ with low-confidence explicitly flagged" to discourage quantity-over-quality padding
- L02 status → `ready`

### 2026-05-15 — L03 implementation landed + FD heap-diff post-fix validation

- Developer agent shipped: theme.js refactor (+22/-8, 195 lines total) replacing per-container `_themeListenerCleanup` expando with module-scoped `_activeThemeListenerCleanup`; new browser test `tests/browser/test_theme_toggle_cleanup.py` simulating the H1 scenario end-to-end
- Broad pytest 1669p/4s/375d exit 0 (+1 deselected from the new browser test). Browser suite 316p/35s (+1 vs L02-landed baseline — the new regression test). Zero existing-test regressions
- **FD post-fix MCP heap-diff** (`mcp__chrome-devtools__evaluate_script` against L01 Scenario 1, 50 loops × 3 effective transitions = 150 area-switches):
  - Pre-cycle heap: 2.18 MB
  - Post-cycle heap: 2.26 MB
  - **Heap delta: +85 KB / +3.92%** (was +30.88% / +505 KB in L01) — **87% reduction in retention growth**
  - **WELL UNDER ≤20% BUDGET** ✓
  - p50/p95 `area-switch.full` unchanged: 0.10 ms / 0.20 ms (fix was leak-side only, not latency-side)
- **H1 confirmed as the primary leak driver**. H2 was subsumed by H1 (the document listener was the retainer root for the detached DOM trees). Remaining +3.92% is normal V8/JIT warm-up + perf.js mark-buffer instrumentation artifact (H3, gated off in production). H4-H8 deferred per L03 spec — the budget is met, the rest is noise.
- agents.md updated with post-L03 baseline alongside the original pre-fix baseline (operator can audit the delta)
- L03 status → `landed`

### 2026-05-15 — L02 implementation landed + FD heap-diff validation pass

- Developer agent (Sonnet) shipped the Retainer-Hypothesis Report: 8 hypotheses, 3 statically-confirmed (H1-H3), 5 requires-heap-diff (H4-H8, with H6/H7/H8 explicitly flagged low-confidence)
- Strongest finding **H1 — Admin theme-toggle `document` listener accumulation** (statically-confirmed): `theme.js:175` attaches `document.addEventListener(THEME_EVENT, listener)` and stores cleanup on a DIV expando (`container._themeListenerCleanup`). Each `admin.activate()` re-runs `renderSystemPage(contentEl)` → `contentEl.innerHTML = ...` which destroys the prior `#admin-theme-toggle-mount` div. The cleanup-check at `theme.js:105-108` reads `_themeListenerCleanup` off the FRESH (different) container — always undefined. Result: one orphan `document` listener per chat→admin transition, accumulating without bound.
- **H2 — Detached-DOM retention** across `_refresh()` calls in admin / studio / providers-grid / system-page that do `innerHTML = ...` rewrites. Many small leaks compound.
- **H3 — perf.js mark/measure buffer growth** (instrumentation artifact only; HAT-scope, gated off in production). ~75KB of L01's measured +505KB delta could be explained by this; must be netted out of the +30.88% interpretation.
- Developer correctly noted that L01's specific scenario (zero chat sends, single session-join) leaves the chat-side closure maps (`traceShells`, `oauthPopups`, `sourceNames`, `inFlightSessions`) empty → they are NOT the +30.88% driver in L01's scenario, but remain real leak surfaces for chat-message-heavy HAT scenarios. Out of L03's primary scope.
- Cleanup-callsite ratio repo-wide: ~70 `addEventListener` callsites vs only 5 `removeEventListener` callsites. Most listener-leaks are GC'd via DOM-detachment, but H1 is the standout because the listener is on `document` (long-lived root) with cleanup on a destroyed expando.
- **FD heap-diff validation attempt**: ran 10 chat↔admin cycles via MCP `evaluate_script` + `App.perf.captureHeap()`. Result: heap delta -235KB (GC dominated this short replay). Inconclusive for confirming H1's per-cycle magnitude, but does NOT refute it — H1's predicted per-cycle effect is small (~one `document` listener closure + retained `<div>` subtree), well within GC noise floor in 10-cycle windows. The L01 +30.88% over 200 transitions is the durable signal. **Disposition**: H1, H2, H3 stay as L03 fix targets based on the static-analysis confirmation. L06 HAT re-runs the L01 scenario post-fix to confirm the +30.88% drops into the ≤20% budget.
- L02 status → `landed` (per agentic-workflow batched-review protocol)

### 2026-05-15 — L02 implementation landed (investigative report)

- Developer agent read `app.js`, `perf.js`, `chat.js`, `studio.js`, `admin.js` in full plus the chat/admin/studio sub-helper modules and `theme.js`
- Static grep pass:
  - `addEventListener` callsites across `the_one/interfaces/web/static/js/`: ~70 (across area files + sub-modules + theme/dialog/markdown)
  - `removeEventListener` callsites: 5 total (`mcps-tab.js:44`, `theme.js:177`, `dialog.js:138`, `dialog.js:139`, `mcp-server-editor.js:1726`) — narrow cleanup paths, none on the chat/area-switch hot path
- Hypothesis report appended below (8 hypotheses ranked H1–H8; 3 statically-confirmed, 5 require heap-diff). No code changes — `git diff --stat the_one/` confirms only L01-set files modified.
- L02 status → `landed` (per agentic-workflow batched-review protocol; FD heap-diff validation pass to follow before L03 design)

---

## L02 Retainer-Hypothesis Report

Investigative-only. Hypotheses ranked by likely contribution to the L01-observed +30.88% / +505KB heap growth across 150 area-switches (chat→studio→admin→chat × 50). Scenario notes that constrain interpretation:

- Scenario performs zero chat sends, zero session joins on the second+ cycle (WS stays open across deactivate; `session_joined` fires only on first entry), zero OAuth flows, zero MCP tool fetches. Chat-side closure maps (`traceShells`, `oauthPopups`, `sourceNames`, `inFlightSessions`) therefore stay empty across the cycle — they are real leak surfaces in other scenarios but not the +30.88% driver here.
- `init()` runs once per area (gated by `app.js:102 initialized[areaId]` check). So per-loop allocation comes from `activate()`/`_refresh()`/grid-render paths, NOT from re-running `init()`.
- All three areas have effectively-empty `deactivate()` (chat.js:951, studio.js:1987, admin.js:756) — no cleanup hook is fired between activations.

| Rank | Tier | Source | File:Line | Reasoning | Expected fix area | FD verification (TBD) |
|---|---|---|---|---|---|---|
| H1 | statically-confirmed | Admin theme-toggle `document` listener accumulation | `the_one/interfaces/web/static/js/theme.js:175-178` (attach) + `the_one/interfaces/web/static/js/areas/admin/system-page.js:11-50, 70-75` (caller) | Each `admin.activate()` invokes `_refresh()` → `renderSystemPage(contentEl)` which sets `contentEl.innerHTML = ...`, replacing the `#admin-theme-toggle-mount` element. `theme.renderToggle()` then attaches `document.addEventListener(THEME_EVENT, listener)` (line 175) and stores its cleanup on `container._themeListenerCleanup` (line 176). The cleanup-on-prior-mount check (lines 105-108) looks for `_themeListenerCleanup` on the FRESH `<div id="admin-theme-toggle-mount">`, which is undefined because the prior mount div was discarded by the parent `innerHTML` rewrite. Net: every chat→admin transition (50× in the scenario) registers a new `document` THEME_EVENT listener that is never removed and whose closure retains the now-detached prior container, `OPTS`, `labelledBy`, etc. Strongest candidate — clean static signature plus a hot path exercised on every loop. | Either (a) call `theme.renderToggle` with a stable mount element that survives `innerHTML` rewrites, or (b) make `renderSystemPage` idempotent (don't rewrite `innerHTML` on re-entry; only rebind transient state), or (c) clear stale listeners by tracking the listener at module scope in `theme.js` rather than on a DOM expando. Likely fix lives in `theme.js:175-178` + `system-page.js:11-50`. | TBD |
| H2 | statically-confirmed | Detached-DOM retention via repeated `_refresh()` panel rewrites | `the_one/interfaces/web/static/js/areas/admin.js:610-624` (`_refresh`) + `the_one/interfaces/web/static/js/areas/admin/providers-grid.js:32-44, 88-96` + `the_one/interfaces/web/static/js/areas/admin/system-page.js:11-50` + `the_one/interfaces/web/static/js/areas/studio.js:1915-1932` (`_refresh`) | Each admin/studio activation re-renders into the area's content panel via `container.innerHTML = '...'` (providers-grid.js:32, system-page.js:12, studio's `renderAgentList` agentListEl.innerHTML clear at line 880). The fresh DOM gets fresh listeners (mostly per-tile delegated handlers); the prior subtree becomes detached. Most should be GC-eligible, BUT any retained reference (closure, module-level cache, ARIA-live `aria-busy` polling, `data-*` expandos like `_dotTimer` from `handleSystem`, or H1's `container._themeListenerCleanup` expando held via a closure on `document`) pins the entire detached subtree. The scenario fires this rewrite ~50× per area. Classic SPA "small repeated detached-tree retention" signature — fits the "+505KB across 150 switches" magnitude better than a single large object. | Audit re-render call sites to either reuse mount roots OR null out cached pointers in `deactivate()`. The system-page rotateBtn click handler (system-page.js:80) holds `flashEl` + `setTimeout` closures over the detached container — minor but additive. Likely fix split between `admin.js:_refresh` and the individual sub-module render fns. | TBD |
| H3 | statically-confirmed | `performance` mark/measure buffer growth (perf-only HAT footgun) | `the_one/interfaces/web/static/js/perf.js:35-43` + `the_one/interfaces/web/static/js/app.js:88-93, 134-135` | When `?perf=1` is active (the L01/L02 scenario condition), every cross-area switch fires 3 entries: `area-switch:start`, `area-switch:deactivated`, `area-switch:activated` marks + 2 measures. 150 switches × ~5 entries ≈ 750 `PerformanceEntry` objects accumulating in the browser's internal mark/measure buffer between `App.perf.reset()` calls. Each entry is small (~100 bytes), so this caps around ~75KB — meaningful but probably not the dominant +505KB. CRITICAL caveat: gated by `?perf=1`, so this leak ONLY exists in HAT measurement runs, NEVER in production. It nonetheless inflates the heap-delta number L01 is measuring, so it must be subtracted from the budget interpretation. Production code path is unaffected. | Document in `agents.md` scenario procedure that `App.perf.reset()` must run between cycles (already there for scenario start, but the buffer accumulates DURING the loop). Optional: `perf.js` could auto-trim entries when `getEntriesByType('mark').length` exceeds a threshold. Not a production fix — measurement-instrumentation hygiene only. | TBD |
| H4 | requires-heap-diff | Studio `loadAll()` per-activation Promise + intermediate-array churn | `the_one/interfaces/web/static/js/areas/studio.js:781-797` (`loadAll`) + `the_one/interfaces/web/static/js/areas/studio.js:1972-1974` (`activate` → `_refresh` → `loadAll`) | Each studio.activate() fires `Promise.all([fetchAgents, fetchTools, fetchMcpSources, fetchKnowledgeBases, fetchProviders])` + chained `fetchProviderModelCaps`. Per loop iteration: 5+ fetch Promises, 5+ JSON-parsed response arrays, intermediate `results` array, `byModel` per Ollama provider, `agents/tools/mcp/kb/providers` arrays assigned to `self._*`. Old assigned arrays should be GC'd on overwrite, but per-loop transient allocation rate is high. If V8 doesn't compact young-gen quickly enough between switches OR if any cache field is array-extended rather than replaced, growth compounds. Likely contributes some warm-up retention but probably not the dominant share. Marked requires-heap-diff because static reading shows clean overwrite semantics. | If confirmed, debounce `_refresh` (skip re-fetch when same activation occurs within N ms) or move `loadAll` from `activate` to a sub-routine triggered only on data-changed signals. Likely fix in `studio.js:1972` (`activate`). | TBD |
| H5 | requires-heap-diff | Studio agent-tile `addEventListener('keydown', ...)` closure churn | `the_one/interfaces/web/static/js/areas/studio.js:879-995` (`renderAgentList`) + `studio.js:983-990` (per-tile listener) | `renderAgentList()` clears `agentListEl.innerHTML = ''` and rebuilds N tiles per refresh. Each tile gets `tileEl.onclick = function () { selectAgent(agent); }` AND `tileEl.addEventListener('keydown', ...)` capturing `agent`, `tileEl`, `selectAgent`. With agents.length = K, that's 2K listener closures per studio activation (50× = 100K closures over the scenario, each capturing per-agent state). Old listeners should die with the old detached tile DOM, but if anything (a Set of agents, the agent-list ARIA listbox, a focus tracker) pins a ref to any prior tile, the whole closure graph is retained. | If confirmed, switch to event-delegation on `agentListEl` (single keydown handler, dispatch via `e.target.closest('.entity-tile')`) — eliminates the K-listener-per-render multiplier. Lives in `studio.js:879-995`. | TBD |
| H6 | requires-heap-diff | Hash-routing handler small-object accumulation | `the_one/interfaces/web/static/js/app.js:178-182` + `the_one/interfaces/web/static/js/app.js:45-51` (`parseHash`) | Every hashchange fires `parseHash(location.hash)` which allocates a fresh `{area, sub}` object plus regex match intermediates. 150 hashchanges = 150 transient objects (plus their parsed sub-strings). All should be short-lived GC. Marked requires-heap-diff because the only retention path would be `currentId`/`currentSub` capturing — both are scalar strings, not objects. Low confidence: included for completeness in case heap-diff surfaces unexpected `(string)` retainer growth tied to hash slugs. **Low-confidence flagged** per skill protocol — likely innocuous but mentioned because Chrome heap-diff sometimes attributes ~KB of growth to interned strings with no other obvious owner. | If confirmed, intern common slugs ('chat', 'studio', 'admin') as module-level constants. `app.js:45-51`. | TBD |
| H7 | requires-heap-diff | Chat WS still-open across cycle, no per-cycle handler churn (anti-hypothesis to verify) | `the_one/interfaces/web/static/js/areas/chat.js:676-904` (`connect`) + `chat.js:951-953` (`deactivate`) | Static read: chat.deactivate() preserves WS; `connect()` only runs on initial activate OR if `readyState > 1` (CLOSING/CLOSED). In a healthy scenario WS stays OPEN across all 50 loops; ws.onopen/onmessage/onclose handlers are set ONCE. No accumulation. Hypothesis is "this is NOT a leak source in this scenario" — flagged here so FD's heap-diff explicitly tests it (i.e., look for `WebSocket` retainer count = 1, not 50). If heap-diff shows multiple `WebSocket` instances retained, then auto-reconnect at `chat.js:693` (`setTimeout(connect, 2000)`) is firing unexpectedly and old `ws` objects are being pinned by something (the `connect` closure's `ws` re-assignment should make them eligible — but `inFlightSessions` clear at line 691 inside `onclose` captures the prior closure scope). Low-confidence positive hypothesis — listed to scope the heap-diff. | None if anti-hypothesis holds. If heap-diff DOES show stacked WS, fix is to explicitly null-out the prior `ws` reference before re-`connect`. `chat.js:676-694`. | TBD |
| H8 | requires-heap-diff | Studio `_modelCapsByProvider` / `_modelCapsBy` (editor-local) / `_modelCtxBy` Object churn | `the_one/interfaces/web/static/js/areas/studio.js:755 + 792-794` (`_modelCapsByProvider` on instance) + `studio.js:1284-1287, 1355-1356, 1375-1376, 1400` (`modelCapsBy`, `modelCtxBy` local to init closure) | The instance-level `_modelCapsByProvider` is re-fetched and reassigned on every loadAll (each studio.activate). The init-closure-local `modelCapsBy` / `modelCtxBy` are reset per `fetchModelsForProvider` call (line 1355) — but `fetchModelsForProvider` fires only on provider-select change in the editor, NOT on area-switch. In THIS scenario the editor is never opened, so the closure-locals stay empty. Therefore likely NOT the leak source for the area-switch scenario — but listed because the dicts grow without bound across many provider switches (a separate HAT scenario). **Low-confidence for area-switch scenario specifically.** | Not in scope for L03's area-switch fix; flag for a different scenario (provider-switch torture). `studio.js:1284-1287`. | TBD |

**Notes for Flight Director MCP heap-diff pass**:

1. Strongest priors are H1 (theme listener on `document`) and H2 (detached-DOM retention via repeated `innerHTML` rewrites in admin's `_refresh`). These are statically confirmed (grep shows no compensating cleanup) and exercised once per loop iteration (×50). Recommend the heap-diff Comparison view filter on `Detached` nodes first, then look for retainer chains from `document` event listeners → captured container expandos.
2. H3 is a measurement-instrumentation artifact — quantify its share (`performance.getEntriesByType('mark').length`) and subtract from the budget interpretation. Not a production bug.
3. H7 is an explicit "verify this is NOT a problem" anti-hypothesis — confirm WebSocket retainer count == 1 in the heap snapshot. If it's > 1, an unexpected reconnect path is firing during the cycle.
4. H4, H5 are real but ambient — likely some contribution to the +30.88% via per-loop transient pressure, but the dominant share is most likely H1+H2 combined.



## Leg Progress

(Populated as legs land.)

---

## Decisions

Runtime decisions not in original plan.

---

## Deviations

Departures from planned approach.

---

## Anomalies

Unexpected issues encountered.

---

## Session Notes

Chronological notes from work sessions.

### 2026-05-15 — L03 memory-and-perf-fixes implemented

**Status**: landed (FD heap-diff validation pending — runs post-Developer).

**Core fix applied** to `the_one/interfaces/web/static/js/theme.js`:
- Added module-scoped `var _activeThemeListenerCleanup = null;` after the `THEME_EVENT` declaration, with a constraint docstring noting the single-active-toggle assumption (a future second concurrent toggle would require a Set of cleanups).
- Updated the `renderToggle` cleanup-contract docstring to describe the new module-scoped pattern (the closure outlives the container, so cleanup fires regardless of container identity).
- Replaced the prologue's `container._themeListenerCleanup` check (lines 105-108) with the module-scoped variable check.
- Replaced the epilogue's `container._themeListenerCleanup = function () {...}` assignment (lines 176-178) with `_activeThemeListenerCleanup = function () {...}`.

Static check: `grep "_themeListenerCleanup\|_activeThemeListenerCleanup" theme.js` returns only the 5 references to the new module-scoped variable — the per-container expando is gone entirely.

**Regression test added**: `tests/browser/test_theme_toggle_cleanup.py` (new file) — simulates the H1 scenario directly:
1. Render toggle into container1 inside a host div.
2. Rewrite host's `.innerHTML` to discard container1 (mirrors `system-page.js`'s re-render).
3. Render toggle into a fresh container2.
4. Dispatch `THEME_EVENT` with `pref: 'dark'`.
5. Assert container1's active option is unchanged (its listener was cleaned up) AND container2's active option is `dark` (its new listener fired).

Under the buggy code, container1's orphan listener would have flipped its active state — the assertion catches that regression cleanly.

**Test results**:
- Broad pytest: `1669 passed, 4 skipped, 375 deselected` (375 deselected = 374 baseline + the 1 new browser test, which is deselected without the browser marker). Passing count unchanged from L02-landed.
- Browser suite: `316 passed, 35 skipped, 1697 deselected` (315 baseline + 1 new theme regression test, 35 skipped unchanged). Zero regressions in flow/snapshot/markdown tests.

**Environment note**: the browser suite needed `playwright install chromium` + `playwright install-deps chromium` inside the container before the first run — playwright browsers were not present. This is a one-time container setup, not a code issue. Subsequent runs reuse the cached browser.

**Theme-toggle UX preservation**: the cleanup retargets from `container._themeListenerCleanup` to module-scope `_activeThemeListenerCleanup` but executes at the same point in the same flow (prologue cleanup + epilogue assign). No change to clickability, keyboard nav, ARIA wiring, or `App.theme.set` integration. The existing browser tests that exercise theme (`test_visual_snapshots.py` uses `App.theme.set` across all snapshots) all pass.

**Not committed** — per leg instructions, FD batches commits after L05.

**Outstanding (FD)**: re-run L01 Scenario 1 (50 loops × chat→studio→admin→chat) via MCP heap-diff; verify the +30.88% delta drops to ≤20%; record post-fix numbers in agents.md as "Post-L03 baseline".

### 2026-05-14 — Architect design-review cycle 1

Spawned Architect (Opus) against the F7 draft. Result: **approve with changes**. 2 high + 2 medium + 1 low + several suggestions + 4 questions.

**Cycle-1 changes incorporated**:

- **[high]** L04 mid-stream usage emission requires widening `Agent.step`'s callback contract — `on_chunk(chunk.content)` is string-only today; threading interim `usage` needs either a wider signature OR a new `on_usage` callback. **Fix applied**: added explicit Design Decision noting the new `on_usage: Callable[[TokenUsage], Awaitable[None]] | None = None` parameter on `Agent.step`, with back-compat for existing callers.
- **[high]** Eager-resolve via existing `/api/providers/{id}/models` has TWO gaps: (a) `openai-compatible` provider branch at `api.py:2454-2465` doesn't return `context_length`; (b) `session_joined` carries `agent_name`, not `provider_config_id`. **Fix applied**: L04 adds a NEW endpoint `GET /api/agents/{name}/context-window` that constructs the provider server-side, runs the resolver, and returns the resolved value.
- **[medium]** L05 bundled 6 items including investigative routing-triage. **Fix applied**: routing-triage moved into L06 HAT (operator-driven anyway). L05 becomes pure code+test+docs cleanup.
- **[medium]** L02/L03 split had a hidden divert path. **Fix applied**: explicit L02-close decision gate in Technical Approach (zero leaks → L03 dropped; fixable-within-contract → L03 executes; requires-contract-restructure → L03 KI'd).
- **[low]** False precedent claim about F2 design-language `?perf=1` gating. **Fix applied**: dropped the claim; kept the gating rationale anchored in real concerns.
- **Suggestions accepted**: `addMsg()`-specific instrumentation; session-join budget split into WS→DOM + DOM→paint sub-budgets; Anthropic uses native `message_delta` (real numbers, no heuristic); L01 perf-budget anchor invariant — read instance `max_context_tokens`, never class default; client-side rAF coalescing as a measurement-driven safeguard.
- **Question resolutions**: new endpoint (not two-hop); single session with 50 area-switches; L05 HAT routing covers chat + studio + admin sample; `BYTES_PER_TOKEN` is module-level per provider, edit-and-rebuild for tuning.

**Cycle-2 decision**: skipped per skill protocol. High-severity fixes are content additions aligning the spec with recon-discovered reality; medium fixes are leg-shape reorganization. No structural pivot. F7 leg count stays at 6.

F7 status → `planning`; will flip to `ready` after operator sign-off.

### 2026-05-14 — Flight planning

- F6.5 merged as `95ae1f7` on main; F7 planning begins
- F7 scope locked per mission spec: methodology + baselines + memory audit + targeted fixes + cross-area routing triage + final pixel regen
- Absorb F6.5 carry-forwards (AIs #1-6) + F6 KI #5 (mid-stream usage)
- 6-leg breakdown: L01 (methodology+baselines), L02 (memory audit investigative), L03 (memory+perf fixes), L04 (mid-stream usage + eager-resolve), L05 (carry-forward cleanup + routing triage), L06 (HAT + final pixel regen)
- Out of scope: stop button, qwen loops, WS-reconnect HAT, Studio test cleanup, agent rename keys, native select popup, OPENAI_MODEL_CONTEXT drift watch (all carry-forward)
- Design decisions pre-committed: instrumentation lives in `App.perf` gated by `?perf=1`/localStorage; measurement methodology is operator-runnable DevTools recipes documented in `agents.md`, NOT automated CI; per-area `deactivate()` is the canonical leak audit surface; mid-stream usage via chunk-byte heuristic; routing triage is verification-only at HAT
- Reconnaissance report compiled (see above)
