# Squawk 0187: agent-rules failed-toggle focus test is flaky under host load

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-11
**Completed**: 2026-10-13

## Report
`tests/browser/test_flow_agent_rules.py::test_failed_toggle_and_failed_save_restore_focus`
failed once in the sortie 02 leg 1 `--parallel 3` gate (agents lane, 474/510 s wall):
after a failed toggle it found no focused element. It passed in isolation and in a
re-run of its file. Not related to sortie 02's change (the Rules and notes tab is untouched).

## Evidence
- `tests/browser/test_flow_agent_rules.py:232` (`def test_failed_toggle_and_failed_save_restore_focus`).
- `sorties/02-model-providers-in-library/flight-log.md`, leg `library-and-providers`, Part B gate.

## Deferral
Found mid-flight in sortie 02, out of scope. Revisit trigger: the next squawk turnaround,
or the next time the Rules and notes tab or `App.focusAfter` is touched, whichever comes first.

## Corrective Action
Root cause was a test race, not a product bug. In `rules-notes-tab.js`, `makeMutate`'s failure path shows the inline error first, then re-reads the list (`cfg.load()`), and only then calls `restoreOrigin` (focus). The test read `document.activeElement` once as soon as `rules-error` was visible, so under load it could run in the window between the error rendering and the focus restore (the list re-render had dropped focus to body). Focus restore is unconditional, so no product change.

Fix (test-only): added generic `wait_active_testid(page, testids, timeout=10000)` to `tests/browser/_lists.py` (bounded `page.wait_for_function` on `document.activeElement` identity; no sleeps). `test_failed_toggle_and_failed_save_restore_focus` now uses it for both the toggle and the save-button focus checks (the latter also drops Playwright's window-focus-dependent `to_be_focused`, same as sibling squawk 0204).

## Verification
- `ruff check` / `ruff format --check` on both changed files: clean.
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python TEST_TIMEOUT=900 bash scripts/run-tests.sh tests/browser/test_flow_agent_rules.py -m browser -x --timeout 60` x5: 13 passed each time (~29 s).
- Same under 12 background busy-loop processes (recorded PIDs, killed exactly those): 13 passed (45 s).
- The original flake could not be reproduced on demand, so no fails-without-fix demonstration.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet; the batch includes the OAuth sign-in path, 0202), batch review of the 2026-10-13 squawk turnaround
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-10-13` commit on `squawk/turnaround-2026-10-13`. The final gate passed: unit 6287 passed and 14 skipped (the expected count under `THE_ONE_TEST_NETNS=1`); `PARALLEL_RESULT rc=0 total=998s lanes=9 failed=-`, every lane within budget. Flake fix: the original failure was not reproduced, so there is no fails-without-fix demonstration.
