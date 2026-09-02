# Squawk 0034: inbound.py cites the wrong pin test for its inlined literals

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-02
**Completed**: —

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
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
