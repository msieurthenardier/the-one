# Squawk 0310: `ProposalOp.run` returns the applied proposal id by writing into the caller's dict

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-02
**Completed**: —

## Report
Mission 34 Flight 2 needed the applied proposal's id for its log line, so `ProposalOp.run` now writes it back into the row dict the caller passed in (`self.row["proposal_id"] = await _insert(...)`), and `service.agent_change` reads it with `row.get("proposal_id")`. The flight Reviewer confirmed it is safe today (one caller, which owns the dict), but it is implicit coupling: a second caller, or a caller that reuses its row, gets an unexpected key. Hand the id back explicitly (a return value or an attribute on the op) and drop the dict write.

## Evidence
- `the_one/routines/proposals.py:161` — `self.row["proposal_id"] = await _insert(conn, row, "applied", _now_iso())`.
- `the_one/routines/service.py:635` — `_log_proposal(row.get("proposal_id"), agent_name, action, "applied", untrusted, applied_id)`.
- Mission 34 Flight 2 debrief (Developer interview), Action Items.

## Corrective Action
*(written at completion)*

## Verification
- The caller's row dict is not mutated by `ProposalOp.run` (a test asserts the dict is unchanged); the applied line still carries the proposal id (`tests/test_routines_service.py` log tests pass); `make test-unit` passes.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
