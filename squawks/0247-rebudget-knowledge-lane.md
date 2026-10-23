# Squawk 0247: Re-budget the knowledge browser lane

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-23
**Completed**: —

## Report
The `knowledge` lane ran 279 s against its 300 s budget in the M31 F3 debrief gate (`--parallel 3`). That is 93% of budget and +22% over leg 09's 229 s, from the 16 HAT tests (43 → 59). It is past the 15% re-budget threshold (squawk 0217's rule). Re-budget it to 360 s (measured +25%, rounded up to 30 s) in the script's table, and update CLAUDE.md's lane table (budget 360, measured 279). Found in the M31 F3 debrief.

## Evidence
- `scripts/run-tests.sh` ~:66: `[knowledge]=300`.
- CLAUDE.md "Lane time budgets" table: `knowledge` 300 / 229.
- The debrief gate log: `knowledge` 279 s, 59 passed.

## Corrective Action

## Verification

## Sign-Off
