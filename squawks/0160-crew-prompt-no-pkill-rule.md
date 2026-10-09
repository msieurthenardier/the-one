# Squawk 0160: leg-execution crew Implement prompt does not forbid pkill by pattern

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-09
**Completed**: —

## Report
Developers ran `pkill -f` against their own test runs twice this cycle: once in the 2026-10-08 squawk turnaround, and once in Mission 26 F01 leg 3. Both times the spawn prompt forbade it. The rule is not in the project's crew file, so it depends on the Flight Director restating it in every spawn prompt. A pattern kill can hit the operator's own processes, such as a `make up` server or another session's tests.

## Evidence
- `.flightops/agent-crews/leg-execution.md` "Developer: Implement" prompt: no process-hygiene rule (no mention of `pkill`, `killall` or kill-by-pattern).
- Flight log Flight Director Notes, Leg 3: "`pkill -f` once against its own hung run".
- Fix: add one line to the Implement and Fix Review Issues prompts. Kill only recorded PIDs or PGIDs (or the `.pgids` files from `run-tests.sh --parallel`), never by name or pattern.

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
