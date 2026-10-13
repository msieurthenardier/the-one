# Flight Log: Automatic negotiation of protocol 2026-07-28

**Flight**: [Automatic negotiation of protocol 2026-07-28](flight.md)

## Summary
Mission 29 Flight 2, **ready** (approved 2026-10-12). Planning branch `flight/02-auto-negotiation`, cut from merged main `307ad22` in the worktree `../the-one-sortie-03`. The dev instance on port 8492 (scratch data dir, the operator's Cloudflare and Sonos sources) is kept running for this flight's HAT.

---

## Reconnaissance Report (2026-10-12)

Source: Flight 1's debrief (Recommendations 1-2 and "What Could Be Improved > Technical") plus the Flight 1 Architect's forward-looking analysis. Each item was checked against `307ad22` and the installed `mcp` 2.3.0, read-only. Probe scripts are in the session scratchpad (`f2probe/`).

| Item | Classification | Evidence | Recommendation |
|---|---|---|---|
| A1 `_meta` read from the InitializeResult | confirmed-live | `client.py:581` reads from `result`, which is set only by `initialize()` (`:411`). Modern `discover_result.meta` holds the serverInfo stamp. | DD3 |
| A2 doctor gate doesn't prove `httpcore2` | confirmed-live | `diagnostics.py:583-612`. After the gate's imports, `httpcore2` is not in `sys.modules`; it loads only after `httpx2.AsyncClient()`. | DD11 |
| A3 DD1 translation ladder duplicated | confirmed-live | 11 `_auth_required_since` sites, 3 SSE-cap arms, 2 session-terminated arms, 3 `except* (OAuthFlowError, OAuthTokenError)` blocks. Arm order differs between `list_tools` and `call_tool`. | DD5 |
| A4 timeout-vs-401 keeps stale secrets | confirmed-live | `api.py:3698` runs before `:3704-3735` (`looks_like_token_failure` strip). Pinned by `tests/test_mcp_test_connection_stale_tokens.py`. | DD7 (operator: clear them) |
| A5 `CancelledError` translated with no `cancelling()` gate | confirmed-live | `client.py:743-750, 889-895` | DD6 |
| A6 auth-posture probe vs a server that speaks only 2026-07-28 | confirmed-live | `streamable_http.py:255-288` (no header; `"error"` on non-200/401); `api.py:3606-3612` short-circuits. 2.x servers pass (header-less → handshake path). | DD9 |
| A7 version gate is handshake-only | confirmed-live | `client.py:553-561` | DD4 |
| A8 `_PINNED_PROTOCOL_VERSION` and the two tripwires | confirmed-live | `__init__.py:12,65`; `client.py:370,433,561`; `streamable_http.py:260`; tripwires `test_mcp_client.py:56`, `test_mcp_wire_shapes.py:102-106`; `test_mcp_client.py:733` monkeypatch. Hard-coded "2025-11-25" in `api.py:3791, 4658`. | DD4, DD10 |
| A9 `MCPVersionMismatch` wording | confirmed-live | `errors.py:19-22`; only `test_mcp_client.py:451` pins `.pinned`; the frontend keys on the class name | DD5 |
| A10 `_signin_record.py` smells (private `_AUTH_RECORDS` written from the transport; module owns `MAX_SSE_EVENT_BYTES`) | confirmed-live | `transports/streamable_http.py:32-37, 430`; `_signin_record.py:15` | Optional; not scheduled (low value, would churn Flight 1's layering pin) |
| A11 input-required on `call_tool` | confirmed-live (gap) | Modern: SDK `RuntimeError` text reaches the LLM verbatim via `agent/core.py:630-635`. Handshake: already a plain `MCPCallError`. | DD8 |
| A12 squawk 0199 (stale MCP docs) | partially-satisfied | Still live: `mcp/__init__.py:3`, `streamable_http.py:221-222`, `CLAUDE.md:305`. Already satisfied: the dual-HTTP-stack rule at `the_one/agents.md:1060` (DD4 paragraph, `api.httpx2.AsyncClient` patch target). | DD12 (operator: fold in, close the squawk) |

Operator review (2026-10-12): every item accepted as classified. A12 was narrowed to its three live items and folded into this flight. A10 was left unscheduled by the Flight Director as low value.

## Design Inputs from Reconnaissance (Part B, summarised)
- **The negotiation policy** (`mcp/client/_probe.py::negotiate_auto`, private) uses only public `ClientSession` methods (`send_discover`, `initialize`, `adopt`) plus public types, so it can be re-implemented without private API (DD1).
- **How older servers answer discover.**
  - 1.28.1 over HTTP answers with an immediate 400 and a JSON-RPC body, stateful and stateless (stateful leaks an unused server session); over stdio, -32602. Both give a fast fallback.
  - 2.3.0's handshake-only `serve_loop` answers -32601.
  - A silent drop costs `DISCOVER_TIMEOUT_SECONDS` (10 s, patchable at call time). A pipe close cannot fall back.
- **The modern era over HTTP:** all requests are POSTs, there is no GET stream, no session id and no DELETE on close. The DD1 hook records every one. An `initialize` fallback clears the transport's cached `MCP-Protocol-Version`.
- **Self-configuration loopback:**
  - It negotiates 2026-07-28 under `stateless_http=True` (the header routing runs first).
  - The caller stamp should resolve through `ServerMessageMetadata(request_context=request)`.
  - Refusal text is byte-identical in both eras.
- **Era memory:** the pool writes nothing back today, and the only persistence API (`MCPSourceRepository.update`) overwrites the whole row and races token writes. Hence the in-memory map plus the Test-connection result (DD2).
- **The editor's protocol display** needs no change (`mcp-server-editor.js:327, 372`).
- **RFC 8707:** with negotiation, the SDK path sends `resource` to an authorization server with no protected-resource metadata, while the-one's flow drivers would not (DD10).
- **Test hazard:** the bare-`MagicMock` session fixtures would raise `TypeError` on `send_discover` (DD1). `test_mcp_signin_detection.py:64` must add `server/discover` to `fail_methods`.

## Flight Director Notes
- **2026-10-12, planning.** Operator decisions:
  - re-implement negotiation on the public API (DD1);
  - in-memory era map plus the Test-connection result (DD2);
  - clear stale tokens on Test (DD7);
  - align the flow drivers' `resource` behaviour (DD10);
  - fold in squawk 0199 (DD12).

  The dev instance on 8492 is kept for the HAT.

- **Design review, cycle 1** (Architect): **needs rework**, limited to DD2, DD5, DD6 and DD9. Applied:
  - **DD6.** The `cancelling() == 0` premise was disproved by probe (anyio delivers cancel-scope cancellation via `task.cancel()`). The rule is now owner-task identity.
  - **DD2.** The saved `_cache.protocol_version` hint would have pinned every existing source, Sonos included, to the handshake. After a second question, the operator chose in-memory era memory only. A failed shortcut now runs the full policy, and the era is cleared on update and delete.
  - **DD5.** The full per-operation matrix is now spelled out, cleanup stays at the call sites, and the "did not respond" / "cancelled during initialize" strings are pinned as a contract.
  - **DD9.** A fourth probe verdict, `unexpected_status`, now falls through into Phase B on sign-in. Transport errors keep failing fast.
  - **DD7.** The clear now works on a re-read of the stored row, so the operator's unsaved override is never written. The existing strip had the same flaw and is fixed too. It clears all four OAuth-managed keys, matching pre-Flight-1 behaviour.
  - **DD4 and DD10.** Their contradiction is resolved: the drivers keep an `initialize` body and add the handshake version header. The modern offer now comes only from the SDK.
  - **DD13.** Every older revision is proven on a real fixture, latency is checked structurally, and the era map is isolated between tests.
  - **DD3, DD8, DD11, DD12.** Fixture and detail fixes.
  - **Legs.** Leg 2 is split into core and api.
  - **HAT.** H1-H5 are defined, with a real 1.x server for H4.

  A second, final review cycle follows.

- **Design review, cycle 2** (Architect, final): **approve with changes**. It confirmed DD6's owner-task rule in both the Test-connection and pool shapes, DD2's shortcut against the sign-in record, and that DD9 starts exactly one sign-in. Applied:
  - **DD7.** Strip the in-memory override's secrets rather than swapping `source` for the stored row, so Phase B signs in against the URL under test.
  - **DD5 row 3.** Any mid-session -32022 marks the connection dead and forgets the era. It is `MCPVersionMismatch` only when there is no shared version.
  - **`_era.py`.** Created in leg 1.
  - **DD13.** The older-revision mechanism (patching the runner globals), with an audit row and its limit stated.
  - **DD1.** The shortcut reads the record via `auth_record_for`, and `None` means no 401.
  - **DD5 rows 1-2.** Reordered to today's order; `connect`'s elicitation pass-through is an intended change, and the transport arms are named.
  - **Leg 1 interim notes.**
  - **Suggestions adopted.** No `remember_era` on a body-override Test, and `_owner_task` reset on connect and disconnect.
  - **Open question (posture overwrite after Phase A).** Left as today's behaviour: Phase A's cache write keeps omitting `auth_posture`, so a later tokenless Test re-probes. Out of scope.

  Operator approved the spec (2026-10-12); flight `ready`.

---

## Leg Progress
