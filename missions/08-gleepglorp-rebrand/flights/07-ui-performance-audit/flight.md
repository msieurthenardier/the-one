# Flight: UI Performance Audit

**Status**: completed
**Mission**: [GleepGlorp AI Rebrand & UX Polish](../../mission.md)

## Contributing to Criteria

- [ ] Browser-side performance has been measured under realistic use (long chat sessions, many agents, repeated area switching) and meets an established memory and responsiveness budget — no unbounded growth across normal interaction, no blocking work that freezes the UI
- [ ] Per-area routing and navigation behaves correctly across every page within an area: deep links resolve, page refresh restores the visible state, browser back/forward moves through history sensibly, and there are no dead routes, broken back targets, or routes that bounce the user somewhere unexpected
- [ ] Automated browser tests pass; local visual-snapshot baselines regenerate cleanly post-palette-swap and snapshot tests fail meaningfully on subsequent regression (final mission regen lands here per mission spec)
- [ ] All existing functionality (M01–M07 capabilities) continues working — no regression

---

## Pre-Flight

### Objective

Evaluate browser-side performance against realistic usage and bring it under explicit budgets. The mission spec's three target scenarios — long-running chat sessions, large session-history lists / many agents in Studio, and repeated area switching — anchor the work. Establish a measurement methodology (DevTools heap snapshots + allocation timeline + performance traces, plus lightweight in-app `performance.mark/measure` instrumentation since the project ships zero perf hooks today), capture baselines, identify hotspots and leaks, and apply fixes for anything that violates the established budget. Absorb the small carry-forwards from F6.5 (eager-resolve max_context_tokens at session join; mid-stream `usage` event emission — F6 KI #5; OpenRouter `_init_provider_state` hook refactor; explicit Anthropic resolver override; `_process_and_broadcast` live-read unit test; `make rebuild` Chromium-wipe doc) and triage cross-area routing/navigation issues surfaced during F3-F6 polish that weren't fixed in-place. Close with operator HAT + the final mission-level pixel baseline regeneration per the mission spec.

