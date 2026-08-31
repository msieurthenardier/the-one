# Squawk 0027: AsyncMock "never awaited" RuntimeWarnings in TestToolFiltering

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-08-31
**Completed**: —

## Report

The Flight 1 debrief's fresh `make test-unit` run (2026-08-31, main @ `138025e`) shows two
`RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited` warnings in
`tests/test_factory.py::TestToolFiltering` (MCP tool-filtering tests). The file's connector edits
in Flight 1 did not touch these tests, so this is likely pre-existing AsyncMock hygiene debt —
but flight logs don't record warnings, so provenance is unconfirmed. Investigate and fix the mock
setup so the suite runs warning-clean in this file (an unawaited mock coroutine can mask a real
call-shape mismatch).

## Evidence

- `make test-unit` debrief run: `3561 passed, 10 skipped, 542 deselected, 19 warnings in 370.54s`
- `tests/test_factory.py::TestToolFiltering` — the two warning sites
- Raised by the Flight 1 debrief (2026-08-31), Developer interview, Test Metrics

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
