# Flight: Chat-loop Robustness & Control

**Status**: completed
**Mission**: [LLM Provider Layer Hardening & Capability Completeness](../../mission.md)

## Contributing to Criteria
This flight does not advance a *named* provider-layer success criterion. It is a
robustness addition the operator scoped into M16's wrap-up after a live repro this
session: while exercising the providers (Sonos Agent on the installed 8484
instance, claude-sonnet-4-6 + Sonos MCP + web tools), the chat loop **hung
indefinitely** and there was no way to recover. The failure is provider-agnostic
(also seen with ministral-3:8b), so it lives in the agent-loop / tool layer, not a
provider. Recorded against the mission's Known-Issues surface.

- [ ] Chat turns cannot hang indefinitely on a tool call (web-stream fetch or any
      other), and the operator can always interrupt an in-flight turn.

---

## Pre-Flight

### Objective
Eliminate the indefinite-hang class in the chat loop and give the operator control
over in-flight turns. Concretely: (1) fix the `http_request`/`fetch_url` web tools
so a continuous-stream URL can no longer wedge a turn; (2) add a per-tool-call
timeout so no single tool can stall a turn indefinitely; (3) add an interrupt/cancel
control (WS action + backend task cancellation + frontend button); (4) allow the
operator to queue one message while a turn is running (send-while-thinking). Net
result: a turn always terminates (success, tool-error, timeout, or cancel) and the
UI is never stranded.

### Open Questions
- [x] **Web-tool fix shape** → DD1. Resolved: stream + in-loop byte cap (mirror the
      existing `download_file` pattern) + total deadline + media content-type
      short-circuit.
- [x] **Loop-timeout scope** → DD2. Resolved (operator): per-tool-call timeout,
      env-configurable.
- [x] **Cancel partial-output semantics** → DD3. Resolved (operator): keep the
      partial assistant message, marked interrupted.
- [x] **Queue depth for send-while-thinking** → DD4. Resolved (operator): exactly
      one queued message.
- [ ] **`web_search` returns "No results found" on 8484** — every search query in
      the repro returned nothing, which made the model flail and *guess* URLs
      (raising the odds of fetching a stream). Is the search backend unconfigured
      on the installed instance, or is the tool broken? Resolve in the
      verify/recon leg; may split to a follow-up if it's purely operator config.

### Design Decisions

**DD1 — Web tools stream the body with an in-loop byte cap (mirror `download_file`)**:
`http_request` (web.py:125) and `fetch_url` (web.py:190) currently do
`await client.request()/get()`, which buffers the **entire** body before returning;
the 1 MB cap (`WebConfig.response_size_cap_bytes`, default `1_048_576`) and the
binary-content check are applied **after** the read. A continuous audio/video stream
URL never completes the body, so the await never returns. httpx's `timeout` is
per-operation (the read timeout is the max gap *between* bytes, default 30s, ceiling
120s) — a stream sends bytes continuously, so it never trips. Fix: refactor both
tools to use `async with client.stream(...)` + `async for chunk in resp.aiter_bytes()`
and enforce the byte cap **during** iteration — exactly the pattern
`download_file` already uses (web.py:295-303). Additionally wrap the whole fetch in
a **total wall-clock deadline** (`asyncio.wait_for`, ≤ `timeout_seconds_max`) as
belt-and-suspenders against a slow-trickle stream that stays under the cap, and
**short-circuit on response `Content-Type`** of `audio/*`, `video/*`, or
`application/octet-stream` (available from `resp.headers` before reading the body
when streaming) → return a helpful "looks like a media stream, not fetchable as
text — this is a playable URL" message.
- Rationale: kills the hang at its source, reuses an in-repo precedent, and turns a
  stream URL into a *useful* signal (the agent was hunting for exactly such URLs).
- Trade-off / **correction (design review)**: `fetch_url`'s HTML path
  (`readability.Document` + `markdownify`, web.py:202-208) needs the full decoded
  text. Two real changes vs "same as today": (a) after a streamed read you CANNOT use
  `resp.text`/`resp.content` (raises `StreamConsumed`) — accumulate chunks into a
  `bytearray` and decode (`errors="replace"`, mirroring `_truncate_response`);
  (b) `_truncate_response` is **tail-preserving**, wrong for HTML (a tail-cut
  document has no `<head>` / dangling tags → readability extracts garbage), so the
  HTML path must **head-preserve** the capped bytes (first N) before `Document(...)`.
  Today truncation runs on the markdown post-extraction, so this is a genuine
  behavior change — add a large-HTML regression test asserting sane extraction.

