# Squawk 0217: Re-budget the `agents` and `shared` browser lanes

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-15
**Completed**: —

## Report
Two browser lanes now run at or over their wall-clock budgets in a `--parallel 3` gate. `agents` read 504, 501, **523**, 503 and 500 s against 510 across sortie 04's gates (506 at sortie 03, whose debrief already asked for a re-budget). `shared` read 283, 292, **302**, 300 and 301 s against 300, growing with every shared-lane browser test. Over budget is only a warning, so the next flight that adds browser tests will make the warning permanent noise. Re-budget from the current measurements (proposed: `agents` about 560, `shared` about 330), keeping the same "+~10% headroom, rounded to 30 s" style.

## Evidence
- `scripts/run-tests.sh` budget table (`[agents]=510`, `[shared]=300`, ~l.57-68) and the `--help` text that prints it (~l.85).
- CLAUDE.md "Lane time budgets" table (`agents` 510 / 459, `shared` 300 / 235, ~l.368-373), last re-measured at sortie 02.
- `sorties/04-honest-mcp-sign-in/flight-debrief.md` "Test Metrics"; `sorties/03-claude-plan-token/flight-debrief.md`.

## Corrective Action
*(written at completion)*

## Verification
`tests/test_run_tests_lanes.py` (pins the budget table: every canonical lane once) green; a full `--parallel 3` gate shows no OVER BUDGET for `agents`/`shared`; CLAUDE.md's table matches the script.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
