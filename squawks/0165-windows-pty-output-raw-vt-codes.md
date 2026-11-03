# Squawk 0165: Windows shell-session output carries raw ConPTY control codes

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-09
**Completed**: 2026-11-03

## Report
Reported while checking 0.10.4 and 0.10.5 for #246. In the packaged Windows app, `shell_session_send` returns the unrendered ConPTY stream: the command output is there, but mixed with VT control sequences such as `ESC[4;16H` (cursor position). The agent has to read past them, and they take up the tool's output budget.

## Evidence
- `the_one/platform/pty_windows.py:WindowsPtySession._read_until_idle_blocking` returns the raw bytes from `proc.fileobj.recv`. `the_one/tools/sessions.py:ShellSessionSendTool.execute` passes them through `_truncate_output` unchanged, and no stage strips control sequences (`git grep` finds no ANSI/VT handling under `the_one/`).
- ConPTY always emits VT: it repaints the screen with cursor-positioning (CSI `…H`), erase (`…K`/`…J`) and mode (`?25l`/`?25h`) sequences, and can send a title OSC (`ESC]0;…BEL`).

## Scope note
The expected fix strips CSI/OSC sequences from session output, and the verification is a unit test over captured ConPTY output plus a Windows-worker run (`fly -t the-one execute -c ci/tasks/windows-tests.yml -i repo=.`). ConPTY sometimes moves the cursor where a newline would be. If stripping alone glues lines together or drops text, and a correct result needs screen rendering (a terminal emulator, a new dependency), that is a design decision: escalate to a sortie rather than grow this squawk. Check also whether the Unix backend's output has the same problem before choosing where the stripping lives (the backend or the tool).

## Corrective Action
Root cause: the Windows backend returned the raw ConPTY stream. Added a pure
`strip_vt_sequences(bytes)` to the platform-neutral `the_one/platform/pty.py` (importable on
Linux, no pywinpty): strips OSC (BEL or ST terminated), CSI and other ESC sequences, drops BEL,
applies backspace within a line; CR/LF and non-ASCII bytes are kept. `WindowsPtySession._send_blocking`
(`the_one/platform/pty_windows.py`) now returns the stripped bytes. Unix backend is unchanged (its
output was not part of the report); the stripping lives in the shared module so the Windows
backend only calls it. Cursor movement is dropped, not emulated: no captured real ConPTY sample was
available, so whether stripping glues words/lines in real output is only checkable on the Windows
worker (the escalation trigger for a terminal emulator).

## Verification
- `tests/test_pty_vt_strip.py` (8 tests, realistic ConPTY-style samples: `?25l`, `2J`, `H`, `4;16H`, `K`, title OSC with BEL and ST, CRLF): pass. Falsified: yes (disabled the ESC stripping by editing, 6 of 8 failed; restored and re-read).
- `ruff check` / `ruff format --check` on touched files: clean. `THE_ONE_TEST_NETNS=1 make test-unit`: 8737 passed, 15 skipped.
- Windows verification pending fly login: `fly -t the-one status` returned "please login again" ("not authorized"); the Windows worker run (`ci/tasks/windows-tests.yml`) was not made.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches the shell-write hook, `App.safeUrl`, the encryption status count and the credential docs), batch review of the 2026-11-02-2 squawk turnaround, scoped to the diff. Its one blocking finding (0135's Dockerfile `uv venv` line) and the non-blocking items were fixed in a fix pass, which a Haiku Reviewer re-checked: `[HANDOFF:confirmed]`. An Accessibility Reviewer (Sonnet) confirmed the UI changes (0239, 0289, 0290, 0291, 0254). The final gate on the batch tree: `THE_ONE_TEST_NETNS=1 make test-unit` 8738 passed, 15 skipped (219 s, start load 0.48); browser `--parallel 3` `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript` (start load 0.72). The one failure is new squawk 0315, which passed 3 of 3 isolated runs. Windows: `windows-tests` build 795947 ran `tests/test_pty_windows.py` through the stripped `_send_blocking` path on real ConPTY and passed (576 passed in that task). The glued-words risk did not show up in those tests. A sequence split across two reads is carried by new squawk 0321.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02-2` commit on `squawk/turnaround-2026-11-02-2`.

## Disposition
- **2026-11-02 triage (Flight Director, Mission 34 squawk turnaround):** burn-down in the next turnaround. Still valid: there is no VT handling under `the_one/`. The operator confirmed that local Concourse is up with a Windows worker, so the Windows PTY lane can verify it. Write a unit test over captured ConPTY output first. Escalate if stripping glues lines, which would need a terminal emulator.