**DD2 — Per-tool-call timeout at `_execute_tool`** *(wrap point corrected by design
review)*: Wrap the single tool invocation in `the_one/agent/core.py` `_execute_tool`
— specifically `await tool.execute(**args)` (~core.py:520) — in
`asyncio.wait_for(..., TOOL_CALL_TIMEOUT)`, env `THE_ONE_TOOL_CALL_TIMEOUT_SECONDS`
(default 120). Add an `except asyncio.TimeoutError` clause beside the existing
`except Exception` (~core.py:540-545) that returns a `ToolResult(is_error=True,
content="tool X timed out after Ns")`, so `_run_iterations` records it and the turn
terminates cleanly. **Do NOT wrap `_dispatch_tool_calls` or `_stream_response`** —
the former tangles with the auth-pause `return`, and the latter is the *LLM* stream
(a different failure class, already covered by provider httpx timeouts), not a tool
call. The auth-pause and degraded-model paths both flow through `_execute_tool`, so a
timeout there is recorded like any other result with no special handling. MCP tools
already carry a ~30s SDK timeout; this generalizes the guarantee to all tools.
- Rationale: defense-in-depth — DD1 fixes the known offender; this bounds the whole
  class. Keeps the per-session lock from being held forever.
- Trade-off: a legitimately long single tool call (>120s) is cut; the ceiling is
  env-tunable, and 120s already matches the web-tool max.

**DD3 — Interrupt/cancel via WS action + task cancellation, partial output kept**:
Add a WS `{action: "cancel"}` handler. Track the current in-flight task per session
(today `_inflight_tasks` is an unkeyed set, app.py:414) so cancel can find and
`.cancel()` the right task; cancellation raises `CancelledError` inside
`_process_and_broadcast`, which already re-raises it (app.py:455-458), releasing the
session lock.
**Partial-output persistence — HIGH, harder than it looks (design review).** Streamed
text lives only in `_stream_response`'s local `accumulated_text` (core.py:368); the
assistant `Message` is appended to `session.agent.messages` ONLY when the loop yields
it (core.py:275). If cancel fires mid-`llm.stream` (core.py:370), the loop raises
before yielding → the partial text is lost and `_save_session_to_db` (which encodes
`agent.messages`, app.py:1005) has nothing to persist. So the cancel-backend leg MUST:
(1) capture the streamed text at cancel time — accumulate it in the `_broadcast_chunk`
closure (or expose partial text from the agent); (2) in an `except asyncio.CancelledError`
block inside `_process_and_broadcast`, synthesize and append an interrupted
`Message.assistant(...)` to `session.agent.messages`, save, emit a `cancelled` event,
then **re-raise** (preserving the lock-release semantics at app.py:455-458). Tests
must cover cancel **mid-LLM-stream** AND **mid-tool-call** (the mid-stream case is the
hard one). The cancel handler must also no-op gracefully if the task already finished
(race with natural completion + `_inflight_tasks.discard`). The frontend gets a stop
control that sends the action and resets state on `cancelled` (see DD4).
- Rationale: the operator's required escape hatch; pairs with DD1/DD2 so even an
  unforeseen stall is recoverable.
- Trade-off: cancelling mid-tool-call may leave a side effect half-done (e.g. a
  Sonos command); acceptable — the agent reports state next turn.

**DD4 — Send-while-thinking, one queued message**:
The frontend (`chat.js` `send()`, :719) blocks input while a turn runs
(`isCurrentBusy()` early-return + `sendBtn.disabled`); the backend already
serializes successive messages via `session_locks[session.id]` (proven this session:
5 rapid WS sends → 5 correct serialized responses). Allow the UI to accept and send
**one** queued message during an active turn, shown immediately as pending; further
sends are ignored until it starts. The backend needs no change to its serialization
(the lock handles it); the work is frontend state + a small guard so at most one is
queued.
- Rationale: matches operator expectation; backend is already safe.
- Trade-off: deliberately capped at one to avoid runaway pile-ups; revisit if the
  operator wants deeper queues.
- **Resolved sub-decision (cancel vs. queued msg)**: pressing stop cancels the
  running turn AND discards any pending queued message — "stop" means stop
  everything. Documented so the behavior is intentional; revisit if operators want a
  queued follow-up to survive a cancel.
