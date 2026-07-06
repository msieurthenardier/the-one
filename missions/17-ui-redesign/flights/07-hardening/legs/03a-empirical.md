# Leg: 03a-empirical (EMPIRICAL — perf re-run + behavior sweep)

**Status**: completed
**Flight**: [Hardening & Mission-End Acceptance](../flight.md)

## Objective

The empirical half of Flight 7 acceptance: two kinds of live measurement on the **8485 dev instance only** (never 8484 — the operator's packaged PROD app), all **sequenced, never overlapping** on 8485.

1. **PART 1 — SC8 perf re-run** (Scenario 1 from `perf-baseline.md`, target 8485).
2. **PART 2 — behavior sweep**: 4 Witnessed behavior specs, one spec at a time.

## Ledger

### PART 1 — SC8 perf re-run — **PASS** (retained-heap + latency; raw-metric caveat flagged)

- Apparatus: chrome-devtools MCP (CDP). Version `0.2.15` (matches baseline). Heap **byte-precise**. Pre-run smoke passed (`App.perf.enabled===true`, `area-switch.full` populated).
- 50 cycles × chat→studio→admin→chat = **150** `area-switch.full` measures, landmark-polled, 0 stalls, no confirmLeave.
- **Latency**: p50 **0.10 ms** / p95 0.30 ms / max 0.40–0.60 ms — PASS (≤50 ms budget; matches the 0.10 ms anchor).
- **Heap**: raw 2s-settle metric read **+23.0% / +23.16%** (two runs) — over the ≤20% budget on its face, but per-chunk heap stayed **flat during cycling** (growth was end-capture transient garbage on the lean ~2.5 MB dev heap vs baseline's ~6.7 MB). **Forced-GC retained growth = +0.99%** (2,593,937 → 2,619,614 B) — flat, **no leak**. Diagnosed GC-timing/denominator artifact, not a retention regression.
- Full note: [../../../perf-result-f7.md](../../../perf-result-f7.md). Advisory: raw metric over budget is recorded transparently; SC8 pass rests on retained-heap + latency; operator confirms the formal checkbox with the caveat visible.

### PART 2 — behavior sweep (chrome-devtools MCP apparatus; 8485 only; sequenced)

Pre-sweep grid hygiene: `GET /api/providers` on 8485 returned only Anthropic + Ollama Local (operator's real providers) — **no orphaned test/mock artifacts** to delete.

1. **chat-roundtrip.md — DARK theme** (owed SC7 run): **PASS 5/5** + CP5 [a11y] PASS. Stop witnessed mid-stream (delay widened to 15000ms), markdown real `<strong>`/`<code>`, round-trip persisted across cold reload, dark contrast 15.17:1/14.4:1. Seeded provider+agent cleaned. [run log](../../../../tests/behavior/chat-roundtrip/runs/2026-07-06-05-28-01.md)
2. **system-provider-config.md — both themes** (H1/subtitle re-render proof): **PASS 20/20** (light 10/10, dark 10/10). **Step 7 H1 re-render confirmed BOTH themes** (H1 `→ — edited` in place, no reload; subtitle re-rendered). Step 9 [a11y] armed-delete PASS both. Grid mock badge quiet. Providers created+deleted by the flow; grid clean. Caveat: Executor mis-sampled armed-button computed colors (a11y judged from screenshots, pass AA). [run log](../../../../tests/behavior/system-provider-config/runs/2026-07-06-05-41-42.md)
3. **studio-agent-crud.md — dark theme** (cap-chip quiet non-regression): **PASS 9/9** + cap-chip PASS. **Cap-chip quiet CONFIRMED**: 12 organic visible `.cap-chip` on studio agent-tiles, lowercase, text-transform:none, letter-spacing:normal. Step 8 [a11y] PASS (armed accessible-name via DOM sample, two-step safety via API; caveat: armed-state screenshots caught the reverted resting state — visual corroboration missing, load-bearing claims sound). Seeded provider cleaned. [run log](../../../../tests/behavior/studio-agent-crud/runs/2026-07-06-06-06-19.md)
4. **shell-navigation-smoke.md — both/auto** (final regression smoke): **PASS 6/6**. Shell nav contract holds after all F7 changes: 3-area render, Studio nav, theme flip (light→dark) + restore to Auto, Chat composer, cold `#admin/providers` deep-link hash-survival. Read-only, no seeding. [run log](../../../../tests/behavior/shell-navigation-smoke/runs/2026-07-06-06-21-43.md)

## Behavior sweep verdict: 4/4 specs PASS

| Spec | Theme(s) | Result | Key confirmation |
|------|----------|--------|------------------|
| chat-roundtrip | dark | PASS 5/5 (+CP5 a11y) | Stop witnessed mid-stream; markdown real `<strong>`/`<code>`; round-trip persisted cold reload |
| system-provider-config | light + dark | PASS 20/20 | **H1 + subtitle re-render in place on edit-save, both themes** (F7 fix) |
| studio-agent-crud | dark | PASS 9/9 (+cap-chip) | **cap-chip quiet held**: 12 organic visible chips, lowercase/no eyebrow/no letter-spacing |
| shell-navigation-smoke | both/auto | PASS 6/6 | nav contract + hash-survival + theme flip/restore green |

**Anomalies (evidence-capture only, no product defect):** (a) system-provider-config Executor mis-sampled the armed delete-button computed colors — a11y judged from screenshots (pass AA); (b) studio-agent-crud Step-8 armed screenshots caught the reverted resting state (the ~3s armed window outran the capture) — armed accessible-name proven via synchronous DOM sampling, two-step safety via API. Both are apparatus-timing artifacts; the load-bearing claims are soundly evidenced. Recommend future runs freeze the armed transient (suppress revert timer) before both screenshot and a11y snapshot.

**Cleanup confirmed:** every seeded artifact removed; final providers grid = {Anthropic, Ollama Local}; no leftover test agents; theme restored to Auto (localStorage empty).

## Acceptance Criteria

- [x] SC8 Scenario 1 re-run on 8485; heap + latency compared to baseline; verdict recorded in perf-result-f7.md
- [x] chat-roundtrip dark theme run (Witnessed) — pass 5/5, run log written, data cleaned
- [x] system-provider-config both themes (Witnessed) — H1 + subtitle re-render confirmed both themes, run log, cleaned
- [x] studio-agent-crud dark (Witnessed) — cap-chip quiet confirmed, run log, cleaned
- [x] shell-navigation-smoke (Witnessed) — regression smoke green 6/6, run log
- [x] Ledger written; leg landed
