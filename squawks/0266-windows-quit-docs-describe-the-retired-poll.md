# Squawk 0266: three documents still describe the retired 90-second quit poll

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-26
**Completed**: —

## Report
`v0.12.1` replaced the installer's quit step. The old step was `ExecAsOriginalUser(..., ewNoWait)` followed by a 90-second `tasklist`/`Sleep` poll. The new one waits for `quit --wait` itself (`ewWaitUntilTerminated`; the CLI bounds the wait at about 80 s), checks once, and then runs `KillRunning`. Three documents still describe the old sequence.

## Evidence
- `the_one/agents.md` "Windows packaging (M32 F4)" (line ~2715): "poll up to 90 s until neither exe is running, then `KillRunning`".
- `packaging/windows/README.md`, the quit-sequence list: "2. **Poll.** Up to 90 s, until neither `the-one-app.exe` nor `the-one.exe` is running."
- `docs/windows-install.md` "Upgrading" (~line 85) and "Uninstalling while the app is running" (~line 171): "waits up to 90 seconds".
- The current code: `packaging/windows/the-one.iss` `QuitThenKillSetup` / `CheckThenKill` (Mission 32 Flight 4, PR #325).

## Corrective Action
*(written at completion)*. Describe v0.12.1's sequence in all three: the quit call waits for the CLI (about 80 s at most), then one check, then `KillRunning` always last. The user guide's wording can stay plain ("waits for it to finish, up to about a minute and a half"). Edits to `the_one/agents.md` stay additive in spirit (one sentence replaced; the file is shared with Mission 31).

## Verification
- `grep -rn "90 s\|90 seconds\|Poll\.\*Up to" the_one/agents.md packaging/windows/README.md docs/windows-install.md` finds no description of a poll loop.
- `tests/test_windows_lifecycle_static.py` and the docs-touching tests still pass.

## Sign-Off
*(written at completion)*

## Disposition
- **Logged** at Mission 32 Flight 4's debrief (operator's choice of debrief follow-ups).
