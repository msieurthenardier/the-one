# Squawk 0249: OAuth modal test flakes on the popup wait under parallel load

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-23
**Completed**: —

## Report
`tests/browser/test_oauth_modal_flow.py::test_second_auth_required_event_navigates_popup_to_consent_url` intermittently times out its 10 s popup wait in the `shared` lane during a full `--parallel 3` run. Its whole file, and the `shared` lane run alone, pass.
- Seen in Mission 31 Flight 3 leg 02 (recorded as a flake, not squawked).
- Seen again in Mission 31 Flight 4 leg 04d (`shared` stopped under `-x`; the lane re-run alone passed 257/257).

Neither change touched the OAuth modal.

## Evidence
- `tests/browser/test_oauth_modal_flow.py:188` `test_second_auth_required_event_navigates_popup_to_consent_url`: the popup wait times out under load.
- The M31 F3 flight log (leg 02 verification) and the M31 F4 flight log (leg 04d) record both occurrences.

Likely a fixed timeout racing the second `auth_required` event's navigation when the host is busy. Check what the test waits on, and wait on the navigation event itself (or the popup's `url` change) rather than a fixed deadline.

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
