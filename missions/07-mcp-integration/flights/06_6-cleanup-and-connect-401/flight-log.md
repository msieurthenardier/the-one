# Flight Log: Cleanup + connect-time 401 translation

**Flight**: [Cleanup + connect-time 401 translation](flight.md)

## Summary

Flight in `ready` state — design phase complete; design review cycle 1 passed; ready for execution.

---

## Flight Director Notes

### 2026-05-09 — Flight kickoff

**Origin**: Born from F6.5 debrief recommendations 1-4 (carry-forward maintenance) + F6.5 Design Decision §3's explicit deferral of connect-time 401 widening. Replaces the originally-scoped F7 inspector flight, which was reframed away post-F6.5 review (form-driven invocation + JSON-RPC trace pane judged developer-tooling rather than operator-facing). Useful F7 leftovers (capability flags display, input-schema visibility) folded into F8's scope per mission amendment in this same commit.

**Scope tightness**: 2 legs, no HAT, ~230 LOC total. Verification entirely via unit tests since no new operator-facing surfaces are introduced. F6.5 Design Decision §4's binding-HAT-for-OAuth-flights pattern explicitly waived (see flight.md Design Decision §4 for rationale).

---

## Leg Progress

> Append leg-execution entries below as L0 + L1 land.

---

## Decisions

> Append runtime decisions not in original plan.

---

## Deviations

> Append departures from planned approach.

---

## Anomalies

> Append unexpected issues encountered.

---

## Session Notes

### 2026-05-09 — F6.6 design + mission scope amendment

Flight artifact authored against F6.5 debrief carry-forward items + F6.5 Design Decision §3 deferral. Mission amendment in the same commit: F7 entry struck through with rationale; useful leftovers absorbed into F8's scope. F9 prose updated to drop "inspector" reference.

Open questions all resolved at design time (no Phase 4 user iteration needed — the scope is mechanical: maintenance batch + a small connect-time addition). Spec passed design review cycle 1 with corrections; see `flight.md::Design Review Cycle 1` for the trail.

**Design review correction (cycle 1)**: original spec mis-framed L1 as "verbatim mirror of F6.5 L2's `list_tools` pattern." Architect verified the actual `connect()` body — it already has 401-translation via outer BaseExceptionGroup walk (F6 A5 work). Real gap is the `OAuthFlowError`/`OAuthTokenError` `except*` clause. L1 reframed as "ADD only the missing clause" with nested `try/except*` (Python's no-mix-`except`-with-`except*` constraint forces the nesting). Net diff estimate dropped from ~80 LOC to ~30 LOC for L1.
