# Squawk 0181: The crew Review prompt doesn't say browser files need `-m browser`

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-11
**Completed**: —

## Report
In Mission 28 F2 the flight-end Reviewer ran `scripts/run-tests.sh tests/browser/<file>` without `-m browser`. All 16 tests were deselected by the `addopts` marker filter, so the browser coverage went unverified in that pass and a re-review was needed.

## Evidence
`.flightops/agent-crews/leg-execution.md` (Reviewer: Review prompt, and the Implement prompt's test line). The fix: one sentence. A bare browser file path needs `-m browser` passed through, and on the WSL host also `THE_ONE_TEST_NETNS=1`.

Logged from the Mission 28 flight debriefs.

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
