# Flight Log: Chat-loop Robustness & Control

**Flight**: [Chat-loop Robustness & Control](flight.md)

## Summary

Flight created (planning). Sourced from a live reproduction + root-cause this
session, not a written artifact: the chat loop hangs indefinitely when a turn
fetches a continuous-stream URL via the web tools, and there is no interrupt. Adds
a web-tool streaming fix, a per-tool-call timeout, an interrupt/cancel control, and
one-deep send-while-thinking. No execution yet.

---

## Reconnaissance Report

Source: this session's live repro against the **Sonos Agent** (claude-sonnet-4-6 +
Sonos MCP + web tools) on the installed 8484 instance, plus dev-instance probes on
:8485. Every cited location was read against current `main` (`5608d97`) this session.

| Item | Classification | Evidence | Recommendation |
|------|----------------|----------|----------------|
| `http_request` buffers full body → hangs on infinite stream | `confirmed-live` | `the_one/tools/web.py:125` (`await client.request(...)` then `_truncate_response(resp.content)` at :126) | Stream + in-loop cap (DD1, leg 1) |
| `fetch_url` buffers full body → same hang | `confirmed-live` | `the_one/tools/web.py:190` (`await client.get(url)`; binary-check at :192 only runs post-read) | Stream + in-loop cap (DD1, leg 1) |
| `download_file` already streams with in-loop cap (the fix precedent) | `already-satisfied` | `the_one/tools/web.py:295-303` (`client.stream` + `aiter_bytes` + cap raise) | Reuse this pattern; no change to download_file |
| httpx timeout is per-op (read = between-bytes gap), not a total deadline | `confirmed-live` | `WebConfig.timeout_seconds_default=30 / _max=120` (`_web_config.py:151-173`); stream defeats it | Add total `asyncio.wait_for` (DD1) |
| Byte cap exists but applied post-read | `confirmed-live` | `WebConfig.response_size_cap_bytes=1_048_576` (`_web_config.py:187`); `_truncate_response` (tail-preserving) runs on `resp.content` after full read | Enforce cap during streaming; head-preserve for the HTML path (DD1) |
| Agent loop has no per-tool/turn timeout | `confirmed-live` | `the_one/agent/core.py` `_execute_tool` `await tool.execute(**args)` (:520, no `wait_for`); `except Exception` at :540 | Per-tool-call `wait_for` at `_execute_tool` — NOT `_stream_response` (that's the LLM stream) (DD2, leg 2) |
| MCP tool calls DO have a timeout (~30s SDK) | `already-satisfied` | `the_one/mcp/_tool_provider.py:269` comment ("~30s SDK timeout") | Hang is the web tools, not MCP — scope confirmed |
| No interrupt/cancel for an in-flight turn | `confirmed-live` | `_inflight_tasks` is an unkeyed set (`app.py:414`); only cancelled en masse at shutdown (`app.py:235`); no per-session map | Add session→task map + `cancel` action (DD3, leg 3) |
| `_process_and_broadcast` re-raises `CancelledError` (cancel will release the lock cleanly) | `already-satisfied` | `app.py:455-458` | Cancel design can rely on this |
| Frontend blocks send-while-thinking | `confirmed-live` | `chat.js:719-727` (`send()` early-returns on `isCurrentBusy()`, disables `sendBtn`) | Allow one queued send (DD4, leg 4) |
| Backend already serializes concurrent sends (queue is safe) | `already-satisfied` | `session_locks[session.id]` in `_spawn_message_processing` (`app.py:442`); proven this session (5 rapid WS sends → 5 correct serialized responses) | No backend serialization work needed for DD4 |
| `web_search` returns "No results found" for every query on 8484 | `needs-human-recheck` | Live repro turn 3 (all `web_search` calls returned "No results found.") — likely an unconfigured search backend on the installed instance; not verifiable from repo alone | Resolve in verify leg; may split to a follow-up |

No `drifted` or `partially-satisfied` items. The three `already-satisfied` rows are
recorded so the spec's scope is auditable (download_file is the fix template; MCP
already bounded; backend serialization already safe).

