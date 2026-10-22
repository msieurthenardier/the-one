# Squawk 0230: test_filter_keystroke_cost_ratio_60_vs_10_throttled failed once under parallel load

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-22
**Completed**: —

## Report
`tests/browser/test_flow_agents_scale.py::test_filter_keystroke_cost_ratio_60_vs_10_throttled` failed once in a `--parallel 3` run during Mission 31 Flight 2 leg 11 (the run right after the `agents` lane split). It passed 3 of 3 alone, and the lane then passed alone (161 in 378 s). The test asserts a timing ratio (filter keystroke cost at 60 agents against 10, under CPU throttling), which is sensitive to host load from neighbouring lanes.

## Evidence
- The flight log of Mission 31 Flight 2, `### agents-close` (the second parallel run).

## Corrective Action
*(written at completion)*

## Verification
- The ratio is measured in a way that does not drift with neighbouring lane load (for example, a median over repeated keystrokes, or a ratio bound with load margin), and the test passes in repeated `--parallel 3` runs. Or the flake does not recur over the rest of Mission 31's gates, and that is recorded.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
