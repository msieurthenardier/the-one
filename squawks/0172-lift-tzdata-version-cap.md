# Squawk 0172: Lift the `tzdata<2026.5` cap

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-11
**Completed**: 2026-11-03

## Report
`pyproject.toml` pins `tzdata>=2025.2,<2026.5` because 2026.5 was under 14 days old at lock time (Mission 28 F1 L1 soak rule). Zone data that isn't updated goes stale (DST rule changes), and on Linux the name set comes from tzdata while the rules come from the host.

## Evidence
`pyproject.toml:~30` (the comment says "lift the cap later"); `uv.lock` resolves tzdata 2026.4. The fix: remove the upper bound once 2026.5 is 14 or more days old, re-lock, and confirm `the-one doctor` `time zones: OK`.

Logged from the Mission 28 flight debriefs.

## Corrective Action
Operator approved 2026-11-02. Changed `tzdata>=2025.2,<2026.5` to `tzdata>=2025.2` in `pyproject.toml` (comment updated). `uv lock --upgrade-package tzdata`: tzdata 2026.4 -> 2026.6; no other package moved. Installed 2026.6 into the repo venv (`uv pip install --python .venv/bin/python tzdata==2026.6`).

## Verification
- `uv lock --check`: clean.
- `THE_ONE_DATA_DIR=$HOME/the-one-behavior-test-scratch/0172/data .venv/bin/the-one doctor`: `time zones: OK — 345 zones (tzdata 2026f)`, RESULT: PASS.
- `tests/test_time_zones.py` + `tests/test_packaging_metadata.py`: 106 passed, 1 skipped.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches the shell-write hook, `App.safeUrl`, the encryption status count and the credential docs), batch review of the 2026-11-02-2 squawk turnaround, scoped to the diff. Its one blocking finding (0135's Dockerfile `uv venv` line) and the non-blocking items were fixed in a fix pass, which a Haiku Reviewer re-checked: `[HANDOFF:confirmed]`. An Accessibility Reviewer (Sonnet) confirmed the UI changes (0239, 0289, 0290, 0291, 0254). The final gate on the batch tree: `THE_ONE_TEST_NETNS=1 make test-unit` 8738 passed, 15 skipped (219 s, start load 0.48); browser `--parallel 3` `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript` (start load 0.72). The one failure is new squawk 0315, which passed 3 of 3 isolated runs.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02-2` commit on `squawk/turnaround-2026-11-02-2`.

## Disposition
**Deferred**: the cap exists because tzdata 2026.5 (uploaded 2026-10-03) was
under the 14-day soak window. It is still under it on 2026-10-11. Revisit
**on or after 2026-10-17**: remove the `<2026.5` bound, re-lock, check that
`the-one doctor` reports `time zones: OK`, and complete this squawk.
**Trigger fired** (2026-10-30): the revisit date has passed and tzdata 2026.6 is on PyPI; the cap is still `<2026.5` (`pyproject.toml:31`). Waiting on the operator's approval to lift ([maintenance 2026-10-30](../maintenance/2026-10-30.md)).
- **2026-11-02 triage (Flight Director, Mission 34 squawk turnaround):** **operator approved lifting the cap.** Next turnaround: remove `<2026.5`, re-lock, check that `the-one doctor` reports `time zones: OK`, and batch it with 0226/0227 (same `pyproject.toml`).
