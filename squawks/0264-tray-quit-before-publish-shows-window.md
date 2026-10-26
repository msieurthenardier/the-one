# Squawk 0264: a tray Quit between the tray start and the window publish leaves the window shown with no tray

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-26
**Completed**: —

## Report
In `DesktopSession._boot`, the tray icon starts at step 5 (`run_detached`), and the main window is published to `session_state` at step 6 (`state.publish_window`). A Quit chosen from the tray in the short gap between those two steps runs `_on_quit`. That sets `really_quit` and stops the icon, but it does not set `quit_requested`. `publish_window` then returns `False`, so the boot shows the window anyway. The user ends up with a visible window and no tray icon.

This happens on non-darwin platforms; macOS has no tray. The gap is a few lines long, so it is rare. It existed before Mission 32 Flight 4.

## Evidence
- Found by the leg 5 code reviewer, while reviewing the quit-during-boot fix (commit `4caf728`), as a non-blocking finding.
- `the_one/interfaces/desktop/shell.py`: `_on_quit` (it sets `really_quit` and stops the icon); `_boot` steps 5 (the tray) and 6 (`publish_window`, whose `quit_now` reads `quit_requested`); `the_one/interfaces/desktop/session_state.py::publish_window`.

## Corrective Action
*(written at completion)*. The likely fix: `_on_quit` records the quit through `state.begin_quit()` (or sets `quit_requested` under the lock), so that `publish_window` returns `quit_now`, with a unit test driving a tray Quit before publish.

## Verification
- A unit test on the Windows and Linux policies: a tray Quit before publish ends with both windows destroyed and the server drained.

## Sign-Off
*(written at completion)*

## Disposition
- **Logged** by the Flight Director at Mission 32 Flight 4, leg 5. Not fixed in v0.12.0.
