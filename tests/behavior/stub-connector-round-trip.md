# Behavior Test: Stub Connector Round-Trip

**Slug**: `stub-connector-round-trip`
**Status**: draft
**Created**: 2026-08-31
**Last Run**: never

## Intent
Verifies the Mission 23 channel contract end-to-end without a live platform: connector creation with masked credentials, pairing-code admission (silence for unknown senders, allowlist append on the code), the reply round-trip through the connector's default agent, the operator's private console (operator-typed messages visible in unified history but never sent to the platform), and the agent-initiated send tool. This is inherently multi-component (Studio UI → routes → manager → inbound pipeline → agent loop → Chat UI → stub outbound record) and turns on real-environment observables a unit test cannot witness in one piece.

## Preconditions
- Dev instance running with `THE_ONE_PORT=8485`, a scratch `THE_ONE_DATA_DIR`, `dev_mode` on, and `THE_ONE_STUB_TEST_ENDPOINT=1` (the stub seam is dual-gated like purge-sweep; never port 8484 or the operator's default data directory).
- An agent exists (e.g. `test-agent`) with the `send_to_platform_channel` tool enabled and a provider configured that can answer a trivial prompt.
- Browser apparatus (chrome-devtools MCP or similar) available; `curl` available for seam calls.

## Observables Required
- browser (Studio connector form, Chat unified history and visibility distinction — via chrome-devtools MCP)
- http (seam routes `POST /api/_test/stub/inbound` and `GET /api/_test/stub/outbound`; `GET /api/chat/sessions` for keying fields — via curl)

## Steps

*(Draft — step wording to be finalized in the flight's `behavior-gate-and-docs` leg once the form's testids exist. Key observables and step count are fixed here.)*

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | In Studio, create a connector of type `stub` named `bt-stub`, token `dummy`, default agent `test-agent`; save. | Form saves; connector row appears; token displays masked, never the literal `dummy`. |
| 2 | Click the pairing-code button. | A short code with an expiry is shown. |
| 3 | Via seam: inject an inbound DM from unknown peer `peer-1` with body `hello?`. | Within 10s, `GET /api/_test/stub/outbound` shows NO reply to `peer-1`; no chat session for `peer-1` exists (`GET /api/chat/sessions`). |
| 4 | Via seam: inject an inbound DM from `peer-1` whose body is exactly the pairing code. | `peer-1` appears in the connector's allowlist (Studio form reload); code is consumed (a second unknown peer sending it gets silence). |
| 5 | Via seam: inject an inbound DM from `peer-1`: `What is 2+2?`. | Within 60s the stub outbound record contains the agent's reply to `peer-1`; the Chat UI shows a session keyed `(stub, bt-stub, dm:peer-1)` containing both the peer message and the reply. |
| 6 | In the Chat UI, open that session and type an operator message: `note to self`. | The message renders in the unified history with the operator-only visual distinction; the stub outbound record does NOT contain it. |
| 7 | Via seam: inject `please send me the word "ping" using your send tool`. | Within 60s the stub outbound record contains a message with `ping` sent via the send tool; the Chat UI history shows the send-tool result with peer-visible rendering. |

## Out of Scope
- Live Discord/Telegram behavior (Flights 3–4 live HATs).
- Reconnect/backoff under gateway failure (unit-tested; live-verified in Flight 3).
- Channel (non-DM) reply policy nuances — @mention and always-listen are unit-tested; a live-channel variant may be added in Flight 3.
