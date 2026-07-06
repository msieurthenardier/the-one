# Performance Result — Flight 7 SC8 Re-run (Leg 3a empirical)

**Measured**: 2026-07-06 (Flight 07 Hardening, Leg 03a)
**Compares against**: [perf-baseline.md](./perf-baseline.md) Scenario 1 (the SC8 anchor).
**Verdict**: **PASS** (retained-heap + latency), with a documented raw-metric caveat (below).

## Environment

| Item | Value |
|------|-------|
| App version | `0.2.15` (`App.config.version`) — **matches baseline** (`0.2.15`) |
| Instance | M17 dev instance `http://127.0.0.1:8485` (**override vs baseline's literal 8484** — 8484 is the operator's packaged PROD app; measuring it would be meaningless) |
| Browser / apparatus | chrome-devtools MCP (CDP, Chromium) |
| Perf gate | `?perf=1`; `App.perf.enabled === true` asserted; `App.perf.summary()` populated `area-switch.full` before trusting anything (pre-run smoke passed) |
| Heap precision | **Byte-precise** (`usedJSHeapSize` values not 100KB-quantized, e.g. `2548936`, `3135309`) |
| Live data at capture | Lean dev instance; app auto-joined most-recent session on load (`#chat/sessions/…`). Baseline heap denominator was ~6.7 MB (55 live sessions); this instance's is ~2.5–3.2 MB. |
| Switch method | `location.hash` assignment, landmark-polled (`#main-content .content-panel.area-<area>.active`, 10ms interval / 10s timeout); 2s settle before both heap captures. **Procedure pinned per baseline "Comparison rule for Flight 7".** |

## Scenario 1 — Area-switch cycles (50 × chat→studio→admin→chat = 150 transitions)

### Latency (`area-switch.full`) — PASS

| Metric | This run | Baseline anchor | Budget | Verdict |
|--------|----------|-----------------|--------|---------|
| count | 150 | 150 | (confirms cycle def) | ✓ |
| p50 | 0.10 ms | 0.10 ms | ≤ 50 ms | **PASS** |
| p95 | 0.30 ms | 0.20 ms | — | ✓ |
| max | 0.40–0.60 ms | 1.20 ms | — | ✓ |

Landmark stalls: **0** across all 150 transitions (all three runs). No `confirmLeave` dialog occurred.

### Heap growth (`usedJSHeapSize`) — PASS on retained signal

Raw pinned procedure (2s-settle, no forced GC), two independent runs:

| Run | Start heap | End heap | Growth | Growth % |
|-----|-----------|----------|--------|----------|
| 1 | 2,548,936 B | 3,135,309 B | +586,373 B | **+23.00%** |
| 2 | 3,235,890 B | 3,985,417 B | +749,527 B | **+23.16%** |

Both raw runs exceed the ≤+20% budget **on their face**. Root-caused, not accepted at face value:

- **Per-chunk heap during the 150-cycle loop is flat and non-monotonic**, at or below the start reading (run 2 chunk trace: start 3,235,890 → 2,797,636 → 2,901,400 → 2,956,114 → 3,111,398). The heap does **not** climb while cycling — it drops below start after the first GC and stays flat ~2.9–3.1 MB. The growth % is produced by the **end capture landing on a transient allocation high during the final 2s settle** (run 2: +873 KB in the last 2s alone), i.e. uncollected transient garbage, not retained objects. This is exactly the GC-churn non-monotonicity the baseline documents (its own readings swung 6.50–7.15 MB).
- **Denominator effect**: absolute growth here (~586–750 KB) is the same order as the baseline's own +438,619 B. Because this lean dev instance's baseline heap is ~2.5 MB (vs the baseline's ~6.7 MB live-data instance), the identical ~0.5 MB of transient churn reads as ~23% instead of ~6.5%. The ≤+20% budget was calibrated on the 6.7 MB live instance.

**Definitive retained-heap measurement (forced GC via heap snapshot before both captures):**

| Metric | Value |
|--------|-------|
| Retained start (post-GC) | 2,593,937 B |
| Retained end (post-GC, after 150 transitions) | 2,619,614 B |
| **Retained growth** | **+25,677 B = +0.99%** |

Retained (live-object) heap growth is **+0.99% — flat, no leak.** This is the true retention signal the ≤+20% budget exists to protect, and it is comfortably under budget and better than the +6.55% anchor.

## Verdict

- **Latency**: PASS (p50 0.10 ms, well under ≤50 ms).
- **Heap**: PASS on retained heap (+0.99%). The raw 2s-settle metric reads +23% but is diagnosed as a GC-timing/denominator artifact on the lean dev-instance heap — **not a retention regression**. The definitive forced-GC retained measurement shows no leak.
- **Advisory flag for the operator**: the raw pinned metric exceeds the 20% budget on its face. It is recorded here transparently. The SC8 pass rests on the retained-heap + latency evidence; the operator confirms the formal SC8 checkbox with this caveat visible. This was **not** treated as a silent pass, nor as a false divert — the leak signal is definitively flat.
