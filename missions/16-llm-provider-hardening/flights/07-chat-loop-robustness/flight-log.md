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
