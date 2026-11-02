# Squawk 0312: the dead-code removal method is not written down

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-02
**Completed**: —

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
*(written at completion)*

## Verification
- `the_one/agents.md` "Project Conventions" carries the convention in a few short bullets; any doc guard (`make test-unit`) passes.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
