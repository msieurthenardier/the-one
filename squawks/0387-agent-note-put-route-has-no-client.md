# Squawk 0387: The agent note PUT route has no client

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-19
**Completed**: 2026-11-19

## Report
In Mission 36 Flight 1's HAT, the operator removed note editing from both the agent Notes tab and GleepGlorp's Notes section. Its client chain (`updateNote`) was deleted in the flight-end review fixes. `PUT /api/agents/{name}/notes/{note_id}` stays: the "Edited by you" marker still shows for a note edited that way, and the route is in the name-rule classification. Nothing in the app calls it now.

Pin the route with a direct API test, so it can't rot unnoticed: an edit changes the text and marks the note operator-edited, an unknown id is 404, and an over-limit text is 422. Then note in `the_one/agents.md` that it is API-only. Removing the route instead would change a shared interface, so that path is escalated, not done here.

## Evidence
- `the_one/interfaces/web/api.py:update_agent_note` — `@router.put("/agents/{name}/notes/{note_id}")`.
- `tests/test_api_name_rule.py:76` lists the route.
- `grep -rn "notes/' +\|updateNote" the_one/interfaces/web/static/js`: no caller after `7b059fd3`.
- Flight log, "Flight-end review fixes and gate", item 3.

## Corrective Action
The route already had direct API tests in `tests/test_agent_notes_api.py` (`test_list_edit_delete_clear_flow`: edit changes the text and sets `updated_by == "operator"`, clears the flag; `test_unknown_agent_and_unknown_note_are_404`; `test_edit_errors_are_422_without_echoing_text`: over-limit, empty, duplicate and non-string text; `test_another_agents_note_is_404`; `test_operator_can_edit_and_delete_while_off`). The report's premise (no pin) was wrong, so no test was added; the existing set was confirmed to cover every case named. Added one clause to `the_one/agents.md` (Notes section, "There is no Edit") saying the PUT route is API-only, kept and pinned. Route and behaviour unchanged.

## Verification
Falsified `test_list_edit_delete_clear_flow`: dropping `updated_by` from the route's response made it fail (KeyError); reverted. Final runs: `tests/test_agent_notes_api.py` and `tests/test_api_name_rule.py` pass; ruff check and format clean on touched Python.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet), batch review of squawks 0386-0390
**Verdict**: confirmed (the report's premise was wrong: the route was already pinned; the doc clause matches)
**Commit**: `squawk: turnaround 2026-11-19` on flight/01-gleepglorp-exists-and-answers (PR #380)
