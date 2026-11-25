# Squawk 0427: Crew prompts do not forbid loading the shared host on purpose

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-25
**Completed**: —

## Report

In Mission 37 Flight 1 Leg 2, a Developer ran a 24-process CPU-burner stress test (load above 40) to provoke timing failures under xdist. Its guidance did not ask for that. The host is shared with other projects' sessions and tests, so deliberate load can skew their runs and this project's own timing readings. The leg-execution crew prompts cover background tasks, `pgrep` loops and scratch logs (squawk 0410), but not deliberate load. Found by the Mission 37 Flight 1 debrief.

## Evidence
- `missions/37-maintenance/flights/01-unit-tier-runtime-iii/flight-log.md`, Leg 2 entry: "a 24-CPU-burner stress (load above 40)".
- `.flightops/agent-crews/leg-execution.md`: the "Waiting on a long run" paragraphs (Implement, about line 188; Fix Review Issues, about line 303) have no load rule.

## Corrective Action
*(written at completion)*

## Verification
The Implement and Fix Review Issues prompts say never to add CPU, memory or I/O load to the host on purpose, for example stress tools or parallel burners. They say to reproduce load-sensitive failures by other means, such as shortening windows in a scratch copy, and to report when a load test seems necessary. This is an operator-owned methodology file, so the operator approves the wording.

## Sign-Off
*(written at completion)*
