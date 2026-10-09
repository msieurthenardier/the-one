# Squawk 0165: Windows shell-session output carries raw ConPTY control codes

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-09
**Completed**: —

## Report
Reported while checking 0.10.4 and 0.10.5 for #246. In the packaged Windows app, `shell_session_send` returns the unrendered ConPTY stream: the command output is there, but mixed with VT control sequences such as `ESC[4;16H` (cursor position). The agent has to read past them, and they take up the tool's output budget.

## Evidence
- `the_one/platform/pty_windows.py:WindowsPtySession._read_until_idle_blocking` returns the raw bytes from `proc.fileobj.recv`. `the_one/tools/sessions.py:ShellSessionSendTool.execute` passes them through `_truncate_output` unchanged, and no stage strips control sequences (`git grep` finds no ANSI/VT handling under `the_one/`).
- ConPTY always emits VT: it repaints the screen with cursor-positioning (CSI `…H`), erase (`…K`/`…J`) and mode (`?25l`/`?25h`) sequences, and can send a title OSC (`ESC]0;…BEL`).

## Scope note
The expected fix strips CSI/OSC sequences from session output, and the verification is a unit test over captured ConPTY output plus a Windows-worker run (`fly -t the-one execute -c ci/tasks/windows-tests.yml -i repo=.`). ConPTY sometimes moves the cursor where a newline would be. If stripping alone glues lines together or drops text, and a correct result needs screen rendering (a terminal emulator, a new dependency), that is a design decision: escalate to a sortie rather than grow this squawk. Check also whether the Unix backend's output has the same problem before choosing where the stripping lives (the backend or the tool).

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
