# Squawk 0204: Chat-list delete focus test flakes under load

**Status**: deferred
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-13
**Completed**: —

## Report
`tests/browser/test_flow_chat_list.py::test_row_delete_arms_confirms_and_focuses_the_neighbour` failed once in a full `--parallel 3` browser run, the Mission 29 Flight 2 debrief run. The failure was "Locator expected to be focused … unexpected value 'inactive'". On the same tree, the `chats` lane then passed on its own (181/181). The full run had `chats` at 348/360 s, close to its budget. So this looks like a timing assertion under host load, not a product defect.

It is one of a family of focus- and timing-under-load flakes: 0168 (jump-to new chat), 0187 (agent rules focus) and 0201 (OAuth popup navigation). Two different such flakes failed in two consecutive full runs.

## Evidence
- Failing run: `PARALLEL_RESULT rc=1 total=1034s lanes=9 failed=chats`. The failing test: `tests/browser/test_flow_chat_list.py::test_row_delete_arms_confirms_and_focuses_the_neighbour`.
- Re-run: the `chats` lane alone passed 181/181 in 309 s, on `bf42907`.

## Corrective Action
*(written at completion)* A likely fix is to wait for focus to settle with a bounded wait (Playwright `expect(...).to_be_focused(timeout=…)` around the post-delete focus move) rather than asserting focus once. It could share an approach with 0201.

## Verification

## Sign-Off
*(written at completion)*

## Disposition
**Deferred**: a load-only timing flake, outside Mission 29's scope. Revisit together with 0201 at the next squawk turnaround, if it recurs in a gate, or when the browser lanes are re-budgeted (Flight 2 debrief, Recommendation 2).
