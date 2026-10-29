# Squawk 0232: the `_activeSection` check in `onSelfConfigChanged` cannot be made to fail by any test

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-22
**Completed**: 2026-10-29

## Report
`agent-editor-controller.js` `onSelfConfigChanged` guards the in-place patch with `self._activeSection === 'agents' && !!d && !!d.handle && ...` (about `:179`). Removing the `_activeSection` term leaves every test green. Leaving Agents for Library destroys the editor first, so the slot-key/identity check and `!!d.handle` already stop the patch. On Chats and Settings, `_activeSection` stays `'agents'`, so the term never blocks there either: a write that resolves there patches the hidden editor in place, which is accepted behaviour. The term reads as a guard it is not. Found at Mission 31 Flight 2's flight review; recommended in its debrief.

## Evidence
- The flight log `### Flight review fixes`, item 6 (the guard-removal check), and the FD note "flight review, cycle 2".
- `tests/browser/test_studio_self_configuration_dirty.py::test_write_resolving_after_leaving_agents_does_not_throw_and_stored_value_shows_on_return`, whose docstring records the gap.

## Corrective Action
Removed the `self._activeSection === 'agents'` term from `onSelfConfigChanged`'s `live` condition (now in `agent-editor-selfconfig.js`) and commented what `live` covers: a write resolving on Chats or Settings patches the hidden editor in place (accepted); leaving Agents for Library destroys the editor.

## Verification
The term is removed and the comment states the Chats/Settings behaviour. The dirty-file tests (`tests/browser/test_studio_self_configuration_dirty.py`, `agent-tabs` lane) pass.

## Sign-Off
**Reviewer**: Flight 3 Batch A Reviewer (Sonnet), independent of the implementing Developer; Accessibility Reviewer (Sonnet) for 0273
**Verdict**: confirmed (the batch's only blocking item, a lint failure in another file, was fixed in the review-fix pass)
**Commit**: the Mission 33 Flight 3 Batch A commit, `flight/3: Batch A - routes moved, caps and retention, recurrence core, date and time controls`
