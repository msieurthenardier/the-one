# Squawk 0267: the installer still logs `quit-poll` lines although it no longer polls

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-26
**Completed**: —

## Report
Since `v0.12.1`, the installer's `[Code]` makes one check after the quit call, with no poll loop. To keep the lifecycle parsers unchanged, it still writes `<tag> quit-poll: present (iteration 0)`, `quit-poll: gone (iteration 0)` and `quit-poll: nothing left before KillRunning`. Anyone reading a field setup log would expect a loop that no longer exists.

## Evidence
- `packaging/windows/the-one.iss` lines ~170-181 (`CheckThenKill`): `Log(Tag + ' quit-poll: present (iteration 0)')`, etc.
- The parsers and pins that read these strings:
  - `packaging/windows/lifecycle.ps1` ~353-368 (L7 order: `poll-present`, `poll-gone`, `nothing-left`, and L9/L11 by the same patterns);
  - `packaging/windows/lib.ps1` ~754-769 (self-test fixtures);
  - `tests/test_windows_lifecycle_static.py` ~104-125;
  - `packaging/windows/README.md` (the `/LOG` line list).
- Flight 4 debrief, What Could Be Improved / Technical.

## Corrective Action
*(written at completion)*. Rename the prefixes to what happens, for example `<tag> quit-check: present|gone|nothing left before KillRunning`, and drop `(iteration 0)`. Change the `.iss`, `lifecycle.ps1`, the `lib.ps1` self-test fixtures, the static test and the README together, in one commit. Keep `quit-call:` and `quit-killrunning:` as they are.

## Verification
- `lib.ps1 -SelfTest` and `lifecycle.ps1 -SelfTest` pass in the `mcr.microsoft.com/powershell` container (`m32-pwsh-*`, `--rm`).
- `tests/test_windows_lifecycle_static.py` passes.
- `fly execute` of `ci/tasks/windows-installer-build.yml` compiles the `.iss`.
- The behaviour proof (L7, L9 and L11 read the new lines) is the next hosted Windows lifecycle run, such as the next release dry run. It needs the operator's go for a hosted run, so it can ride the next release rather than spend a run of its own.

## Sign-Off
*(written at completion)*

## Disposition
- **Logged** at Mission 32 Flight 4's debrief (operator's choice of debrief follow-ups).
