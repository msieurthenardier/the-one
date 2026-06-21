# Leg: per-tool-call-timeout

**Status**: completed
**Flight**: [Chat-loop Robustness & Control](../flight.md)

## Objective
Bound every tool invocation with a configurable timeout so no single tool call can
wedge a turn (defense-in-depth beyond the web-tool fix).

## Context
- Flight DD2 (wrap point corrected by design review). The agent loop has no
  app-level tool timeout. Wrap the single invocation in `_execute_tool` —
  specifically `await tool.execute(**args)` (~core.py:520) — NOT
  `_dispatch_tool_calls` (tangles with the auth-pause `return`) and NOT
  `_stream_response` (that's the LLM stream, a different class already covered by
  provider httpx timeouts).
- MCP tools already carry a ~30s SDK timeout; this generalizes the guarantee.

## Inputs
- `the_one/agent/core.py` `_execute_tool` (~:507-547): `await tool.execute(**args)`
  at ~:520; existing `except Exception` → `ToolResult(is_error=True, ...)` at ~:540-545;
  `current_tool_call_id` set/reset in `finally`.
- A config source for the timeout (env reader pattern like
  `_get_web_session_idle_ttl` in app.py / WebConfig).

## Outputs
- A timed-out tool returns a tool-error `ToolResult` and the loop continues to `done`.

## Acceptance Criteria
- [ ] `await tool.execute(**args)` in `_execute_tool` is wrapped in
      `asyncio.wait_for(..., TOOL_CALL_TIMEOUT)`.
- [ ] `THE_ONE_TOOL_CALL_TIMEOUT_SECONDS` env var (default 120) controls the ceiling,
      read at call time (monkeypatchable), with a safe fallback on bad values.
- [ ] On `asyncio.TimeoutError`, `_execute_tool` returns
      `ToolResult(is_error=True, content="tool {name} timed out after {N}s")` — the
      turn still terminates with a `done`.
- [ ] `_dispatch_tool_calls` and `_stream_response` are NOT modified.
- [ ] Auth-pause path and degraded-model path are unaffected (still flow through
      `_execute_tool`; a timeout is recorded like any other result).
- [ ] `current_tool_call_id` ContextVar is still reset on timeout (finally runs).

## Verification Steps
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_agent_*.py tests/test_tool*.py -x --timeout 30`
- New test: a stub tool whose `execute` sleeps beyond a low `THE_ONE_TOOL_CALL_TIMEOUT_SECONDS`
  → `_execute_tool` returns a timeout tool-error; the agent loop yields a final message
  with `done` semantics (no hang).
- New test: auth-required tool still produces its pause `ToolResult` (no interference).

## Implementation Guidance
1. Add an env reader `_get_tool_call_timeout()` (default 120, floor e.g. 1) near the
   other agent/config readers; read at call time.
2. In `_execute_tool`, wrap only `await tool.execute(**args)` in `asyncio.wait_for`.
   Add `except asyncio.TimeoutError:` BEFORE/beside the existing `except Exception`
   returning the timeout `ToolResult`. Keep the `finally` reset intact.
3. Tests with a controllable slow stub tool + monkeypatched low timeout.

## Edge Cases
- **Tool raises after partial work**: existing `except Exception` still applies.
- **Timeout vs MCP's own 30s**: MCP fires first for MCP tools; the 120s is a superset.
- **Very low configured timeout in tests**: floor prevents 0/negative.

## Files Affected
- `the_one/agent/core.py` — `_execute_tool` wrap + env reader.
- `tests/` — new test for tool-timeout → tool-error → loop completes.

---

## Post-Completion Checklist
- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (commit deferred to flight-wide review)

---

## Design-Review Corrections (binding)
- **Except ordering**: `except asyncio.TimeoutError` MUST come before
  `except Exception` (TimeoutError is an Exception subclass) and live in the INNER
  try (core.py:517) so the outer `finally` (:546) still resets `current_tool_call_id`.
- **Env reader lives in the agent layer** (core.py or a config module importable
  without a cycle) — do NOT import app.py's `_get_web_session_idle_ttl`.
- **Cooperative-cancel caveat**: `asyncio.wait_for` cancels the wrapped coroutine; a
  tool that swallows `CancelledError` may not return promptly — the guarantee is
  best-effort on tool cooperation. Note in Edge Cases.
