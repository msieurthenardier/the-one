# Squawk 0034: inbound.py cites the wrong pin test for its inlined literals

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-02
**Completed**: 2026-09-02

## Report

The DD-10 comment block in `the_one/connectors/inbound.py` (~line 62) says its two
inlined literals are pinned by `tests/test_connector_send_tool.py::test_shared_constants_pin_llm_base_literals`,
but the test that actually pins inbound's copies is
`test_shared_constants_pin_inbound_literals` (present at `tests/test_connector_send_tool.py:45`).
One-line comment fix — the tests themselves are correct.

## Evidence

- `the_one/connectors/inbound.py:62` — the drifted citation
- `tests/test_connector_send_tool.py:45` — the actual pin test
- Raised by the Flight 3 debrief (2026-09-02), Developer interview

## Corrective Action

Corrected the DD-10 comment citation at `the_one/connectors/inbound.py:62`: changed
`test_shared_constants_pin_llm_base_literals` to `test_shared_constants_pin_inbound_literals`,
matching the test that actually pins inbound's inlined literals (verified present at
`tests/test_connector_send_tool.py:45`; the previously-cited test also exists, at
`tests/test_connector_send_tool.py:32` — both are legitimate tests, just mismatched to
this citation site). One-line comment-only change.

## Verification

`PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_connector_send_tool.py -x --timeout 30`
— 24 passed in 7.51s, confirming both test names exist and pass.

## Sign-Off
**Reviewer**: independent batch Reviewer (Haiku), squawk/turnaround-2026-09-02
**Verdict**: confirmed
**Commit**: squawk/turnaround-2026-09-02 batch commit (PR follows)
