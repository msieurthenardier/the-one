# Squawk 0376: The `mcp` browser lane sits at its time budget after sortie 18

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-17
**Completed**: —

## Report
Sortie 18's closing browser gate printed `OVER BUDGET` for the `mcp` lane: 331 s against a 330 s budget. The run was on a loaded host (start load about 3, about 7 during the run, with a dev instance up for the HAT), so by the quiet-host rule it is not a budget reading. The lane did grow, though: leg 2 added thirteen flow tests for the Arguments rows and the HAT fix added more, and before the sortie the lane measured 292 s.

Needed: one `--parallel 3` run on a quiet host (1-minute load below about 1.0, no other test process), then re-budget `mcp` from that reading (measured plus 25%, rounded up to 30 s) in `scripts/run-tests.sh` and the lane table in `CLAUDE.md`. If the lane is over 1.3 times its budget on that run, consider splitting it instead.

## Evidence
- Sortie 18 closing gate: `PARALLEL_RESULT rc=0 total=2240s lanes=20 failed=-`; `mcp rc=0 wall=331s budget=330s OVER BUDGET` (`sorties/18-mcp-arguments-as-rows/flight-log.md`, Flight Director Notes).
- Sortie 18 debrief gate (2026-11-17, `7717fec8`): `mcp` 390 s, 105 passed, in a `--parallel 3` run that started at load 1.02 and ended at 5.29. Also a loaded reading, so still not a budget reading. A solo `--lane mcp` run after the HAT fix took 261 s. The quiet-host run is still needed (`sorties/18-mcp-arguments-as-rows/flight-debrief.md`, "Test metrics").
- **A quiet-start reading, sortie 19's closing gate (2026-11-18):** `PARALLEL_RESULT rc=0 total=2179s lanes=20 failed=-`, start load 0.87, no other test process on the host and the local CI workers idle at the start; `mcp rc=0 wall=322s budget=330s`, no lane over budget. The lane's file set is unchanged since sortie 18 (sortie 19 added its editor tests to `mcp-connection`). By the rule above (measured plus 25%, rounded up to 30 s) the budget would be 420 s (`sorties/19-local-mcp-servers-newest-protocol/flight-log.md`, "closing gate").
- `CLAUDE.md` "Lane time budgets" — `mcp` budget 330 s, measured 292 s; "Quiet-host rule (squawk 0259)".
- `scripts/run-tests.sh` — the budget table is the source of truth.

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
