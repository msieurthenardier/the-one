# Squawk 0229: test_agent_save_never_steals_focus_the_user_moved failed once under load (Save stayed enabled)

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-21
**Completed**: —

## Report
`tests/browser/test_flow_agents_focus_after.py::test_agent_save_never_steals_focus_the_user_moved` failed once in a full agents-lane run, which was beside the contracts lane under netns. Save was still enabled after the held PUT was released. Mission 31 Flight 2 leg 07b's run hit it. The test passed alone four times, then 8 of 8 under Chromium CPU throttling (1-16x) and 15 of 15 under 24 CPU-burning processes. The full agents lane then passed 227 of 227.

The suspected cause was refuted: a same-identity patch whose snapshot is overtaken by the async model refetch. The model-fetch callback already retakes the snapshot when the form is clean, and superseded fetches are aborted. Squawk 0228's window (Save before the first model list lands) is a candidate, since the test fills and saves right after the editor appears, but no run reproduced it.

Keep this open as the known-flake record. On a recurrence, capture the trace and the PUT body, and check 0228 first.

## Evidence
- The flight log of Mission 31 Flight 2, `### general-tab` → "Fix: Save-enabled race after a same-identity patch" (the investigation), and `### mcps-tab` (the failing run).

## Corrective Action
*(written at completion)*

## Verification
- A root cause is identified and fixed, with a test that fails before the fix. Or the flake does not recur over the rest of Mission 31's gates, and that is recorded.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:

- **2026-11-02 (Mission 34 Flight 1 Leg 2):** did not recur in the quiet-host `--parallel 3` run (`PARALLEL_RESULT rc=1 total=2027s`, start load 0.23; the `agents`, `settings-tools` and `providers` focus-after files all passed). Stays open: 0228 (the product defect it waits on) is unresolved.
