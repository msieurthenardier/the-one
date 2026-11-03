# Squawk 0266: three documents still describe the retired 90-second quit poll

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-26
**Completed**: 2026-11-03

## Report
`v0.12.1` replaced the installer's quit step. The old step was `ExecAsOriginalUser(..., ewNoWait)` followed by a 90-second `tasklist`/`Sleep` poll. The new one waits for `quit --wait` itself (`ewWaitUntilTerminated`; the CLI bounds the wait at about 80 s), checks once, and then runs `KillRunning`. Three documents still describe the old sequence.

## Evidence
- `the_one/agents.md` "Windows packaging (M32 F4)" (line ~2715): "poll up to 90 s until neither exe is running, then `KillRunning`".
- `packaging/windows/README.md`, the quit-sequence list: "2. **Poll.** Up to 90 s, until neither `the-one-app.exe` nor `the-one.exe` is running."
- `docs/windows-install.md` "Upgrading" (~line 85) and "Uninstalling while the app is running" (~line 171): "waits up to 90 seconds".
- The current code: `packaging/windows/the-one.iss` `QuitThenKillSetup` / `CheckThenKill` (Mission 32 Flight 4, PR #325).

## Corrective Action
Docs only, read against `packaging/windows/the-one.iss` (`QuitThenKillSetup`, `CheckThenKill`; unchanged). `the_one/agents.md` (Windows packaging quit sequence), `packaging/windows/README.md` (step 1 now waits for the call, bounded by the CLI at about 80 s; step 2 is "Check once") and `docs/windows-install.md` (both places: "up to about a minute and a half") now describe v0.12.1's sequence. Original plan text: describe v0.12.1's sequence in all three: the quit call waits for the CLI (about 80 s at most), then one check, then `KillRunning` always last. The user guide's wording can stay plain ("waits for it to finish, up to about a minute and a half"). Edits to `the_one/agents.md` stay additive in spirit (one sentence replaced; the file is shared with Mission 31).

## Verification
Done: the grep finds no poll-loop description (remaining hits are unrelated lines); `THE_ONE_TEST_NETNS=1 make test-unit`: 8724 passed, 15 skipped (includes `test_windows_lifecycle_static.py`). No new tests.
- `grep -rn "90 s\|90 seconds\|Poll\.\*Up to" the_one/agents.md packaging/windows/README.md docs/windows-install.md` finds no description of a poll loop.
- `tests/test_windows_lifecycle_static.py` and the docs-touching tests still pass.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches the shell-write hook, `App.safeUrl`, the encryption status count and the credential docs), batch review of the 2026-11-02-2 squawk turnaround, scoped to the diff. Its one blocking finding (0135's Dockerfile `uv venv` line) and the non-blocking items were fixed in a fix pass, which a Haiku Reviewer re-checked: `[HANDOFF:confirmed]`. An Accessibility Reviewer (Sonnet) confirmed the UI changes (0239, 0289, 0290, 0291, 0254). The final gate on the batch tree: `THE_ONE_TEST_NETNS=1 make test-unit` 8738 passed, 15 skipped (219 s, start load 0.48); browser `--parallel 3` `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript` (start load 0.72). The one failure is new squawk 0315, which passed 3 of 3 isolated runs.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02-2` commit on `squawk/turnaround-2026-11-02-2`.

## Disposition
- **Logged** at Mission 32 Flight 4's debrief (operator's choice of debrief follow-ups).
