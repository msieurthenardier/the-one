# Flight Log: UX Hotfixes from F3 Debrief

**Flight**: [UX Hotfixes from F3 Debrief](flight.md)

## Summary

Planning phase. Reconnaissance complete (F3 debrief's 3 hotfix items + 4 methodology codifications + criterion-coverage map seed all verified against current code). Design decisions documented in `flight.md`. Awaiting Architect design review.

---

## Reconnaissance Report

Walk of every F3-debrief-cited source item against current code state (2026-05-23, post-F3 ship at commits e53f9e1 + 4cc562f + 75639d4 + edf4383). Per the F3-debrief-recommended `cross-flight-ux-debt-reconciliation` discipline.

| # | Item | Classification | Evidence | Recommendation |
|---|---|---|---|---|
| R1 | A1 — Test Connection does NOT warm pool | confirmed-live | `api.py:2573-2638` `test_connector_connection` calls `plugin.doctor()` at L2621; zero `account_acquire` references in the function | F4 L2 — bundle with C1 |
| R2 | A2 — checkbox-mode renders raw IDs | confirmed-live | `connectors-tab.js:507` `nameSpan.textContent = item;` where `item` is raw snowflake; no label-cache lookup | F4 L3 — fetch L4 API; resolve labels |
| R3 | C1 — `test_edit_session_continuation_round_trip` text drift | confirmed-live | `tests/browser/test_flow_studio_connector_account_editor.py:417` asserts `"Distinct from the pool idle timeout"`; source at `connector-account-editor.js:368` says `"Inbound continues the same chat session within this window."` | F4 L2 — one-line test update; bundle with A1 |
| R4 | `pool-warming-entrypoints-are-finite-and-named` convention | confirmed-live | Not in `agents.md` (grep returns zero hits) | F4 L1 codification |
| R5 | `frozen-snapshot-for-cross-lock-read` convention | confirmed-live | Not in `agents.md` | F4 L1 codification |
| R6 | `slot-getter-bridge-for-dropdown-collect-path` convention | confirmed-live | Not in `agents.md` | F4 L1 codification |
| R7 | `two-concurrent-callers-reasoning` architect-checklist extension | confirmed-live | Not in `agents.md` | F4 L1 codification (separate subsection or text in L1 leg artifact) |
| R8 | `cross-flight-ux-debt-reconciliation` + `touched-surface-ux-debt-folding` (mission-control side) | partially-satisfied | F4 itself USES these disciplines (this recon table is `cross-flight-ux-debt-reconciliation`-shaped); project-side `agents.md` note codifies for the project; mission-control's `/flight` and `/leg` skill prompts remain un-touched per "no mission-control changes" stance from F3 | F4 L1 — project-side note only |
| R9 | M11 criterion-coverage living artifact (M10 debrief recommendation #5) | confirmed-live | `missions/11-discord-connector-depth/criterion-coverage.md` does not exist | F4 L1 — seed |
| R10 | `account_acquire` callable from `api.py` | confirmed-live | `the_one/connectors/_pool.py:830` exports `async def account_acquire(account_id: str) -> ConnectorClient`; existing `api.py` callsites import via function-local-import convention | A1's integration target |
| R11 | L4 GET endpoint `/api/connector-accounts/{id}/discoverable-entities` callable from `connectors-tab.js` fetch | confirmed-live | F3 L4 shipped + F3 L7 HAT verified the endpoint live | A2's integration target |

**Operator-confirmed live items folded into F4**: R1 (L2), R2 (L3), R3 (L2 bundle), R4-R7 (L1), R8 (L1 project-side note), R9 (L1 seed), R10 (A1 integration), R11 (A2 integration).

**Items DEFERRED out of F4 scope per operator selection**:
- F3 L7 step 8 (stale-entry indicator HAT verification) — operator-side Discord action required; deferred to F9 (Live-traffic HAT script).
- F3 debrief Routine-maintenance candidates (C3 AIAT cluster; C5a/b chronic UI tests; unify `_xxxValues` getter pattern; lift axis vocabulary constant; remove `_RegistryEntry.account_type=""` default; L4 `prior_cache` force-interleaving test) — slot for `/routine-maintenance` between F4 and F5 OR fold into F5+ as touched-surface debt.
- Mission-control skill prompt changes (`cross-flight-ux-debt-reconciliation` + `touched-surface-ux-debt-folding` skill updates; `two-concurrent-callers-reasoning` extension to `/leg`) — out of project scope; project-side notes in `agents.md` are the binding fallback.

**Phase 4 crew interview outcomes** (2026-05-23):
- Codifications first per L1-style; mirrors F3 L1 precedent.
- A1: `account_acquire` placement AFTER `plugin.doctor()` succeeds (not before; not in parallel). Adds `details.pool_warmed` field to response envelope.
- A2: per-tile fetch (not shared cache). Per-tile cost is one L4 cache hit; acceptable.
- C1: update test-side (not source-side) per L2 `match-tests-to-code-when-code-is-operator-friendly` precedent.
- L4 HAT scope: A1 + A2 only; stale-entry deferred to F9.
- Criterion-coverage map: seed with M11 19 criteria + initial status; format = plain markdown table; future flights maintain incrementally.

---

## Leg Progress

*(empty — to be populated as legs are planned + executed)*

---

## Decisions

Runtime decisions not in original plan.

*(empty — to be populated during execution)*

---

## Deviations

Departures from planned approach.

*(empty)*

---

## Anomalies

Unexpected issues encountered.

*(empty)*

---

## Session Notes

### 2026-05-23 — Architect Design Review

- **Cycle 1**: approve with changes. One MED + 2 LOW catches:
  - MED: L4 HAT step 3 "cold-test variant" was impractical — no test-only API to evict; idle TTL is 30 min. Restart is the cold-pool path; merged into step 1.
  - LOW: F3 flight.md correction site moved from L4-body to F3-header annotation per agentic-workflow `SKILL.md:47` guidance.
  - LOW: `two-concurrent-callers-reasoning` placement pinned as regular Project-wide convention.
  - Plus suggestions absorbed: A1 inner-try/except error-surface isolation (avoids regression where pool-warmup-fail looks like Test Connection FAIL); A2 lazy-on-tile-expand + tile-local closure cache; criterion-coverage row schema locked; maintenance contract pinned; HAT renumbered to 6 steps with envelope inspection; Known UX Gaps escalation location pinned to F4 flight-debrief subsection.
- **Cycle 2**: approve. All cycle-1 fixes landed cleanly. 3 LOW inline refinements flagged for leg-author absorption (not blocking):
  - Narrow `BaseException` → `Exception` in A1 (L2 leg author note); preserves cooperative-cancellation discipline.
  - Add self-describing maintenance contract line to criterion-coverage.md header (L1 leg author note); applies the `mechanical-fallback-prompt-truth-pairing` convention recursively.
  - Reconcile stale L4-cache-strategy phrasing in L2 leg description (applied inline).
- F4 status: `ready`. Awaiting operator approval / `/agentic-workflow` execution.

### 2026-05-23 — Planning Session

- F3 just completed (PR #71 open; flight artifact status `completed`; debrief at `flight-debrief.md`).
- F4 scope sourced from F3 debrief Action Items "Immediate (before F4)" + "Methodology (before F4 planning)" + cumulative-UX-debt enumeration. Operator selected the broadest scope option ("hotfixes + codifications + criterion-map + HAT smoke-verify").
- Phase 1b recon (this section) is the n=1 application of the new `cross-flight-ux-debt-reconciliation` discipline F3 debrief recommended. It verified all 11 source items against current code.
- Phase 4 crew interview resolved 6 design decisions documented in `flight.md`.
- L1's codifications close the F3 debrief's "before F4 planning" methodology Action Items. L2-L4 close the "Immediate (before F4)" Action Items + the HAT smoke-verify.
- F4's framing as "intervention to arrest UX-debt accumulation" is explicit in flight.md Objective. Adaptation Criteria mandate: if HAT surfaces new UX issues, fold into F4 OR escalate as Known UX Gap with near-term path — NOT F8/F10 deferral.
