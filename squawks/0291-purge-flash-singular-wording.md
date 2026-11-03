# Squawk 0291: Purge flash reads "Deleted 1 chat and their history."

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-30
**Completed**: 2026-11-03

## Report
After Purge now on an agent with one chat the flash reads "Deleted 1 chat and their history." (M33 F4 fix pass 3). The pronoun should follow the count ("its history" for one chat).

## Evidence
- `the_one/interfaces/web/static/js/areas/studio/agent-editor-controller.js` (the purge success flash).
- `tests/test_store_static.py` pins the flash anchor.

## Corrective Action
`agent-editor-controller.js` now builds the flash as "Deleted 1 chat and its history." for one chat and "Deleted N chats and their history." otherwise. The pin in `tests/browser/test_flow_studio_purge_now_button.py` was updated (`tests/test_store_static.py` did not contain the string).

## Verification
`agents` lane run (see report). The updated browser test pins the singular text; no new test (the existing one was the pin, so falsification is the old text failing it: not separately run).

The flash reads "Deleted 1 chat and its history." for one chat and "Deleted N chats and their history." otherwise; the pin is updated.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches the shell-write hook, `App.safeUrl`, the encryption status count and the credential docs), batch review of the 2026-11-02-2 squawk turnaround, scoped to the diff. Its one blocking finding (0135's Dockerfile `uv venv` line) and the non-blocking items were fixed in a fix pass, which a Haiku Reviewer re-checked: `[HANDOFF:confirmed]`. An Accessibility Reviewer (Sonnet) confirmed the UI changes (0239, 0289, 0290, 0291, 0254). The final gate on the batch tree: `THE_ONE_TEST_NETNS=1 make test-unit` 8738 passed, 15 skipped (219 s, start load 0.48); browser `--parallel 3` `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript` (start load 0.72). The one failure is new squawk 0315, which passed 3 of 3 isolated runs.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02-2` commit on `squawk/turnaround-2026-11-02-2`.
