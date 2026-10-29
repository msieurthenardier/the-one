# Squawk 0285: The flight debrief reuses the flight's last full gate when no code changed since

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-29
**Completed**: 2026-10-29

## Report
The `/mission-control:flight-debrief` skill tells the Flight Director to
have the debrief Developer run the full test suite once: the unit suite
plus the `--parallel 3` browser suite, about 45 minutes on this host.

At Mission 33 Flight 2 that run only re-measured code the flight's own
quiet-host gate had already measured:
- the gate ran on `ee4e8c5b`;
- the only later commit touched artifacts, CLAUDE.md, a behavior run log
  and the `run-tests.sh` budget table.

The operator stopped the run and adopted a rule: the debrief reuses the last
full gate when nothing it would measure has changed. That rule should live
in the project's debrief crew file, so every debrief applies it.

## Evidence
- `missions/33-routines/flights/02-agent-routines/flight-debrief.md`:
  Methodology Observation 1, Recommendation 1, and the deviations table.
- The debrief's unit half matched the gate exactly (8237 passed, 15 skipped).
- `.flightops/agent-crews/flight-debrief.md` says nothing about test metrics
  or reusing a gate.

## Corrective Action
Edited `.flightops/agent-crews/flight-debrief.md`: added a Developer Interview
step (the Flight Director decides the metrics source), a "Test metrics: reuse the
flight's gate" subsection stating the reuse / run-fresh / name-the-source rule
(noting it narrows the skill's "run the full suite once" instruction), and a
**Test Metrics** group in the Developer debrief prompt.

## Verification
`.flightops/agent-crews/flight-debrief.md` states the rule where the Flight
Director briefs the debrief Developer:
- **Reuse** the flight's last full gate (a unit run plus a quiet-host
  `--parallel 3` browser run, both on the same commit) when
  `git diff <gate commit>..HEAD` touches nothing under `the_one/`, `tests/`
  or `scripts/` except the lane-budget table in `scripts/run-tests.sh`.
  Record the gate's commit, its `PARALLEL_RESULT` line, the per-lane times
  and the unit counts, and compare those against prior debriefs.
- **Run fresh** otherwise, including when the gate ran on a loaded host or
  the branch was rebased onto a moved `main`.
- **Either way,** say which run each number came from.

Verified: the file's `## Crew`, `## Interaction Protocol`, `## Prompts` sections
and both prompts' fenced blocks are intact, and the added text states the rule
as above.

## Sign-Off
**Reviewer**: Reviewer agent (Haiku), scoped to the diff, `[HANDOFF:confirmed]`.
The rule, its placement, the crew file's structure (`## Crew`,
`## Interaction Protocol`, `## Prompts`, balanced fences) and confinement
were all verified. Its one low note, that the metrics decision came after the
spawn step, was applied by the FD: the Developer Interview steps now decide
the metrics source first, then spawn with that brief.
**Verdict**: confirmed
**Commit**: (this commit, on `squawk/0285-debrief-gate-reuse`)
