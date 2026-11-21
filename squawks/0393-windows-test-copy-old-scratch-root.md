# Squawk 0393: The Windows test copy's default scratch root can no longer be adopted

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-21
**Completed**: 2026-11-21

## Report
`scripts/windows_test_copy.py setup` refuses its default scratch root,
`%LOCALAPPDATA%\Temp\the-one-f5`. The root holds 29 leftover entries from
earlier missions (`cache`, `data-l1a`, `data-l2-*`, `data-bt20061-1`,
`data-f6-dd17`, …) but no `.the-one-f5-root` sentinel, so the tool will not
adopt it.

Mission 36 Flight 3 Leg 9 worked around it with
`--root %LOCALAPPDATA%\Temp\the-one-f5-m36f3`. A later run that forgets
`--root` stops at setup.

The operator asked for a squawk on 2026-11-21. The fix is one of these
(pick one, no design needed):
- **Clean it:** delete the old root, an operator-side action on their
  Windows machine, so the default works again.
- **Document it:** record in `the_one/agents.md` "Windows test copy" that a
  fresh `--root the-one-f5-<tag>` is the way to start clean.

## Evidence
- `scripts/windows_test_copy.py:61`: `SENTINEL = ".the-one-f5-root"`.
- `scripts/windows_test_copy.py:4586`:
  `HelperError(f"refusing to adopt non-empty {root!r} with no {SENTINEL} sentinel")`.
- 2026-11-21 run, `setup` with no `--root`: "REFUSED: refusing to adopt
  non-empty 'C:\\Users\\…\\AppData\\Local\\Temp\\the-one-f5' with no
  .the-one-f5-root sentinel".
- The fresh root `the-one-f5-m36f3` carries the sentinel after `setup`.

## Corrective Action
"Document it" chosen by the Flight Director (cleaning the Windows folder is an
operator-side action). Added a bullet "Default root is stale on the operator's
machine" to `the_one/agents.md` "Windows test copy (M25 F5 L1a)": the default
root has no sentinel so `setup` refuses it; start clean with
`--root %LOCALAPPDATA%\Temp\the-one-f5-<tag>` (leaf must start with
`the-one-f5`); or the operator deletes the old root. The squawk's description
of the rule is correct; no script change.

## Verification
Checked in `scripts/windows_test_copy.py`: line 61 `SENTINEL = ".the-one-f5-root"`,
line 62 `ROOT_LEAF_PREFIX = "the-one-f5"`; line 4586
`refusing to adopt non-empty {root!r} with no {SENTINEL} sentinel`; line 228
`refusing root ...: leaf must match the-one-f5* (rule: root leaf)` and line 224
root must be under `%LOCALAPPDATA%\Temp`; line 4960 flag `--root`
("scratch root (default %LOCALAPPDATA%\Temp\the-one-f5)"). Script unchanged, so
its tests were not re-run; no Windows-side action taken.

Original acceptance note:
`windows_test_copy.py setup` with no `--root` succeeds after the cleanup, or
the agents.md text names the `--root` route and a run following it succeeds.
`snapshot --compare` is clean.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet; the security tier, since the batch changed the shell-write hook and CLAUDE.md's safety rules), batch review of squawks 0368, 0379, 0384, 0385, 0391-0397
**Verdict**: confirmed
**Commit**: `squawk: turnaround 2026-11-21` on squawk/turnaround-2026-11-21
