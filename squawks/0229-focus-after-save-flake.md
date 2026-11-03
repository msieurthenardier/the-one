# Squawk 0229: test_agent_save_never_steals_focus_the_user_moved failed once under load (Save stayed enabled)

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-21
**Completed**: 2026-11-02

## Report
`tests/browser/test_flow_agents_focus_after.py::test_agent_save_never_steals_focus_the_user_moved` failed once in a full agents-lane run, which was beside the contracts lane under netns. Save was still enabled after the held PUT was released. Mission 31 Flight 2 leg 07b's run hit it. The test passed alone four times, then 8 of 8 under Chromium CPU throttling (1-16x) and 15 of 15 under 24 CPU-burning processes. The full agents lane then passed 227 of 227.

The suspected cause was refuted: a same-identity patch whose snapshot is overtaken by the async model refetch. The model-fetch callback already retakes the snapshot when the form is clean, and superseded fetches are aborted. Squawk 0228's window (Save before the first model list lands) is a candidate, since the test fills and saves right after the editor appears, but no run reproduced it.

Keep this open as the known-flake record. On a recurrence, capture the trace and the PUT body, and check 0228 first.

## Evidence
- The flight log of Mission 31 Flight 2, `### general-tab` → "Fix: Save-enabled race after a same-identity patch" (the investigation), and `### mcps-tab` (the failing run).

## Corrective Action
No code change. The only candidate cause named in the report, squawk 0228 (Save before the first model list lands), was fixed in Mission 34 Flight 2 Leg 4. Since then the flake has not recurred, so it is closed under the second branch of the verification clause below, by operator decision at the 2026-11-02 triage. No root cause was proven. If it recurs, log a new squawk with the trace and the PUT body.

## Verification
- A root cause is identified and fixed, with a test that fails before the fix. Or the flake does not recur over the rest of Mission 31's gates, and that is recorded.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches `tests/test_encryption.py` key-path guards and logging setup), batch review of the 2026-11-02 squawk turnaround, scoped to the diff, `[HANDOFF:confirmed]` with no blocking issues; the Reviewer's own `THE_ONE_TEST_NETNS=1 make test-unit`: 8618 passed, 15 skipped; `ruff check`/`format --check` clean. Close-as-fixed by operator decision (2026-11-02 triage), with no code change; the Reviewer confirmed the recorded evidence meets this squawk's own verification clause (did not recur, recorded), no root cause shown.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02` commit on `squawk/turnaround-2026-11-02`.

- **2026-11-02 (Mission 34 Flight 1 Leg 2):** did not recur in the quiet-host `--parallel 3` run (`PARALLEL_RESULT rc=1 total=2027s`, start load 0.23; the `agents`, `settings-tools` and `providers` focus-after files all passed). Stays open: 0228 (the product defect it waits on) is unresolved.

- **2026-11-02 (Mission 34 Flight 2 Leg 4):** after the 0228 fix, `test_flow_agents_focus_after.py::test_agent_save_never_steals_focus_the_user_moved` ran 10 times isolated: all passed (exit 0 x10). No root cause shown; stays open.

## Disposition
- **2026-11-02 triage (Flight Director, Mission 34 squawk turnaround):** **operator chose close-as-fixed**, per this squawk's own verification clause ("does not recur, and that is recorded"). After 0228's fix (Mission 34 Flight 2) it did not recur in any gate since, and passed 10 of 10 isolated runs. No root cause was shown. Completed in this turnaround with that evidence; reopen as a new squawk if it recurs.