**Live repro evidence**: turn 3 of the Sonos research conversation issued ~27 tool
calls (web_search/fetch_url/http_request) hunting a non-mp3 stream; it hung with no
events for 200s immediately after
`http_request GET https://stream.radioparadise.com/aac-320` (a continuous AAC
stream) returned no tool_result. Finite URLs (`.pls` files, JSON) returned normally;
only the infinite stream wedged. Provider-agnostic — the same hang class was seen
with ministral-3:8b during dev probes.

---

## Flight Director Notes

- **2026-06-21** — Flight planned via `/flight`. Recon done inline (all items
  verified this session, table above). Operator design decisions captured:
  per-tool-call timeout (env-configurable, default 120s); cancel keeps partial
  output marked interrupted; one queued send-while-thinking; verification via unit +
  behavior tests + optional HAT. Behavior-test spec
  `tests/behavior/chat-loop-hang-and-cancel.md` drafted during planning.

- **2026-06-21 — Design review (Architect) → approve-with-changes.** All cited line
  numbers verified accurate. Incorporated: **[HIGH]** DD3 partial-output persistence
  is harder than stated (streamed text lives only in `_stream_response`'s local and
  is lost if cancel fires before the loop yields; cancel-backend must capture it in
  the `_broadcast_chunk` closure and append an interrupted Message before save, in an
  `except CancelledError` that re-raises) — DD3 + leg 3 + tests updated. **[MEDIUM]**
  DD2 wrap point corrected from `_dispatch_tool_calls`/`_stream_response` to
  `_execute_tool` (`await tool.execute`); do NOT timeout the LLM stream. **[MEDIUM]**
  DD1 HTML path must accumulate+decode (no `resp.text` post-stream) and head-preserve
  the cap (tail-truncation breaks readability). **[MEDIUM]** field name corrected to
  `response_size_cap_bytes`. **[LOW]** DD4 frontend state transitions + "cancel
  discards the queued message" decision; doc-update assigned to leg 5; never-ending
  stream fixture flagged as new test infra. No structural rework needed; second
  review cycle skipped (changes are the review's own prescriptions, not new design).

---

## Deviations

_(none yet)_

---

## Anomalies

_(none yet)_

---

## Session Notes

- **2026-06-21** — Flight created. Scope sourced from a live repro of the operator's
  Sonos-agent chat-loop hang (see Reconnaissance Report).

- **2026-06-21 — /agentic-workflow started.** Phase file leg-execution.md valid
  (Developer=Sonnet, Reviewer=Haiku). Flight ready→in-flight. Designed legs 01-04;
  ran ONE combined Developer design-review over all four (FD efficiency call — the
  Architect already validated these designs at flight level). Verdict: legs 1/2/4
  approve-with-changes, leg 3 needs-rework; all findings folded into each leg's
  "Design-Review Corrections (binding)" section (leg 3 HIGHs: no Message.metadata
  field → mark interrupted via content suffix; CancelledError handler also fires on
  shutdown → best-effort suppress + re-raise; per-session task-map identity-guard).
  Deferred-commit model: legs 01-03 implemented in PARALLEL (disjoint files —
  web.py / core.py / app.py), then leg 04 (frontend, depends on leg 03's cancel
  action + cancelled event), then leg 05 verify + single flight-wide review + commit.

- **2026-06-20 — Leg 01 (web-tool-stream-and-cap) landed.** Refactored
  `http_request` and `fetch_url` in `the_one/tools/web.py` to stream the body via
  `async with client.stream(...) + aiter_bytes`. Added two module-level helpers:
  `_stream_read_with_cap` (accumulates chunks, raises `ConstraintError` when
  body exceeds cap — used for text/binary paths) and `_stream_read_head_capped`
  (accumulates first N bytes, stops silently — used for HTML path so readability
  always has a valid document head). Added `_is_media_stream_type` narrow predicate
  (`audio/*` | `video/*` | `application/octet-stream` only — does NOT reuse
  `_is_binary_content_type` to avoid regressing binary tail-truncation for
  image/pdf/zip). Both tools wrapped in `asyncio.wait_for(..., timeout_seconds_max)`
  total deadline. FetchUrlTool's HTML path uses `_stream_read_head_capped` so readability
  extracts from a valid partial document. Behavior deviations from pre-F7 (intentional,
  per DD1): http_request with body > cap now returns `[error] [constraint] response
  exceeded N bytes` instead of a truncation marker; fetch_url HTML path silently
  truncates at cap (head-preserved) rather than extracting then truncating markdown.
  Updated `tests/test_web_tools.py`: 2 pre-F7 truncation tests reworded to match new
  behavior; added `_InfiniteByteStream` (never-ending `httpx.AsyncByteStream`) +
  `TestStreamCapAbort` (3 tests: http_request and fetch_url text+html cap-abort without
  hanging), `TestMediaShortCircuit` (5 tests: audio/video/octet-stream short-circuit;
  image/png NOT short-circuited — regression guard), `TestLargeHtmlHeadPreserve`
  (1 test: 12KB HTML with marker in title → 8192-byte head-cap → readability finds
  marker). 50 tests, all green. Ruff clean.

- **2026-06-20 — Leg 03 (cancel-backend) landed.** Implemented all binding
  design-review corrections in `the_one/interfaces/web/app.py` only:
  (1) `_session_inflight: dict[str, asyncio.Task]` added at module level (~:418);
  populated at task-spawn site (~:2077) with identity-guard done-callback (`if
  _session_inflight.get(sid) is t: del _session_inflight[sid]`). Coexists with
  `_inflight_tasks` — shutdown still cancels all via the set.
  (2) WS `cancel` action branch inserted before the regular-message block:
  snapshots `_session_inflight.get(session.id)`, guards `t and not t.done()`, calls
  `t.cancel()`. No-op if no session bound, no task registered, or already done.
  (3) `partial_text` accumulator added in `_broadcast_chunk` closure (nonlocal);
  `except asyncio.CancelledError` added as SIBLING to `except Exception` (~:1584) —
  appends `Message.assistant(content=partial_text + "\n\n_[interrupted]_")` only if
  partial_text non-empty (skips synthetic message on mid-tool-call-no-preamble cancel),
  then best-effort `_save_session_to_db` and `_send_to_session({"type":"cancelled"})`
  both inside `contextlib.suppress(Exception)` for shutdown safety, then re-raises
  `CancelledError` preserving lock-release at _spawn_message_processing. Message has
  NO metadata field (confirmed) — content suffix used. New test file
  `tests/test_cancel.py`: 14 tests, all passing. Covers: cancel mid-stream (partial
  text persisted with suffix, `cancelled` event emitted, lock released, save called
  with interrupted message), cancel mid-tool-call (no synthetic message, `cancelled`
  event emitted, lock released, next message accepted), exception-hierarchy regression
  guard (CancelledError NOT subclass of Exception; propagates through function),
  per-session task-map (registered on spawn, cleared in done-callback, identity guard
  prevents stale clear), and cancel no-ops. Ruff clean.

- **2026-06-20 — Leg 02 (per-tool-call-timeout) landed.** Added `_get_tool_call_timeout()`
  env reader in `the_one/agent/core.py` (reads `THE_ONE_TOOL_CALL_TIMEOUT_SECONDS`,
  default 120, floor 1, ValueError→fallback). Wrapped `await tool.execute(**args)` in
  `_execute_tool` with `asyncio.wait_for(..., timeout)`. Added `except asyncio.TimeoutError`
  BEFORE the existing `except Exception` (inner try at :546), returning
  `ToolResult(is_error=True, content="tool {name} timed out after {N}s")`; outer
  `finally` still resets `current_tool_call_id`. `_dispatch_tool_calls` and
  `_stream_response` NOT touched. New test file `tests/test_tool_call_timeout.py`:
  13 tests — env reader unit tests (default, custom, bad value, floor/negative clamp,
  float), `_execute_tool` timeout (error content, exact message format, ContextVar reset
  after timeout), agent loop with slow tool (yields final message, no hang), fast tool
  (no interference), auth-required tool (MCPAuthRequired still produces pause result,
  loop still defers). All 13 new + 28 existing agent tests pass. Ruff clean.

- **2026-06-20 — Leg 04 (cancel-and-queue-frontend) landed.** Implemented all three
  acceptance-criterion surfaces in `the_one/interfaces/web/static/js/areas/chat.js`
  and added styling in `the_one/interfaces/web/static/css/chat.css`. No Python files
  or other JS modules touched.
  (1) **Stop control**: added `<button class="btn-stop-turn">` in the input-area
  HTML (between input and Send). Show/hide is reactive — derived from
  `isCurrentBusy()` via `updateStopControl()` called on every mutation of
  `inFlightSessions`. Clicking sends `{action:"cancel"}`, optimistically hides
  the thinking indicator, and discards any pending queued message. The
  authoritative full reset is deferred to the `cancelled` event.
  (2) **`cancelled` event**: mirrors the FULL `done` reset — `hideThinking()`,
  `finalizeStreamingBubble()`, `currentStreamingVisibility = null`, clears
  `inFlightSessions[currentSessionId]`, clears `pendingQueuedMessages[currentSessionId]`,
  `clearPendingQueued()`, `updateStopControl()`, re-enables Send (banner-gated),
  `refreshSessionList()`.
  (3) **One-slot queue in `send()`**: if `isCurrentBusy()` and not
  blocked by the health gate (`sessionBannerEl`/`inputEl.disabled`), accepts one
  queued message per session (`pendingQueuedMessages` keyed by session id, mirroring
  `inFlightSessions` shape). Immediately WS-sends it (backend lock serializes it).
  Second queue attempt while one is pending is ignored. Shown as a dashed
  `.pending-queued` indicator in the message area.
  State reconciliation: `updateStopControl()` and `clearPendingQueued()` called on all
  terminal paths — `done`, `cancelled`, `handleSystem` error branch, `onclose`
  (which also wipes both maps), and `session_joined` (which restores the pending
  indicator if the joined session still has one in flight). Syntax verified:
  `node --check chat.js` exits 0. Functional verification deferred to leg 5 behavior
  test + leg 6 HAT.

- **2026-06-21 — Legs 01-04 landed (parallel impl), Leg 05 verify done.** Full suite
  `3489 passed / 10 skipped / 595 deselected`, 0 failures, no new flakes (+41 over the
  3448 baseline). Ruff check + format clean tree-wide. Flight-wide Reviewer (Sonnet,
  not the crew's Haiku — standardized deviation for a large multi-file deferred-commit
  diff per the F05 debrief): `[HANDOFF:confirmed]`, one non-blocking note (timeout
  message diagnostic). `web_search` DDG-scrape "No results" SPLIT to a mission Known
  Issue (out of scope). `THE_ONE_TOOL_CALL_TIMEOUT_SECONDS` documented in-code.
  Committing legs 01-05; Leg 06 HAT (interactive) remains before landing.

- **2026-06-21 — Leg 06 HAT + FLIGHT LANDED.** Live verification on :8485 (new code):
  the exact hang URL (`stream.radioparadise.com/aac-320`) now returns in 0.3s via BOTH
  web tools (media short-circuit) — no hang; WS cancel mid-turn → `cancelled` event +
  session recovered (lock released). Operator accepted the live verification (UI-visual
  stop-button / queued-indicator eyeball deferred to operator; behavior-test spec
  available via `/behavior-test chat-loop-hang-and-cancel`). Flight landed → 6/6 legs
  completed; Flight 7 checked off in mission.md. [COMPLETE:flight]
