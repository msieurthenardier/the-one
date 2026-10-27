# Squawk 0249: OAuth modal test flakes on the popup wait under parallel load

**Status**: in-progress
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
M31 F6 L01. Root cause found by reading and then reproduced on demand: the test never stubbed `POST /api/oauth/start`. The "Log in" click's real request answers 404 for the made-up source (`api.py:5001-5004`), and `abandon()` (`chat.js:1306-1309`) then closes and drops the popup, so when the 404 beat the test's second `auth_required` frame the popup was never navigated. The sibling `test_popup_closes_on_auth_resolved_event` passed falsely for the same reason (`abandon()` closed the popup anyway). The three unstubbed tests (`test_button_click_opens_popup_with_window_open_features`, `test_second_auth_required_event_navigates_popup_to_consent_url`, `test_popup_closes_on_auth_resolved_event`) now call the existing `_stub_oauth_start(page)`, with a comment each (the first is not racy, only consistent). `chat.js` reads nothing from the `/api/oauth/start` response body (`r.ok` then return), so the stub's `{}` is safe. No assertion changed.

## Verification
- Demonstration (a temporary test, deleted): the unstubbed click held until the real POST answered: `DEMO oauth/start status: 404`, then the popup `closed === true` before the second frame, then `DEMO popup href after second frame: about:blank` and `AssertionError: assert 'about:blank' == 'https://idp.example.com/authorize?state=ST'`.
- Falsification: with the global popup close removed from the `auth_resolved`/`auth_failed` frame handler in `chat.js` (a temporary edit, reverted byte-for-byte; `cmp` clean), `test_popup_closes_on_auth_resolved_event` fails (`Page.wait_for_function: Timeout 10000ms exceeded`). Before the stub it would have passed.
- `tests/browser/test_oauth_modal_flow.py`: 18 passed. `shared` passed in run 2 (rc=0).

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
