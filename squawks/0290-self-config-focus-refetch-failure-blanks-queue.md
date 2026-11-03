# Squawk 0290: A failed focus refetch blanks the Self-configuration waiting list

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-30
**Completed**: 2026-11-03
**Related**: 0289: same self-configuration tab refetch path; complete together ([maintenance 2026-10-30](../maintenance/2026-10-30.md)).

## Report
A refetch triggered only by window focus or visibility (M33 F4 fix pass 3) that fails (offline, a transient error) takes the `renderRoutineQueue([])` / `setUnavailable` branch, so the operator's waiting list disappears on a mere window return. A passive refetch should keep the shown list and only surface the error.

## Evidence
- `the_one/interfaces/web/static/js/areas/studio/self-config-routines.js` (the queue's error branch).
- Mission 33 Flight 4 flight log, "Review of fix pass 3 and F-H1-1".

## Corrective Action
`self-config-routines.js`: `refetchRoutines(passive)`; a passive failure keeps the shown waiting list and shows "Unable to refresh waiting changes." on the existing error line (cleared by the next successful refetch). `self-configuration-tab.js` `activate` passes `true`. The Agent prompt queue's `refetchRevisions` has the same blanking on failure; not changed (squawk names routines only).
After review: `showError(text, passive)` now resets `passiveError` for any non-passive text or clear, so a later passive success no longer wipes an unrelated action error; new test `test_a_later_passive_success_keeps_an_action_error` (falsified by editing the reset out: failed; restored: passed).

## Verification
New `test_a_failed_return_refetch_keeps_the_waiting_list` in `tests/browser/test_flow_agent_routines_self_config.py`. Falsified (passive branch disabled by editing: failed; restored: passed). Lanes: see report.

A browser test fails a focus refetch and the previously shown waiting items stay visible with an error line.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches the shell-write hook, `App.safeUrl`, the encryption status count and the credential docs), batch review of the 2026-11-02-2 squawk turnaround, scoped to the diff. Its one blocking finding (0135's Dockerfile `uv venv` line) and the non-blocking items were fixed in a fix pass, which a Haiku Reviewer re-checked: `[HANDOFF:confirmed]`. An Accessibility Reviewer (Sonnet) confirmed the UI changes (0239, 0289, 0290, 0291, 0254). The final gate on the batch tree: `THE_ONE_TEST_NETNS=1 make test-unit` 8738 passed, 15 skipped (219 s, start load 0.48); browser `--parallel 3` `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript` (start load 0.72). The one failure is new squawk 0315, which passed 3 of 3 isolated runs. A fix pass after review resets `passiveError` on any non-passive error, so a later passive success cannot clear an action error. A new browser test covers it and is falsified.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02-2` commit on `squawk/turnaround-2026-11-02-2`.
