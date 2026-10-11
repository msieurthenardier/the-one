# Squawk 0167: CLAUDE.md's expected unit skip count is stale

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-10
**Completed**: 2026-10-11

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
CLAUDE.md's skip-count paragraph rewritten from a measured run: baseline 12 (10 test_pty_windows + 1 dispatch + 1 locale skip from Mission 28's test_locale_neutral on hosts without fr_FR/de_DE), 14 for the timing-conditional watcher case, 14 under THE_ONE_TEST_NETNS=1 (12 + 2 root-only kb_walk/kb_watcher skips; netns count taken from Mission 28 gate logs, composition inferred), and 15 with an explicit -m that omits requires_bwrap.

## Verification
Ran `bash scripts/run-tests.sh tests/ -m 'not browser and not live and not pixel' -q -rs`: 5989 passed, 15 skipped; -rs showed 10 test_pty_windows, 1 dispatch, 1 locale, 3 requires_bwrap (the make target's -m excludes those, so 12). The netns run itself was not repeated.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet), batch review of the 2026-10-11 squawk turnaround
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-10-11` commit on `squawk/turnaround-2026-10-11`. The final gate passed: unit 5946 passed and 14 skipped; `PARALLEL_RESULT rc=0 total=977s lanes=8 failed=-`, every lane within budget.
