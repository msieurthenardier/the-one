# Squawk 0181: The crew Review prompt doesn't say browser files need `-m browser`

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-11
**Completed**: 2026-10-11

## Report
In Mission 28 F2 the flight-end Reviewer ran `scripts/run-tests.sh tests/browser/<file>` without `-m browser`. All 16 tests were deselected by the `addopts` marker filter, so the browser coverage went unverified in that pass and a re-review was needed.

## Evidence
`.flightops/agent-crews/leg-execution.md` (Reviewer: Review prompt, and the Implement prompt's test line). The fix: one sentence. A bare browser file path needs `-m browser` passed through, and on the WSL host also `THE_ONE_TEST_NETNS=1`.

Logged from the Mission 28 flight debriefs.

## Corrective Action
leg-execution.md: Implement and Reviewer Review prompts now state a bare browser file path needs -m browser passed to scripts/run-tests.sh, and every browser run/gate on this WSL host needs THE_ONE_TEST_NETNS=1; Implement prompt gained the gate-flake triage sentence. CLAUDE.md Testing section make gate sentence now states the THE_ONE_TEST_NETNS=1 prerequisite.

## Verification
grep shows the crew file keeps ## Crew, ## Interaction Protocol, ## Prompts with 12 fence lines (6 balanced blocks) unchanged in count; tests/test_run_tests_lanes.py and tests/test_ui_guards.py pass (34).

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet), batch review of the 2026-10-11 squawk turnaround
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-10-11` commit on `squawk/turnaround-2026-10-11`. The final gate passed: unit 5946 passed and 14 skipped; `PARALLEL_RESULT rc=0 total=977s lanes=8 failed=-`, every lane within budget.
