# Leg: perf-methodology-baselines

**Status**: completed
**Flight**: [UI Performance Audit](../flight.md)

## Objective

Establish the performance-measurement substrate for F7: ship a new `App.perf` module gated by `?perf=1` URL param OR `localStorage.setItem('the-one-perf','1')`, add `performance.mark`/`performance.measure` calls at the critical interaction points the flight spec calls out (area `activate`/`deactivate`, session-join WS-event-to-DOM and DOM-to-paint sub-budgets, chat-input keystroke → `addMsg()` → render, telemetry-overlay update), and document the four core MCP-driven measurement recipes in `the_one/agents.md`. Capture baseline numbers for each scenario as the pre-fix reference; document the working budget thresholds and the verifiable-by-MCP procedures so L02 onward consume the same measurement surface the operator HAT will at L06.

## Context

- **Flight design decision**: `App.perf` lives in a NEW module `the_one/interfaces/web/static/js/perf.js`, gated by `?perf=1` URL param OR `localStorage` key — production runs pay zero measurement cost. Performance.mark itself is microseconds; the gate protects against accidental `App.perf.dump()` invocation via stale URL share AND against `performance.memory` heap-snapshot costs in the hot path.
- **Flight design decision (cycle-1 architect)**: measurement scenarios become Chrome DevTools MCP-runnable, NOT manual recipes. The mission's "multi-week automation build-out" carve-out was based on hand-rolled tooling assumptions; with the MCP installed, automation cost is minutes. L01 documents the MCP-server-tool calls used for each scenario in `the_one/agents.md` so future flights can re-run the measurements.
- **Flight design decision**: budget split into "WS-event-to-DOM-mutation" (≤30ms) and "DOM-mutation-to-paint" (≤20ms) on session-join. `addMsg()` specifically gets its own `performance.mark` so smart-scroll/markdown-render costs are visible. Anchor invariant: any perf-budget calc MUST read `session.agent.llm.max_context_tokens` (instance), NEVER `LLMProvider.max_context_tokens` (class default 128_000) — F6.5 AI #4 carry.
- **Recon (flight-log.md row #17)**: zero performance instrumentation in `the_one/interfaces/web/static/` today. L01 is greenfield for the instrumentation surface.
- **MCP availability**: Chrome DevTools MCP is installed and connected (operator pre-flight task complete). Tools available include `performance_start_trace` / `performance_stop_trace` / `performance_analyze_insight` / `take_memory_snapshot` / `evaluate_script` / `click` / `navigate_page` / `lighthouse_audit` / `list_console_messages`. L01's recipes use these as the canonical measurement procedure.
- **Area lifecycle invariant** (verified during L01 planning): `app.js:99` only calls `init()` once per area (`if (!initialized[areaId])`). Subsequent cross-area switches toggle `.active` classes via `app.js:113-116` and call `deactivate()` on the outgoing area. So the leak surface is (a) listeners attached during the once-per-area init that persist forever, (b) WS message-handler accumulation per session join, (c) timers/intervals, (d) DOM-node accumulation within a single area's session. L01 instrumentation surfaces all four.

## Inputs

Files that exist before this leg runs:
- `the_one/interfaces/web/static/index.html` — script load order; `App.perf` script tag needs to be inserted BEFORE `app.js` (so areas can use `App.perf.mark()` from their own init)
- `the_one/interfaces/web/static/js/app.js` — area registration + cross-area-switch logic (`performCrossAreaSwitch` at line 87); the `init()`/`deactivate()` callbacks that need wrapping with `App.perf.mark`
- `the_one/interfaces/web/static/js/areas/chat.js` — `session_joined` handler at line 727 (the WS→DOM site); `addMsg()` at line 116 (cycle-1 corrected line number; message-render site); `_broadcast_chunk`/streaming render paths
- `the_one/interfaces/web/static/js/areas/chat/telemetry-overlay.js` — `updateTelemetry` at line 68 (cycle-1 corrected; high-frequency call site during streaming)
- `the_one/agents.md` — operator-facing test/measurement docs root; the MCP recipes append here
- L06 (telemetry-overlay) and L01 (lazy resolver) from F6.5 are merged on main; provider instance attributes already populated by first `complete()`/`stream()` call

State that must be true:
- F6.5 merged to main (✓ commit `95ae1f7`)
- Broad pytest 1669p/4s/374d; browser suite 315p/35s; pixel suite 12/12 (✓ at F6.5 close)
- Chrome DevTools MCP installed + connected; `mcp__chrome-devtools__list_pages` returns the attached page
- Container `the-one` running; `make rebuild` available on host

## Outputs

Files created:
- `the_one/interfaces/web/static/js/perf.js` — NEW ~120-160 LOC module exposing:
  - `App.perf.enabled` — boolean, true when `?perf=1` is in URL OR `localStorage.getItem('the-one-perf') === '1'`. Captured at module-load; reload required to flip.
  - `App.perf.mark(name)` — when enabled, calls `performance.mark(name)`; when disabled, no-op
  - `App.perf.measure(name, startMark, endMark)` — when enabled, calls `performance.measure(name, startMark, endMark)`; when disabled, no-op
  - `App.perf.captureHeap()` — when enabled and `performance.memory` available (Chromium same-origin-isolated), returns `{usedJSHeapSize, totalJSHeapSize, jsHeapSizeLimit, timestamp}`; otherwise returns `null`
  - `App.perf.dump()` — returns `{enabled, marks: PerformanceEntry[], measures: PerformanceEntry[], heap: object|null}` — raw entry list
  - `App.perf.summary()` — returns `{enabled, measures: {[name]: {count, p50, p95, max}}, heap}` — aggregated per measure name. Cycle-1 reviewer addition: avoids dump-payload bloat when 100+ `addMsg` entries pile up during session-join replay.
  - `App.perf.reset()` — clears all collected marks/measures (per-scenario reset)

Files modified:
- `the_one/interfaces/web/static/index.html` — insert `<script src="/static/js/perf.js"></script>` BEFORE `app.js`, AFTER `theme.js` (perf has no DOM deps)
- `the_one/interfaces/web/static/js/app.js` — wrap `performCrossAreaSwitch` body with marks: `App.perf.mark('area-switch:start')` before `deactivate()`, `App.perf.mark('area-switch:deactivated')` after, `App.perf.mark('area-switch:activated')` after `init()` / panel show, plus `App.perf.measure('area-switch.deactivate', 'area-switch:start', 'area-switch:deactivated')` and `App.perf.measure('area-switch.full', 'area-switch:start', 'area-switch:activated')`
- `the_one/interfaces/web/static/js/areas/chat.js` — wrap `session_joined` handler at line 727 with `App.perf.mark('session-join:received')` at the top and `App.perf.mark('session-join:dom-mutated')` AFTER `showChrome()` + scroll fix; the `ws-to-dom` measure fires immediately. Then `requestAnimationFrame(() => { App.perf.mark('session-join:painted'); App.perf.measure('session-join.dom-to-paint', 'session-join:dom-mutated', 'session-join:painted'); })` — the `dom-to-paint` measure MUST be INSIDE the rAF closure since the `painted` mark only exists after rAF fires. Wrap `addMsg()` body with `App.perf.mark('addMsg:start')` / `App.perf.mark('addMsg:end')` and `App.perf.measure('addMsg', ...)`.
- `the_one/interfaces/web/static/js/areas/chat/telemetry-overlay.js` — wrap `updateTelemetry` body with `App.perf.mark` boundaries (high-frequency; useful for measuring overlay-update cost during streaming)
- `the_one/agents.md` — append a new section `## Performance Measurement (F7)` documenting the four MCP-runnable scenarios with exact tool calls + expected baseline targets:
  - Scenario 1: Area-switch cycles (50 cross-area transitions)
  - Scenario 2: Long-chat session (100-message conversation rendering + scroll)
  - Scenario 3: Large session-history list (sidebar with 50+ sessions)
  - Scenario 4: Many-agents-in-studio rendering

State after:
- `App.perf` is loaded but inactive in production paths (gated)
- Adding `?perf=1` to any URL OR setting localStorage flag activates the marks; `App.perf.dump()` returns a JSON measurement blob via `mcp__chrome-devtools__evaluate_script(...)` + `list_console_messages`
- Each of the 4 scenarios in `the_one/agents.md` has a copy-pastable MCP-runnable procedure; baselines captured live by running the procedure once against current `main` (post-F6.5)
- Working budget thresholds documented; L02 onward consume them as the failure threshold

## Acceptance Criteria

- [ ] `the_one/interfaces/web/static/js/perf.js` exists; exposes `App.perf.{enabled, mark, measure, captureHeap, dump, summary, reset}` (cycle-1 reviewer added `summary` aggregator); gating via `?perf=1` URL OR `localStorage.getItem('the-one-perf') === '1'`, captured at module-load (reload-required to flip)
- [ ] Disabled-path call sites are no-ops — calling `App.perf.mark('test')` in a fresh tab WITHOUT the gate does NOT create a `performance.getEntriesByName('test', 'mark')` entry (cycle-1 reviewer rewording — every function returns undefined; the observable contract is "no native performance.mark call")
- [ ] Enabled-path `App.perf.mark('test')` calls native `performance.mark('test')` AND `App.perf.dump()` returns a serializable blob containing the recorded mark; verifiable via MCP `evaluate_script({ function: () => { App.perf.mark('test'); return App.perf.dump(); } })`
- [ ] **[Developer]** `App.perf.captureHeap()` is implemented to return `{usedJSHeapSize, totalJSHeapSize, jsHeapSizeLimit, timestamp}` (numbers) when `performance.memory` is available, `null` otherwise. **[Flight Director]** verifies empirically against the running app — runs `captureHeap()` once via MCP and records `null vs numbers` finding alongside the baseline TBDs in `the_one/agents.md`. Developer-side verification limited to code inspection (no Chrome to run against).
- [ ] `index.html` loads `perf.js` BEFORE `app.js` (so areas can use `App.perf` from their own init); script tag inserted AFTER `theme.js` (no DOM dep ordering concern)
- [ ] `app.js`'s `performCrossAreaSwitch` is instrumented with marks `area-switch:{start,deactivated,activated}` and measures `area-switch.deactivate` + `area-switch.full`
- [ ] `chat.js`'s `session_joined` handler is instrumented with marks `session-join:{received,dom-mutated,painted}` and measures `session-join.ws-to-dom` + `session-join.dom-to-paint`; `painted` mark fires inside a `requestAnimationFrame` callback so it reflects the post-paint frame
- [ ] `chat.js`'s `addMsg()` is instrumented with marks `addMsg:{start,end}` and measure `addMsg`
- [ ] `telemetry-overlay.js`'s `updateTelemetry` is instrumented with marks `telemetry-update:{start,end}` and measure `telemetry-update`
- [ ] **[Developer]** `the_one/agents.md` has a new section `## Performance Measurement (F7)` documenting all 4 scenarios with: (a) MCP tool-call sequence (the exact `mcp__chrome-devtools__*` calls), (b) **template rows** for expected baseline / acceptable variance / failure-mode notes — all rows filled with `TBD` placeholders. (c) what to do on a failure (file location + fix candidate area). The Developer ships the template + scaffolding text; baseline values themselves are AC #11 / Flight-Director scope.
- [ ] `the_one/agents.md` has a `## Performance Measurement (F7)` section with all 4 scenarios using `TBD` placeholders in each "Expected baseline" row. **Baseline-numbers capture is Flight-Director-owned** (cycle-1 reviewer [high]) — the Developer agent SHIPS the instrumentation + template; the Flight Director then runs the MCP scenarios end-to-end and fills the TBD values via a small follow-up Edit before signaling [HANDOFF:review-needed]. This split is necessary because the spawned Developer agent does NOT have access to `mcp__chrome-devtools__*` tools (only the Flight Director's session has them).
- [ ] Anchor invariant verified (cycle-1 reframed): perf instrumentation introduces NO new reads of `LLMProvider.max_context_tokens` (class default). Confirm via `grep -rn "LLMProvider\.max_context_tokens\|max_context_tokens: int = 128_000" the_one/interfaces/web/static/` returns empty. Pure-JS perf code shouldn't touch Python class attributes; this is a negative-check guardrail against future drift.
- [ ] Broad pytest exits 0; pass count unchanged from F6.5 baseline 1669 (no new Python tests); JavaScript changes do not affect Python test counts
- [ ] Browser suite preserved at 315 passing / 35 skipped — the new `perf.js` script must not cause any existing browser test to time out or fail
- [ ] Pixel suite preserved at 12/12 — the perf module has zero visual rendering; pixel baselines should be unchanged

## Verification Steps

- **Gating works**: open chat in browser without `?perf=1` and without localStorage flag; in DevTools console run `App.perf.enabled` → should be `false`; `App.perf.mark('x')` returns undefined; `App.perf.dump()` returns empty object or `{enabled: false}`. Then set `localStorage.setItem('the-one-perf','1')`, reload, run same → `App.perf.enabled` is `true`, mark+dump return populated state.
- **Enabled-path round trip via MCP**:
  ```
  mcp__chrome-devtools__navigate_page(url='http://localhost:8484/?perf=1#chat')
  mcp__chrome-devtools__evaluate_script(function='() => { App.perf.mark("test1"); App.perf.measure("m1", "test1", "test1"); return App.perf.dump(); }')
  ```
  Returns a JSON blob with `marks: [...test1...]`, `measures: [...m1...]`.
- **Area-switch instrumentation fires**: with perf gated on, click chat→studio→admin→chat in the topbar; `App.perf.dump()` returns measures for `area-switch.deactivate` (≥3) and `area-switch.full` (≥3) — one per transition.
- **Session-join instrumentation fires**: in a fresh chat session, send first message → `session-join:received` mark visible; `session-join.dom-to-paint` measure ≥ 0ms.
- **addMsg instrumentation fires**: after sending any chat message, `addMsg` measure appears.
- **MCP recipes documented**: `the_one/agents.md` has 4 distinct sub-sections with copy-pastable MCP tool calls; running them produces measurements.
- **[Flight Director]** Baseline numbers recorded: each scenario sub-section in `the_one/agents.md` has an "Expected baseline (F7 L01)" row populated with actual numbers from the FD's MCP-driven capture pass. NOT a Developer-deliverable; the Developer agent's landed-state check passes with TBD placeholders in place.
- **Broad pytest**: `docker exec the-one pytest -x --timeout 30` exits 0 with 1669p/4s/374d unchanged.
- **Browser suite**: `docker exec the-one pytest -m browser --timeout 60 --tb=line` returns 315/35 unchanged.

## Implementation Guidance

1. **Create `the_one/interfaces/web/static/js/perf.js`**:

   ```javascript
   // App.perf — F7 performance measurement substrate.
   //
   // Gated by ?perf=1 in URL query string OR localStorage.getItem('the-one-perf') === '1'.
   // Production paths pay zero cost (no-op when disabled).
   //
   // Public surface:
   //   App.perf.enabled    -> boolean
   //   App.perf.mark(name) -> void
   //   App.perf.measure(name, startMark, endMark) -> void
   //   App.perf.captureHeap() -> { usedJSHeapSize, totalJSHeapSize, jsHeapSizeLimit, timestamp } | null
   //   App.perf.dump() -> { enabled, marks: PerformanceEntry[], measures: PerformanceEntry[], heap: object|null }
   //   App.perf.reset() -> void
   //
   // The dump() output is the canonical operator-readable export; capture via
   // Chrome DevTools MCP's evaluate_script + list_console_messages.
   (function () {
     'use strict';
     window.App = window.App || {};

     function isEnabled() {
       try {
         var u = new URL(window.location.href);
         if (u.searchParams.get('perf') === '1') return true;
       } catch (e) { /* IE / legacy — fall through */ }
       try {
         return window.localStorage.getItem('the-one-perf') === '1';
       } catch (e) {
         return false;
       }
     }

     var enabled = isEnabled();

     function mark(name) {
       if (!enabled || typeof performance === 'undefined' || !performance.mark) return;
       try { performance.mark(name); } catch (e) { /* swallow — same mark twice is fine */ }
     }

     function measure(name, startMark, endMark) {
       if (!enabled || typeof performance === 'undefined' || !performance.measure) return;
       try { performance.measure(name, startMark, endMark); } catch (e) { /* swallow */ }
     }

     function captureHeap() {
       if (!enabled) return null;
       var m = (typeof performance !== 'undefined') && performance.memory;
       if (!m) return null;
       return {
         usedJSHeapSize: m.usedJSHeapSize,
         totalJSHeapSize: m.totalJSHeapSize,
         jsHeapSizeLimit: m.jsHeapSizeLimit,
         timestamp: Date.now()
       };
     }

     function entriesAsArray(type) {
       if (typeof performance === 'undefined' || !performance.getEntriesByType) return [];
       return performance.getEntriesByType(type).map(function (e) {
         return { name: e.name, startTime: e.startTime, duration: e.duration };
       });
     }

     function dump() {
       return {
         enabled: enabled,
         marks: enabled ? entriesAsArray('mark') : [],
         measures: enabled ? entriesAsArray('measure') : [],
         heap: captureHeap()
       };
     }

     function reset() {
       if (!enabled || typeof performance === 'undefined') return;
       try {
         performance.clearMarks();
         performance.clearMeasures();
       } catch (e) { /* swallow */ }
     }

     // Cycle-1 reviewer addition: aggregator avoids dump-payload bloat when
     // many entries share a name (e.g. 100 addMsg measures from session-join
     // replay). Returns count + percentile durations per measure name.
     function percentile(sorted, p) {
       if (sorted.length === 0) return 0;
       var idx = Math.min(sorted.length - 1, Math.floor(sorted.length * p));
       return sorted[idx];
     }

     function summary() {
       if (!enabled) return { enabled: false, measures: {}, heap: null };
       var byName = {};
       var measures = entriesAsArray('measure');
       for (var i = 0; i < measures.length; i++) {
         var m = measures[i];
         (byName[m.name] = byName[m.name] || []).push(m.duration);
       }
       var out = {};
       for (var name in byName) {
         if (!Object.prototype.hasOwnProperty.call(byName, name)) continue;
         var arr = byName[name].slice().sort(function (a, b) { return a - b; });
         out[name] = {
           count: arr.length,
           p50: percentile(arr, 0.5),
           p95: percentile(arr, 0.95),
           max: arr[arr.length - 1]
         };
       }
       return { enabled: true, measures: out, heap: captureHeap() };
     }

     window.App.perf = {
       enabled: enabled,
       mark: mark,
       measure: measure,
       captureHeap: captureHeap,
       dump: dump,
       summary: summary,
       reset: reset
     };
   })();
   ```

2. **Edit `the_one/interfaces/web/static/index.html`** — insert `perf.js` BEFORE `app.js`:

   ```html
   <script src="/static/js/theme.js"></script>
   <!-- ... CSS links ... -->
   </head>
   <body>
   <!-- ... DOM scaffolding ... -->
   <script src="/static/js/perf.js"></script>  <!-- NEW: loads before app.js -->
   <script src="/static/js/app.js"></script>
   ```

   Actually insert it as the first `<script>` in the `<body>` section (line ~30, before `app.js`).

3. **Edit `the_one/interfaces/web/static/js/app.js`** — instrument `performCrossAreaSwitch` at line 87:

   ```javascript
   function performCrossAreaSwitch() {
     App.perf.mark('area-switch:start');
     if (currentId && areas[currentId]) {
       areas[currentId].deactivate();
     }
     App.perf.mark('area-switch:deactivated');
     App.perf.measure('area-switch.deactivate', 'area-switch:start', 'area-switch:deactivated');

     // ... existing panel-show + init logic ...

     App.perf.mark('area-switch:activated');
     App.perf.measure('area-switch.full', 'area-switch:start', 'area-switch:activated');
   }
   ```

   Place the final marks AFTER the panel-show + aria-label updates so the measure captures the full transition.

4. **Edit `the_one/interfaces/web/static/js/areas/chat.js`** — instrument `session_joined` handler at line 727 + `addMsg()` at line 116 (cycle-1 corrected). Pattern for session-join:

   ```javascript
   if (data.type === 'session_joined') {
     App.perf.mark('session-join:received');
     // ... existing renderHistory + showChrome + scroll-to-bottom ...
     App.perf.mark('session-join:dom-mutated');
     App.perf.measure('session-join.ws-to-dom', 'session-join:received', 'session-join:dom-mutated');
     requestAnimationFrame(function () {
       App.perf.mark('session-join:painted');
       App.perf.measure('session-join.dom-to-paint', 'session-join:dom-mutated', 'session-join:painted');
     });
     refreshSessionList();
     return;
   }
   ```

   Pattern for `addMsg`:

   ```javascript
   function addMsg(cls, text, attribution, opts) {
     App.perf.mark('addMsg:start');
     messagesEl.appendChild(App.chat.renderMessage(cls, text, opts));
     // ... attribution + scroll ...
     App.perf.mark('addMsg:end');
     App.perf.measure('addMsg', 'addMsg:start', 'addMsg:end');
   }
   ```

5. **Edit `the_one/interfaces/web/static/js/areas/chat/telemetry-overlay.js`** — wrap `updateTelemetry` body:

   ```javascript
   function updateTelemetry(chromeContent, data) {
     App.perf.mark('telemetry-update:start');
     // ... existing body ...
     App.perf.mark('telemetry-update:end');
     App.perf.measure('telemetry-update', 'telemetry-update:start', 'telemetry-update:end');
   }
   ```

6. **Append `## Performance Measurement (F7)` section to `the_one/agents.md`** — for each of the 4 scenarios:

   ```markdown
   ### Scenario 1: Area-switch cycles (200 cross-area transitions over 50 cycles)

   **Purpose**: detect retention growth across area-lifecycle activate/deactivate cycles. Mission criterion: "memory behavior across `App.areas.activate` / `deactivate` cycles." This supersedes the flight spec's working number of "50 area-switches" — cycle-1 reviewer recommended the higher count (50 loops × 4 transitions per loop = 200) as a stronger leak-detection signal. Budget threshold is computed against the 200-transition total.

   **MCP procedure**:
   ```
   1. `mcp__chrome-devtools__navigate_page(url='http://localhost:8484/?perf=1#chat')`
   2. `mcp__chrome-devtools__evaluate_script(function='() => App.perf.reset()')`
   3. `mcp__chrome-devtools__take_memory_snapshot()` — pre-cycle heap
   4. Loop 50 times: click topbar Chat → Studio → Admin → Chat (4 transitions per loop = 200 area-switches total). Use `mcp__chrome-devtools__click` against `[data-area="studio"]`, `[data-area="admin"]`, `[data-area="chat"]` selectors in turn.
   5. `mcp__chrome-devtools__take_memory_snapshot()` — post-cycle heap
   6. `mcp__chrome-devtools__evaluate_script(function='() => App.perf.summary()')` — collect aggregated area-switch.* measures
   ```

   **Expected baseline** (F7 L01 capture, operator's machine — Flight-Director-filled post-implementation):
   - Pre-cycle heap: TBD MB
   - Post-cycle heap: TBD MB
   - Heap growth: TBD MB / TBD% (BUDGET: ≤20%)
   - p50 `area-switch.full` measure: TBD ms
   - p95 `area-switch.full` measure: TBD ms

   **On failure**: leak roots are most likely in `chat.js:init()`'s closure state (per-init listeners attached to globally-rooted elements survive deactivate); investigate via L02's heap-diff.
   ```

   Repeat similar structure for Scenarios 2-4. Use the MCP to actually run the procedures during this leg and write the observed numbers into the "Expected baseline" rows.

7. **Run `make rebuild`** so the static-asset chain picks up `perf.js`. Then run targeted browser tests:

   ```bash
   docker exec the-one pytest tests/browser/test_flow_chat.py -x --timeout 60 -v
   docker exec the-one pytest -x --timeout 30
   docker exec the-one pytest -m browser --timeout 60 --tb=line
   ```

8. **Capture baselines via MCP** — **THIS STEP IS FLIGHT-DIRECTOR-OWNED** (cycle-1 reviewer [high]): the spawned Developer agent ships the instrumentation + the `the_one/agents.md` template with `TBD` placeholders in every "Expected baseline" row. After the Developer agent reports `landed`, the Flight Director runs each of the 4 MCP scenarios end-to-end and writes the observed numbers into the TBD rows as a small follow-up Edit before the L01 → L02 transition. This split is mandated because spawned Developer agents do NOT have `mcp__chrome-devtools__*` tools (only the Flight Director's session does). **Developer agent**: ship template with TBDs and STOP. **Flight Director**: capture and fill.

9. **Update flight log** with L01 progress entry.

10. **Do NOT commit** — Flight Director batches commits after L05.

## Edge Cases

- **`performance.memory` is Chromium-only**: Firefox / Safari return `undefined` for `performance.memory`. `App.perf.captureHeap()` returns `null` in those browsers. Measurement scenarios assume Chromium (Chrome DevTools MCP attaches to Chrome). Document this limitation in `the_one/agents.md`.
- **`performance.mark` collisions**: marking the same name twice is allowed by spec (creates a second entry). The reset() at scenario start clears all entries; without reset, accumulated marks across navigations could inflate the dump payload. The MCP procedures explicitly call `reset()` at scenario start.
- **`requestAnimationFrame` may not fire on a non-foregrounded tab**: if the operator runs MCP scenarios while the browser tab is in the background, rAF callbacks are throttled or paused. The MCP `select_page` / `navigate_page` should bring the page to foreground.
- **`localStorage.getItem` in private mode**: some browsers throw on localStorage access in private mode. The `try/catch` in `isEnabled()` returns `false` on exception (safe default — perf off).
- **Script load order**: `perf.js` MUST load before `app.js`. `app.js` uses `App.perf.mark(...)` in the cross-area-switch path. Since `perf.js` unconditionally assigns `window.App.perf = { mark, measure, ... }` at module load (no async deps), the order guarantee from `index.html`'s script tag insertion is sufficient. **Decision (cycle-1 reviewer)**: do NOT use defensive `(App.perf && App.perf.mark)` guards in the call sites — they add noise without value once the load-order guarantee is in place. If a future flight adds dynamic-import scripting, revisit.
- **`session_joined` handler synchronous renderHistory cost**: the `session-join:dom-mutated` mark fires AFTER `renderHistory()` + `showChrome()` + scroll-to-bottom complete (lines 739-755). If the budget is exceeded, L02/L03 investigate `renderHistory()` specifically.
- **`addMsg` is called in tight loop during streaming**: each chunk arrival doesn't call `addMsg` (it uses the chunk-pacing path), but each iteration boundary (`tool_call` / `tool_result` events) does. So `addMsg` measures will accumulate. Acceptable — the dump() output keeps all entries; aggregation happens at analysis time.
- **`telemetry-update` is called at every `usage` event**: F6 emits `usage` per step; F7 L04 will add mid-stream emission making this higher-frequency. The instrumentation captures the rate naturally.
- **Areas that DON'T fire `App.perf.mark` in their callbacks won't be measured**: chat/studio/admin all need explicit instrumentation. L01 instruments chat fully; studio + admin lifecycle marks land via the `app.js:performCrossAreaSwitch` wrapper (which fires before/after the per-area `init`/`deactivate`). If granular per-area instrumentation is needed later, add `App.perf.mark` inside each area's `init()` / `deactivate()` — L01 leaves that to future legs.
- **`addMsg` replay inflation during session-join** (cycle-1 reviewer [medium]): `renderHistory` calls `addMsg` once per stored event (`chat.js:223,225,244`); a 100-message session-join generates 100 `addMsg` measure entries. Acceptable for Scenarios 1-2 (~5KB JSON dump payload), but bloats the dump output. Mitigation in this leg: `App.perf.summary()` helper (see new module surface) returns `{name, count, p50, p95, max}` per measure name rather than raw entries — operator can call `App.perf.summary()` instead of `App.perf.dump()` when only aggregates matter.
- **`performance.memory` availability is more restrictive than initial assumption** (cycle-1 reviewer [medium]): Chrome only exposes `performance.memory` for same-origin-isolated contexts; values are throttled to 100KB precision and may require `--enable-precise-memory-info` for fine-grained readings. L01 verification MUST include a quick `App.perf.captureHeap()` smoke against the running app to confirm `performance.memory` returns numbers in THIS Chrome context. If it returns null, the heap-snapshot AC (#4) is unverifiable from the page; scenarios fall back exclusively to `mcp__chrome-devtools__take_memory_snapshot` for heap data. Document the empirical finding in `the_one/agents.md` Scenario sections.
- **`enabled` flag is captured at module-load time** (cycle-1 reviewer suggestion): setting `localStorage.setItem('the-one-perf','1')` mid-session does NOT activate perf until reload. Operators using the localStorage gate must reload after toggling. Document in `the_one/agents.md`.
- **Reload during gated mode**: the perf flag persists via localStorage; URL-only gates (without setting localStorage) clear on reload. The MCP procedures use `?perf=1` URL gating which sets nothing in localStorage — clean test boundaries.

## Files Affected

- `the_one/interfaces/web/static/js/perf.js` — NEW (~100-130 LOC)
- `the_one/interfaces/web/static/index.html` — insert `<script src="/static/js/perf.js"></script>` before app.js
- `the_one/interfaces/web/static/js/app.js` — instrument `performCrossAreaSwitch` (3 marks + 2 measures)
- `the_one/interfaces/web/static/js/areas/chat.js` — instrument `session_joined` handler (3 marks + 2 measures inside rAF) and `addMsg()` (2 marks + 1 measure)
- `the_one/interfaces/web/static/js/areas/chat/telemetry-overlay.js` — instrument `updateTelemetry` (2 marks + 1 measure)
- `the_one/agents.md` — NEW section `## Performance Measurement (F7)` with 4 scenarios + MCP procedures + baseline numbers (filled in by running the procedures via MCP during this leg)

---

## Post-Completion Checklist

**Complete ALL steps before marking the leg landed:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (broad pytest exit 0 with 1669p/4s/374d; browser suite 315p/35s; pixel suite 12/12)
- [ ] Update flight-log.md with leg progress entry, INCLUDING the captured baseline numbers (operator may want to revise at HAT)
- [ ] Set this leg's status to `landed` (NOT `completed`)
- [ ] Do NOT check off this leg in flight.md yet — that happens during the post-L05 commit batch
- [ ] Do NOT commit — Flight Director batches commits after L05

---

## Citation Audit

7 source-code citations verified against current code at leg design time:
- `the_one/interfaces/web/static/index.html:30+` (script load order) — OK
- `the_one/interfaces/web/static/js/app.js:87` (`performCrossAreaSwitch`) — OK
- `the_one/interfaces/web/static/js/app.js:99` (init-once invariant `if (!initialized[areaId])`) — OK
- `the_one/interfaces/web/static/js/areas/chat.js:727` (`session_joined` handler) — OK
- `the_one/interfaces/web/static/js/areas/chat.js:116` (`addMsg` — cycle-1 corrected line) — OK
- `the_one/interfaces/web/static/js/areas/chat/telemetry-overlay.js:68` (`updateTelemetry` — cycle-1 corrected line) — OK
- `the_one/agents.md` (operator-facing docs root) — OK (project convention; verified during recon)
