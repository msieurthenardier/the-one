# Squawk 0234: the unit tier's runtime crept from 195 s to 300 s with no profile

**Status**: escalated
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-22
**Completed**: —

## Report
`make test-unit` took 195 s at sortie 03, 281 s at the Mission 31 Flight 1 debrief, and 300 s at the Flight 2 debrief (6717 passed, 14 skipped under netns). It runs before every `make gate`. A `--durations` profile has been owed since sortie 04 and has not been run. Recommended in the Mission 31 Flight 2 debrief.

## Evidence
- `missions/31-control-library-everywhere/flights/01-library-completion-and-pilot/flight-debrief.md` (the 281 s figure and the owed profile).
- `missions/31-control-library-everywhere/flights/02-agents-on-the-library/flight-debrief.md` (300 s).

## Corrective Action
*(written at completion)*

## Verification
- `make test-unit` is profiled with `--durations=30`, and the slowest tests and their causes are recorded here. Any obvious fix that fits a squawk (a fixture that rebuilds a template, a real sleep) is made, and the before and after times are recorded. A larger cause is escalated.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:

## Disposition
**Escalated**: fails *verifiable by one test*/*bounded*: the profile this squawk asked for was taken on 2026-10-30 ([maintenance 2026-10-30](../maintenance/2026-10-30.md), finding #1: 430 s, about 82 s from test count and about 182 s from diffuse per-test cost: per-test API app builds, evals harness, AST re-walks, real timeouts, real subprocesses). The fix spans many test modules →
[Mission 34 Flight 1: Test-suite runtime II](../missions/34-maintenance/flights/01-test-suite-runtime-ii/flight.md), leg `unit-per-test-cost`

**Result**: see the [Mission 34 Flight 1 flight log, leg 1 `unit-per-test-cost`](../missions/34-maintenance/flights/01-test-suite-runtime-ii/flight-log.md): unit tier 437.46 s to 229.33 s (solo).
