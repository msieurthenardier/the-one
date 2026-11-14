# Squawk 0344: test_cached_no_auth_posture… fails with consent_url_timeout on this host

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-09
**Completed**: 2026-11-14

## Report
On this WSL host, `tests/test_mcp_library_test_missing_values.py::test_cached_no_auth_posture_still_takes_the_branch_and_keeps_its_posture` fails every time. The second Test connection gets `{'error': 'consent_url_timeout'}` after about 15 s, where the test expects `auth_flow_error:` ("Phase B ran (no driver stub)"). It fails the same way on `main`'s pre-flight code (`3dc20800`, a clean worktree with `PYTHONPATH` pointed at it), with and without `THE_ONE_TEST_NETNS=1`. So it is not caused by Mission 35 Flight 2. The test passed in this session's unit run about an hour earlier (9662 passed), so the failure depends on something in the environment that changed. Most likely Phase B's flow waits on a request that now hangs instead of failing fast; nothing listening locally looked unusual (`ss -ltnp`).

**Update (same day):** the test passed in a later full unit run (9674 passed), so the failure is **intermittent** on this host: a flake in the `consent_url_timeout` path, not a constant failure.

## Evidence
- `tests/test_mcp_library_test_missing_values.py:126`: `assert body["error"].startswith("auth_flow_error:"), body` fails with `{'error': 'consent_url_timeout', 'status': 'error'}`.
- `the_one/interfaces/web/api.py:4831`: `return {"status": "error", "error": "consent_url_timeout"}, recordable`.
- Found by Mission 35 Flight 2, at the leg 2 unit run (`flight-log.md`, Flight Director Notes).

## Deferral
The failure is pre-existing and does not touch the flight's scope. Revisit at the flight's closing gate, and if it still fails then, investigate what Phase B waits on, which is the timeout path behind `consent_url_timeout`.
Completed in the 2026-11-14 turnaround.

## Corrective Action
Cause found (test-side). The second Test connection reaches Phase B, whose driver (`_drive_flow_test` in `api.py`) opens a real `httpx2.AsyncClient` connection to the source URL; it does not use the ASGI test seam. The test's URL is `http://localhost/mcp`, so the driver does a real TCP connect to localhost:80. On this WSL host that connect accepts and stalls (`bash /dev/tcp/localhost/80` hangs until a timeout, and the debug log ends at `connect_tcp.started host='localhost' port=80`), so nothing fails fast and the 15 s `consent_url_timeout` fires. The product code is as intended. The fix: before the second Test, the test points the source's URL at a loopback port it bound and released (`http://127.0.0.1:<closed port>/mcp`), so the driver is refused at once and returns `auth_flow_error:` as the test expects.

## Verification
The test failed 3 of 3 before (about 15.7 s each) and now `tests/test_mcp_library_test_missing_values.py` passes (18 tests) 5 runs in a row in about 1 s each. Falsified in effect by the before-runs. The test still needs no listener on a random loopback port, which a freshly released ephemeral port makes a safe assumption.

Gate (Flight Director, full gate on the final tree, 2026-11-14): unit tier 10155 passed, 15 skipped (under `THE_ONE_TEST_NETNS=1`); browser `PARALLEL_RESULT rc=0 total=2253s lanes=20 failed=-`.

## Sign-Off
**Reviewer**: independent Reviewer (Sonnet tier, because the batch diff touches the MCP sandbox error path), who confirmed the batch diff with `[HANDOFF:confirmed]` on 2026-11-14 with no high or medium issues.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-14` commit on `squawk/turnaround-2026-11-14`
