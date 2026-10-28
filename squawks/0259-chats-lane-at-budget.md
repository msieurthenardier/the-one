# Squawk 0259: `chats` browser lane at 99% of its budget

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-25
**Completed**: 2026-10-28 (signed off at the Mission 31 Flight 6 landing)

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

M31 F5 L12: re-measured again in a quiet-host `--parallel 3` run (start load 0.86, rc=0, 1693 s): `chats` 388 s vs 450 s (moved 5% from 409 s), budget unchanged.

M31 F6 L01: re-measured a third time in a quiet-host `--parallel 3` run (start load 0.62, rc=0, 1653 s): `chats` 421 s vs 450 s, 94% of budget and growing (388 s at F5 L12), so the lane was split. `chats-transcript` is an explicit list of the transcript, composer and streaming files (`chats_transcript_pat`); `chats` is the chats globs minus that list (`chats_files()`), so a new `test_flow_chat_*` file lands in `chats`. The `chat` alias is both lanes. Run 2 (start load 0.74, rc=0, 1600 s, 15 lanes): `chats` 283 s and `chats-transcript` 122 s, budgeted 360 s and 180 s by the measured-plus-25% rule (the split is uneven because the leg's list was fixed in advance: the transcript files are the shorter half). No lane was over budget except `chats` against its provisional 270 s, replaced by 360 s from this reading.

M31 F6 L09b: the final quiet-host `--parallel 3` run (first run: start load 0.94, `rc=1 total=1763s`, one WebKit timing flake fixed by squawk 0276; deciding re-run: start load 0.74, `PARALLEL_RESULT rc=0 total=1662s lanes=16 failed=-`, with `chats` 305 s and `chats-transcript` 191 s, no budget changed) measured `chats` 329 s (283 s at L01, +16%) and `chats-transcript` 191 s. Re-budgeted by the rules: `chats` 360 to 420 s, `chats-transcript` 180 to 240 s, `contracts-chat` (provisional 300 s) to 90 s from 71 s, `contracts-controls` 480 to 600 s (463 s), `contracts-overlay` 270 to 330 s (241 s); the other eleven lanes moved under 15% and kept their budgets. No lane is over 1.3x its new budget, so no further split.

## Verification
`PARALLEL_RESULT rc=0 total=1600s lanes=15 failed=-` (M31 F6 L01 run 2); per-lane times in the flight log (all within the new budgets). `chats` 283 s vs 360 s, `chats-transcript` 122 s vs 180 s. CLAUDE.md and `scripts/run-tests.sh` budget tables agree (a script compared the two). `tests/test_run_tests_lanes.py` pins the split (disjoint, union is the suite, the by-file pair test). Final (M31 F6 L09b): `PARALLEL_RESULT rc=1 total=1763s lanes=16 failed=contracts-overlay` (one isolated-clean flake), `chats` 329 s vs 420 s, `chats-transcript` 191 s vs 240 s, all sixteen lanes within their new budgets; CLAUDE.md's table matches `scripts/run-tests.sh` (a script compared the two: 16 of 16 equal) and `tests/test_run_tests_lanes.py` passes (18). Sign-off by the flight-end Reviewer; closes with the flight's commit.

## Sign-Off
**Reviewer**: the Mission 31 Flight 6 flight-end Reviewer for the batch that carried the fix (independent of the Developer)
**Verdict**: `[HANDOFF:confirmed]`; the full gate (unit tier and all 16 browser lanes) passed at the flight's close
**Commit**: on branch `flight/06-chats-and-closing-the-counts`, in the batch commit that carried the fix (batches B1-B5 and the HAT batch), merged with the Flight 6 PR
