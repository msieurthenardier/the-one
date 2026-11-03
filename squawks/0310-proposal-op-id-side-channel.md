# Squawk 0310: `ProposalOp.run` returns the applied proposal id by writing into the caller's dict

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-02
**Completed**: 2026-11-02

## Report
Mission 34 Flight 2 needed the applied proposal's id for its log line, so `ProposalOp.run` now writes it back into the row dict the caller passed in (`self.row["proposal_id"] = await _insert(...)`), and `service.agent_change` reads it with `row.get("proposal_id")`. The flight Reviewer confirmed it is safe today (one caller, which owns the dict), but it is implicit coupling: a second caller, or a caller that reuses its row, gets an unexpected key. Hand the id back explicitly (a return value or an attribute on the op) and drop the dict write.

## Evidence
- `the_one/routines/proposals.py:161` — `self.row["proposal_id"] = await _insert(conn, row, "applied", _now_iso())`.
- `the_one/routines/service.py:635` — `_log_proposal(row.get("proposal_id"), agent_name, action, "applied", untrusted, applied_id)`.
- Mission 34 Flight 2 debrief (Developer interview), Action Items.

## Corrective Action
`ProposalOp` is now a plain (non-frozen) dataclass with an `applied_id: str | None` field (`init=False`). `run` sets `self.applied_id` from `_insert` and no longer writes into the caller's row dict. `service.agent_change` logs `op.applied_id`. The one caller of `run` with a result use is `agent_change`; the repository calls discard it, so no contract changed. The `agents.md` routine-log paragraph is updated. New test `test_insert_applied_run_does_not_mutate_row_and_exposes_id` in `tests/test_routines_proposals.py`.

## Verification
Done: row dict unchanged (new test; falsified by restoring the dict write, it failed, then removed); `test_routines_proposals.py`, `test_routines_service.py`, `test_routine_log_vocabulary.py` 77 passed; ruff check/format clean; `THE_ONE_TEST_NETNS=1 make test-unit` 8617 passed, 15 skipped.
- The caller's row dict is not mutated by `ProposalOp.run` (a test asserts the dict is unchanged); the applied line still carries the proposal id (`tests/test_routines_service.py` log tests pass); `make test-unit` passes.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches `tests/test_encryption.py` key-path guards and logging setup), batch review of the 2026-11-02 squawk turnaround, scoped to the diff, `[HANDOFF:confirmed]` with no blocking issues; the Reviewer's own `THE_ONE_TEST_NETNS=1 make test-unit`: 8618 passed, 15 skipped; `ruff check`/`format --check` clean. Process note: a falsification revert dropped a newline (a syntax error in one interim run), fixed by editing before the final gate.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02` commit on `squawk/turnaround-2026-11-02`.
