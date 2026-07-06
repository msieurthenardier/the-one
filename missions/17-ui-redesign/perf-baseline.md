# Performance Baseline — Mission 17 (pre-redesign anchor)

**Captured**: 2026-07-03 (Flight 01, Leg 03)
**Purpose**: SC8's comparison anchor. Every later flight in this mission (and Flight 7's
regression verdict in particular) compares against the numbers in this file, re-measured
with the exact procedures below.

## Environment

| Item | Value |
|------|-------|
| App version | `0.2.15` (`App.config.version`; static assets served with `?v=0.2.15`) |
| Instance | Operator's live `make up` instance at `http://127.0.0.1:8484` (host-native, WSL2) |
| Browser / apparatus | goldfinch MCP 0.5.7 (Electron 42.4.0, Chrome/148.0.7778.254 — Chromium engine) |
| Perf gate | `?perf=1` URL param; `App.perf.enabled === true` asserted before capture |
| Heap source | `performance.memory` via `App.perf.captureHeap()` — **available** in this context |
| Heap precision | **Byte-precise** (observed values are not 100KB-quantized, e.g. `6695608`, `7134227`) |
| Live data at capture | 55 chat sessions in sidebar, 3 agents, 1 connector; app auto-joined most-recent session (`#chat/sessions/…`) on load — realistic operator state, per leg edge-case guidance |
| Driving method | goldfinch `evaluate` (page main world); area switches by `location.hash` assignment |

## Scenario 1 — Area-switch cycles (heap retention + switch latency)

**Procedure (pin this exactly for Flight 7 re-runs):**

1. Open a fresh tab at `http://127.0.0.1:8484/?perf=1#chat`; wait for
   `#main-content .content-panel.area-chat.active`.
2. Assert `App.perf.enabled === true` (disambiguates `captureHeap() === null`: it returns
   null BOTH when the gate is off and when `performance.memory` is missing).
3. Idle-settle 2s, `App.perf.reset()`, then `App.perf.captureHeap()` → **start**.
4. **50 cycles of chat→studio→admin→chat = 150 effective hash transitions** (the M08 F7
   Scenario 1 cycle definition; the cycle-boundary chat→chat hop is a hashchange no-op, so
   50 cycles yield exactly 150 `area-switch.full` measures — verified: count was 150).
   Each transition: assign `location.hash = '#<area>'`, then **poll the landmark**
   `#main-content .content-panel.area-<area>.active` (10ms interval, 10s timeout) — no
   fixed delays (`hashchange` fires as a separate task).
   **Switch method**: `location.hash` assignment (funnels into the same `switchTo` /
   `performCrossAreaSwitch` path as topbar clicks). **M08's anchors used topbar clicks** —
   same code path, but record the method every run.
   (Run in chunks of 10 cycles per `evaluate` call to stay under tool timeouts;
   accumulate heap readings per chunk.)
5. Idle-settle 2s, `App.perf.captureHeap()` → **end**; `App.perf.summary()` for the
   built-in `area-switch.full` / `area-switch.deactivate` measures (instrumentation at
   `app.js:125-130,171-172` — no marks added by the measurement pass).

**Measured (2026-07-03):**

| Metric | Value | Budget (M08 F7) | Verdict |
|--------|-------|-----------------|---------|
| Start heap (`usedJSHeapSize`) | 6,695,608 B (6.39 MB) | — | — |
| End heap (`usedJSHeapSize`) | 7,134,227 B (6.80 MB) | — | — |
| **Heap growth** | **+438,619 B = +6.55%** | ≤ 20% over 50 cycles | **PASS** |
| `area-switch.full` count | 150 | (confirms cycle definition) | ✓ |
| `area-switch.full` p50 / p95 / max | 0.10 ms / 0.20 ms / 1.20 ms | p50 ≤ 50 ms | **PASS** |
| `area-switch.deactivate` p50 / p95 / max | 0.00 ms / 0.00 ms / 0.10 ms | — | ✓ |
| Loop wall time | ~1.7 s for 150 transitions | — | — |

