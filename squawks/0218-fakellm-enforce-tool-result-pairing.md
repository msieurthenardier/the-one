# Squawk 0218: `FakeLLM` accepts a history that real providers reject

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-15
**Completed**: —

## Report
`FakeLLM` (the scripted provider most agent-loop tests use) accepts any message history. Real providers reject a history where one `tool_use` id has more than one `tool_result`, or a result with no preceding call. Sortie 04's HAT hit exactly that: `resume_after_auth` left the "auth required" placeholder beside the real result, and the Claude API returned 400 `invalid_request_error`. Every unit test passed because `FakeLLM` did not check. Make `FakeLLM` validate tool-call/result pairing on each call by default (raise a clear assertion naming the id), with an explicit opt-out for tests that build malformed histories on purpose.

## Evidence
- `tests/conftest.py::FakeLLM` (~l.143) — records calls and returns scripted messages; no history validation.
- `sorties/04-honest-mcp-sign-in/flight-log.md` (H2 third re-run: "each tool_use … multiple tool_result blocks"); the fix in `the_one/agent/core.py::resume_after_auth`.

## Corrective Action
*(written at completion)*

## Verification
A unit test that `FakeLLM` raises on a duplicate `tool_result` id and on an orphan result, and passes with the opt-out; `make test-unit` green (any test that trips the check is either a real bug or opts out explicitly, named in the corrective action).

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
