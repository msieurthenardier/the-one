# Leg: 03-agent-loop-pause-resume

**Status**: landed
**Flight**: [Lazy OAuth 2.1 + PKCE for Remote MCP Servers](../flight.md)

## Objective

Land the agent-loop pause/resume primitive: extend `ToolResult` with a generic `metadata: dict[str, Any] | None = None` field, refactor `Agent.step` to check for `metadata.is_auth_required` after each tool call (deferring the current and remaining tool calls + exiting the step early when triggered), add `Agent.resume_after_auth()` (no-parameter — reads `self._deferred_tool_calls`) that re-dispatches the deferred list and resumes the paused iteration with the remaining iteration budget, and wire the WebSocket layer in `app.py` to broadcast `auth_required` events from yielded tool messages and to dispatch `auth_resolved` events into `resume_after_auth` via the OAuth-callback route's server-side invocation.

## Context

**Flight design references**:

- §4 (agent-loop pause/resume primitive — generic `metadata` field on `ToolResult`) is the load-bearing spec for this leg. The multi-tool-call iteration semantic is locked there: when tc_B in `[tc_A, tc_B, tc_C]` returns a ToolResult with `metadata.is_auth_required=True`, tc_A's result has already been appended/yielded (rolling back would corrupt history), tc_B is yielded so chat history reflects the auth_required surface, tc_B + tc_C are deferred, the WebSocket event is broadcast, and the step exits.
- §4 also pins the `continue` virtual-signal carve-out: `continue` is handled inline without going through `_execute_tool`; its synthesized ToolResult has `metadata=None` by construction, so the `is_auth_required` check naturally short-circuits.
- §11 lists the L3 touchpoints: `the_one/llm/base.py::ToolResult` (new field), `the_one/agent/core.py::Agent.step` (deferral logic), `the_one/agent/core.py::Agent.resume_after_auth` (new entry point), `the_one/interfaces/web/app.py` (WS event broadcast).

**Critical invariants from the flight design + cycle-1 design review (2026-05-07)**:

1. **`metadata` is generic, NOT OAuth-specific** — the field is on `ToolResult` (provider-neutral LLM type at `the_one/llm/base.py:25`). Cross-provider future use cases (token-usage reporting, MCP elicitation events, custom tool results) can populate it. This leg uses ONLY the `is_auth_required` payload shape.

2. **Iteration counter resumes via `_remaining_iterations` (cycle-1 D8/D9 fix)** — not by tracking "iterations consumed" (which has fence-post bugs). `Agent.__init__` declares `self._remaining_iterations: int = 0`; `step` initializes it to `self.max_iterations`; `_run_iterations` decrements it at the top of each iteration body BEFORE the LLM stream. On pause, `_run_iterations` returns; `_remaining_iterations` already reflects what's left. On resume, `_run_iterations` is re-entered and continues decrementing. Total iterations across step + any number of resumes cannot exceed `max_iterations`.

3. **Pause state is in-memory only, NOT persisted across server restart** — `self._deferred_tool_calls` + `self._remaining_iterations` live on the `Agent` instance. FastAPI restart loses the pause. The DB codec's `messages_to_ui_events` does NOT propagate `metadata` (cycle-1 D2 disposition: pause-state-loss-on-restart is documented; historical paused conversations replay as informational tool_msgs without the Login-required affordance).

4. **`auth_resolved` dispatches resume server-side from the OAuth-callback route (cycle-1 D6 lock)** — NOT via WebSocket-inbound. L2's `oauth_callback` route in `the_one/interfaces/web/api.py` already broadcasts `auth_resolved` to the chat session's WebSocket subscribers. L3 extends the same route to ALSO `asyncio.create_task(_resume_paused_session(session))` after the broadcast. The WebSocket-inbound alternative would loop the event through the chat UI's JS back to the server — unnecessary roundtrip. Server-side invocation is the cleanest pattern given that the route already has the chat session ID via `entry.chat_session_id`.

5. **Reconnect snapshot derives from agent state (cycle-1 D12 + suggestion fix)** — NO new `pending_auth_event` field on `Session`. When a WebSocket subscriber connects and the session's agent has `_deferred_tool_calls is not None`, the connect handler walks `agent.messages` BACKWARDS to find the last message with `msg.role == Role.TOOL AND msg.tool_result.metadata.get("is_auth_required") is True`, and reconstructs the `auth_required` event payload from that message's metadata. One source of truth (the agent), no caching. The walk-backwards (not `messages[-1]`) handles the case where additional non-tool messages were appended between the pause and the reconnect.

6. **The continue virtual signal is unaffected** — its synthesized ToolResult has `metadata=None` by construction. The check is `if result.metadata and result.metadata.get("is_auth_required"):` — None short-circuits cleanly.

7. **`has_real_tool` is dead code in the current `Agent.step` body (cycle-1 D3 finding)** — every branch of the inner `for tc in response.tool_calls` loop sets `has_real_tool = True`, so the `if not has_real_tool: break` line at the loop's tail is unreachable. The L3 refactor drops this dead variable cleanly. Verified: `agent/core.py:107-132` shows the for-loop has only continue + execute branches, both setting True.

**Lazy-path `consent_url` cross-leg seam (cycle-1 D10 disposition)**:

