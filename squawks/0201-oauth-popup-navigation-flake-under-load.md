# Squawk 0201: OAuth modal popup-navigation test flakes under load

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-12
**Completed**: 2026-10-13

## Report
`tests/browser/test_oauth_modal_flow.py::test_second_auth_required_event_navigates_popup_to_consent_url` failed once in a full `--parallel 3` browser run, during Mission 29 Flight 2's gate. The popup's `href` was still `about:blank` when the test asserted that it had navigated to the consent URL.

In the same tree, the file then passed in isolation (6/6), and the whole `shared` lane passed on its own (251/251). The failing run was under heavy load: three lanes plus a reviewer's targeted unit run at the same time, and five lanes over budget. So this looks like a timing assertion, not a product defect.

## Evidence
- Failing run: `PARALLEL_RESULT rc=1 total=1128s lanes=9 failed=shared`, with `AssertionError: assert 'about:blank' == 'https://idp.example.com/authorize?state=ST'`.
- Re-runs: the file alone passed 6/6, and `--lane shared` alone passed 251/251, both on the same tree.

## Corrective Action
Test-only. The product path is synchronous (`startLoginFlow` registers the popup in `oauthPopups`; the second `auth_required` handler sets `p.location.href` inline in `chat.js`), so the flake is in the assertion, not a product race. In `tests/browser/test_oauth_modal_flow.py`, the single `page.evaluate` read of the popup's `location.href` in `test_second_auth_required_event_navigates_popup_to_consent_url` is preceded by a bounded `page.wait_for_function(..., timeout=10_000)` for the consent URL. The popup is a JS stub, so Playwright's `expect(popup).to_have_url` does not apply. The same single-shot read of `closed` in `test_popup_closes_on_auth_resolved_event` got the same wait. The final assert stays, so a real failure still reports the actual value. The file's other tests already use `expect` auto-waits or are synchronous reads of values set inside the click.

## Verification
- `ruff check` / `ruff format --check` on the file: clean.
- 5 runs of `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python TEST_TIMEOUT=900 bash scripts/run-tests.sh tests/browser/test_oauth_modal_flow.py -m browser -x --timeout 60`: 6 passed each time (about 12 s).
- One more run with 12 self-started busy-loop python processes (PIDs 122143-122154, killed by PID afterwards): 6 passed in 17.8 s.
- The original flake was load-only and could not be reproduced here, so there is no fail-without-fix demonstration.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet; the batch includes the OAuth sign-in path, 0202), batch review of the 2026-10-13 squawk turnaround
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-10-13` commit on `squawk/turnaround-2026-10-13`. The final gate passed: unit 6287 passed and 14 skipped (the expected count under `THE_ONE_TEST_NETNS=1`); `PARALLEL_RESULT rc=0 total=998s lanes=9 failed=-`, every lane within budget. Flake fix: the original failure was not reproduced, so there is no fails-without-fix demonstration.

## Disposition
**Deferred**: a load-only timing flake, out of scope for Mission 29 Flight 2. Revisit at the next squawk turnaround, or if it recurs in a gate.
