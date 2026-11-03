# Squawk 0264: a tray Quit between the tray start and the window publish leaves the window shown with no tray

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-26
**Completed**: 2026-11-03

## Report
In `DesktopSession._boot`, the tray icon starts at step 5 (`run_detached`), and the main window is published to `session_state` at step 6 (`state.publish_window`). A Quit chosen from the tray in the short gap between those two steps runs `_on_quit`. That sets `really_quit` and stops the icon, but it does not set `quit_requested`. `publish_window` then returns `False`, so the boot shows the window anyway. The user ends up with a visible window and no tray icon.

This happens on non-darwin platforms; macOS has no tray. The gap is a few lines long, so it is rare. It existed before Mission 32 Flight 4.

## Evidence
- Found by the leg 5 code reviewer, while reviewing the quit-during-boot fix (commit `4caf728`), as a non-blocking finding.
- `the_one/interfaces/desktop/shell.py`: `_on_quit` (it sets `really_quit` and stops the icon); `_boot` steps 5 (the tray) and 6 (`publish_window`, whose `quit_now` reads `quit_requested`); `the_one/interfaces/desktop/session_state.py::publish_window`.

## Corrective Action
`DesktopSession._on_quit` (`shell.py`) now calls `state.begin_quit()` instead of `state.really_quit = True`, so `really_quit` and `quit_requested` are set together under the lock; `publish_window` then returns True and `_boot` runs `_on_quit` again, destroying the window. `begin_quit` was not changed and no other quit path was touched. New test `test_tray_quit_before_publish_destroys_the_window` (`tests/test_desktop_shell.py`) wraps `state.publish_window` to run a tray `_on_quit` just before it, then asserts `quit_requested` and that the main window and splash are destroyed. Falsified (yes): with `state.really_quit = True` restored by edit it failed; fix put back.

## Verification
- Result: desktop unit files 187 passed; ruff clean; full unit tier see report.
- A unit test on the Windows and Linux policies: a tray Quit before publish ends with both windows destroyed and the server drained.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches the shell-write hook, `App.safeUrl`, the encryption status count and the credential docs), batch review of the 2026-11-02-2 squawk turnaround, scoped to the diff. Its one blocking finding (0135's Dockerfile `uv venv` line) and the non-blocking items were fixed in a fix pass, which a Haiku Reviewer re-checked: `[HANDOFF:confirmed]`. An Accessibility Reviewer (Sonnet) confirmed the UI changes (0239, 0289, 0290, 0291, 0254). The final gate on the batch tree: `THE_ONE_TEST_NETNS=1 make test-unit` 8738 passed, 15 skipped (219 s, start load 0.48); browser `--parallel 3` `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript` (start load 0.72). The one failure is new squawk 0315, which passed 3 of 3 isolated runs.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02-2` commit on `squawk/turnaround-2026-11-02-2`.

## Disposition
- **Logged** by the Flight Director at Mission 32 Flight 4, leg 5. Not fixed in v0.12.0.
