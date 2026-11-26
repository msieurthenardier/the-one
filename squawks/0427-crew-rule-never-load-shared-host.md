# Squawk 0427: Crew prompts do not forbid loading the shared host on purpose

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-25
**Completed**: 2026-11-25

## Report

In Mission 37 Flight 1 Leg 2, a Developer ran a 24-process CPU-burner stress test (load above 40) to provoke timing failures under xdist. Its guidance did not ask for that. The host is shared with other projects' sessions and tests, so deliberate load can skew their runs and this project's own timing readings. The leg-execution crew prompts cover background tasks, `pgrep` loops and scratch logs (squawk 0410), but not deliberate load. Found by the Mission 37 Flight 1 debrief.

## Evidence
- `missions/37-maintenance/flights/01-unit-tier-runtime-iii/flight-log.md`, Leg 2 entry: "a 24-CPU-burner stress (load above 40)".
- `.flightops/agent-crews/leg-execution.md`: the "Waiting on a long run" paragraphs (Implement, about line 188; Fix Review Issues, about line 303) have no load rule.

## Corrective Action
Added a short load rule, citing squawk 0427, to three prompts in `.flightops/agent-crews/leg-execution.md`: Developer: Implement and Developer: Fix Review Issues (after the "Waiting on a long run" paragraph) and Reviewer: Review (after squawk 0410's scratchpad line). The rule says never to add CPU, memory or I/O load to the host on purpose (no stress tools, CPU burners or parallel load generators) because the host is shared, to reproduce timing failures by deterministic means (a shorter window or delay in a scratch copy, a route stub, a slow fake), and to report a seemingly necessary load test instead of running it. The Reviewer wording is shorter: it carries the prohibition and the report-instead rule only.

## Verification
Wording approved by the operator, 2026-11-25 (as drafted, all three passages).

Intended behavior: the Implement and Fix Review Issues prompts say never to add CPU, memory or I/O load to the host on purpose, for example stress tools or parallel burners. They say to reproduce load-sensitive failures by other means, such as shortening windows in a scratch copy, and to report when a load test seems necessary. This is an operator-owned methodology file, so the operator approves the wording.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet), batch review of squawks 0422 and 0424-0427; wording approved by the operator
**Verdict**: confirmed
**Commit**: `squawk: turnaround 2026-11-25-2` on squawk/turnaround-2026-11-25-2
