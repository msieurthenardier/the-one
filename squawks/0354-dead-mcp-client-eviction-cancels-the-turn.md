# Squawk 0354: Evicting a dead MCP client cancels the chat turn

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-13
**Completed**: 2026-11-13

## Report
When an MCP connection dies mid-chat, the next tool call on that server ends the whole turn as if the operator had pressed Stop, instead of reconnecting (or returning a tool error). The operator sees the agent stop for no reason.

Likely mechanism (inferred from the code and matching timestamps, not yet reproduced): `acquire` finds the pooled client dead and calls `_evict_stale` -> `_teardown_entry`, which runs `await asyncio.wait_for(entry.worker, ...)` and handles only `asyncio.TimeoutError`. If the worker task has already finished as cancelled (its transport task group collapsed and cancelled the task that ran `connect`), awaiting it raises `CancelledError` in the caller, which is the chat turn's task. The turn then takes the cancel path.

Expected: a worker that ended cancelled (or with any error) is treated as torn down; `acquire` goes on to its second attempt and the tool call gets a live client or an ordinary error result. A real cancellation of the calling task must still propagate (tell the two apart, for example by checking `entry.worker.cancelled()` / `done()` rather than swallowing every `CancelledError`). First reproduce in a unit test: an entry whose worker task is already cancelled, then `acquire`.

## Evidence
- `the_one/mcp/_pool.py` `_teardown_entry`: `await asyncio.wait_for(entry.worker, timeout=_WORKER_TEARDOWN_TIMEOUT_SECONDS)` with `except asyncio.TimeoutError` only.
- `the_one/mcp/_pool.py` `_entry_worker`: `await entry.evict_event.wait()` then `finally: await client.disconnect()`; a cancellation delivered there ends the task cancelled.
- Operator's app log, 2026-11-13: `16:24:03,616 WARNING the_one.mcp.client: MCPClient transport close failed` (an `ExceptionGroup` from `streamable_http_client`, cause `httpx2.ReadTimeout`), then `16:24:04,913 INFO the_one.mcp._pool: MCP pool entry ('AWS Reinvent Agent', '7a962912fa66') holds a dead client; evicting and reconnecting`. The chat's stored `_[interrupted]_` message is stamped `22:24:04.913` UTC, the same millisecond, and the operator had not pressed Stop.

## Corrective Action
The hypothesis held and was reproduced in a unit test. `_teardown_entry` in `the_one/mcp/_pool.py` now also catches `asyncio.CancelledError` and any worker `Exception` from the `wait_for` on the worker. A `CancelledError` is absorbed only when the calling task is not itself being cancelled (`current_task().cancelling() == 0`) and the worker task is done; otherwise it is re-raised. A worker that ended cancelled or with an error counts as torn down, so `acquire` goes on to its second attempt. `_evict`, `_evict_stale`, `_evict_all_for_source` and shutdown drain share the helper and keep their contracts.

## Verification
- Reproduced: with an entry whose worker had already finished cancelled, and with a worker that ended cancelled while awaited, `acquire` raised `CancelledError` into the caller. Both new tests failed before the fix and pass after it.
- A third new test (a real cancel of the caller while parked in teardown still propagates) passes before and after the fix; it fails when the `cancelling()`/`done()` guard is edited out, so it pins the guard.
- `tests/test_mcp*.py`: 733 passed, 16 deselected. `ruff check` and `ruff format --check` clean on `the_one/` and `tests/`.
- Unrelated: `tests/test_mcp_library_test_missing_values.py::test_cached_no_auth_posture_still_takes_the_branch_and_keeps_its_posture` fails in this worktree (`consent_url_timeout` instead of `auth_flow_error:`), with and without the `_pool.py` change. Not caused by this squawk.

## Sign-Off
**Reviewer**: batch Reviewer (Haiku tier: no security-sensitive surface in the diff), independent of the implementers. A real cancel of the caller and an unfinished worker both re-raise; `KeyboardInterrupt` and `SystemExit` are not caught. The Reviewer's run of the three touched test files: 58 passed, 2 deselected; ruff clean.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-13` commit on `squawk/turnaround-2026-11-13b`
