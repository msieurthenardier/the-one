# Squawk 0403: The unit tier runs over its 350 s target on a quiet host

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-23
**Completed**: —

## Report

The unit tier now takes about 385 s on a quiet host against its 350 s standing target, so by
`the_one/agents.md` the gate reads as regressed. The per-test cost is flat (about 0.034 s across
F3 and F4). The rise comes from test count (11898 passed), not from slower tests. The Mission 36
Flight 2 debrief already recommended raising the target to about 400 s or profiling with
`--durations`, and neither was done. Found by the Mission 36 Flight 4 debrief.

## Evidence
- **The F4 closing gate:** 11898 passed / 15 skipped in 387.43 s at `3178ae7d`, start load 0.74.
- **The F4 debrief's fresh run:** 384.03 s at `604e052c`.
- `the_one/agents.md` "Host policy" bullet: "the unit tier alone has a 350 s standing target … 387 s
  is 11% over it: re-check on the next quiet gate before raising".

## Corrective Action
*(written at completion)*

## Verification
A `--durations=30` profile of `make test-unit` on a quiet host is recorded. Then either the slowest
tests are fixed and the tier is back under 350 s, or the standing target in `the_one/agents.md` is
raised with the profile cited.
