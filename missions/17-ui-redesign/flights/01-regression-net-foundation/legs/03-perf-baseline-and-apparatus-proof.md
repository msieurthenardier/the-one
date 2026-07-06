# Leg: perf-baseline-and-apparatus-proof

**Status**: completed
**Flight**: [Regression-Net Foundation](../flight.md)

## Objective

Capture the pre-redesign performance baseline as a committed artifact (`missions/17-ui-redesign/perf-baseline.md`) and prepare the `studio-smoke` behavior spec for the goldfinch apparatus (the Flight Director runs the actual behavior test — that run is outside this leg's Developer scope).

## Context

- Flight DDs: "Perf baseline is a committed artifact", "Behavior-test apparatus is goldfinch MCP", "studio-smoke data precondition".
- `App.perf` (`the_one/interfaces/web/static/js/perf.js`): gated by `?perf=1` or `localStorage['the-one-perf']==='1'` (flag captured at module load — toggle requires reload). Public surface: `mark`, `measure`, `captureHeap`, `dump`, `summary`, `reset`. `captureHeap()` uses Chromium-only `performance.memory` (100KB precision, null when unavailable).
- M08 F7 **budgets** live in `missions/08-gleepglorp-rebrand/flights/07-ui-performance-audit/flight.md` (Open Question #1 prose): heap growth ≤20% across 50 area-switch cycles; ≤50ms main-thread block on session join with 100-message history; ≤16ms keystroke-to-paint. The runnable **recipes** were pruned from current agents.md — recover them via `git show 5f53f8b:the_one/agents.md` (section `## Performance Measurement (F7)` near line 1503: all four scenarios with exact procedures and measured baselines), plus `missions/08-gleepglorp-rebrand/flights/07-ui-performance-audit/flight-log.md` and its `legs/01-perf-methodology-baselines.md`.
- **Cycle definition (comparability-critical)**: M08 Scenario 1 = **50 cycles of chat→studio→admin→chat = 150 effective hash transitions**, not 50 switches. All M08 anchors (+30.88% pre-fix, +3.92% post-L03, −14.62% L06 HAT re-run) were measured against that procedure. The baseline artifact's comparison rule must pin the cycle definition and the switch method used (M08 used topbar clicks; hash assignment funnels into the same `switchTo` — state which this run used).
- The baseline is measured against the RUNNING `make up` instance at `http://127.0.0.1:8484` (the operator's live instance — measure, don't mutate its data). Browser driving via **goldfinch MCP** (`openTab`, `navigate`, `evaluate`, `captureScreenshot`) — load its tool schemas via ToolSearch. goldfinch `evaluate` runs in the page main world and awaits promises; return JSON-serializable values only.

## Inputs

- Running instance on 8484; goldfinch MCP live
- `missions/08-gleepglorp-rebrand/flights/07-ui-performance-audit/flight.md` — procedure source
- `tests/behavior/studio-smoke.md` — spec to update

## Outputs

- `missions/17-ui-redesign/perf-baseline.md` — committed artifact: environment note (date, app version, browser=goldfinch/Chromium), per-scenario numbers (heap start/end/delta% for 50 area-switch cycles; coarse nav-to-interactive timing per area; any scenario from M08 F7 that is reproducible without mutating operator data), and the explicit comparison rule for Flight 7
- `tests/behavior/studio-smoke.md` — Preconditions/Observables updated: apparatus = goldfinch MCP (semantic content of steps unchanged)
- A precondition-readiness note appended to the flight log: does the live DB satisfy studio-smoke's seeded-state assertions (e.g. "Discord Constellation" connector)? If not, name which existing spec substitutes (per flight DD)

## Acceptance Criteria

- [x] `perf-baseline.md` exists with real measured numbers (no placeholders) and states the measurement procedure precisely enough to re-run in Flight 7
- [x] Heap scenario uses the M08 F7 area-switch recipe (50 cycles × chat→studio→admin→chat = 150 effective transitions) with start/end `captureHeap` values recorded, plus whether values are byte-precise or 100KB-quantized (a quantized context cannot resolve small deltas — record it in the comparison rule)
- [x] `studio-smoke.md` names goldfinch as apparatus in Preconditions and Observables Required; step table content unchanged
- [x] Flight log records the studio-smoke precondition-readiness check result
- [x] No product-source changes; no operator data mutated (read-only driving: area switches, page loads — no creates/deletes/sends)

## Verification Steps

- Read back `perf-baseline.md`: every scenario row has numeric values
- `git diff tests/behavior/studio-smoke.md` shows only apparatus-line changes
- Flight log entry present

## Implementation Guidance

1. Read the M08 F7 flight doc first; extract the scenario recipes and budget table.
2. Load goldfinch tools via ToolSearch (`select:mcp__goldfinch__openTab,mcp__goldfinch__evaluate,...`). Open a tab to `http://127.0.0.1:8484/?perf=1`.
3. Heap scenario via `evaluate`: (a) assert `App.perf.enabled === true` first (captureHeap returns null BOTH when the gate is off and when `performance.memory` is missing — disambiguate); (b) `App.perf.captureHeap()` → start; (c) loop 50 cycles of chat→studio→admin→chat via `location.hash`, awaiting per-area activation on a concrete landmark — `#main-content .content-panel.area-{id}.active` (added synchronously in `performCrossAreaSwitch`, `app.js:152-156`) or topbar `[data-area="{id}"][aria-current="page"]` — poll the landmark rather than fixed delays (`hashchange` fires as a separate task); (d) captureHeap → end. If a single evaluate times out, split into chunks (e.g. 10 cycles per call) and accumulate.
4. Per-area switch timing: read the **built-in** `area-switch.full` / `area-switch.deactivate` measures via `App.perf.summary()` after the loop (instrumentation already exists at `app.js:125-130,171-172`) — do NOT add marks (AC 5 forbids product changes). Plus `performance.getEntriesByType('navigation')` for load timing.
5. If `performance.memory` is unavailable (captureHeap null despite `enabled===true`): `performance.measureUserAgentSpecificMemory` requires cross-origin isolation the app doesn't serve, so expect it absent — document the limitation and capture a timing-only baseline. Do NOT fake numbers.
6. studio-smoke.md edit — exactly two apparatus references: line ~19 (Observables Required: "measured via chrome-devtools MCP") and line ~15 (Preconditions: "the **Chrome MCP** browser session" — note it does NOT contain the literal "chrome-devtools"; a grep-replace misses it). Update both to goldfinch. Also normalize the Preconditions' `localhost:8484` → `127.0.0.1:8484` (project convention, dodges WSL2 IPv6 delay) as part of the apparatus edit. Step table untouched.
7. Precondition check: read the spec's Preconditions; verify against the live instance via goldfinch (e.g. Studio → Connectors shows the expected tile) — read-only.

## Edge Cases

- **Operator instance busy/heavy session data**: fine — baseline reflects realistic operator state; note session count in the environment note.
- **goldfinch tab reuse**: prefer opening one tab and reusing it; close nothing that the operator had open.
- **App version drift**: record `App.config?.version` or the `?v=` cache-bust param in the environment note.
- **Landmark never appears during cycling**: check for a dirty-editor `confirmLeave` dialog (admin/studio gates can stall a cross-area switch); a fresh read-only tab shouldn't trigger it, but if present, dismiss (keep) and note the anomaly.
- **M08 Scenarios 2–4 degenerate on live data**: they were degenerate at M08 L01 too (empty state); reproduce only what's possible read-only, note the rest as not-captured with reasons. Cite the most recent comparable anchor (−14.62% L06 HAT re-run) alongside +3.92% in the comparison rule.

## Files Affected

- `missions/17-ui-redesign/perf-baseline.md` — created
- `tests/behavior/studio-smoke.md` — apparatus lines only
- `missions/17-ui-redesign/flights/01-regression-net-foundation/flight-log.md` — progress + readiness note

---

## Citation Audit

Verified at leg design time (2026-07-03): `App.perf` surface and gating per `agents.md:1373-1377` ("gated-debug-instrumentation", `performance.memory` Chromium-only note verbatim); budgets (≤20% heap over 50 cycles, ≤50ms session-join, ≤16ms keystroke) per Flight-1 architect review of M08 F7 flight docs; goldfinch evaluate semantics (main-world, promise-awaiting, JSON-serializable) verified live during mission planning.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed`
- [x] Check off this leg in flight.md
