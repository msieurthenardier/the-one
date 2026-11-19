# Squawk 0387: The agent note PUT route has no client

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-19
**Completed**: —

## Report
In Mission 36 Flight 1's HAT, the operator removed note editing from both the agent Notes tab and GleepGlorp's Notes section. Its client chain (`updateNote`) was deleted in the flight-end review fixes. `PUT /api/agents/{name}/notes/{note_id}` stays: the "Edited by you" marker still shows for a note edited that way, and the route is in the name-rule classification. Nothing in the app calls it now.

Pin the route with a direct API test, so it can't rot unnoticed: an edit changes the text and marks the note operator-edited, an unknown id is 404, and an over-limit text is 422. Then note in `the_one/agents.md` that it is API-only. Removing the route instead would change a shared interface, so that path is escalated, not done here.

## Evidence
- `the_one/interfaces/web/api.py:update_agent_note` — `@router.put("/agents/{name}/notes/{note_id}")`.
- `tests/test_api_name_rule.py:76` lists the route.
- `grep -rn "notes/' +\|updateNote" the_one/interfaces/web/static/js`: no caller after `7b059fd3`.
- Flight log, "Flight-end review fixes and gate", item 3.

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
