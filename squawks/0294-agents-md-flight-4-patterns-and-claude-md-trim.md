# Squawk 0294: Name the Flight 4 patterns in agents.md and trim CLAUDE.md's routines change log

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-30
**Completed**: —

## Report
Mission 33 Flight 4 introduced four reusable patterns that are described only inside the routines sections, and CLAUDE.md's Routines and Self-configuration paragraphs have grown into change logs.

## Evidence
- `missions/33-routines/flights/04-hat-and-alignment/flight-debrief.md`, Recommendation 4.
- Patterns: `the_one/routines/service.py::resolve_now_start`; `the_one/routines/runner.py` (`classify`, `_message_saved`); `the_one/interfaces/web/app.py::_restore_session`; the purge success path calling `revertFn()` (`agent-editor-controller.js`).

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

`the_one/agents.md` Project Conventions has a named entry for each of: an operator-only request shape the agent tools refuse (now-start); fail-closed outcomes for unattended work; a re-check of shared state under the same lock after an await; `App.ui.confirm` success paths calling `revertFn()`. CLAUDE.md's Routines and Self-configuration paragraphs state current behaviour only, with history moved to `agents.md`.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