L2's `make_oauth_handlers.redirect_handler` broadcasts `auth_required` with a real `consent_url` because the SDK has constructed the authorize URL by that point. **L3's lazy-path broadcast (from `_process_and_broadcast` reading `tool_result.metadata`) MAY emit `consent_url=None`** because the SDK flow has not yet constructed the URL — L4's `MCPClient.call_tool` raises `MCPAuthRequired` before the SDK's auth provider runs. The chat UI must handle `consent_url=None` by surfacing a "Login required" button that, when clicked, triggers the SDK flow (which then calls L2's `redirect_handler`, which broadcasts a SECOND `auth_required` event with the real `consent_url`). The UI uses the real URL to open the consent tab.

**This is a real cross-leg seam**: L3's broadcast carries no consent URL (lazy); L2's broadcast (triggered by the UI's "Login" click via L4's flow re-trigger) carries the URL. L5's UI handles BOTH events: the first one renders the button; the second one opens the URL. Document this seam in the leg artifact and in `the_one/interfaces/web/app.py`'s commentary; L4 + L5 will lock the trigger mechanism (likely a new POST endpoint that L4 owns).

**DB codec implication**:

`the_one/db/codec.py:15-20` defines `_tool_result_to_dict` (real serializer; the leg modifies this). Deserialization is INLINE in `message_from_dict` at `db/codec.py:46-52` (verified per cycle-1 D1) — there is no `_tool_result_from_dict` function. The leg modifies the inline construction. `messages_to_ui_events` (`db/codec.py:79-102`) does NOT propagate `metadata` (cycle-1 D2 disposition).

**Existing test coverage gap**:

`tests/test_agent.py` exercises only single-tool-call iterations. There are NO tests today with `response.tool_calls = [tc_A, tc_B, tc_C]` (length > 1). L3 adds these multi-tool tests AND the pause/resume tests on top. The 6 existing test methods (`TestNormalFlow.test_text_only_response`, `TestToolExecution.test_tool_call_then_final_response`, `TestContinueSignal.test_continue_not_yielded_to_caller`, `TestMaxIterations.test_stops_at_max_iterations`, `TestToolError.test_tool_exception_yields_error_result`, `TestReset.test_reset_clears_to_system_prompt`) MUST continue to pass UNMODIFIED post-refactor — locked by AC A19.

## Inputs

What exists before this leg runs:

- L0 + L1 + L2 landed (uncommitted; flight branch `flight/05-oauth-pkce-remote-mcp`).
- `the_one/llm/base.py::ToolResult` has 3 fields: `tool_call_id: str`, `content: str`, `is_error: bool = False`.
- `the_one/llm/base.py::Message.tool` factory at lines ~59-61 constructs `Message(role=Role.TOOL, content=result.content, tool_result=result)`.
- `the_one/agent/core.py::Agent.step` (lines 50-132) — iteration loop with streaming + response synthesis + tool-call processing. Continue handling is lines 113-122; `_execute_tool` call is line 125. `has_real_tool` at line 111 is unreachable dead code (cycle-1 D3).
- `the_one/agent/core.py::Agent._execute_tool` (lines 134-144) — returns `ToolResult` on success or with `is_error=True` on exception.
- `the_one/db/codec.py::_tool_result_to_dict` (lines 15-20) — serializer. `db/codec.py::message_from_dict` (lines 46-52) — inline deserialization of ToolResult. `db/codec.py::messages_to_ui_events` (lines 79-102) — UI event projection (does NOT propagate metadata in L3).
- `the_one/interfaces/web/app.py::_process_and_broadcast` (lines 532-645) — Agent.step consumer; emits `tool_call`, `tool_result`, `assistant`, `assistant_chunk`, `system`, `done` events via `_send_to_session`. The TOOL message branch is at lines 612-619. No auth_required handling yet.
- `the_one/interfaces/web/app.py::Session` dataclass (lines 128-159) and `_sessions: dict[str, Session]`. `_send_to_session` at lines 458+. WebSocket dispatch loop at lines 766-919 uses `action = payload.get("action", "message")` (cycle-1 D5: NOT `msg_type`).
- `the_one/interfaces/web/app.py` — `_inflight_tasks` set tracks WebSocket-spawned tasks (lifespan-shutdown cleanup).
- L2's `the_one/mcp/oauth/handlers.py::make_oauth_handlers` broadcasts `auth_required` from inside the SDK auth provider's redirect_handler with a real `consent_url`.
- L2's `the_one/interfaces/web/api.py::oauth_callback` route at lines 850-935 (post-L2 line numbers, recon-confirmed) — already broadcasts `auth_resolved` on success. L3 extends this route to ALSO invoke resume.
- `Agent.step` is called by 4 production sites (cycle-1 D14): `cli.py:69`, `app.py:568` (inside `_process_and_broadcast`), `app.py:673` (selftest), `app.py:687` (selftest). Plus test sites in `tests/test_agent.py`.
- L4 (NOT yet landed) will populate `ToolResult.metadata.is_auth_required` from `MCPClient.call_tool` raising `MCPAuthRequired`. L3's tests use stub tools that return the metadata directly.
- `tests/conftest.py:48-72` provides `FakeLLM(LLMProvider)`. `tests/conftest.py:80-109` provides `StubTool` — tracks `self.calls: list[dict[str, Any]]` (cycle-1 D4: NOT `call_count`).

## Outputs

What exists after this leg completes:

**Modified files**:

- `the_one/llm/base.py` — `ToolResult` gains `metadata: dict[str, Any] | None = None` field. Module imports `Any` from `typing` if not already.
- `the_one/db/codec.py`:
  - `_tool_result_to_dict` extended: include `metadata` key ONLY when the field is non-None (avoid bloating old rows).
  - Inline ToolResult construction in `message_from_dict` extended: read optional `metadata` key with default `None`.
  - `messages_to_ui_events` is INTENTIONALLY NOT modified — `metadata` does not propagate to UI replay events (cycle-1 D2 disposition; pause-state-loss-on-restart is acceptable per the in-memory invariant).
- `the_one/agent/core.py`:
  1. Add `self._deferred_tool_calls: list[ToolCall] | None = None` and `self._remaining_iterations: int = 0` to `__init__` (after `self.messages = ...`).
  2. Refactor `Agent.step` into a thin wrapper (sets up `_deferred_tool_calls=None` + `_remaining_iterations=max_iterations`, appends user message, delegates to `_run_iterations`).
  3. Extract iteration loop body into `_run_iterations(on_chunk) -> AsyncIterator[Message]`. Reads/decrements `self._remaining_iterations` directly (no parameter). Drops the dead `has_real_tool` variable. After dispatching tool calls, checks `if self._deferred_tool_calls is not None: return` to exit on pause.
  4. Extract per-tool-call dispatching into `_dispatch_tool_calls(tcs) -> AsyncIterator[Message]`. Handles continue inline (matches existing semantic — no yield, just append + continue). For real tools: calls `_execute_tool`, appends + yields tool_msg, checks `result.metadata.get("is_auth_required")`, and on True sets `self._deferred_tool_calls = list(tcs[i:])` + returns.
  5. Add `Agent.resume_after_auth() -> AsyncIterator[Message]` (no parameter). Reads `self._deferred_tool_calls`; if None, no-op. Otherwise: clears the field; re-dispatches via `_dispatch_tool_calls`; if re-paused, exits. Otherwise continues by re-entering `_run_iterations`.
  6. `Agent.reset()` clears `_deferred_tool_calls = None` and `_remaining_iterations = 0`.
- `the_one/interfaces/web/app.py`:
  1. `_process_and_broadcast`: replace the existing TOOL-message broadcast block (lines 612-619) with a conditional structure that branches on `msg.tool_result.metadata and msg.tool_result.metadata.get("is_auth_required")`. On True: broadcast `auth_required` (NOT `tool_result`), do NOT broadcast `done`, return early from the function. On False: broadcast `tool_result` as today.
  2. Extract per-message broadcast logic into a private helper `_broadcast_one(session, msg, source)` so both the step path and the resume path use the same code. (The helper already exists implicitly inside `_process_and_broadcast`'s loop body — make it a real private function.)
  3. WebSocket connect handler (find via `subscribers.add(websocket)`): after adding the subscriber, if `session.agent._deferred_tool_calls is not None`, derive the `auth_required` event payload from the LAST tool_msg in `session.agent.messages` whose `tool_result.metadata.is_auth_required is True`, and re-emit to the new subscriber only.
  4. Add a private async helper `_resume_paused_session(session: Session) -> None` that pipes `agent.resume_after_auth()` yielded messages through `_broadcast_one(session, msg, source="resumed")` and broadcasts `done` at the end. This is the function the OAuth-callback route invokes via `asyncio.create_task(...)`.
  5. Track resume tasks in `_inflight_tasks` (or equivalent shutdown-cleanup set) so they get cancelled on lifespan shutdown.
- `the_one/interfaces/web/api.py`:
  1. `oauth_callback` route (success branch, post-L2): AFTER the existing `auth_resolved` broadcast and BEFORE returning the HTML, schedule the resume:
     ```python
     from the_one.interfaces.web.app import _sessions, _resume_paused_session
     session = _sessions.get(entry.chat_session_id)
     if session is not None and session.agent._deferred_tool_calls is not None:
         asyncio.create_task(_resume_paused_session(session))
     ```
     Guard with `if session.agent._deferred_tool_calls is not None` (cycle-1 D13: race protection).
- `tests/test_agent.py` — extends with the new test functions (NOT classes — flat function naming for clarity per cycle-1 D11):
  - `test_pause_at_single_tool_defers_and_exits` — tc_A returns auth_required → step yields tool_msg + exits; `_deferred_tool_calls = [tc_A]`; `_remaining_iterations` reflects what's left.
  - `test_pause_at_tc_b_defers_tc_b_and_tc_c` — `[tc_A, tc_B, tc_C]`; tc_A succeeds (yielded); tc_B auth_required (yielded); tc_C NOT executed (verified via stub `tools.get("tool_c").calls` — empty list).
  - `test_resume_after_auth_redispatches_deferred_and_continues` — given `_deferred_tool_calls=[tc_B, tc_C]`, resume yields tc_B + tc_C tool_msgs then runs at most 1 more LLM iteration (with `_remaining_iterations=1` after the prior pause).
  - `test_resume_after_auth_with_no_deferred_state_is_noop` — `_deferred_tool_calls is None` → resume yields nothing.
  - `test_resume_re_pauses_when_tool_returns_auth_required_again` — resumed tc_B re-pauses; second resume after fresh auth completes the dispatch.
  - `test_continue_signal_metadata_is_none` — assert that the continue-tool branch creates a ToolResult with `metadata=None`; auth_required check short-circuits.
  - `test_reset_clears_pause_state` — after a paused step, `agent.reset()` clears both `_deferred_tool_calls` and `_remaining_iterations`.
  - `test_iteration_counter_resumes_correctly_with_max_iterations_3` — `Agent(max_iterations=3)`; pause after iteration 0 (which did 1 LLM call + tool dispatch); resume re-dispatches tools then enters iteration 2 (decrements remaining from 2 to 1); model returns more tool calls; iteration 3 (remaining 1→0); model returns text-only; loop ends. Total LLM calls = 3.
- `tests/test_db_codec.py` — extend with two new tests:
  - `test_tool_result_metadata_round_trip` — set metadata, serialize via `_tool_result_to_dict`, build new ToolResult via `message_from_dict`'s inline path, assert equality.
  - `test_tool_result_legacy_no_metadata_round_trip` — deserialize old JSON dict without `metadata` key, assert `metadata=None`.
- `tests/test_app_websocket_pause_resume.py` (NEW) — WebSocket-layer tests:
  - `test_yielded_auth_required_tool_msg_broadcasts_auth_required_event_and_skips_done` — stub agent that yields a tool_msg with auth_required metadata; assert broadcast contains `auth_required` event AND no `done` event AND no `tool_result` event for that message.
  - `test_oauth_callback_resume_dispatches_resume_after_auth` — POST-style integration: trigger `oauth_callback` route success path against a session with paused agent; assert `_resume_paused_session` task is created; assert resumed tool_msgs broadcast.
  - `test_websocket_reconnect_replays_auth_required_from_agent_state` — paused session; new WebSocket subscriber connects; receives the cached `auth_required` payload (derived from agent.messages[-1].tool_result.metadata).

**Net new test count target**: 11 new test functions (8 in test_agent.py + 2 in test_db_codec.py + 3 in test_app_websocket_pause_resume.py). A14 sets the bound at exactly 11 functions; if any function is parametrized via `pytest.mark.parametrize` with `n` cases, the count grows accordingly — the implementer records the exact final count in the flight log.

**Net LOC target**: ~120 LOC of production code (~30 in agent/core.py refactor including new methods + reset; ~5 in llm/base.py + ~5 in db/codec.py; ~70 in app.py for the broadcast + helper extraction + reconnect snapshot + resume task; ~5 in api.py oauth_callback extension) + ~280 LOC of tests = ~400 LOC total.

## Acceptance Criteria

- [ ] **A1 — `ToolResult.metadata` field added**: `the_one/llm/base.py::ToolResult` has a fourth field `metadata: dict[str, Any] | None = None`. Verified by `grep -n "metadata: dict" the_one/llm/base.py` → 1 match.

- [ ] **A2 — DB codec round-trip**:
  - `tests/test_db_codec.py::test_tool_result_metadata_round_trip`: construct `ToolResult(tool_call_id="t1", content="ok", metadata={"is_auth_required": True, "source_id": "s1"})`; serialize via `_tool_result_to_dict`; deserialize via the inline path in `message_from_dict` (constructs a `Message` with `tool_result`); assert `result.tool_result.metadata == {"is_auth_required": True, "source_id": "s1"}`.
  - `tests/test_db_codec.py::test_tool_result_legacy_no_metadata_round_trip`: deserialize a `Message` JSON dict whose `tool_result` sub-dict lacks the `metadata` key; assert `result.tool_result.metadata is None`.
  - The serializer writes `metadata` ONLY when non-None; the deserializer reads with `.get("metadata")` default None.

- [ ] **A3 — Single-tool auth_required pauses the step**: a stub tool that returns `ToolResult(tool_call_id="t1", content="auth required", metadata={"is_auth_required": True, "source_id": "s1", "resource_metadata_url": "https://x/.well-known/oauth-protected-resource", "tool_call_id": "t1"})` causes `Agent.step` to:
  1. Yield the auth_required tool_msg (so chat history reflects it).
  2. Set `self._deferred_tool_calls = [tc_A]`.
  3. Have `self._remaining_iterations` reflect the remaining iteration budget (with `max_iterations=20` and pause after iteration 0, value is 19).
  4. Exit the step (`StopAsyncIteration`).
  5. NOT yield a follow-up assistant message.

- [ ] **A4 — Multi-tool deferral semantic** (flight §4 verbatim, cycle-1 D8 fence-post lock): given `response.tool_calls = [tc_A, tc_B, tc_C]` where tc_A succeeds and tc_B returns auth_required, with `Agent(max_iterations=3)`:
  1. tc_A's tool_msg is appended to `self.messages` AND yielded.
  2. tc_B's auth_required tool_msg is yielded.
  3. `self._deferred_tool_calls == [tc_B, tc_C]` (current + remaining; NOT just tc_C).
  4. tc_C's stub tool's `.calls` list remains empty (not invoked).
  5. The step exits without re-entering the iteration loop.
  6. **Iteration counter (cycle-1 D8 lock)**: pause-during-iteration-i CONSUMES iteration i. After pause-on-iteration-0 with `max_iterations=3`, `self._remaining_iterations == 2`. (The LLM call at the top of iteration 0 already happened; the pause comes after the LLM responded; iteration 0 is consumed.)

- [ ] **A5 — `resume_after_auth` re-dispatches deferred + continues loop**: given a stubbed `_execute_tool` that succeeds for both tc_B and tc_C (post-auth tokens are now valid), `await Agent.resume_after_auth()` (no parameter — reads `self._deferred_tool_calls`) yields:
  1. tc_B's success tool_msg.
  2. tc_C's success tool_msg.
  3. The next LLM iteration's response (e.g. an assistant text-only completion).
  4. After resume completes, `self._deferred_tool_calls is None`.

- [ ] **A6 — Iteration counter resumes correctly (cycle-1 D8/D9 worked example)**: with `Agent(max_iterations=3)`, scripted scenario:
  - Iteration 0: LLM returns `[tc_A, tc_B]`. tc_A succeeds (yielded). tc_B returns auth_required (yielded; defer `[tc_B]`). Pause. `_remaining_iterations=2`.
  - Resume: re-dispatch `[tc_B]` (yielded). LLM is invoked for iteration 1 (one of the 2 remaining); LLM returns `[tc_C]`; tc_C succeeds (yielded); iteration 1 done. `_remaining_iterations=1`.
  - Iteration 2: LLM returns text-only response. Loop ends. `_remaining_iterations=0`.
  - Total LLM calls = 3 (matches `max_iterations`). Verified by inspecting `fake_llm.calls` length.

- [ ] **A7 — `resume_after_auth()` is a no-op when no deferred state**: with `_deferred_tool_calls is None`, `resume_after_auth()` returns immediately (`StopAsyncIteration`); does NOT touch `self.messages`; does NOT call the LLM (verified via `fake_llm.calls` empty).

- [ ] **A8 — Resumed tool returns auth_required again** (re-pause): tc_B is re-dispatched but raises auth_required again (token revoked between issuance and use). `resume_after_auth()`:
  1. Yields tc_B's auth_required tool_msg.
  2. Re-defers `[tc_B, tc_C]` (current + remaining).
  3. Exits without dispatching tc_C.
  4. A subsequent `resume_after_auth()` after a fresh auth completes the dispatch.
  - **A8b (head-of-list re-pause, cycle-2 suggestion)**: parametrize the re-pause test to also cover the case `[tc_A_auth, tc_B_auth, tc_C]` where the FIRST tool of a multi-tool iteration returns auth_required. After resume, tc_A succeeds; tc_B then returns auth_required → re-defer `[tc_B, tc_C]`; second resume completes. Confirms the slice-from-current-index pattern works at index 0.

- [ ] **A9 — `continue` virtual signal is unaffected**: a new test `test_continue_signal_metadata_is_none` constructs the continue-tool branch's ToolResult and asserts `metadata is None`. The existing `TestContinueSignal.test_continue_not_yielded_to_caller` test passes UNMODIFIED (locked by A19).

- [ ] **A10 — `Agent.reset()` clears pause state**: after a paused step, `agent.reset()` zeroes `_deferred_tool_calls` to None AND `_remaining_iterations` to 0. The next `step()` call starts fresh.

- [ ] **A11 — WebSocket layer: auth_required broadcast (cycle-1 D7 concrete restructure)**:

  The current `_process_and_broadcast` block at `app.py:612-619` broadcasts a `tool_result` event for every TOOL message. After L3, that block is wrapped:

  ```python
  if msg.role == Role.TOOL and msg.tool_result is not None:
      meta = msg.tool_result.metadata
      if meta and meta.get("is_auth_required"):
          # F5 L3: pause path — broadcast auth_required, skip tool_result + done, exit
          event = {
              "type": "auth_required",
              "source_id": meta.get("source_id"),
              "resource_metadata_url": meta.get("resource_metadata_url"),
              "tool_call_id": meta.get("tool_call_id"),
              "consent_url": meta.get("consent_url"),  # MAY be None on lazy path
          }
          await _send_to_session(session, event)
          return  # exit _process_and_broadcast; do NOT broadcast done
      # ... existing tool_result broadcast (lines 612-619 verbatim) ...
  ```

  Verified by:
  - Stub agent yields a tool_msg with auth_required metadata.
  - Assert mock-`_send_to_session` received exactly 1 call with `{"type": "auth_required", ...}` payload.
  - Assert NO `tool_result` event was broadcast for the auth_required message.
  - Assert NO `done` event was broadcast.

- [ ] **A12 — OAuth-callback route schedules resume (cycle-1 D6 lock)**: `the_one/interfaces/web/api.py::oauth_callback` (success path), AFTER broadcasting `auth_resolved` to the chat session, schedules `asyncio.create_task(_resume_paused_session(session))`. Guarded by `session is not None AND session.agent._deferred_tool_calls is not None` (cycle-1 D13 race protection). Verified by:
  - Set up a session with a paused agent (`_deferred_tool_calls=[tc_X]`).
  - Trigger `oauth_callback` route success path via FastAPI TestClient.
  - Assert `asyncio.create_task` was called (mock-spy on `create_task`).
  - Assert the resume yields tc_X's success tool_msg through `_send_to_session`.

- [ ] **A13 — WebSocket reconnect snapshot derives from agent state (cycle-1 D12 + suggestion lock)**: when a NEW WebSocket subscriber connects to a `Session` whose `agent._deferred_tool_calls is not None`, the connect handler:
  1. Walks `agent.messages` BACKWARDS to find the last message with `msg.role == Role.TOOL AND msg.tool_result.metadata.get("is_auth_required") is True`.
  2. Constructs the same `auth_required` event payload as A11 from that message's metadata.
  3. Sends it to the new subscriber via `await websocket.send_json(payload)`.
  4. Existing subscribers do NOT receive a duplicate.
  - Verified by: paused session with one stale subscriber; add a new subscriber; assert new subscriber receives the auth_required payload while existing subscriber's queue is empty.

- [ ] **A14 — Test count expansion**: `pytest tests/test_agent.py tests/test_db_codec.py tests/test_app_websocket_pause_resume.py -q --timeout=30` is green; new test count N = 11 (8 + 2 + 3). Pre-leg full-suite baseline re-confirmed at implementation start.

- [ ] **A15 — Full-suite regression neutral**: `pytest -q --timeout=30` passes at `<L2 baseline = 1267> + 11 = 1278`, 2 skipped, 1 pre-existing failure (carried from L0/L1; unchanged).

- [ ] **A16 — Lint clean**: `docker compose exec the-one ruff check the_one/llm/ the_one/agent/ the_one/db/codec.py the_one/interfaces/web/app.py the_one/interfaces/web/api.py tests/test_agent.py tests/test_db_codec.py tests/test_app_websocket_pause_resume.py` exits 0 BEFORE `[HANDOFF:review-needed]`.

- [ ] **A17 — Citation audit (per `leg/SKILL.md` Phase 2 item 7)**: BEFORE implementation begins,
  - `grep -rn "ToolResult(" tests/ the_one/` → confirm 10 prior call sites (cycle-1 D15: NOT 12). Verify each remains backward-compatible with the new default-None field.
  - `grep -rn "agent\.step\b\|\.step(" tests/ the_one/` → expect 4 production callers (cli.py:69, app.py:568, app.py:673, app.py:687) + test sites. Verify the public `step` signature is preserved.
  - `grep -rn "_execute_tool\b" tests/ the_one/` → confirm only tests monkey-patch this; no production code calls it externally.
  - `grep -rn "tool_result\." tests/ the_one/` → confirm field-access sites continue to work.
  - Citation audit results recorded in this leg's flight-log entry.

- [ ] **A18 — Pause-state-not-persisted-across-restart documented**: `the_one/agent/core.py::Agent` class docstring (or above the `_deferred_tool_calls` declaration) includes a sentence: "Pause state (`_deferred_tool_calls`, `_remaining_iterations`) is in-memory only — server restart loses the pause and the operator must re-trigger the original tool call. Session replay via `messages_to_ui_events` does NOT propagate `metadata`; historical paused conversations show the auth_required tool_msg as informational text without the Login-required affordance."

- [ ] **A19 — Existing test suite unchanged (cycle-1 suggestion lock)**: all 6 existing test methods in `tests/test_agent.py` (`TestNormalFlow.test_text_only_response`, `TestToolExecution.test_tool_call_then_final_response`, `TestContinueSignal.test_continue_not_yielded_to_caller`, `TestMaxIterations.test_stops_at_max_iterations`, `TestToolError.test_tool_exception_yields_error_result`, `TestReset.test_reset_clears_to_system_prompt`) pass UNMODIFIED. The refactor is invisible to existing tests.

## Verification Steps

- `grep -n "metadata: dict\[str, Any\] | None = None" the_one/llm/base.py` → 1 match in `ToolResult`.
- `grep -n "_deferred_tool_calls\|_remaining_iterations\|resume_after_auth\|_run_iterations\|_dispatch_tool_calls" the_one/agent/core.py` → 5+ matches each appropriate to the new structure.
- `grep -n "_resume_paused_session\|auth_required" the_one/interfaces/web/app.py` → matches for the new helper + branch logic.
- `grep -n "_resume_paused_session\|create_task" the_one/interfaces/web/api.py` → match in `oauth_callback`.
- `docker compose exec the-one ruff check the_one/llm/ the_one/agent/ the_one/db/codec.py the_one/interfaces/web/app.py the_one/interfaces/web/api.py tests/test_agent.py tests/test_db_codec.py tests/test_app_websocket_pause_resume.py` → clean.
- `docker compose exec the-one pytest tests/test_agent.py tests/test_db_codec.py tests/test_app_websocket_pause_resume.py -v --timeout=30` → all green; total count includes 11 new tests.
- `docker compose exec the-one pytest -q --timeout=30` → 1278 passed, 2 skipped, 1 pre-existing failure.

## Implementation Guidance

1. **Extend `the_one/llm/base.py::ToolResult` and `the_one/db/codec.py`**:

   ```python
   # the_one/llm/base.py — extend the dataclass
   from typing import Any  # confirm import is present

   @dataclass
   class ToolResult:
       tool_call_id: str
       content: str
       is_error: bool = False
       metadata: dict[str, Any] | None = None  # F5 L3: generic cross-provider payload
   ```

   **`the_one/db/codec.py`** — read the file first; the leg's prior draft cited a fictitious `_tool_result_from_dict`. Actual structure per cycle-1 D1:

   - Modify `_tool_result_to_dict` (lines 15-20) to include `metadata` only when non-None:
     ```python
     def _tool_result_to_dict(tr: ToolResult) -> dict:
         d = {"tool_call_id": tr.tool_call_id, "content": tr.content, "is_error": tr.is_error}
         if tr.metadata is not None:
             d["metadata"] = tr.metadata
         return d
     ```
   - Modify the INLINE deserialization in `message_from_dict` (lines 46-52):
     ```python
     if "tool_result" in d:
         tr = d["tool_result"]
         tool_result = ToolResult(
             tool_call_id=tr["tool_call_id"],
             content=tr["content"],
             is_error=tr.get("is_error", False),
             metadata=tr.get("metadata"),  # NEW: None when absent (legacy)
         )
     ```
   - **Do NOT modify `messages_to_ui_events`** (lines 79-102). Per cycle-1 D2: `metadata` is intentionally NOT propagated to UI replay events. Document with a comment near the function: `# F5 L3: tool_result.metadata is intentionally NOT projected here. Pause state is in-memory only; replay shows historical auth_required tool_msgs as informational text without the Login-required affordance.`

2. **Refactor `Agent` in `the_one/agent/core.py`** — read the current step body verbatim before refactoring. Drop the dead `has_real_tool` variable (cycle-1 D3).

   **Step 2a: Add instance state to `__init__`**:
   ```python
   def __init__(
       self,
       llm: LLMProvider,
       tools: ToolRegistry,
       system_prompt: str,
       max_iterations: int = 20,
   ) -> None:
       self.llm = llm
       self.tools = tools
       self.system_prompt = system_prompt
       self.max_iterations = max_iterations
       self.messages: list[Message] = [Message.system(system_prompt)]
       # F5 L3: pause/resume state (in-memory only; not persisted — see class docstring)
       self._deferred_tool_calls: list[ToolCall] | None = None
       self._remaining_iterations: int = 0  # set by step; decremented in _run_iterations
   ```

   **Step 2b: Refactor `step` into thin wrapper + `_run_iterations` helper**:
   ```python
   async def step(
       self,
       user_input: str,
       on_chunk: Callable[[str], Awaitable[None]] | None = None,
   ) -> AsyncIterator[Message]:
       """Process a user message through the agent loop."""
       self.messages.append(Message.user(user_input))
       # F5 L3: clear stale pause state at the start of a new step
       self._deferred_tool_calls = None
       self._remaining_iterations = self.max_iterations
       async for msg in self._run_iterations(on_chunk):
           yield msg

   async def _run_iterations(
       self,
       on_chunk: Callable[[str], Awaitable[None]] | None = None,
   ) -> AsyncIterator[Message]:
       """The iteration loop body — extracted for resume_after_auth re-use.

       Reads self._remaining_iterations and decrements at the top of each
       iteration body. On pause (any tool returns metadata.is_auth_required),
       the helper returns; self._remaining_iterations reflects what's left
       for a subsequent resume_after_auth call.
       """
       if await self.llm.supports_tools():
           tool_schemas = (self.tools.all_schemas() or []) + [CONTINUE_SCHEMA]
       else:
           tool_schemas = []

       while self._remaining_iterations > 0:
           self._remaining_iterations -= 1  # F5 L3: consume one iteration up-front

           # ... (existing streaming + response synthesis logic from current
           # agent/core.py:65-105 — verbatim copy; chunk handling, message
           # synthesis, append + yield) ...

           accumulated_text = ""
           final_chunk = None
           async for chunk in self.llm.stream(
               messages=self.messages,
               tools=tool_schemas or None,
           ):
               if chunk.content:
                   accumulated_text += chunk.content
                   if on_chunk:
                       await on_chunk(chunk.content)
               if chunk.is_final:
                   final_chunk = chunk
                   break

           if final_chunk is not None and final_chunk.message is not None:
               response = final_chunk.message
           else:
               response = Message.assistant(
                   content=accumulated_text,
                   tool_calls=(final_chunk.tool_calls if final_chunk else []),
                   usage=(final_chunk.usage if final_chunk else None),
               )
           self.messages.append(response)
           yield response

           if not response.tool_calls:
               return  # text-only response — done

           # F5 L3: dispatch tools through helper; check for pause afterward
           async for tool_msg in self._dispatch_tool_calls(response.tool_calls):
               yield tool_msg

           if self._deferred_tool_calls is not None:
               return  # paused — exit; remaining iterations preserved
   ```

   **Step 2c: Add `_dispatch_tool_calls` helper**:
   ```python
   async def _dispatch_tool_calls(
       self, tcs: list[ToolCall]
   ) -> AsyncIterator[Message]:
       """Dispatch a list of tool calls in order.

       Continue tool: appends but does not yield (matches existing semantic).
       Real tools: calls _execute_tool, appends + yields. If any tool returns
       metadata.is_auth_required, captures current + remaining tool calls
       into self._deferred_tool_calls and exits early.
       """
       for i, tc in enumerate(tcs):
           if tc.name == "continue":
               # Continue virtual signal — preserved verbatim from original
               # core.py:113-122 semantic. The synthesized ToolResult has
               # metadata=None by construction (F5 §4 carve-out).
               reason = tc.arguments.get("reason", "")
               tool_msg = Message.tool(
                   ToolResult(
                       tool_call_id=tc.id,
                       content=reason or "continuing...",
                   )
               )
               self.messages.append(tool_msg)
               # NOTE: continue is NOT yielded — original code only appends
               # and continues the iteration. Preserve this exactly.
               continue

           result = await self._execute_tool(tc)
           tool_msg = Message.tool(result)
           self.messages.append(tool_msg)
           yield tool_msg

           # F5 L3: pause/resume check — must be AFTER append+yield so chat
           # history reflects the auth_required surface
           if result.metadata and result.metadata.get("is_auth_required"):
               self._deferred_tool_calls = list(tcs[i:])
               return  # exit dispatcher; caller checks _deferred_tool_calls
   ```

   **Step 2d: Add `resume_after_auth`** (no parameter, per cycle-1 suggestion):
   ```python
   async def resume_after_auth(self) -> AsyncIterator[Message]:
       """Re-dispatch deferred tool calls after auth_resolved.

       Reads self._deferred_tool_calls; no-op when None. Otherwise:
       1. Clears the deferred field BEFORE re-dispatch (so a re-pause can
          set it again).
       2. Re-dispatches via _dispatch_tool_calls.
       3. If re-paused (deferred set again), exits — caller will receive
          another auth_resolved later.
       4. Otherwise continues the iteration loop with the remaining
          iteration budget.
       """
       if self._deferred_tool_calls is None:
           return  # A7 no-op

       deferred = self._deferred_tool_calls
       self._deferred_tool_calls = None  # consumed before re-dispatch

       async for tool_msg in self._dispatch_tool_calls(deferred):
           yield tool_msg

       if self._deferred_tool_calls is not None:
           return  # re-paused (A8)

       # Continue normally with remaining iteration budget
       async for msg in self._run_iterations():
           yield msg
   ```

   **Step 2e: Update `Agent.reset()`**:
   ```python
   def reset(self) -> None:
       """Reset messages to system prompt only and clear pause state."""
       self.messages = [Message.system(self.system_prompt)]
       self._deferred_tool_calls = None
       self._remaining_iterations = 0
   ```

   **Step 2f: Add class docstring per A18**:
   ```python
   class Agent:
       """The agent loop runtime.

       Pause state (`_deferred_tool_calls`, `_remaining_iterations`) is
       in-memory only — server restart loses the pause and the operator
       must re-trigger the original tool call. Session replay via
       `messages_to_ui_events` does NOT propagate `metadata`; historical
       paused conversations show the auth_required tool_msg as
       informational text without the Login-required affordance.
       """
   ```

3. **Update WebSocket layer in `the_one/interfaces/web/app.py`**:

   **Step 3a + 3b are a single refactor** (cycle-2 clarification): introduce `_broadcast_one(session, msg, source)` AND a small `_auth_required_event_from_metadata(meta) -> dict` helper, then call `_broadcast_one` from `_process_and_broadcast`'s loop. The end-state is described below; do NOT do an inline-wrap-then-extract pass — go straight to the helper.

   **Step 3a: Add a small `_auth_required_event_from_metadata` helper** (consolidates 3 construction sites):

   ```python
   def _auth_required_event_from_metadata(meta: dict[str, Any]) -> dict[str, Any]:
       """Build the `auth_required` WebSocket event payload from ToolResult.metadata.

       Used by _broadcast_one (lazy-path step + resume) and the WebSocket
       reconnect snapshot. Field set must match L2's redirect_handler payload
       in the_one/mcp/oauth/handlers.py — they share the UI consumer.
       """
       return {
           "type": "auth_required",
           "source_id": meta.get("source_id"),
           "resource_metadata_url": meta.get("resource_metadata_url"),
           "tool_call_id": meta.get("tool_call_id"),
           "consent_url": meta.get("consent_url"),  # MAY be None on lazy path
       }
   ```

   **Step 3b: Extract `_broadcast_one(session, msg, source) -> None`** so the resume path uses the same per-message broadcast logic:

   ```python
   async def _broadcast_one(
       session: Session, msg: Message, source: str = "step",
   ) -> None:
       """Translate a single yielded Message to its WebSocket event(s).

       Used by both _process_and_broadcast (step path) and
       _resume_paused_session (resume path). Returns None; the caller
       handles loop control (e.g. early exit on auth_required).
       """
       if msg.role == Role.ASSISTANT:
           # ... existing assistant + assistant_chunk + tool_call event logic
       elif msg.role == Role.TOOL and msg.tool_result is not None:
           meta = msg.tool_result.metadata
           if meta and meta.get("is_auth_required"):
               await _send_to_session(session, _auth_required_event_from_metadata(meta))
               # Caller checks msg.tool_result.metadata for this — return signals "stop"
               return
           await _send_to_session(session, {
               "type": "tool_result",
               "content": msg.tool_result.content[:2000],
               "is_error": msg.tool_result.is_error,
           })
   ```

   Refactor `_process_and_broadcast` to call `_broadcast_one` in its loop. The early-return on auth_required becomes:
   ```python
   async for msg in session.agent.step(user_input, on_chunk=_broadcast_chunk):
       # ... existing pre-broadcast logic ...
       await _broadcast_one(session, msg, source="step")
       if (msg.role == Role.TOOL and msg.tool_result and
               msg.tool_result.metadata and
               msg.tool_result.metadata.get("is_auth_required")):
           return  # paused — do NOT broadcast done
   ```

   **Step 3c: Add `_resume_paused_session(session) -> None`**:
   ```python
   _inflight_resume_tasks: set[asyncio.Task] = set()  # lifespan-shutdown cleanup

   async def _resume_paused_session(session: Session) -> None:
       """Drive Agent.resume_after_auth and broadcast its yields.

       Called from the OAuth-callback route via asyncio.create_task.
       Guarded by the caller — only invoked when the session's agent has
       _deferred_tool_calls != None.
       """
       if session.agent._deferred_tool_calls is None:
           # Race protection (cycle-1 D13): another resume already cleared state
           return
       # cycle-2 NEW-M3: ensure the model is loaded before re-issuing LLM calls.
       # Operator may have walked away long enough for Ollama to evict; without
       # this call, the resume's first stream() hits an unloaded model.
       await _ensure_ollama_model_loaded(session)
       try:
           async for msg in session.agent.resume_after_auth():
               await _broadcast_one(session, msg, source="resumed")
               if (msg.role == Role.TOOL and msg.tool_result and
                       msg.tool_result.metadata and
                       msg.tool_result.metadata.get("is_auth_required")):
                   return  # re-paused — do NOT broadcast done
           await _send_to_session(session, {"type": "done"})
       except Exception:
           logger.exception("Resume after auth failed")
           await _send_to_session(session, {
               "type": "system",
               "content": "Failed to resume after authentication. "
                          "Please re-trigger the action.",
           })
   ```

   **Step 3d: WebSocket reconnect snapshot** (cycle-2 NEW-M2: 5 `subscribers.add(ws)` sites at app.py:795, 808, 821, 860, 896 across `join`, `new_session`, regular-message auto-create branches).

   Add a helper called from EACH `subscribers.add(ws)` site:
   ```python
   async def _send_pause_snapshot_if_needed(
       session: Session, websocket: WebSocket
   ) -> None:
       """Send the cached auth_required event to a NEW subscriber.

       Called immediately after `session.subscribers.add(websocket)` in any
       branch (join, new_session, auto-create). No-op if the session's agent
       has no pending pause. Existing subscribers don't receive duplicates
       because the send targets only the new websocket.
       """
       if session.agent._deferred_tool_calls is None:
           return
       # Walk messages backwards to find the last auth_required tool_msg
       for past_msg in reversed(session.agent.messages):
           if (past_msg.role == Role.TOOL and past_msg.tool_result and
                   past_msg.tool_result.metadata and
                   past_msg.tool_result.metadata.get("is_auth_required")):
               try:
                   await websocket.send_json(
                       _auth_required_event_from_metadata(
                           past_msg.tool_result.metadata
                       )
                   )
               except (RuntimeError, WebSocketDisconnect):
                   # New subscriber's WS broke before snapshot delivery
                   pass
               break
   ```

   Each of the 5 add sites becomes:
   ```python
   session.subscribers.add(websocket)
   await _send_pause_snapshot_if_needed(session, websocket)
   ```

4. **Update `the_one/interfaces/web/api.py::oauth_callback` route** — extend the success branch:
   ```python
   # ... existing success-path code that calls _state.resolve and broadcasts auth_resolved ...

   # F5 L3: schedule resume of the paused agent
   from the_one.interfaces.web.app import _sessions, _resume_paused_session, _inflight_resume_tasks
   resume_session = _sessions.get(entry.chat_session_id)
   if (resume_session is not None
           and resume_session.agent._deferred_tool_calls is not None):
       resume_task = asyncio.create_task(_resume_paused_session(resume_session))
       _inflight_resume_tasks.add(resume_task)
       resume_task.add_done_callback(_inflight_resume_tasks.discard)

   return HTMLResponse("<h1>Login successful</h1><p>You may close this tab.</p>", status_code=200)
   ```

5. **Pre-implementation citation audit** (per `leg/SKILL.md` Phase 2 item 7) — RUN BEFORE writing code:
   - `cd /home/cprch/projects/the-one && grep -rn "ToolResult(" tests/ the_one/`
   - `cd /home/cprch/projects/the-one && grep -rn "agent\.step\b\|\.step(" tests/ the_one/`
   - `cd /home/cprch/projects/the-one && grep -rn "_execute_tool\b" tests/ the_one/`
   - `cd /home/cprch/projects/the-one && grep -rn "tool_result\." tests/ the_one/`
   - Record results in flight log.

6. **Tests** (11 functions across 3 files):

   - **`tests/test_agent.py` extensions** — use the existing `FakeLLM` fixture from conftest.py. For tools, define a small inline helper class `AuthRequiredStubTool` that returns a pre-built ToolResult with metadata. **Use `len(tool.calls) == 0` to assert non-invocation** (cycle-1 D4: NOT `tool.call_count`).

     Skeleton for the deferral test (flat function — NO class wrapper, per cycle-2 NEW-M1):
     ```python
     async def test_pause_at_tc_b_defers_tc_b_and_tc_c() -> None:
         tools = ToolRegistry()
         tool_a = SuccessStubTool(name="tool_a")
         tool_b = AuthRequiredStubTool(name="tool_b")
         tool_c = SuccessStubTool(name="tool_c")
         tools.register(tool_a)
         tools.register(tool_b)
         tools.register(tool_c)
         llm = FakeLLM(responses=[
             Message.assistant(content="", tool_calls=[
                 ToolCall(id="tc_a", name="tool_a", arguments={}),
                 ToolCall(id="tc_b", name="tool_b", arguments={}),
                 ToolCall(id="tc_c", name="tool_c", arguments={}),
             ]),
         ])
         agent = Agent(llm=llm, tools=tools, system_prompt="...", max_iterations=3)
         messages = [m async for m in agent.step("trigger")]

         # Assistant + tc_a tool_msg + tc_b auth_required tool_msg = 3
         assert len(messages) == 3
         assert messages[1].tool_result.tool_call_id == "tc_a"
         assert messages[1].tool_result.metadata is None
         assert messages[2].tool_result.tool_call_id == "tc_b"
         assert messages[2].tool_result.metadata.get("is_auth_required") is True
         assert [tc.id for tc in agent._deferred_tool_calls] == ["tc_b", "tc_c"]
         assert len(tool_c.calls) == 0  # cycle-1 D4: .calls list, not .call_count
         assert agent._remaining_iterations == 2  # max=3, consumed iter 0
     ```

   - **`tests/test_db_codec.py` extensions** — pattern after the existing `test_tool_result` round-trip (at `tests/test_db_codec.py:32`). Construct `Message.tool(ToolResult(..., metadata={...}))`, serialize via `message_to_dict`, deserialize via `message_from_dict`, assert metadata round-trips.

   - **`tests/test_app_websocket_pause_resume.py` (NEW)** — uses the existing FastAPI TestClient pattern. Uses a stub Agent (NOT the real Agent) that yields scripted Messages — drives `_process_and_broadcast` directly. For the OAuth-callback route test, sets up a `_sessions` entry with a paused stub agent and triggers the route via TestClient.

7. **Lint + post-completion checklist**:
   - Run `docker compose exec the-one ruff check ...` on every changed file.
   - Update flight-log.md with: pre-edit SHA, files changed (LOC delta), test count delta (re-confirmed pre-leg baseline first), citation audit results, any deviations.
   - Update flight.md L3 checkbox + leg artifact status to `landed` ONLY (NOT `completed`).
   - **Do NOT commit.** Signal `[HANDOFF:review-needed]`.

## Edge Cases

- **`continue` virtual signal mid-iteration**: if `response.tool_calls = [tc_continue, tc_real_with_auth_required]`, the continue tool's ToolResult has `metadata=None` (short-circuits the auth check); tc_real_with_auth_required's check fires and defers `[tc_real_with_auth_required]`. The continue tool was already appended (no yield). On resume, only tc_real is re-dispatched — the continue is NOT replayed. Correct semantic since continue is a turn-keeping signal, not a real tool. Document in test_agent.py.

- **`_execute_tool` itself raises** (existing error path at agent/core.py:140-143): the existing catch returns `ToolResult(..., is_error=True)` with `metadata=None`. The auth_required check short-circuits cleanly. Existing `TestToolError` test continues to pass unmodified (A19).

- **Resume called BEFORE step ever ran**: `agent.resume_after_auth()` with `_deferred_tool_calls is None` → no-op (A7). Cannot accidentally re-enter `_run_iterations` with stale `_remaining_iterations` because the helper's `while self._remaining_iterations > 0` guard handles `=0` correctly.

- **Agent destroyed while paused (server restart)**: `_sessions` is freshly built; new `Agent` has `_deferred_tool_calls = None`. The `oauth_callback` route's resume guard `if session.agent._deferred_tool_calls is not None` short-circuits → no resume task created. The chat UI receives only the `auth_resolved` event (already broadcast); no resumed messages follow. Operator must manually re-trigger the original action. Documented per A18.

- **Concurrent `auth_resolved` events for the same session** (operator clicks Login button + reconnect snapshot replay both trigger): the second resume sees `_deferred_tool_calls is None` (cleared by the first inside `resume_after_auth` on entry) and is a no-op (race protection in `_resume_paused_session`).

- **Browser refresh during pause + reconnect**: the new WebSocket subscriber receives the `auth_required` event derived from `agent.messages[-1].tool_result.metadata` (A13). Other subscribers don't see a duplicate. Existing pause state on the agent is unchanged.

- **`max_iterations` exhausted during resume**: if `_remaining_iterations == 0` already (the original step exhausted the budget plus a pause snuck in), resume re-dispatches the deferred tool calls then returns immediately (the `_run_iterations` while-loop's guard fails). No further LLM calls. Tested by A6 + A8.

- **`metadata` on a `is_error=True` ToolResult**: legitimate combination — a tool can return `is_error=True` AND `metadata.is_auth_required=True`. Both flags are checked independently; pause logic fires.

- **HTTP `/api/chat` endpoint cannot pause/resume (cycle-1 D18)**: the non-WebSocket chat entry at `app.py:710` returns the full `result_messages` list synchronously. If the agent step pauses mid-iteration, the function returns the partial list (including the auth_required tool_msg as the last entry) and ends. HTTP callers don't get pause/resume — they re-invoke `/api/chat` after auth. Documented as a known limitation; HTTP is not the supported chat surface for OAuth-protected MCP.

- **Lifespan-shutdown task cleanup**: `_inflight_resume_tasks` is added to the shutdown drain in the existing `lifespan` async context manager (alongside the F4 pool drain and the periodic OAuth-state sweep). On shutdown, all resume tasks are cancelled and awaited. Pause state on the agents dies with them.

- **Lazy-path `consent_url=None` (cycle-1 D10 cross-leg seam)**: the `auth_required` event broadcast by L3's pause path MAY have `consent_url=None` because the SDK flow has not constructed the URL yet. L5's UI handles this by rendering a "Login required" button that, when clicked, triggers an L4-owned re-invocation of the SDK flow (via a POST endpoint that L4 will add). The SDK flow then calls L2's `redirect_handler`, which broadcasts a SECOND `auth_required` event with the real `consent_url`. The UI uses the second event's URL to open consent. Document this in the L3 leg's flight-log entry as a seam to lock with L4 + L5.

## Files Affected

- `the_one/llm/base.py` — add `metadata` field to `ToolResult`.
- `the_one/db/codec.py` — extend `_tool_result_to_dict` (line 15-20) + inline ToolResult construction in `message_from_dict` (line 46-52). `messages_to_ui_events` (line 79-102) is INTENTIONALLY UNCHANGED with a comment marking the deliberate omission.
- `the_one/agent/core.py` — refactor step into thin wrapper + `_run_iterations` (drops dead `has_real_tool`); extract `_dispatch_tool_calls`; add `resume_after_auth` (no parameter); add `_deferred_tool_calls` + `_remaining_iterations` instance state; update `reset()`; add class docstring per A18.
- `the_one/interfaces/web/app.py` — wrap TOOL-message broadcast block at lines 612-619 with auth_required pre-check; extract `_broadcast_one` helper; add `_resume_paused_session` + `_inflight_resume_tasks`; add WebSocket-reconnect snapshot derivation; extend lifespan shutdown to cancel resume tasks.
- `the_one/interfaces/web/api.py::oauth_callback` — schedule `_resume_paused_session` task in success branch.
- `tests/test_agent.py` — add 8 new test functions (NOT classes per cycle-1 D11).
- `tests/test_db_codec.py` — add 2 round-trip tests.
- `tests/test_app_websocket_pause_resume.py` — NEW; covers the 3 WebSocket-layer scenarios.
- Flight log + flight checkbox + leg artifact status — flight-final updates per the post-completion checklist.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria A1-A19 verified
- [ ] `docker compose exec the-one ruff check the_one/llm/ the_one/agent/ the_one/db/codec.py the_one/interfaces/web/app.py the_one/interfaces/web/api.py tests/test_agent.py tests/test_db_codec.py tests/test_app_websocket_pause_resume.py` clean
- [ ] `docker compose exec the-one pytest tests/test_agent.py tests/test_db_codec.py tests/test_app_websocket_pause_resume.py -q --timeout=30` green
- [ ] `docker compose exec the-one pytest -q --timeout=30` shows 1278 passed, 2 skipped, 1 pre-existing failure (unchanged) — re-confirmed pre-leg baseline at implementation start
- [ ] Citation audit grep results recorded in flight log (10 ToolResult call sites; 4 production agent.step callers)
- [ ] Update flight-log.md with the L3 progress entry
- [ ] Set leg status to `landed` in this file's header
- [ ] Check off leg L3 in `flight.md`
- [ ] Mark C3 checkpoint `[x]` in `flight.md`
- [ ] Do NOT commit; do NOT update flight status to landed (final autonomous leg of flight is L5 → triggers flight-final review + commit)
- [ ] Signal `[HANDOFF:review-needed]` (NOT `[COMPLETE:leg]`)

## Citation Audit

11 citations verified against current code at leg design time (recon + cycle-1 review 2026-05-07):

- `ToolResult` dataclass — `the_one/llm/base.py:24-28` — OK (3 fields).
- `Message.tool` factory — `the_one/llm/base.py:60-61` — OK.
- `ToolCall` dataclass — `the_one/llm/base.py:17-21` — OK.
- `Agent.step` — `the_one/agent/core.py:50-132` — OK; `has_real_tool` at line 111 is unreachable dead code (cycle-1 D3); refactor drops it.
- `Agent._execute_tool` — `the_one/agent/core.py:134-144` — OK.
- `continue` virtual signal handling — `the_one/agent/core.py:113-122` — OK.
- DB codec ToolResult round-trip — `the_one/db/codec.py:15-20` (serializer `_tool_result_to_dict`) + `the_one/db/codec.py:46-52` (inline deserialize in `message_from_dict`) — OK; cycle-1 D1 confirmed there is NO `_tool_result_from_dict` function; deserialization is INLINE.
- `messages_to_ui_events` — `the_one/db/codec.py:79-102` — OK; intentionally NOT modified by L3 (cycle-1 D2 disposition).
- `_process_and_broadcast` and `_send_to_session` patterns — `the_one/interfaces/web/app.py:532-645` and `:443-458` — OK.
- WebSocket dispatch loop uses `action`, NOT `msg_type` — `the_one/interfaces/web/app.py:766-919` — OK (cycle-1 D5 finding); L3 invokes resume server-side via the OAuth-callback route, NOT via WebSocket-inbound, so this finding is informational only.
- `Session` dataclass — `the_one/interfaces/web/app.py:128-159` — OK; L3 does NOT add a new field (cycle-1 D12 + suggestion lock: derive reconnect snapshot from agent state).
- L2 hooks — `the_one/mcp/oauth/handlers.py::make_oauth_handlers` (broadcasts auth_required with real consent_url) and `the_one/interfaces/web/api.py::oauth_callback` (broadcasts auth_resolved on success at lines 850-935) exist post-L2 — OK.
- 4 production callers of `Agent.step` — `cli.py:69`, `app.py:568`, `app.py:673`, `app.py:687` — OK (cycle-1 D14).
- 10 prior `ToolResult(...)` constructor call sites — verified backward-compatible with the new default-None field (cycle-1 D15: count is 10, NOT 12).
- `StubTool` tracks `self.calls` (a list), NOT `self.call_count` — `tests/conftest.py:80-109` — OK (cycle-1 D4).

No drift unrepaired; no `gone` citations.