Per-10-cycle heap readings (usedJSHeapSize, taken at each chunk boundary):
`7,154,273 → 6,768,875 → 6,683,512 → 6,498,527 → 7,134,227` — non-monotonic (GC churn),
no unbounded-growth signature.

No `confirmLeave` dialog or landmark stall occurred at any of the 150 transitions.

## Scenario — Coarse nav-to-interactive per area (fresh page load)

**Procedure**: full page load (`location.reload()`) landing at each area hash with
`?perf=1`; read `performance.getEntriesByType('navigation')[0]` plus the
`area-switch:activated` mark's `startTime` (elapsed ms from navigation start to the area
panel's activation — the initial activation runs through `performCrossAreaSwitch`, so the
mark exists on every fresh load). Single-sample, coarse — treat ±50% swings on re-run as
noise unless reproducible.

| Area (landing hash) | nav → area activated | DOMContentLoaded | loadEventEnd | responseEnd |
|---------------------|---------------------|------------------|--------------|-------------|
| `#chat` | 63.6 ms | 60.2 ms | 61.0 ms | 8.0 ms |
| `#studio` | 213.6 ms | 210.5 ms | 211.3 ms | 159.9 ms |
| `#admin` | 57.4 ms | 54.5 ms | 55.2 ms | 4.0 ms |

Note: studio's higher figure is dominated by document `responseEnd` (159.9 ms server/fetch
variance on that sample), not by JS activation cost — activated-minus-DCL is ~3 ms for all
three areas.

## M08 F7 Scenarios 2–4 — not captured (with reasons)

Reproduced read-only where possible; the leg forbids mutating operator data (no
creates/deletes/sends, no joining sessions beyond the app's own auto-join).

- **Scenario 2 (100-message session join)**: not captured. The auto-joined session renders
  ~11 messages; no ≥100-message session was joined (joining other sessions was avoided
  under read-only discipline). Degenerate at M08 L01 too (empty state there).
- **Scenario 3 (50+-session sidebar refresh)**: not captured as a standalone number. The
  live sidebar DOES carry 55 sessions (precondition met by live data), but the M08
  procedure drives 10 `refreshSessionList` triggers via message sends (mutating), and no
  built-in measure covers the sidebar render (`activate()` runs after the
  `area-switch.full` measure closes). Flight 7 can capture this with a seeded dev instance
  if needed.
- **Scenario 4 (30+ agents in studio)**: not captured — live instance has 3 agents;
  seeding is a mutation. Degenerate at M08 L01 too.

## Comparison rule for Flight 7

1. Re-run **Scenario 1 exactly as pinned above**: 50 cycles × chat→studio→admin→chat =
   **150 effective hash transitions**, `location.hash` switching, landmark-polled, 2s
   settle before both heap captures, `?perf=1`, goldfinch (Chromium) against the live
   instance. A run with a different cycle count, switch method, or settle procedure is
   **not comparable** — re-run, don't adjust.
2. Compare `usedJSHeapSize` growth %. **Budget: ≤ +20% (M08 F7)**. Acceptable run-to-run
   variance on the same machine: ±5 pp heap growth; ±25% on p95 latency (M08 rule).
3. This baseline's heap values are **byte-precise**. If a future measuring context
   quantizes `performance.memory` to 100KB (some Chromium contexts do), deltas smaller
   than ~100KB per reading are unresolvable there — record the precision observed in every
   run and do not read sub-quantum deltas as signal.
4. Anchors for context: M08 F7 measured **+30.88%** pre-fix, **+3.92%** post-L03, and
   **−14.62%** at the L06 HAT re-run (most recent comparable anchor). This run's **+6.55%**
   sits in the healthy post-fix range given live operator data (55 sessions, live WS held
   across cycles — chat's deactivate intentionally keeps the WS alive).
5. Nav-to-interactive per area is a coarse, single-sample sanity metric: compare orders of
   magnitude, not milliseconds; investigate only a reproducible multi-x regression of the
   activated-minus-DCL gap (~3 ms here).
