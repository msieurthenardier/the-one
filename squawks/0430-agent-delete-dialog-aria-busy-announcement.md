# Squawk 0430: Check that the agent-delete dialog's "Deleting…" status is announced

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-26
**Completed**: —

## Report
While the delete request runs, the agent-delete dialog sets a `role="status"` text to "Deleting…" and also sets `aria-busy="true"` on the dialog. Some screen readers defer or suppress live-region announcements inside an `aria-busy` ancestor, so the status may never be spoken. The text is set before the attribute, so it is probably queued first. This is unverified. Raised by the sortie 20 accessibility re-review as advisory (WCAG 4.1.3); see `sorties/20-deleting-an-agent-deletes-its-chats/flight-debrief.md`.

## Evidence
- `the_one/interfaces/web/static/js/areas/studio/agent-delete-dialog.js::setRunning` (around `:87`): `dlg.setAttribute('aria-busy', 'true')` beside the status text.

## Corrective Action
*(written at completion)*

Suggested direction: check with NVDA and Chrome (and Orca if available). If the status is not spoken, drop `aria-busy` and rely on the status text alone, then update the assertion in `tests/browser/test_flow_agents_delete_dialog.py::test_running_moves_focus_to_cancel_announces_and_failure_focuses_delete`.

## Verification
A screen-reader observation recorded here. If `aria-busy` is dropped, the dialog test passes with the changed assertion.

## Sign-Off
*(written at completion)*
**Reviewer**: —
**Verdict**: —
**Commit**: —
