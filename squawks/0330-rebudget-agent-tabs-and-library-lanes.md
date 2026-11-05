# Squawk 0330: Re-budget the `agent-tabs` and `library` browser lanes

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-05
**Completed**: —

## Report
Sortie 10 added a browser test file to each of these lanes. On the sortie 10 debrief's quiet-host gate (commit `ba5ff7ee`, `PARALLEL_RESULT rc=0 total=1938s lanes=17`, start load 0.88):
- `agent-tabs` measured 466 s against its 510 s budget (91%), up 14.5% from the M34 F1 L02 reading of 407 s. The sortie 09 debrief had already flagged it at 83%.
- `library` measured 379 s against 420 s (90%), up 9% from 348 s.

The next sortie that adds tests to either lane will push it over budget.

## Evidence
- `scripts/run-tests.sh:71` — `[agent-tabs]=510   # M34 F1 L02 quiet-host gate: measured 407 s`; `:73` — `[library]=420`.
- The CLAUDE.md lane-budget table lists `agent-tabs` 510/407 and `library` 420/348.
- `sorties/10-secrets/flight-debrief.md` "Test Metrics".

## Corrective Action
*(written at completion)* Planned: apply the CLAUDE.md rule (measured plus 25%, rounded up to 30 s), which gives `agent-tabs` 600 s and `library` 480 s. Update `scripts/run-tests.sh` and the CLAUDE.md table and notes, citing this reading. Splitting `agent-tabs` is a separate decision, not this squawk.

## Verification
`tests/test_run_tests_lanes.py` passes (it pins the budget table), and `bash scripts/run-tests.sh --parallel 3 --plan` shows the new budgets.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
