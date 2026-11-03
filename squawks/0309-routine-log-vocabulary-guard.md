# Squawk 0309: the routine log line vocabulary has no single guard and its scheduler formatting is repeated

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-02
**Completed**: 2026-11-02

## Report
Mission 34 Flight 2 made the routine log lines an operator-facing contract (`the_one/agents.md` "Routine log lines"; the behavior test `routine-run-observable-from-logs` greps them). The decision lines in `the_one/routines/scheduler.py::_handle` repeat the `routine decision=… routine=%s agent=%r … late_s=%.1f` formatting in four branches, and nothing pins the vocabulary as a whole: a renamed key or decision word breaks operator grep recipes and the behavior test while each unit test, asserting its own line, is edited along with it. Extract a `_log_decision(...)` helper (as `service.py::_log_proposal` already does for proposals) and add one unit test that pins the decision words and key order of every routine line family (`decision=`, `run=… started|outcome=`, `proposal=… decision=`, `purge sweep`).

## Evidence
- `the_one/routines/scheduler.py:223` (`unreadable_due`), `:242` (`skip_changed`), `:268` (`missed`), `:288` (spawn / still_running_skip) — four inline format strings.
- `the_one/routines/service.py::_log_proposal` — the existing single-helper pattern.
- Mission 34 Flight 2 debrief (Developer interview), Action Items.

## Corrective Action
Extracted `scheduler.py::_log_decision(decision, routine_id, agent_name, due, *, late_s, run, trigger, nxt, finished, reason)`, which builds every `routine decision=…` line in a fixed key order (omitting keys not passed; `unreadable_due` logs at WARNING with a repr-quoted `due`); the four inline format strings in `_handle` now call it. Emitted text is unchanged. Added `tests/test_routine_log_vocabulary.py`: drives `_log_decision` and `service._log_proposal` and pins their exact text, and reads the inline runner (`routine run=…`) and `purge sweep` format strings from the source with `ast`.

## Verification
- One helper formats every scheduler decision line; the emitted text is byte-identical to today's (existing caplog tests pass unchanged).
- A new vocabulary test fails when a decision word or key is renamed (falsified by editing, then restored by editing); `make test-unit` passes.
- Result: existing `test_routines_scheduler.py` log tests pass unchanged; the new test failed with `late_s=` renamed to `late=` and passed after restore; ruff check/format clean; unit tier counts in the hand-off.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches `tests/test_encryption.py` key-path guards and logging setup), batch review of the 2026-11-02 squawk turnaround, scoped to the diff, `[HANDOFF:confirmed]` with no blocking issues; the Reviewer's own `THE_ONE_TEST_NETNS=1 make test-unit`: 8618 passed, 15 skipped; `ruff check`/`format --check` clean.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02` commit on `squawk/turnaround-2026-11-02`.
