# Squawk 0353: A cancelled turn leaves an unanswered tool call and the chat fails forever

**Status**: completed
**Type**: defect
**Severity**: grounding
**Reported**: 2026-11-13
**Completed**: 2026-11-13

## Report
When a turn is cancelled while a tool call is being dispatched, the assistant message carrying `tool_calls` is already in `agent.messages` and is saved, but no `Role.TOOL` result follows it. Anthropic rejects every later request for that chat with a 400 (`tool_use ids were found without tool_result blocks immediately after`), so the chat can never take another message. Nothing repairs the history on save, on load or when the request is built.

The same hole is reachable by: Stop pressed mid-tool-call; lifespan shutdown mid-tool-call; a cancel after the first of several tool calls in one assistant message; and an auth pause followed by a new user message (`Agent.step` clears `_deferred_tool_calls`, so calls after the paused one in the same assistant message stay unanswered).

Expected: stored and in-memory history never holds an assistant tool call without a result. An unanswered call gets a synthetic error result (for example "interrupted before the tool returned") placed directly after its assistant message, in call order. Chats already stored broken must heal the next time they are loaded or used, with no operator action.

Constraint: `the_one/agent/core.py` is frozen; do the repair outside it (one pure helper over a message list, called where the web layer loads, starts and cancels a turn). If the fix cannot be done without changing `core.py`, stop and report.

## Evidence
- `the_one/interfaces/web/app.py` `_process_and_broadcast`, `except asyncio.CancelledError`: "the next turn starts clean" — it appends at most an `_[interrupted]_` assistant message and saves.
- `the_one/agent/core.py` `_run_iterations`: `self.messages.append(response)` runs before `_dispatch_tool_calls`; a cancel inside `_execute_tool` leaves the call unanswered.
- Restore paths apply no repair: `app.py` `decode_messages(db_session.messages)` in the session restore and `_resync_session_from_db`.
- Observed 2026-11-13 in the operator's app: session `9f906a500c438e5cbe7807efc3558379`, stored index 223 is an assistant message with `toolu_01TVzusBx4HSvGWXgc2AwQVf` (`mcp__Goldfinch__captureScreenshot`), index 224 is the `_[interrupted]_` assistant message, no tool message between. The provider error named `messages.222` (the system message is not in the API list).

## Corrective Action
Added `the_one/agent/history_repair.py::repair_unanswered_tool_calls(messages)`, a pure in-place helper (no I/O, `core.py` untouched). Every assistant tool call with no `Role.TOOL` result anywhere in the list gets a synthetic error result ("The tool call was interrupted before it returned a result.") placed directly after that assistant message's existing results, in call order. A call counts as answered by any tool result with its id (an auth-required placeholder included), so it is idempotent and never duplicates a result.

Called from `the_one/interfaces/web/app.py`: the cancel path before the save (skipped while the agent holds `_deferred_tool_calls`, so `resume_after_auth` still answers a live auth pause itself); the start of `_process_and_broadcast` before `agent.step` (a new step supersedes a pause, and this heals in-memory broken sessions; routine runs use this path); `_restore_session` and `_resync_session_from_db` right after `decode_messages` (stored broken chats heal on load); and `the_one/connectors/inbound.py` after it loads stored history (the connector path does not go through `_process_and_broadcast`).

Not covered: the CLI (`interfaces/cli.py`) keeps history in memory only and cannot be cancelled into a save. `messages_to_ui_events` shows the synthetic result as an ordinary error tool result; no UI change needed or made. The stored chat is rewritten healed on its next save.

## Verification
- `tests/test_history_repair.py` (new, 5 tests): helper cases (single unanswered, second of two, call order, valid list unchanged and idempotent, auth placeholder not duplicated) and a stored broken history (assistant tool call, `_[interrupted]_`, user) healed by `_resync_session_from_db`, with `AnthropicProvider._build_kwargs` giving every `tool_use` its `tool_result` in the next message.
- `tests/test_cancel.py` (3 new tests): cancel mid-tool-call through the real `_process_and_broadcast` saves a result for every call; a live auth pause is not repaired on cancel; the next turn repairs a broken in-memory history.
- Falsified by editing the fix out: cancel repair (test fails: yes), pause guard (test fails: yes), turn-start repair (yes), resync repair (yes). The pure helper tests were not falsified (they test the helper directly).
- `ruff check` and `ruff format --check` on `the_one/ tests/` clean; touched files 26 passed; unit tier result recorded in the report.

## Sign-Off
**Reviewer**: batch Reviewer (Haiku tier: no security-sensitive surface in the diff), independent of the implementers. The helper's placement, call order and idempotence were read in the code; `core.py` is unchanged; the turn-start repair runs before `pre_step_len`; the fingerprint causes no resync loop. The Reviewer's run of the three touched test files: 58 passed, 2 deselected; `ruff check` and `ruff format --check` clean. Non-blocking: the cancel-path test does not assert that the result sits before `_[interrupted]_` (the code places it there). Follow-up candidates, not fixed here: a cancel during `resume_after_auth` has no cancel-path repair (it heals at the next turn start or load), and the CLI is not repaired. Two unit tests fail in the worktree's Python 3.13 environment on unmodified `main` too (`tests/test_fake_platforms_seam.py::test_refuses[http://[::ffff:127.0.0.1]:8490]`, `tests/test_mcp_library_test_missing_values.py::test_cached_no_auth_posture_still_takes_the_branch_and_keeps_its_posture`), so they are not from this change.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-13` commit on `squawk/turnaround-2026-11-13b`
