# Squawk 0377: The PTY send-timeout unit test fails on a loaded host

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-17
**Completed**: —

## Report
`tests/test_pty_session.py::TestUnixPtySession::test_send_timeout_raises_when_no_output` failed once in the sortie 18 debrief's unit run (`THE_ONE_TEST_NETNS=1 make test-unit`, 10222 passed, 15 skipped, 1 failed, host load about 2.0 to 2.7 with other sessions running). Run alone it passed in 1.35 s. The sortie touched no PTY code.

The test turns terminal echo off, sends a command that blocks with no output, and expects `send(..., timeout=0.5)` to raise `asyncio.TimeoutError`. It can only fail if some byte reaches the buffer inside that half second, so the likely cause is ordering under load: the `stty -echo` send returning before echo is really off, or a late byte from it arriving during the next send. Unverified; the failing run's output was not kept.

Expected: the test passes on a loaded host, or fails only when the timeout path is really broken.

Scope note: if the cause is in `UnixPtySession.send` (how it decides the shell is idle) and not in the test, the fix touches product code on the execution path and this squawk is escalated, not grown.

## Evidence
- `tests/test_pty_session.py::TestUnixPtySession::test_send_timeout_raises_when_no_output` — `await s.send("stty -echo")`, then `with pytest.raises(asyncio.TimeoutError): await s.send("read x", timeout=0.5)`.
- `tests/test_pty_session.py` — the sibling test that sends `read x` with `timeout=0.2` uses the same two steps and has the same exposure.
- `sorties/18-mcp-arguments-as-rows/flight-debrief.md`, "Test metrics" — the run, the load and the solo re-run.

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
