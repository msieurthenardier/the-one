# Squawk 0393: The Windows test copy's default scratch root can no longer be adopted

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-21
**Completed**: —

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
*(written at completion)*

## Verification
`windows_test_copy.py setup` with no `--root` succeeds after the cleanup, or
the agents.md text names the `--root` route and a run following it succeeds.
`snapshot --compare` is clean.
