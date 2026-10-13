# Squawk 0201: OAuth modal popup-navigation test flakes under load

**Status**: deferred
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-12
**Completed**: —

## Report
`tests/browser/test_oauth_modal_flow.py::test_second_auth_required_event_navigates_popup_to_consent_url` failed once in a full `--parallel 3` browser run, during Mission 29 Flight 2's gate. The popup's `href` was still `about:blank` when the test asserted that it had navigated to the consent URL.

In the same tree, the file then passed in isolation (6/6), and the whole `shared` lane passed on its own (251/251). The failing run was under heavy load: three lanes plus a reviewer's targeted unit run at the same time, and five lanes over budget. So this looks like a timing assertion, not a product defect.

## Evidence
- Failing run: `PARALLEL_RESULT rc=1 total=1128s lanes=9 failed=shared`, with `AssertionError: assert 'about:blank' == 'https://idp.example.com/authorize?state=ST'`.
- Re-runs: the file alone passed 6/6, and `--lane shared` alone passed 251/251, both on the same tree.

## Corrective Action
*(written at completion)* A likely fix is to make the test wait for the popup's URL to change (a Playwright `expect(...).to_have_url` with a timeout, or `wait_for_url`) instead of reading `href` once.

## Verification

## Sign-Off
*(written at completion)*

## Disposition
**Deferred**: a load-only timing flake, out of scope for Mission 29 Flight 2. Revisit at the next squawk turnaround, or if it recurs in a gate.
