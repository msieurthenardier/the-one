# Squawk 0360: a comment in app.py still names the "Tool activity" accordion

**Status**: deferred
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-14
**Completed**: —

## Report
A comment in `the_one/interfaces/web/app.py` describes where the chat puts a tool result with the old name. Since sortie 16 a tool result goes into the turn's work group (`App.ui.turnWork`); there is no "Tool activity" accordion any more. The comment is the only place left in the product code that names it. No behaviour is affected.

## Evidence
- `the_one/interfaces/web/app.py::_build_session_joined_ok`, the comment above `"platform": session.platform` — "…needed to gate promoting a delivered tool result to a top-level bubble instead of collapsing it into the "Tool activity" accordion."
- Sortie 16 left it alone on purpose: its charter is browser-only and it changed no Python (`sorties/16-turn-work-group/flight-log.md`, Flight Director Notes, "Left out of scope on purpose").

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*

## Disposition
**Deferred**: comment-only, and in Python, outside sortie 16's browser-only charter — revisit at the next squawk turnaround after sortie 16 merges.
