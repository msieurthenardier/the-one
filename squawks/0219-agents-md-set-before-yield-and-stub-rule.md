# Squawk 0219: Name "set state before the yield" and the stub rule in agents.md's Project Conventions

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-15
**Completed**: 2026-11-03

## Report
Sortie 04 found two pre-existing pause/resume defects that came from two general patterns, but the lessons are only recorded in an MCP-specific paragraph. Add both to `the_one/agents.md`'s "Project Conventions" as named patterns:
- **set-state-before-yield**: state that a consumer reads after an async generator yields must be set before the yield, because consumers may `break` at that message and code after the yield never runs (origin: `Agent._dispatch_tool_calls`).
- **stub-presets-only-reachable-state**: a test stub may preset a state only if a real-component test shows the real collaborator reaches that state through the same consumer (origin: the `StubAgent` in `tests/test_app_websocket_pause_resume.py`, which preset `_deferred_tool_calls` and hid the bug).
Keep the MCP paragraph, pointing at the new entries.

## Evidence
- `the_one/agents.md` "## Project Conventions" (~l.103); the sortie 04 paragraph "Auth-pause state is set before the yield" (~l.1189, end of "MCP error translation").
- `sorties/04-honest-mcp-sign-in/flight-debrief.md` "Key Learnings".

## Corrective Action
Docs only. `the_one/agents.md` Project Conventions gained `set-state-before-yield` and `stub-presets-only-reachable-state` (origins `Agent._dispatch_tool_calls` and the `StubAgent` in `tests/test_app_websocket_pause_resume.py`). The "Auth-pause state is set before the yield" MCP paragraph is kept and now points at both entries.

## Verification
Done: doc review against `agent.py`/the cited tests; `THE_ONE_TEST_NETNS=1 make test-unit`: 8724 passed, 15 skipped. No new tests.
Original: doc review; `make lint` (no code change).

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches the shell-write hook, `App.safeUrl`, the encryption status count and the credential docs), batch review of the 2026-11-02-2 squawk turnaround, scoped to the diff. Its one blocking finding (0135's Dockerfile `uv venv` line) and the non-blocking items were fixed in a fix pass, which a Haiku Reviewer re-checked: `[HANDOFF:confirmed]`. An Accessibility Reviewer (Sonnet) confirmed the UI changes (0239, 0289, 0290, 0291, 0254). The final gate on the batch tree: `THE_ONE_TEST_NETNS=1 make test-unit` 8738 passed, 15 skipped (219 s, start load 0.48); browser `--parallel 3` `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript` (start load 0.72). The one failure is new squawk 0315, which passed 3 of 3 isolated runs.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02-2` commit on `squawk/turnaround-2026-11-02-2`.
