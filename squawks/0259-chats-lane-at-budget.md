# Squawk 0259: `chats` browser lane at 99% of its budget

**Status**: in-progress
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-25
**Completed**: —

## Report
At Mission 31 Flight 4's landing, the `chats` lane ran 446 s against a 450 s budget in the final `--parallel 3` gate. It was 396 s at Flight 3's debrief and 409 s at Flight 4 leg 11, and it gained no tests in between, so the jump may be host noise or the Mission 32 merge. It is the next lane to trip `OVER BUDGET`, and Flight 5 will add browser tests.

## Evidence
- `scripts/run-tests.sh:63`: `[chats]=450`.
- The Flight 4 debrief's Test Metrics table (`missions/31-control-library-everywhere/flights/04-settings-on-the-library/flight-debrief.md`): chats 396 → 409 → 446 s, 191 tests.

**Action:**
1. Re-measure in a `--parallel 3` browser run on a quiet host (no other test process at all: no Developer lanes, no unit suite, no other session's tests). A solo `--lane chats` run measures something else, because budgets are wall seconds inside a `--parallel 3` run. (Amended by M31 F5 L01.)
2. If it holds above about 410 s, raise the budget by the measured-plus-25% rule (squawk 0217) or split the lane.
3. Record the quiet-host condition in the lane-budget rule in CLAUDE.md.

## Corrective Action
M31 F5 L01: the quiet-host `--parallel 3` run (start load 1.03, rc=0, 1490 s) measured `chats` at 391 s, 87% of its 450 s budget, down from 446 s at the Flight 4 landing, so the earlier reading was host load. By the measured-plus-25% rule the budget stays at 450 s (not over budget, moved 4% from 409 s). The quiet-host rule is added to CLAUDE.md ("Lane time budgets") and to the budget comment in `scripts/run-tests.sh`.

## Verification
`PARALLEL_RESULT rc=0 total=1490s lanes=13 failed=-`; per-lane times in the flight log (all within budget). `chats` 391 s vs 450 s. CLAUDE.md and `scripts/run-tests.sh` budget tables agree (grep). Sign-off by the flight-end Reviewer; closes with the flight's commit.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