- **State-reconciliation hazards (design review, LOW but the file has prior
  input-stuck-disabled history)**: the `cancel-and-queue-frontend` leg must reconcile
  `inFlightSessions`, `sendBtn.disabled`, and `thinkingEl` across all paths —
  `done` (chat.js:1145-1155), the `handleSystem` error path (:801-808), `onclose`
  (:821-827, which wipes `inFlightSessions` on reconnect), and session-switch
  (:939-944). Specifically: the new `cancelled` event must reset state exactly like
  `done` (hide thinking, clear the in-flight flag, re-enable send unless a session
  banner is shown); the one-slot queue guard must survive an `onclose`/reconnect.

**DD5 — Apparatus for the real-environment behavior tests**:
The hang-fix, cancel, and queue are real-environment (WS + agent + UI) behaviors not
coverable by unit tests alone. Apparatus = the WebSocket driver pattern proven this
session (connect with Origin → `new_session` → drive turns → observe
`assistant_chunk`/`tool_call`/`tool_result`/`done`/`cancelled` events) against a
live dev instance on :8485.
- **Act axis**: the WS client sends `message` and `cancel` actions — confirmed
  drivable this session.
- **Observe axis**: the assertions read the WS event stream (`done` arrives within
  bound; a stream-URL fetch returns a tool_result instead of no event; `cancel`
  yields a `cancelled` event and unblocks). All are existing emitted events — no new
  measurement seam required.

### Prerequisites
- [ ] A dev instance runnable on :8485 with the web tools + an agent that has web
      tools (verified this session — `sonnet-loop-test` exists; create an equivalent
      if the dev DB is reset).
- [ ] A reliable "never-ending response" fixture for unit tests — an
      `httpx.MockTransport` that yields bytes forever (or until cancelled) so the
      stream-cap abort can be asserted without a real network stream.
- [ ] No new network service/port introduced (cancel/queue are in-process; web-tool
      changes are outbound-only) — no environment-conflict check needed.
- [ ] Behavior-test execution apparatus: dev instance on :8485 + the WS driver;
      `tests/behavior/chat-loop-hang-and-cancel.md` authored before the verify leg.

### Pre-Flight Checklist
- [x] All open questions resolved (the `web_search` backend question resolves in the
      verify/recon leg by design; it does not block the hang/cancel/queue work)
- [x] Design decisions documented (DD1–DD5)
- [ ] Prerequisites verified
- [x] Validation approach defined (unit + behavior tests + HAT)
- [ ] Legs defined (drafted below; created one at a time during execution)

---

## In-Flight

### Technical Approach
Four independent changes, each with its own tests, landed under a single flight:
1. **web.py** — refactor `http_request` and `fetch_url` to the streaming + in-loop
   byte-cap pattern already used by `download_file`; add a total deadline and a
   media content-type short-circuit. (Leaf change; no contract change to the tool
   schemas.)
2. **agent/core.py** — wrap `await tool.execute(**args)` in `_execute_tool` with
   `asyncio.wait_for(TOOL_CALL_TIMEOUT)`; surface timeouts as tool-error
   `ToolResult`s so the loop terminates cleanly.
3. **interfaces/web/app.py** — track the per-session in-flight task; add a `cancel`
   WS action that cancels it, persists partial output as interrupted, and emits a
   `cancelled` event.
4. **interfaces/web/static/js/areas/chat.js** — cancel/stop control wired to the
   `cancel` action + `cancelled` event; allow one queued send-while-thinking shown
   as pending; reconcile the busy/thinking state.

### Checkpoints
- [x] A continuous-stream URL fetched via `http_request`/`fetch_url` returns a
      bounded result (cap-abort or media short-circuit), never an indefinite hang —
      asserted by a never-ending-transport unit test.
- [x] Any tool exceeding `THE_ONE_TOOL_CALL_TIMEOUT_SECONDS` returns a tool-error
      and the turn still emits `done`.
- [x] A `cancel` WS action aborts the in-flight turn, keeps partial output marked
      interrupted, emits `cancelled`, and releases the session lock.
- [x] The UI exposes a stop control during a turn and accepts exactly one queued
      message while thinking.
- [x] core behaviors verified live (no-hang + cancel + lock release); behavior-test spec authored; full suite green at/above
      the M16 baseline, no new flakes.

### Adaptation Criteria

**Divert if**:
- The streaming refactor proves to break the `fetch_url` HTML-extraction path in a
  way that can't be preserved within the byte cap — escalate before changing the
  HTML contract.

