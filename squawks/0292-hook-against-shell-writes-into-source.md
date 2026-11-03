# Squawk 0292: A PreToolUse hook should refuse shell writes into source

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-30
**Completed**: —

## Report
Squawk 0286 put "edit source and test files only through the edit tool" into both Developer prompts, yet three of seven Developers in Mission 33 Flight 4 wrote into source or tests through the shell (`sed -i`, heredoc appends). Each self-reported and a reviewer verified the diff, but a written rule did not hold. The operator chose a mechanical guard at the Flight 4 debrief.

## Evidence
- `missions/33-routines/flights/04-hat-and-alignment/flight-debrief.md`, Methodology Observation 2 and Recommendation 2.
- The flight log's fix pass 1, leg 05 and fix pass 3 entries.
- No project `.claude/settings.json` exists yet (only `settings.local.json`).

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

A project `.claude/settings.json` `PreToolUse` hook on `Bash` (a script under `.claude/hooks/`) refuses, with a one-line message naming the Edit/Write tools, a command whose `sed -i`/`perl -i`/`tee`/output redirect/heredoc write/`python` file write/`cp`/`mv`/`install` targets `the_one/`, `tests/`, `docs/`, `scripts/`, `missions/` or `evals/`, while redirects to `/dev/null` and the scratchpad, `git`, `make`, `pytest`, `ruff` and `gh` pass. A unit test feeds the script sample commands (blocked and allowed) and checks the exit codes.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:

## Disposition
- **2026-11-02 triage (Flight Director, Mission 34 squawk turnaround):** **operator approved adding the project PreToolUse hook** (`.claude/settings.json`). It refuses `sed -i`, heredoc and redirect writes into `the_one/` and `tests/` and will limit autonomous crew's shell use. Write the allow/deny list down in the squawk at completion. Burn-down next turnaround.
