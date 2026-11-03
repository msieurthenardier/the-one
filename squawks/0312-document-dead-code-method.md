# Squawk 0312: the dead-code removal method is not written down

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-02
**Completed**: 2026-11-02

## Report
Mission 34 Flight 3 removed dead code with a method that worked, but it lives only in that flight's leg artifacts and log, so the next sweep will rediscover it. Add a short "Removing dead code" convention to `the_one/agents.md` "Project Conventions":
- confirm each item with a repo-wide grep that excludes `.claude/` (worktree copies), `.git/`, `.venv/` and the planning directories (`missions/`, `maintenance/`, `squawks/`, `sorties/`); record the command and result;
- check names that are built as strings (CSS classes such as `'badge badge--' + kind` or `'ui-list-pane-' + density`, testids, `getattr`) against their producers before deleting, and leave the known traps alone (decorator-registered handlers, pydantic hooks, framework callbacks, ctypes fields, `_reset_for_tests` helpers);
- run the UI ownership, emitted-class and inventory guards and ruff after deleting (orphaned imports);
- to retire a test-only production method: for each of its tests, name the live test that fails on the same regression (or "property removed with the method", with the reason), write or extend those live tests first, falsify them, invert any test that spies on the method, then delete.

## Evidence
- `missions/34-maintenance/flights/03-dead-code/legs/01-definite-dead-sweep.md` and `02-retire-test-only-methods.md` (its Design Review table); the flight log's Leg 1 and Leg 2 entries.
- Mission 34 Flight 3 debrief (Developer and Architect interviews), Action Items.

## Corrective Action
Added a `removing-dead-code` convention (four bullets: grep with exclusions and recorded result; string-built names checked against producers plus the known traps; UI guards and ruff after deleting; the method for retiring a test-only production method) to `the_one/agents.md` "Project Conventions", before `landmark-elements-over-aria-roles`. Added `removing-dead-code` to the named-pattern list line in `CLAUDE.md`.

## Verification
- `the_one/agents.md` "Project Conventions" carries the convention in a few short bullets; any doc guard (`make test-unit`) passes.
- Doc-reading guards (`test_routine_log_vocabulary`, `test_studio_editor_contracts_static`, `test_store_static`, `test_design_tokens_a11y`): 329 passed. `THE_ONE_TEST_NETNS=1 make test-unit`: 8618 passed, 15 skipped.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches `tests/test_encryption.py` key-path guards and logging setup), batch review of the 2026-11-02 squawk turnaround, scoped to the diff, `[HANDOFF:confirmed]` with no blocking issues; the Reviewer's own `THE_ONE_TEST_NETNS=1 make test-unit`: 8618 passed, 15 skipped; `ruff check`/`format --check` clean.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02` commit on `squawk/turnaround-2026-11-02`.
