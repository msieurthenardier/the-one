# Squawk 0434: the resolver-clip property test hangs under load

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-26
**Completed**: —

## Report

Under load, the whole unit tier was killed twice inside `tests/test_resolver_clip.py::TestProperties::test_clip_is_total_and_resolve_of_the_clip_never_raises[FilesystemConfig]`, with no failure reported either time:
- the Mission 37 Flight 2 Leg 2 run, killed at 98% by a 1200 s timeout;
- the Flight 2 debrief run, killed at 98% by a 3600 s timeout, at load 15-19.

The same test takes about 7.6 s on a clean host (the M37 F1 profile), and passed in Leg 4's run at load 14. A seeded test that sometimes takes over an hour points to a hang or a pathological path in filesystem canonicalisation, not ordinary slowness.

## Evidence
- The debrief run's log ends with that test's node id and then `run-tests.sh: TIMEOUT after 3600s`. 12190 PASSED lines, 0 FAILED. The log is scratchpad `unit.log` and is not kept.
- The test (`tests/test_resolver_clip.py:725`) runs `CASES` seeded random rows. Each one canonicalises generated paths under `tmp_path` and a monkeypatched `HOME`.
- Flight 2 did not touch the resolver, so this is not a Flight 2 regression.

## Corrective Action
*(written at completion)* First, find where it blocks. Run the file alone under load with `--timeout 120`, so pytest-timeout prints the stack. Then fix the cause, for example a path the generator can produce that blocks or loops when resolved. Lowering `CASES` is not a fix.

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
