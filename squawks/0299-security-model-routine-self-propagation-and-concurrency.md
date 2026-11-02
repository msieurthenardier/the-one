# Squawk 0299: State routine self-propagation and the missing concurrency bound in SECURITY-MODEL

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-30
**Completed**: 2026-11-01

## Report
SECURITY-MODEL.md's Routines caps paragraph says a worst case is bounded by the 50 active routines and the one-minute floor. It omits two facts the 2026-10-30 maintenance cycle traced: a routine run is an ordinary turn with a fresh 5-write budget and the routine tools, so routines an agent writes can create further routines up to the cap; and there is no per-agent or global bound on concurrent runs (only one run per routine), so 50 routines due together run as 50 concurrent turns of up to 900 s each. With approval off by default for new agents, the residual-risk text should say so. Whether to add a minimum interval or a run cap is an operator decision recorded in the maintenance report, not part of this squawk. From maintenance report 2026-10-30, finding #18.

## Evidence
- `SECURITY-MODEL.md:619` (caps paragraph, "There is deliberately no runs-a-day cap").
- `the_one/routines/limits.py:25` `AGENT_ROUTINE_WRITES_PER_TURN = 5`; the turn context starts each run at zero writes.
- `the_one/routines/runner.py` `RunRegistry.try_spawn`: keyed by routine id only; no semaphore in `runner.py` or `scheduler.py`.

## Corrective Action
Added two sentences to the Routines caps paragraph of SECURITY-MODEL.md (DD3 citation kept): a run is an ordinary turn with a fresh 5-change budget and the routine tools, so agent-written routines can create more up to the active cap, unheld when approval is off (the default for a new agent); and no bound on concurrent runs beyond one per routine, so 50 due together run as 50 concurrent turns of up to 900 s. Confirmed against `routines/limits.py` (`AGENT_ROUTINE_WRITES_PER_TURN = 5`, `ROUTINES_ACTIVE_MAX = 50`), `interfaces/web/app.py` (each turn builds a new `TurnContext`; `routine_writes` defaults to 0 in `agent/_context.py`), `agent/factory.py` (routine tools registered when the item is on), `routines/runner.py` (`RunRegistry.try_spawn` keyed by routine id, no semaphore; timeout default 900 s) and `routines/scheduler.py` (no limit). No correction to the squawk's account.

## Verification
*(written at completion)*

The SECURITY-MODEL.md Routines section states both facts and the resulting worst case, and still cites DD3 for the deliberate absence of a runs-a-day cap. Checked by reading the edited paragraph; no test pins this text (see report).

The SECURITY-MODEL.md Routines section states both facts and the resulting worst case, and still cites DD3 for the deliberate absence of a runs-a-day cap.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet; the batch states security-model residual risks, 0298 and 0299), batch review of the 2026-11-01 squawk turnaround, scoped to the diff, `[HANDOFF:confirmed]`. Every fact matched the squawk; no correction.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-01` commit on `squawk/turnaround-2026-11-01`. Unit tier under `THE_ONE_TEST_NETNS=1`: 8560 passed, 23 skipped, 3 failed (the known `tests/test_desktop_host.py` baseline, unchanged from main).
