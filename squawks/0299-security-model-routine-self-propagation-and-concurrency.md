# Squawk 0299: State routine self-propagation and the missing concurrency bound in SECURITY-MODEL

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-30
**Completed**: —

## Report
SECURITY-MODEL.md's Routines caps paragraph says a worst case is bounded by the 50 active routines and the one-minute floor. It omits two facts the 2026-10-30 maintenance cycle traced: a routine run is an ordinary turn with a fresh 5-write budget and the routine tools, so routines an agent writes can create further routines up to the cap; and there is no per-agent or global bound on concurrent runs (only one run per routine), so 50 routines due together run as 50 concurrent turns of up to 900 s each. With approval off by default for new agents, the residual-risk text should say so. Whether to add a minimum interval or a run cap is an operator decision recorded in the maintenance report, not part of this squawk. From maintenance report 2026-10-30, finding #18.

## Evidence
- `SECURITY-MODEL.md:619` (caps paragraph, "There is deliberately no runs-a-day cap").
- `the_one/routines/limits.py:25` `AGENT_ROUTINE_WRITES_PER_TURN = 5`; the turn context starts each run at zero writes.
- `the_one/routines/runner.py` `RunRegistry.try_spawn`: keyed by routine id only; no semaphore in `runner.py` or `scheduler.py`.

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

The SECURITY-MODEL.md Routines section states both facts and the resulting worst case, and still cites DD3 for the deliberate absence of a runs-a-day cap.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
