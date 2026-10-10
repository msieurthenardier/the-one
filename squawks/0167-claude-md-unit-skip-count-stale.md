# Squawk 0167: CLAUDE.md's expected unit skip count is stale

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-10
**Completed**: —

## Report
CLAUDE.md's "Expected unit skip count (squawk 0132)" says `make test-unit`
normally reports **10 skipped**: "the 9 `tests/test_pty_windows.py` tests"
plus one dispatch test. `tests/test_pty_windows.py` now has **10** tests, so
the normal count is **11**, and **13** under `THE_ONE_TEST_NETNS=1`. Two
Mission 27 Developers misread 11 as possible drift.

## Evidence
- `grep -c "def test_" tests/test_pty_windows.py` returns 10.
- `CLAUDE.md:291` says "**10 skipped** — the 9 `tests/test_pty_windows.py`
  tests".
- Mission 27 Flight 2, leg 2: `make test-unit -rs` showed 11 skips, all
  Windows-only.
- The gate under netns showed 13 skipped.

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