Out of scope (carry-forward to dedicated flights or later missions):
- **Stop / cancel button + agent-loop reliability work** (F6 KI #3, #4) — feature work requiring WS cancel protocol + agent-loop tear-down semantics; warrants its own flight.
- **Studio test-file cleanup** (F4 L07 deferred tests, mission KI #4) — bigger Studio-surface UX investigation; not perf scope.
- **Native `<select>` popup customization** (mission KI #3) — deferred at F4 operator direction; revisit when a real dropdown UX need surfaces.
- **WS-reconnect mid-turn HAT scenario** (F5 AI #5, F6 HAT skip) — unexercised defensive path; reliability flight, not perf.

### Open Questions

- [x] **Performance budget thresholds** → Resolved: L01 establishes them from observed baselines (mission spec: "does not pre-commit specific numbers — those are picked from observed baselines in that flight"). Working defaults: memory growth ≤ 20% across 50 area-switch cycles; main-thread block ≤ 50ms on session join with 100-message history; chat input keystroke-to-paint ≤ 16ms (60Hz). **L01 instrumentation specifics** (cycle-1 architect suggestions): `performance.mark` around `addMsg()` specifically (NOT just keystroke handler entry) so smart-scroll/markdown-render costs are visible. Session-join budget splits into "WS-event-to-DOM-mutation" (target ≤ 30ms) and "DOM-mutation-to-paint" (≤ 20ms) so baselines are diagnostic rather than just pass/fail. **Anchor invariant** (cycle-1 architect [high — F6.5 AI #4 carry]): any perf-budget calc MUST read `session.agent.llm.max_context_tokens` (instance attribute), NEVER `LLMProvider.max_context_tokens` (class default 128_000). L01 verifies this in the instrumented code paths. Operator can revise thresholds during L01 once baselines land.
- [x] **Instrumentation home** → Resolved: a new `the_one/interfaces/web/static/js/perf.js` module exposing `App.perf.mark(name)`, `App.perf.measure(name, startMark, endMark)`, and `App.perf.captureHeap()` (logs to console for now; gated by `?perf=1` URL param OR a localStorage flag so production runs don't pay any cost). See Design Decisions.
- [x] **Measurement methodology** → Resolved: hybrid (a) DevTools heap snapshots + allocation timeline for memory; (b) DevTools performance trace for interaction blocking; (c) lightweight `performance.mark/measure` for repeatable in-app timings (area switching, session join, message render). All three documented as operator-runnable scripts in L01. See Design Decisions.
- [x] **Eager-resolve `max_context_tokens` at session join** (F6.5 carry-forward) → Resolved: yes, in scope. Cycle-1 architect surfaced TWO gaps with the original "client-side fetch via existing `/api/providers/{id}/models`" approach: (a) the `openai-compatible` provider branch at `api.py:2454-2465` doesn't return `context_length`; (b) `session_joined` carries `agent_name`, not `provider_config_id`, so a client-side fetch would require a two-hop sequence (`/api/agents/{name}` → `/api/providers/{provider_config_id}/models` → match by `entry.id == llm_model`). **Resolution**: L04 adds a NEW endpoint `GET /api/agents/{name}/context-window` that returns `{"max_context_tokens": int}` by constructing the provider, calling `await provider._resolve_max_context_tokens_if_needed()`, and returning `provider.max_context_tokens`. Single round trip; abstracts the per-provider-type resolution; works for ALL provider types including `openai-compatible` (which gets the class default unless its real `max_context_tokens` is later configured). Lands in L04.
- [x] **Mid-stream `usage` event emission** (F6 KI #5) → Resolved: in scope. Implementation path: provider's stream() emits intermediate `usage` chunks at chunk boundaries (chunk-byte count × tokens-per-byte heuristic per provider) so the chat telemetry updates DURING streaming, not just at step completion. Per-provider heuristic constants live next to the existing usage-emission code (`openai_provider.py:160-165`, etc.). See Design Decisions.
- [x] **Cross-area routing/navigation triage scope** (mission criterion) → Resolved: enumerate any issues that surfaced during F3-F6 polish flights via the flight logs / debrief Action Items; fix in scope if quick (< 30 min each); KI to a future flight if non-trivial. F3-F6 close didn't carry any specific routing items, so this is mostly a "verify the criterion still holds" pass during HAT.
- [x] **Closing HAT** → Resolved: included. Operator drives perf scenarios + final pixel baseline regen per mission spec.

### Design Decisions

**Instrumentation lives in `the_one/interfaces/web/static/js/perf.js` as `App.perf`, gated by `?perf=1` URL param OR `localStorage.setItem('the-one-perf', '1')`**

- Choice: a new ~80-100 LOC module exposing `App.perf.mark(name)`, `App.perf.measure(name, startMark, endMark)`, `App.perf.captureHeap()` (uses `performance.memory` when available — Chromium only — and `console.profile`/profileEnd hooks otherwise), and `App.perf.dump()` (writes a JSON report of all collected measurements to console).
- Rationale: the codebase has zero perf hooks today (`grep performance.mark` returns empty across `the_one/interfaces/web/static/`). `performance.mark` itself is cheap (microseconds), but the gating provides safety against `App.perf.dump()` being accidentally invoked in production via a stale `?perf=1` URL share, AND keeps `performance.memory` heap-snapshot calls (heavier) out of the hot path. localStorage fallback survives navigation across the SPA.
- Trade-off: another global on `App`; another module to load. Pays for itself in repeatable measurements.
- **Files modified**: NEW `the_one/interfaces/web/static/js/perf.js`; small wiring change in `index.html` to load before `app.js`.

**Measurement scenarios are MCP-driven via Chrome DevTools MCP (operator-installed pre-flight)**

- Choice (REVISED post-cycle-1, pre-execution): operator chose to install `chrome-devtools-mcp` (Google, released late 2025) before flight kickoff. L01 + L02 now use the MCP to drive measurement programmatically instead of manual DevTools recipes. Concretely: `App.perf.dump()` is invoked via `Runtime.evaluate` over CDP; heap snapshots via `HeapProfiler.takeHeapSnapshot`; performance traces via `Performance.getMetrics`; area-switch cycles driven by simulated clicks via MCP. The four core scenarios from the prior design (chat area-switch cycles, long-chat session, large session-history rendering, many-agents-in-studio rendering) remain — but each becomes an MCP-runnable procedure instead of a manual recipe.
- Rationale: original "manual recipes in agents.md" carve-out assumed building automation was multi-week. Chrome DevTools MCP IS that automation; install cost is minutes, not weeks. The mission criterion ("performance has been measured ... no unbounded growth") becomes more reliable with reproducible automated runs.
- Trade-off: F7 acquires a tooling dependency that future maintainers must install before running L01/L02 procedures. Document the install + the MCP-server commands actually used in `agents.md` so future flights can re-run the measurements without re-deriving the recipe.
- **Fallback if MCP misbehaves**: Playwright already drives the browser in `tests/browser/`; a `CDPSession`-based equivalent of each MCP call exists. L01 documents both paths so the operator can swap to Playwright-driven scripts mid-flight without re-planning.
- **What stays unchanged**: in-app `App.perf` instrumentation lands as planned — provides interaction-level timings that work independently of MCP/DevTools.

**Per-area `deactivate()` is the canonical leak audit surface**

- Choice: L02 audits each area's `deactivate()` for what it CLEANS UP. Current state:
  - `chat.deactivate()` at `chat.js:941-943`: "// Keep WS alive" — intentional, but does NOT release the per-init closure state (`sessionListEl`, `messagesEl`, listener refs); area re-activation calls `init()` again, creating NEW closures and DOM listeners on top of stale ones
  - `studio.deactivate()` at `studio.js:1987`: empty `function () {}`
  - `admin.deactivate()` at `admin.js:756`: empty `function () {}`
- The L02 leg investigates: do area re-activations after deactivate() accumulate listeners? Do timers stay scheduled? Do WebSocket message handlers grow? Heap snapshots over 50 area-switch cycles answer this empirically.
- Rationale: the mission criterion explicitly calls out "memory behavior across `App.areas.activate` / `deactivate` cycles." The current empty `deactivate()` impls are the primary suspect.
- Trade-off: fixes may require restructuring how each area holds its DOM/listener state. L03 absorbs the fix-side if leaks are confirmed.

**Mid-stream `usage` emission via chunk-byte heuristic + Anthropic real interim usage**

- Choice: each provider's `stream()` implementation gains a chunk-byte-count → token estimate at chunk boundaries. Emits an interim `usage` chunk so `_process_and_broadcast` broadcasts incremental usage updates DURING streaming. Per-provider constants live module-scope in each provider file: `BYTES_PER_TOKEN` (Anthropic: ~3.7, OpenAI: ~4.0, Ollama: ~3.5). **Anthropic special-case** (cycle-1 architect): Anthropic's streaming API emits `message_delta` with real `usage` periodically — use that directly instead of the heuristic for Anthropic. The heuristic only applies to OpenAI / Ollama / OpenRouter. The final `usage` chunk still replaces estimates with provider-reported truth.
- **Cross-cutting plumbing change** (cycle-1 architect [high]): the current `Agent.step(on_chunk=...)` callback at `the_one/agent/core.py:111-179` invokes `on_chunk(chunk.content)` (string only). Threading interim usage requires either widening the callback signature to accept the `StreamChunk` (or a `usage` tuple) OR adding a parallel `on_usage` callback. Choice: add a new optional `on_usage: Callable[[TokenUsage], Awaitable[None]] | None = None` parameter to `Agent.step` and propagate `chunk.usage` to it when present. Back-compat: `on_usage` is optional; existing single-callback callers stay valid. The only production caller is `_process_and_broadcast` at `app.py:775-799`; tests use `Agent` directly with their own callbacks — verify at L04 implementation.
- **Client-side rAF coalescing** (cycle-1 architect suggestion): at ~20 chunks/sec the telemetry overlay update is well under animation budget, but rAF-coalescing in `chat.js`'s `usage`-event handler is a cheap safety against burst-fast streams. Apply if measurement reveals overlay re-renders dominating frames.
- Rationale: F6.5 architect carry-forward; the lazy-at-first-need pattern is a template but per-stream estimation is just a running counter reset per `stream()` call. Operator-visible effect: telemetry `ctx:` value updates progressively during a long response instead of jumping at the end.
- Trade-off: per-chunk estimate is APPROXIMATE (OpenAI/Ollama/OpenRouter). Anthropic has real numbers. The final `usage` emission still uses provider-reported truth for correctness — this is a smoothness improvement, not a correctness fix.
- **Out of scope**: tokenizer-aware estimation (would require shipping each provider's tokenizer in the browser — too heavy). The byte-count heuristic is good enough for a context-fill percent.

**Routing/navigation triage is verification-only at L06 HAT (NOT a separate L05 task)**

- Choice (cycle-1 architect [medium]): the routing-triage moves out of L05 entirely and into L06 HAT. Routing scenarios are operator-driven (deep-link, hard-refresh, back-forward), so the natural home is HAT — alongside the perf-scenario walk. L05 becomes the "pure code+test+docs cleanup" leg (carry-forwards only, no investigative scope). Scope of the HAT routing pass: chat + studio (the surfaces F4/F6 polish flights touched). Admin is verification-only at a sample-page level.
- F3-F6 flight-debrief Action Items + the F6 mission KIs include zero specific routing defects (the F6 routing scenarios passed; F4 / F3 don't carry forward open routing items).
- Rationale: do not do speculative routing rewrites. Polish flights handled their own areas; F7 confirms the cross-area criterion still holds via HAT walk.
- Trade-off: if a serious routing defect IS surfaced at HAT, it could expand scope. Adaptation Criteria below covers this.

**Pixel baseline regeneration: ONCE at the end (final mission regen)**

- Choice: pixel baselines regenerated at L06 HAT close. This is the final pixel regen for the mission per mission spec.
- Rationale: F6.5 added two visual elements (agent-editor "Max context" chip + telemetry overlay `max:` row) that may have rendered differently in pixel baselines. Regen at L06 captures the final state.
- Trade-off: pixel suite may show drift on first run before L06 regen — acceptable, the suite is gitignored and operator-only-run.

### Prerequisites

- [ ] F6.5 merged to main (✓ — commit `95ae1f7` on origin/main)
- [ ] Broad pytest reliably exits with code 0 (✓ — verified at F6.5 close: 1669 passed, 4 skipped, 374 deselected)
- [ ] Browser suite baseline 315p/35s (✓ — verified at F6.5 close)
- [ ] Pixel suite baseline 12/12 (✓ — verified at F6.5 close)
- [ ] Container `the-one` running and reachable via `docker exec`
- [ ] `make rebuild` available on host (and `make _ensure-playwright` for browser-suite restoration)
- [ ] Chrome / Chromium browser with DevTools accessible (operator-side)
- [ ] **Chrome DevTools MCP installed and connected to Claude Code** (operator pre-flight task — install via `claude mcp add chrome-devtools npx chrome-devtools-mcp@latest` or equivalent; verify connection with `/mcp` in Claude Code). Required for L01 baseline capture and L02 area-switch automation. Fallback (Playwright `CDPSession`) documented but adds friction.

### Pre-Flight Checklist

- [ ] All open questions resolved
- [ ] Design decisions documented
- [ ] Prerequisites verified
- [ ] Validation approach defined (per-leg automated tests where applicable; in-app `App.perf` measurements for interaction timings; DevTools recipes for memory + heap; operator HAT for cross-area routing + final pixel regen)
- [ ] Legs defined

---

## In-Flight

### Technical Approach

**Phase 1 — Instrumentation + baselines (L01).** Create `App.perf` module gated by `?perf=1` / localStorage. Add `performance.mark` calls at the critical interaction points: area `activate`/`deactivate` boundaries, session-join flow (between `session_joined` event arrival and DOM-render-complete), chat-input keystroke handler, telemetry-overlay updates. Document the four measurement scenarios in `agents.md` with DevTools recipes. Capture baseline numbers for each scenario against current main (pre-fix). Document the working budget thresholds (operator can revise).

**Phase 2 — Memory audit + fixes (L02 + L03).** L02 runs the area-switch heap-snapshot scenario as a **single session with 50 area-switch cycles** (cycle-1 architect — tests the area-lifecycle contract, not the session lifecycle). Captures retained-size deltas; identifies any growing retainer roots. **Explicit L02-close decision gate** (cycle-1 architect [medium]): if zero leaks (budget already holds) → L03 is DROPPED, flight log records "skipped — budget already met", proceed to L04. If leaks exceed budget BUT fixable within an area's existing lifecycle contract → L03 executes. If leaks require restructuring an area's init/teardown contract (e.g., reshape `chat.js`'s closure model) → L03 is KI'd to a dedicated refactor flight, F7 ships with budget violated + documented, proceed to L04. L03 (when it executes) applies fixes for budget-violating retention — likely candidates: per-init closure state in chat.js not released, WS message-handler accumulation, timer leakage in studio (mcp-server-editor + agent-editor), event-listener leaks in admin's provider-grid. Re-runs L02's scenario post-fix to confirm flat retention.

**Phase 3 — Mid-stream usage + eager-resolve carry-forwards (L04).** F6 KI #5 mid-stream `usage` emission lands here (per-provider chunk-byte → token estimate for OpenAI/Ollama/OpenRouter; Anthropic uses its native `message_delta` interim usage; requires widening `Agent.step` with an `on_usage` callback). F6.5 eager-resolve-at-session-join lands here too: NEW endpoint `GET /api/agents/{name}/context-window` returns the resolved value via a server-side `_resolve_max_context_tokens_if_needed()` call; chat.js `session_joined` handler fetches it and seeds the telemetry overlay's `max:`. Both together close the "pre-first-turn telemetry shows zeros" observation from F6.5 HAT.

**Phase 4 — Cleanup carry-forwards (L05) — PURE cleanup, no investigation.** Small F6.5 debrief items: OpenRouter `_init_provider_state` hook refactor; explicit Anthropic `_resolve_max_context_tokens` no-op override + migration docstring; unit test for `_process_and_broadcast` live-read of `max_context_tokens`; `agents.md` note about `make rebuild` Chromium wipe; `agents.md` perf-budget table writeback. Routing triage moved to L06 HAT per cycle-1 architect.

**Phase 5 — HAT (L06).** Operator walks the perf scenarios in the live browser; confirms budget compliance; verifies cross-area routing still holds; regenerates pixel baselines (final mission regen); runs broad + browser + pixel regression smoke.

### Checkpoints

- [ ] L01: `App.perf` module landed, gated; `performance.mark`/`measure` calls at critical interaction points; agents.md measurement recipes documented; baseline numbers captured for all 4 scenarios; working budget thresholds documented (revisable at HAT)
- [ ] L02: heap-snapshot run across 50 area-switch cycles produces a retainer-delta report; specific leak roots identified (or "none found" if budget already holds) with code-location citations
- [ ] L03: fixes applied for any retention-budget violations from L02; re-run shows flat retention; no regression in broad/browser
- [ ] L04: mid-stream usage emits during streaming (telemetry `ctx:` updates progressively); session-joined now eager-fetches `max_context_tokens` (`max:` populates before first message instead of showing 0)
- [ ] L05: OpenRouter `_init_provider_state` hook lands; Anthropic explicit override + docstring lands; `_process_and_broadcast` live-read unit test lands; `agents.md` make-rebuild note lands; routing triage report in flight log (defects fixed inline or KI'd)
- [ ] L06: HAT — operator confirms perf budgets met across all 4 scenarios in both themes; routing scenarios pass; pixel baselines regenerated 12/12 clean; broad 1669+ / browser 315/35 preserved

### Adaptation Criteria

**Divert if**:
- L02 surfaces a leak whose fix requires restructuring an area's init/teardown contract — that's bigger than F7 polish scope; KI to a dedicated refactor flight and ship F7 with the budget violated + documented.
- L04 mid-stream usage emission turns out to be more invasive than a chunk-byte heuristic (e.g., a provider's stream() lacks chunk-byte introspection) — narrow scope to providers that DO support it (likely all 4 — they're all HTTP-streamed with byte-counted chunks).
- L05 routing triage surfaces a non-trivial cross-area defect — KI it; do not balloon F7.
- HAT operator finds the working budget thresholds are wrong for their hardware (slower laptop than the baseline machine) — revise thresholds, document the revision in the flight log, don't pretend the original threshold was always the goal.

**Acceptable variations**:
- L01's baseline numbers are observational, not predictive; operator may revise budget after seeing real measurements
- L02's heap-snapshot scenario count (50 area-switch cycles is the suggested default) can be adjusted up or down based on what reveals the leak signature
- L04's per-provider `BYTES_PER_TOKEN` constants are estimates; operator may tune at HAT
- L05's routing triage is verification-only by default; expands only if defects surface

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `perf-methodology-baselines` — `App.perf` module + instrumentation hooks at critical interaction points; agents.md measurement recipes; baseline numbers captured for all 4 mission scenarios; working budget thresholds documented
- [x] `memory-audit-area-switching` — heap-snapshot run across 50 area-switch cycles; retainer-delta report; specific leak roots identified with file:line citations (investigative leg — no fixes yet)
- [x] `memory-and-perf-fixes` — apply fixes for budget-violating retention identified in L02; re-run heap-snapshot scenario to confirm flat retention
- [x] `mid-stream-usage-and-eager-resolve` — F6 KI #5 mid-stream `usage` emission per-provider chunk-byte heuristic; F6.5 eager-resolve `max_context_tokens` at session join via client-side fetch
- [x] `carry-forward-cleanup` — OpenRouter `_init_provider_state` hook refactor; explicit Anthropic resolver override; `_process_and_broadcast` live-read unit test; agents.md make-rebuild note + perf-budget table writeback. Pure cleanup; routing-triage moved to L06 HAT.
- [x] `ui-perf-audit-hat` — operator delegated HAT to FD given full MCP + test-suite access. FD-executed via MCP + test suites. Heap-retention budget -14.62% (well under +20%); routing scenarios pass; broad 1679p/4s/375d; browser 316p/35s; pixel regenerated 12/12 clean

---

## Post-Flight

### Completion Checklist

- [ ] All legs completed
- [ ] Code merged to main
- [ ] Broad pytest exits 0; pass count grows by new unit-test additions (target: 1669 baseline + ≥1 from `_process_and_broadcast` live-read test); no NEW failures or skips
- [ ] Browser suite ≥ 315 passing / ≤ 37 skipped (F6.5 baseline ± 2 new-skip cap)
- [ ] Pixel suite 12/12 on clean rerun after baseline regen (final mission regen)
- [ ] Budget thresholds documented + met (or revisions documented with rationale)
- [ ] Mission KI #5 (mid-stream usage) marked RESOLVED
- [ ] F6.5 debrief action items #1, #2, #3 (OpenRouter init hook, Anthropic override, `_process_and_broadcast` test) marked RESOLVED
- [ ] `agents.md` updated with: measurement recipes (L01), `make rebuild` Chromium wipe note (L05), F7's perf budgets table

### Verification

How to confirm the flight achieved its objective:

1. **`App.perf` is reachable + gated**: `localStorage.setItem('the-one-perf','1'); location.reload(); App.perf.mark('test'); App.perf.measure('test', 'test', 'test')` works in console; un-gated state `App.perf === undefined` or no-op stubs.
2. **Budget compliance**: each of the 4 measurement scenarios from `agents.md` shows current numbers within the documented thresholds (or revisions documented).
3. **Memory baseline**: 50 area-switch cycles show flat retention (within ±20% of starting heap size) — operator captures via DevTools Memory tab.
4. **Mid-stream telemetry**: send a long-streaming response (e.g., "write a 500-word essay"); `ctx:` value updates progressively during streaming, NOT only at the end.
5. **Pre-first-turn telemetry**: open a fresh chat session; before sending any message, telemetry `max:` shows the model's resolved context window (NOT 0).
6. **Routing criterion holds**: HAT walks every chat / studio / admin page through deep-link + hard-refresh + back/forward; all behave sensibly.
7. **Pixel suite 12/12 clean** after L06 regen on a subsequent run.
8. **No regression** in M01–M07 functionality: broad pytest exit 0; browser suite preserved.

---

## Known Issues (carried forward)

Items NOT addressed in F7 (carry-forward to future flights):

- **F6 KI #3** No stop / cancel button — feature work, dedicated reliability/agent-loop flight
- **F6 KI #4** Long-convo loops on qwen — pairs with #3, same dedicated flight
- **F6 KI #8** WS-reconnect mid-turn defensive path unexercised — reliability flight
- **Mission KI** Native `<select>` popup customization — deferred at operator direction (F4)
- **Mission KI** F4 L07 deferred Studio test files — Studio cleanup flight
- **Mission KI** Agent rename stale in-memory PTY tool-session keys — opportunistic fix in agent-loop flight
- **F6.5 debrief carry**: `OPENAI_MODEL_CONTEXT` drift watch — documented in docstring only, no operational reminder. Promote to a maintenance-flight checklist item.