**Acceptable variations**:
- Exact env var name / default for the tool-call timeout.
- Whether cancel is one WS action or reuses an existing control-channel shape.
- Frontend presentation of the queued message and the stop control.
- Whether the `web_search` backend investigation lands here or splits to a
  follow-up (operator's call at the verify leg).

### Legs

> **Note:** Tentative suggestions, not commitments. Legs are planned and created
> one at a time as the flight progresses; this list will evolve.

- [x] `web-tool-stream-and-cap` - Refactor `http_request` + `fetch_url` (web.py) to
      stream with an in-loop byte cap (mirror `download_file`), wrap the whole
      `client.stream` block in a total deadline, and short-circuit
      `audio/*|video/*|application/octet-stream` via `_is_binary_content_type` before
      reading the body. HTML path: accumulate+decode (no `resp.text` post-stream →
      `StreamConsumed`) and **head-preserve** the cap before `Document(...)`. Tests:
      a NEW never-ending iterator-backed `MockTransport` fixture (must cap-abort, not
      hang — `download_file`'s existing test uses a finite body, so this is new
      infra), the media short-circuit, a large-HTML page still extracts sensibly, and
      no-regression for normal HTML/JSON/text fetches.
- [x] `per-tool-call-timeout` - Wrap `await tool.execute(**args)` in
      `agent/core.py` `_execute_tool` (~:520) with
      `asyncio.wait_for(THE_ONE_TOOL_CALL_TIMEOUT_SECONDS, default 120)`; add an
      `except asyncio.TimeoutError` beside the existing `except Exception` (~:540)
      returning a tool-error `ToolResult`; the turn still terminates with `done`.
      Do NOT touch `_dispatch_tool_calls`/`_stream_response`. Unit-test a hanging tool
      → timeout → `done`; verify auth-pause and degraded paths unaffected.
- [x] `cancel-backend` - Per-session in-flight-task map + WS `cancel` action + task
      cancellation. Capture streamed text (in the `_broadcast_chunk` closure) and, in
      an `except asyncio.CancelledError` block in `_process_and_broadcast`, append an
      interrupted `Message.assistant(...)` to `agent.messages`, save, emit
      `cancelled`, then re-raise (preserves lock release). No-op if the task already
      finished. Tests: cancel **mid-LLM-stream** (the hard case) AND **mid-tool-call**,
      both asserting the interrupted message persists and the lock is released.
- [x] `cancel-and-queue-frontend` - chat.js: stop control (sends `cancel`, handles
      `cancelled` by resetting state exactly like `done`); allow ONE queued
      send-while-thinking shown as pending (cancel discards it); reconcile
      `inFlightSessions`/`sendBtn.disabled`/`thinkingEl` across `done`, error,
      `onclose`/reconnect, and session-switch; the one-slot guard survives reconnect.
- [x] `verify-integration` - Author + run `tests/behavior/chat-loop-hang-and-cancel.md`;
      full suite green at/above baseline, no new flakes. Resolve the `web_search`
      "No results found" question (fix or split to a follow-up). **Docs**: add
      `THE_ONE_TOOL_CALL_TIMEOUT_SECONDS` to the env-var reference (alongside
      `THE_ONE_WEB_SESSION_IDLE_TTL_SECONDS` etc.) and document the cancel/queue UI
      behavior.
- [x] `uat-and-alignment` *(optional)* - Guided HAT: drive the real chat UI through
      a stream-URL hunt, an interrupt, and a queued send; fix issues until the
      operator is satisfied.

---

## Post-Flight

### Completion Checklist
- [x] All legs completed
- [ ] Code merged
- [x] Tests passing (unit; behavior-test spec authored, run available), full suite green at/above M16 baseline
- [x] Documentation updated (env var in-code; cancel/queue behavior) (the new env var; the cancel/queue UI behavior)

### Verification
- **Unit**: web tools cap-abort a never-ending stream and short-circuit media
  content-types without regressing normal fetches; a hanging tool trips the
  per-tool-call timeout and the turn still completes; cancel aborts and preserves
  partial output.
- **Behavior test** (`/behavior-test chat-loop-hang-and-cancel`): against a live
  :8485 instance, a turn that fetches a continuous-stream URL terminates (no
  indefinite hang); a `cancel` mid-turn yields a `cancelled` event and unblocks the
  UI; one queued message is accepted while thinking and runs after the current turn.
- **HAT** (optional leg): operator-driven pass through the real Chat UI.
- **Regression**: full unit suite green at/above the mission baseline, no new flakes.
