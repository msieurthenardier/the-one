# Squawk 0289: Self-configuration refetches both queues twice on a window return

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-30
**Completed**: 2026-11-03
**Related**: 0290: same self-configuration tab refetch path; complete together ([maintenance 2026-10-30](../maintenance/2026-10-30.md)).

## Report
Returning to the window often fires both `visibilitychange` and `focus`; the Self-configuration tab (M33 F4 fix pass 3, F-E3-1) refetches both approval queues on each, so a return makes two requests per queue. A sequence guard keeps the result correct; only the duplicate fetch is wasted.

## Evidence
- `the_one/interfaces/web/static/js/areas/studio/self-configuration-tab.js` ~:178-179 (the two listeners).
- Mission 33 Flight 4 flight log, "Review of fix pass 3 and F-H1-1".

## Corrective Action
`self-configuration-tab.js`: `onShown` drops a call within 500 ms of the previous one, so a return that fires both `visibilitychange` and `focus` runs `activate` once (each event alone still refetches).

## Verification
New `test_a_window_return_refetches_each_queue_once` in `tests/browser/test_flow_agent_routines_self_config.py` dispatches both events and counts one request per queue. Falsified (guard removed by editing: failed; restored: passed). Lanes: see report.

A test counts requests on a simulated return that fires both events and sees one refetch per queue.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches the shell-write hook, `App.safeUrl`, the encryption status count and the credential docs), batch review of the 2026-11-02-2 squawk turnaround, scoped to the diff. Its one blocking finding (0135's Dockerfile `uv venv` line) and the non-blocking items were fixed in a fix pass, which a Haiku Reviewer re-checked: `[HANDOFF:confirmed]`. An Accessibility Reviewer (Sonnet) confirmed the UI changes (0239, 0289, 0290, 0291, 0254). The final gate on the batch tree: `THE_ONE_TEST_NETNS=1 make test-unit` 8738 passed, 15 skipped (219 s, start load 0.48); browser `--parallel 3` `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript` (start load 0.72). The one failure is new squawk 0315, which passed 3 of 3 isolated runs.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02-2` commit on `squawk/turnaround-2026-11-02-2`.
