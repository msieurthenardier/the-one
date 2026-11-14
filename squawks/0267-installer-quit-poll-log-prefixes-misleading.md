# Squawk 0267: the installer still logs `quit-poll` lines although it no longer polls

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-26
**Completed**: 2026-11-14

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
These lines are live (the lifecycle rows read them), so they were renamed together, not removed. `packaging/windows/the-one.iss` `CheckThenKill` now logs `<tag> quit-check: present`, `quit-check: absent (nothing was running)`, `quit-check: processes still present after the quit call`, `quit-check: something left before KillRunning`, `quit-check: gone` and `quit-check: nothing left before KillRunning` (no `(iteration 0)`). Updated in the same change: `packaging/windows/lifecycle.ps1` (L7 patterns, the L7/L9/L11 key-line filters and sequences; the event keys are `check-present` and `check-gone`), the `lib.ps1` self-test fixtures, `packaging/windows/README.md` (the `/LOG` line list, now says one check and no poll loop) and `tests/test_windows_lifecycle_static.py`. `quit-call:` and `quit-killrunning:` are unchanged. `packaging/windows/probe/` (the historical quit probe, which really polls and has its own `.iss` and parser) was left alone.

## Verification
- Done: `lib.ps1 -SelfTest` ("lib.ps1 -SelfTest: all ok") and `lifecycle.ps1 -SelfTest` ("SELFTEST PASSED") in the `mcr.microsoft.com/powershell` container (named `m32-pwsh-sq0267*`, `--rm`, source mounted read-only).
- Done: `tests/test_windows_lifecycle_static.py` passes (with `tests/test_ui_control_inventory.py` and `tests/test_nav_helper.py`: 101 passed). `grep -rn quit-poll` outside `packaging/windows/probe/` and the history docs finds nothing.
- NOT done: `fly execute` of `ci/tasks/windows-installer-build.yml` (the `.iss` compile). The `.iss` edit is five string literals inside existing `Log(...)` calls.
- The behaviour proof (L7, L9 and L11 read the new lines) is the next hosted Windows lifecycle run, such as the next release dry run. It needs the operator's go for a hosted run, so it can ride the next release rather than spend a run of its own.

The `.iss` change is not compiled and the hosted Windows lifecycle run has not happened: it is first proven at the next Windows package run.

Gate (Flight Director, full gate on the final tree, 2026-11-14): unit tier 10155 passed, 15 skipped (under `THE_ONE_TEST_NETNS=1`); browser `PARALLEL_RESULT rc=0 total=2253s lanes=20 failed=-`.

## Sign-Off
**Reviewer**: independent Reviewer (Sonnet tier, because the batch diff touches the MCP sandbox error path), who confirmed the batch diff with `[HANDOFF:confirmed]` on 2026-11-14 with no high or medium issues.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-14` commit on `squawk/turnaround-2026-11-14`

## Disposition
- **Logged** at Mission 32 Flight 4's debrief (operator's choice of debrief follow-ups).
- **2026-11-02 triage (Flight Director, Mission 34 squawk turnaround):** deferred. The static half is doable here; verification needs the pwsh container self-tests and a `fly execute` compile. **Revisit trigger:** the next Windows/Concourse window. Complete 0266 (the docs) first.
- **Completed** in the 2026-11-14 turnaround (the static half; see Verification for what is not yet proven).
