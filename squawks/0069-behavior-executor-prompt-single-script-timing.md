# Squawk 0069: Executor prompt: measure "within N s of an API call" with the trigger and the first poll in one process; capture HTTP status

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-16
**Completed**: 2026-09-17

## Report

Behavior test `kb-folder-watch-round-trip` Step 4 went INCONCLUSIVE on its
first attempt because the Executor issued the settings PUT and started its
1 s poll loop as separate tool calls, leaving ~9 s with no sample inside the
5 s window; the rerun bundled both in one shell script (first sample 4 ms
after the response) and the rule was written into that spec's Row
conventions. The Validator also noted that early steps' evidence files
carried response bodies without a captured HTTP status line. Both rules
belong in the project's Executor prompt
(`.flightops/agent-crews/behavior-tests-execution.md`) so every spec
inherits them rather than re-learning them.

## Evidence

- `.flightops/agent-crews/behavior-tests-execution.md:183` — `### Executor: Initial` (no timing-measurement or status-capture guidance)
- `tests/behavior/kb-folder-watch-round-trip.md`, Row conventions, "Measurement conventions (adopted after the first run)"
- `tests/behavior/kb-folder-watch-round-trip/runs/2026-09-16-21-49-20.md`, Checkpoint 4 and the Validator closing

## Corrective Action

Added two rules to the **Executor: Initial** prompt in
`.flightops/agent-crews/behavior-tests-execution.md`, so every future
behavior-test spec inherits them rather than re-learning them:

- A new **MEASURING A TIME BOUND** block, inserted between the existing
  APPARATUS DISCOVERY and EVIDENCE blocks: for any Expected Result of
  the form "within N seconds of <a specific action>", the triggering
  action and the first poll must be issued from a single shell
  invocation (one script that performs the action, records the response
  time, and immediately starts sampling) — issuing them as separate
  tool calls can leave an unsampled gap that straddles the bound and
  makes the clause unjudgeable (INCONCLUSIVE, not a real verdict).
  Also directs recording the wall-clock timestamp of the triggering
  action and of every poll, since the Validator judges the bound from
  those.
- A sentence appended to the existing **EVIDENCE** block: every HTTP
  call captures its status code into the evidence alongside the body
  (`curl -w` for the status line), not the body alone.

Wording matches what actually went wrong per the two cited artifacts:
`tests/behavior/kb-folder-watch-round-trip.md`'s Row-conventions
"Measurement conventions (adopted after the first run)" note, and
Checkpoint 4 + the Validator closing in
`tests/behavior/kb-folder-watch-round-trip/runs/2026-09-16-21-49-20.md`.

Only `.flightops/agent-crews/behavior-tests-execution.md` was touched
(plus this squawk artifact). The Validator prompt, the Executor prompt's
LIFECYCLE/CREDENTIAL & SAFETY/PER-STEP REPORT FORMAT/APPARATUS
DISCOVERY/YOU ARE NOT THE JUDGE blocks, and all signal text are
unchanged.

## Verification

Structural checks against
`.flightops/agent-crews/behavior-tests-execution.md`:

- `## Crew`, `## Interaction Protocol`, and `## Prompts` headers all
  still present (lines 37, 104, 181).
- Fenced code block count is even (18 total ``` markers) — no block
  left unbalanced by the edit.
- Executor prompt signal text unchanged: `[READY]`, `[STEP:N:done]`,
  `[STEP:N:exception]`, `[BLOCKED:no-apparatus-<observable>]`,
  `[BLOCKED:no-dev-instance]` all present verbatim, same as before the
  edit.
- PER-STEP REPORT FORMAT JSON block (step_number/actions_taken/
  raw_state/evidence_paths/executor_notes) byte-identical to before —
  confirmed via `git diff`, which shows only two additive hunks (the new
  MEASURING A TIME BOUND block and one appended EVIDENCE sentence), no
  changes above or below that region.
- Validator prompt (Interaction Protocol section, "### Validator:
  Initial" prompt, and the parallel-validators section) untouched —
  confirmed via `git diff` showing no changes outside the Executor:
  Initial prompt's APPARATUS DISCOVERY/EVIDENCE region.

## Sign-Off

**Reviewer**: batch Reviewer agent (Haiku tier — the diff is documentation, crew prompts and a test comment; no security-sensitive surface, per `.flightops/agent-crews/leg-execution.md`)
**Verdict**: confirmed
**Commit**: (recorded in the follow-up commit on `squawk/turnaround-2026-09-17`)

## Disposition

*(only for deferred or escalated squawks)*
