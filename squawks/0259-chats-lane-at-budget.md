# Squawk 0259: `chats` browser lane at 99% of its budget

**Status**: open
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
1. Run `--lane chats` alone on a quiet host (no other lanes, no unit suite) twice.
2. If it holds above about 410 s, raise the budget by the measured-plus-25% rule (squawk 0217) or split the lane.
3. Record the quiet-host condition in the lane-budget rule in CLAUDE.md.

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
