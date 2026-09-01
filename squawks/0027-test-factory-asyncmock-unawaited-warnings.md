# Squawk 0027: AsyncMock "never awaited" RuntimeWarnings in TestToolFiltering

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-08-31
**Completed**: 2026-09-01

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

Root cause (confirmed by reproduction, not guessed): in
`TestToolFiltering.test_builtins_whitelist_does_not_strip_mcp_tools` and
`test_disabled_tools_still_gates_mcp_at_build`, the `AgentConfig` sets
`mcp_source_ids=["github"]` so `AgentFactory.create()` exercises both the
MCP tool-attach path (`factory.mcp_provider = StubMCPProvider()`, the thing
these tests actually mean to test) *and* an unrelated path,
`_build_source_index()` (`the_one/agent/factory.py`), which builds the
`search_tools` synthetic index for every attached source. Neither test
patches `MCPSourceRepository`, so `_build_source_index` runs the **real**
`MCPSourceRepository.get()` (`the_one/db/repositories.py:501`,
`async with self.conn.execute(...) as cur:`) against `self.conn` — the
`factory` fixture's un-specced `AsyncMock` connection stand-in. An
un-specced `AsyncMock`'s auto-created `.execute(...)` attribute is itself
an `AsyncMock`, so calling it returns a *coroutine object*, not something
that supports the async-context-manager protocol. `async with <coroutine>`
raises `TypeError: 'coroutine' object does not support the asynchronous
context manager protocol` immediately, and the coroutine created by that
`.execute(...)` call is dropped without ever being awaited — the source of
the `AsyncMockMixin._execute_mock_call was never awaited` warning.
`_build_source_index`'s intentionally broad
`except (KeyError, Exception): continue` (there to skip a since-deleted
MCP source without failing agent creation) swallows this TypeError
silently, so the tests still passed — but on an accidental mock-shape
crash rather than the code path they were meant to hit.

Fix (test file only, `tests/test_factory.py`): in both tests, patch
`the_one.db.repositories.MCPSourceRepository` (matching the pattern
already used elsewhere in this file for `LLMProviderRepository` /
`ToolConfigRepository`) with a mock whose `.get()` raises `KeyError`,
wrapping the `await factory.create(...)` call. This routes
`_build_source_index` through its actual intended "deleted/unknown
source — skip silently" branch (the behavior the comment at
`factory.py:71-74` already documents) instead of an unrelated mock-shape
TypeError, so no coroutine is created-and-dropped and the test still
asserts the same MCP-filtering behavior via `StubMCPProvider` as before.
No production code changed — `_build_source_index`'s broad except is
pre-existing behavior, out of scope here.

## Verification

`PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_factory.py -x --timeout 30 -W error::RuntimeWarning`
→ `24 passed in 0.62s`, no warnings (a stray `RuntimeWarning` would now
fail the run outright under `-W error::RuntimeWarning`, so this is a
positive proof of warning-cleanliness, not just an absence-of-log-line
check). Confirmed via reproduction first: an isolated repro script
(`await get_connection()` → `AsyncMock` connection → `conn.execute(...)`
→ coroutine → `async with` TypeError) reproduced the exact
`AsyncMockMixin._execute_mock_call was never awaited` warning text before
the fix, confirming the causal chain rather than assuming it from the
stack trace alone.

## Sign-Off
**Reviewer**: independent batch Reviewer (Sonnet), squawk/turnaround-2026-09-01
**Verdict**: confirmed
**Commit**: squawk/turnaround-2026-09-01 batch commit (PR follows)
