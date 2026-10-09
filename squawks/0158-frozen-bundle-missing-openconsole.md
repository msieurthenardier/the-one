# Squawk 0158: Packaged Windows app omits pywinpty's OpenConsole.exe, so PTY sessions die at start

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-08
**Completed**: 2026-10-08

## Report
GitHub issue #246. In the packaged Windows app, `shell_session_start` (`host_access=true`) returns a session id and `shell_session_list` shows it. Every `shell_session_send` to it then returns `[error] session not active`, even for `echo hello`.

## Evidence
- `the_one/platform/pty_windows.py:WindowsPtySession.send` raises `RuntimeError("session not active")` when `not self.is_alive`, that is, when `PtyProcess.isalive()` is false. The child is already gone right after `start()`, but the registry still holds the session.
- The locked pywinpty 3.0.5 wheel (`uv.lock`) ships `winpty/OpenConsole.exe` and `winpty/winpty-agent.exe` next to `conpty.dll`, `winpty.dll` and `_winpty.*.pyd`. The bundled `conpty.dll` launches `OpenConsole.exe` from its own directory.
- `packaging/windows/the-one.spec`: `winpty_bins = collect_dynamic_libs("winpty")`. Its default search patterns match `*.dll`/`*.pyd`, not `*.exe`.
- In the installed app, `C:\Program Files\GleepGlorp AI\_internal\winpty\` contains only `conpty.dll`, `winpty.dll` and `_winpty.cp311-win_amd64.pyd`. `OpenConsole.exe` and `winpty-agent.exe` are absent.
- The non-frozen Windows CI lane (`ci/tasks/windows-tests.yml`, `tests/test_pty_windows.py`) passes because site-packages has every file. That is consistent with a defect in the frozen build only.

## Corrective Action
`packaging/windows/the-one.spec` now calls `collect_dynamic_libs("winpty", search_patterns=["*.dll", "*.pyd", "*.exe"])`, so `OpenConsole.exe` and `winpty-agent.exe` are bundled into `_internal/winpty/` beside `conpty.dll` (collect_dynamic_libs mirrors the package-relative path as the destination). The spec comment explains why. `tests/test_packaging_winpty_spec.py` statically pins the `*.exe` pattern. No runtime code changed. No bundle-contents assertion existed to extend. A PTY round-trip doctor gate (spawn a PTY, echo, read back) would catch this class of defect at freeze time, but is a sortie-sized follow-up and was not added.

## Verification
Unit: the new static spec test passes; ruff clean. This could NOT be proven here: the spec cannot be frozen on Linux. The real proof needs a Windows freeze (`fly execute -c ci/tasks/windows-installer-build.yml` or a local PyInstaller build) and then, in the packaged app: confirm `_internal/winpty/OpenConsole.exe` (and `winpty-agent.exe`) exist, and that `shell_session_start` (`host_access=true`) followed by `shell_session_send "echo hello"` returns output instead of `[error] session not active`.

## Sign-Off
**Reviewer**: independent Reviewer (Sonnet tier, batched with 0157). It checked that `collect_dynamic_libs` with `destdir=None` keeps the package-relative `winpty/` directory, so the `.exe` files land beside `conpty.dll`, and that `*winpty_bins` stays in `binaries`. The static test is a source-text guard, which is weak but not tautological. **Not yet proven on a real Windows freeze** (see Verification).
**Verdict**: confirmed (`[HANDOFF:confirmed]`)
**Commit**: `squawk: turnaround 2026-10-08 (3)` on branch `squawk/turnaround-2026-10-08-3`
