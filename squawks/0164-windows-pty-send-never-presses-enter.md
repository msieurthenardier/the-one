# Squawk 0164: Windows PTY sessions type input but never press Enter

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-09
**Completed**: 2026-10-09

## Report
GitHub issue #246, found while checking 0.10.4. With the 0162 fix, the packaged app's sessions start and stay attached. But `shell_session_send "echo hello"` only types `echo hello` at the cmd prompt: no output line and no new prompt follow, and each later send goes onto the same line. A bare newline send times out after 30 s. This happens in both host and boxed sessions.

## Evidence
- `the_one/platform/pty_windows.py:WindowsPtySession.send` appends `"\n"` when the input doesn't end with one, and `_send_blocking` writes it unchanged via `self._proc.write(input)`. ConPTY treats `\r` as Enter; a bare `\n` is not a submit.
- pywinpty 3.0.5's own tests submit lines with `\r\n` (`winpty/tests/test_ptyprocess.py`: `pty.write('echo \"foo\"\r\nexit\r\n')`).
- `tests/test_pty_windows.py:test_send_echo_hello_round_trip` asserts `b"hello" in output`. The PTY echoes back the typed `echo hello`, which already contains it, so the test passes without the command running. This is the PTY-echo trap in CLAUDE.md's "Sandbox testing footguns" #2. `test_send_second_command_state_persists` has the same blind spot.

## Corrective Action
`the_one/platform/pty_windows.py`: new pure helper `_normalize_submit` turns `\r\n`, lone `\n` and lone `\r` into `\r\n` and ends the input with exactly one (trailing blank lines collapse; `""` is a bare Enter). `WindowsPtySession.send` now passes `_normalize_submit(input)` to `_send_blocking` instead of appending a bare `\n`; docstring updated. `\r\n` did not double-submit on the real worker. `shell_session_send` (`the_one/tools/sessions.py`) passes `input` straight through and adds no newline of its own, so it needed no change; `pty_unix.py` is untouched.

Tests: `tests/test_pty_windows.py` round-trip tests now assert output the echoed line cannot contain (`set /a 6*7` -> `42`; `echo a^b` -> `ab`; state persists via `%x%`), a new `test_send_multiline_runs_each_line`, and `test_last_activity_updated_after_send` runs a real command. New Linux-runnable `tests/test_pty_windows_input.py` pins the normalization table (with a stubbed `winpty` module) and checks `_send_blocking` writes what it is given.

## Verification
- Linux: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_pty_windows.py tests/test_pty_windows_input.py -x --timeout 30` -> 13 passed, 10 skipped (Windows-only). `ruff check` and `ruff format` clean on the changed files.
- Windows, with fix: `fly -t the-one execute -c ci/tasks/windows-tests.yml -i repo=.` -> 556 passed, 21 skipped, 1 deselected, 1 xfailed, 1 xpassed; `tests/test_pty_windows.py` all 8 non-xfail tests passed (the grandchild-reap test xpassed).
- Windows, `pty_windows.py` reverted to HEAD (tests kept): `test_send_echo_hello_round_trip`, `test_send_second_command_state_persists` and `test_send_multiline_runs_each_line` FAILED (3 failed, 553 passed). The strengthened tests detect the bug.
- Review follow-ups: result assertions now match on their own output line (VT escapes stripped) so echo/prompt text cannot satisfy them; the stale `xfail` on `test_close_reaps_grandchild` (its reason was this same bare-`\n` bug; it XPASSed) is removed; the stub-import fixture also drops the `the_one.platform.pty_windows` attribute.
- Concourse builds (`fly -t the-one builds`): 693278 (fix, succeeded, 556 passed), 693288 (fix reverted, failed, 3 tests failed), 693311 (final, succeeded: 557 passed, 21 skipped, 1 deselected, 1 xfailed; `tests/test_pty_windows.py` 9 passed, 1 xfail, grandchild-reap test now runs unmarked and passed).

## Sign-Off
**Reviewer**: independent Reviewer (Haiku tier: the Windows PTY send path, not a sandbox or credential surface). Two cycles. Cycle 1 confirmed the fix, checked the `_normalize_submit` edge cases and the absence of stub leakage, and raised non-blocking items: two assertions that echo alone could satisfy, the stale `xfail` on `test_close_reaps_grandchild`, fixture teardown, and missing build ids. All were fixed, and cycle 2 confirmed. Accepted nit: `_output_lines` imports `re` inside the function.
**Verdict**: confirmed (`[HANDOFF:confirmed]`)
**Commit**: `squawk/0164: Windows PTY sessions submit input with CR LF` on branch `squawk/0164-windows-pty-enter`
