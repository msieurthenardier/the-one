# Squawk 0130: The testid registry extractor misses a quoted `'data-testid':` attrs key

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-07
**Completed**: —

## Report

The UI guard's testid extractor does not see a testid passed as a quoted `'data-testid':` key in an element-builder attrs object. Mission 25 Flight 6 leg 4c had to set the start pages' testids with `setAttribute('data-testid', …)` literals, so that `test_registered_testids_exist_in_source` could see them. Teach the extractor that key form so builders can pass testids in their attrs object.

## Evidence

- `tests/_ui_guard_helpers.py`:
  - `extract_testids` recognises `data-testid="…"` (`_ATTR_LITERAL`), `setAttribute('data-testid', '…')` (`_SETATTR_LITERAL`), and the `_TESTID_NAME` property forms (`_PROP_LITERAL`, `_TESTID_KEY`).
  - It has no form for a quoted `'data-testid': '…'` key.
- `the_one/interfaces/web/static/js/areas/studio.js`: the `setAttribute('data-testid', 'root-heading')` and `'library-empty-' + group.id` literals (about lines 939 and 968).
- The Flight 6 leg 4c flight-log entry, "Testid guard".

## Corrective Action
*(written at completion)*

## Verification
A guard self-test (with the existing extractor tests) proves that a quoted-key literal and a parametric key are both extracted, and that nothing extracted before is lost.

## Sign-Off
*(written at completion)*
