# Squawk 0204: Chat-list delete focus test flakes under load

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-13
**Completed**: 2026-10-13

## Report
`tests/browser/test_flow_chat_list.py::test_row_delete_arms_confirms_and_focuses_the_neighbour` failed once in a full `--parallel 3` browser run, the Mission 29 Flight 2 debrief run. The failure was "Locator expected to be focused … unexpected value 'inactive'". On the same tree, the `chats` lane then passed on its own (181/181). The full run had `chats` at 348/360 s, close to its budget. So this looks like a timing assertion under host load, not a product defect.

It is one of a family of focus- and timing-under-load flakes: 0168 (jump-to new chat), 0187 (agent rules focus) and 0201 (OAuth popup navigation). Two different such flakes failed in two consecutive full runs.

## Evidence
- Failing run: `PARALLEL_RESULT rc=1 total=1034s lanes=9 failed=chats`. The failing test: `tests/browser/test_flow_chat_list.py::test_row_delete_arms_confirms_and_focuses_the_neighbour`.
- Re-run: the `chats` lane alone passed 181/181 in 309 s, on `bf42907`.

## Corrective Action
The failing assertion was the post-delete `expect(chat_row(c)).to_be_focused()`. Playwright's "inactive" reading comes from the element not being the page's active element as the page sees it, and under parallel headless load window focus is unreliable; the product code (list-pane `restoreFocus`) moves focus synchronously on rebuild, so no product bug. Added `_chats.wait_row_has_focus(page, session_id, timeout=10000)`, which waits via `page.wait_for_function` for `document.activeElement` to be the `chat-row` with that `data-id`. That asserts element identity independent of window focus, with a bounded timeout (reusable by 0166/0187). Used it in the test in place of `to_be_focused` for the post-delete neighbour check. The pre-delete Tab-to-action `to_be_focused` checks were left as is (focus there is set by the test's own keyboard input).

## Verification
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python TEST_TIMEOUT=900 bash scripts/run-tests.sh tests/browser/test_flow_chat_list.py -m browser -x --timeout 60` x5: 10 passed each time (~24 s).
- Same command under 12 background busy loops (own PIDs killed): 10 passed in 36 s.
- `ruff check` and `ruff format --check` on changed files: clean.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet; the batch includes the OAuth sign-in path, 0202), batch review of the 2026-10-13 squawk turnaround
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-10-13` commit on `squawk/turnaround-2026-10-13`. The final gate passed: unit 6287 passed and 14 skipped (the expected count under `THE_ONE_TEST_NETNS=1`); `PARALLEL_RESULT rc=0 total=998s lanes=9 failed=-`, every lane within budget. Flake fix: the original failure was not reproduced, so there is no fails-without-fix demonstration.

## Disposition
**Deferred**: a load-only timing flake, outside Mission 29's scope. Revisit together with 0201 at the next squawk turnaround, if it recurs in a gate, or when the browser lanes are re-budgeted (Flight 2 debrief, Recommendation 2).
