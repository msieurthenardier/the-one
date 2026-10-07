# Squawk 0130: The testid registry extractor misses a quoted `'data-testid':` attrs key

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-07
**Completed**: 2026-10-07

## Report

The UI guard's testid extractor does not see a testid passed as a quoted `'data-testid':` key in an element-builder attrs object. Mission 25 Flight 6 leg 4c had to set the start pages' testids with `setAttribute('data-testid', …)` literals, so that `test_registered_testids_exist_in_source` could see them. Teach the extractor that key form so builders can pass testids in their attrs object.

## Evidence

- `tests/_ui_guard_helpers.py`:
  - `extract_testids` recognises `data-testid="…"` (`_ATTR_LITERAL`), `setAttribute('data-testid', '…')` (`_SETATTR_LITERAL`), and the `_TESTID_NAME` property forms (`_PROP_LITERAL`, `_TESTID_KEY`).
  - It has no form for a quoted `'data-testid': '…'` key.
- `the_one/interfaces/web/static/js/areas/studio.js`: the `setAttribute('data-testid', 'root-heading')` and `'library-empty-' + group.id` literals (about lines 939 and 968).
- The Flight 6 leg 4c flight-log entry, "Testid guard".

## Corrective Action
`tests/_ui_guard_helpers.py` gains `_KEY_LITERAL` and `_KEY_PARAMETRIC`: a quoted `'data-testid':` / `"data-testid":` attrs key (key quotes paired by backreference) with a single-quoted value. A literal value lands in `literals`; a `'prefix-' + ...` value lands in `parametric`, mirroring the `setAttribute` patterns exactly. `extract_testids` runs both. The two `setAttribute('data-testid', ...)` sites in `studio.js` were left unchanged (optional; their elements are not built from an attrs object in a mechanical way), so no JS changed.

## Verification
New tests in `tests/test_ui_mechanism_testids.py`: single- and double-quoted keys and a prefix-concatenation case are extracted; a negative snippet (`data_testid:`, `'data-testid-x':`, `getAttribute('data-testid')`, a non-literal value) yields nothing; and a bite test shows the pre-0130 patterns find nothing in the same snippet while `_KEY_LITERAL` does. `tests/test_ui_mechanism_testids.py` + `tests/test_ui_guards.py`: 25 passed. `make test-unit`: 5458 passed, 10 skipped, 0 failed (no self-configuration flakes). ruff check and format --check clean. Original intent: A guard self-test (with the existing extractor tests) proves that a quoted-key literal and a parametric key are both extracted, and that nothing extracted before is lost.

## Sign-Off

**Reviewer**: independent batch Reviewer (Haiku tier: no credential, gate, sandbox or self-configuration-identity surface in the diff); `make test-unit` 5496 passed, 10 skipped; static guards 265 passed; ruff clean
**Verdict**: confirmed (`[HANDOFF:confirmed]`)
**Commit**: `squawk: turnaround 2026-10-07` on branch `squawk/turnaround-2026-10-07`
