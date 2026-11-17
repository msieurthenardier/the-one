# Squawk 0374: The `real_http_server` browser fixture leaves its output pipe undrained

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-17
**Completed**: —

## Report
Found by squawk 0371's Reviewer (non-blocking there). The fixture that starts the rich MCP fixture server for `test_forget_then_test_brings_the_button_back_at_rest` merges stderr into a stdout pipe and stops reading it after the `PORT` line, so a server that logs enough would fill the pipe and stall mid-test. Its 30 second start deadline is only checked between lines, so a server that prints nothing blocks in `readline()` until the per-test timeout.

Expected: after the port is read, the server's output goes nowhere that can fill (the pattern in `tests/test_mcp_key_server.py` is `stderr=DEVNULL`), and a silent server fails at the fixture's own deadline.

Not observed as a failure; the test passes today.

## Evidence
- `tests/browser/test_flow_studio_mcp_editor_status.py::real_http_server` — `stdout=subprocess.PIPE, stderr=subprocess.STDOUT`, one `readline()` loop that ends at `PORT`, nothing read afterwards.
- `tests/test_mcp_key_server.py` — the existing fixture-server pattern with `stderr=DEVNULL`.

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
