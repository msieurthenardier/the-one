# Squawk 0344: test_cached_no_auth_posture… fails with consent_url_timeout on this host

**Status**: deferred
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-09
**Completed**: —

## Report
On this WSL host, `tests/test_mcp_library_test_missing_values.py::test_cached_no_auth_posture_still_takes_the_branch_and_keeps_its_posture` fails every time. The second Test connection gets `{'error': 'consent_url_timeout'}` after about 15 s, where the test expects `auth_flow_error:` ("Phase B ran (no driver stub)"). It fails the same way on `main`'s pre-flight code (`3dc20800`, a clean worktree with `PYTHONPATH` pointed at it), with and without `THE_ONE_TEST_NETNS=1`. So it is not caused by Mission 35 Flight 2. The test passed in this session's unit run about an hour earlier (9662 passed), so the failure depends on something in the environment that changed. Most likely Phase B's flow waits on a request that now hangs instead of failing fast; nothing listening locally looked unusual (`ss -ltnp`).

**Update (same day):** the test passed in a later full unit run (9674 passed), so the failure is **intermittent** on this host: a flake in the `consent_url_timeout` path, not a constant failure.

## Evidence
- `tests/test_mcp_library_test_missing_values.py:126`: `assert body["error"].startswith("auth_flow_error:"), body` fails with `{'error': 'consent_url_timeout', 'status': 'error'}`.
- `the_one/interfaces/web/api.py:4831`: `return {"status": "error", "error": "consent_url_timeout"}, recordable`.
- Found by Mission 35 Flight 2, at the leg 2 unit run (`flight-log.md`, Flight Director Notes).

## Deferral
The failure is pre-existing and does not touch the flight's scope. Revisit at the flight's closing gate, and if it still fails then, investigate what Phase B waits on, which is the timeout path behind `consent_url_timeout`.

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
