# Squawk 0232: the `_activeSection` check in `onSelfConfigChanged` cannot be made to fail by any test

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-22
**Completed**: —

## Report
`agent-editor-controller.js` `onSelfConfigChanged` guards the in-place patch with `self._activeSection === 'agents' && !!d && !!d.handle && ...` (about `:179`). Removing the `_activeSection` term leaves every test green. Leaving Agents for Library destroys the editor first, so the slot-key/identity check and `!!d.handle` already stop the patch. On Chats and Settings, `_activeSection` stays `'agents'`, so the term never blocks there either: a write that resolves there patches the hidden editor in place, which is accepted behaviour. The term reads as a guard it is not. Found at Mission 31 Flight 2's flight review; recommended in its debrief.

## Evidence
- The flight log `### Flight review fixes`, item 6 (the guard-removal check), and the FD note "flight review, cycle 2".
- `tests/browser/test_studio_self_configuration_dirty.py::test_write_resolving_after_leaving_agents_does_not_throw_and_stored_value_shows_on_return`, whose docstring records the gap.

## Corrective Action
*(written at completion)*

## Verification
- The term is removed, or renamed and commented to say exactly what it covers. The existing dirty-file tests pass, and the comment states that a write resolving on Chats or Settings patches the hidden editor in place.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
