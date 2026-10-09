# Squawk 0161: Windows `shell` tool escapes double quotes as literal `\"`

> Renumbered from 0157 on 2026-10-09: the id collided with a squawk logged concurrently by another session (#247). Commits and the #248 PR still cite the old id.

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-08
**Completed**: 2026-10-08

## Report
GitHub issue #245. On Windows, every `shell` call, in both boxed and `host_access=true` mode, passes double quotes to cmd as literal `\"`. cmd does not treat `\"` as a quote, so quoted arguments break. `echo "a b"` prints `\"a b\"`. `tasklist /FI "PID eq 5212"` splits the filter into separate arguments. `powershell -Command "...; $x=5; Write-Output $x"` gets a mangled string and prints `=5` instead of running it.

## Evidence
- `the_one/platform/shell.py:run_shell`, the sandboxed seam path (`profile is not None`, which is always the case for the tool) calls `asyncio.create_subprocess_exec(spec.command, *spec.args, ...)` with `spec.args == ["/c", command]` from `select_shell()` → `("cmd.exe", ["/c"])`. On Windows, `subprocess` joins a list with `list2cmdline`, which applies MSVCRT argv escaping (`"` → `\"`, and the whole string is wrapped in quotes when it contains spaces). cmd.exe does not use MSVCRT parsing, so it receives the backslashes literally.
- The legacy no-profile path uses `create_subprocess_shell`, which on Windows builds `cmd.exe /c "<command>"` verbatim, so it does not have this problem.

## Corrective Action
`run_shell`'s sandboxed path now branches on `os.name == "nt"`: it calls `asyncio.create_subprocess_shell(command, env=spec.env, cwd=spec.cwd)` instead of `create_subprocess_exec(spec.command, *spec.args)`. `create_subprocess_shell` is the minimal correct mechanism: `subprocess` on Windows turns it into `cmd.exe /c "<command>"` as one string handed to CreateProcess unchanged (the same call the legacy no-profile path already makes), whereas every `*_exec` form builds a list and goes through `list2cmdline`. `spec.command` is always `cmd.exe` on Windows and `PassthroughSandbox.prepare_spawn` forwards command/args/env/cwd unchanged, so nothing it adds is bypassed; env and cwd are still taken from the spec. POSIX branch untouched. Other `select_shell` users (`pty_windows.py`, `pty_unix.py`) use only the shell executable for interactive PTY sessions, not the `/c` one-shot list, so they have no such defect.

## Verification
- New `TestWindowsSandboxedCommandVerbatim` in `tests/test_platform_shell.py` (os.name patched to `nt`, Passthrough backend, fake `create_subprocess_shell`; `create_subprocess_exec` raises if reached) asserts the command, including `echo "a b" ...` and the `powershell -Command "..."` case, arrives verbatim.
- `scripts/run-tests.sh tests/test_platform_shell.py`: 13 passed. `ruff check` / `ruff format --check`: clean.
- `make test-unit`: 5607 passed, 10 skipped, 5 failed. The failures are in `tests/test_openrouter_wire_level.py` (network/auth to openrouter.ai); they fail identically with this change stashed, so unrelated.
- Not run on real Windows.

## Sign-Off
**Reviewer**: independent Reviewer (Sonnet tier: the diff touches the sandboxed spawn seam). It walked CPython's Windows `shell=True` construction (`{ComSpec} /c "{command}"`) and cmd's no-`/s` quote stripping through `echo "a b" "c d"`, the `powershell -Command` case and a command starting with a quoted path, all delivered verbatim. It confirmed `spec.env`/`spec.cwd` pass through, kill semantics are unchanged and the POSIX branch is identical. Non-blocking nit: the test does not assert `cwd`.
**Verdict**: confirmed (`[HANDOFF:confirmed]`)
**Commit**: `squawk: turnaround 2026-10-08 (3)` on branch `squawk/turnaround-2026-10-08-3`
