# Squawk 0160: leg-execution crew Implement prompt does not forbid pkill by pattern

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-09
**Completed**: 2026-10-09

## Report
Developers ran `pkill -f` against their own test runs twice this cycle: once in the 2026-10-08 squawk turnaround, and once in Mission 26 F01 leg 3. Both times the spawn prompt forbade it. The rule is not in the project's crew file, so it depends on the Flight Director restating it in every spawn prompt. A pattern kill can hit the operator's own processes, such as a `make up` server or another session's tests.

## Evidence
- `.flightops/agent-crews/leg-execution.md` "Developer: Implement" prompt: no process-hygiene rule (no mention of `pkill`, `killall` or kill-by-pattern).
- Flight log Flight Director Notes, Leg 3: "`pkill -f` once against its own hung run".
- Fix: add one line to the Implement and Fix Review Issues prompts. Kill only recorded PIDs or PGIDs (or the `.pgids` files from `run-tests.sh --parallel`), never by name or pattern.

## Corrective Action
Added a process-hygiene rule to the "Developer: Implement" and "Developer: Fix Review Issues" prompts in `.flightops/agent-crews/leg-execution.md`: kill only recorded PIDs/PGIDs (or the `.pgids` files from `run-tests.sh --parallel`), never by name or pattern (`pkill`, `killall`, `kill $(pgrep ...)`), since a pattern can hit the operator's own processes.

## Verification
`grep -n '^## \|^### \|^```\|Process hygiene' .flightops/agent-crews/leg-execution.md` shows `## Crew`, `## Interaction Protocol` and `## Prompts` intact, the rule present in both prompts, and every prompt fence still paired (fence count even).

## Sign-Off

**Reviewer**: independent batch Reviewer (Sonnet tier: the batch touches the self-configuration credential-isolation tests and a CI install script). Confirmed the rule is in both Developer prompts, inside their fenced blocks, and the crew file keeps its three required sections.
**Verdict**: confirmed (`[HANDOFF:confirmed]`)
**Commit**: `squawk: turnaround 2026-10-09` on branch `squawk/turnaround-2026-10-09`
