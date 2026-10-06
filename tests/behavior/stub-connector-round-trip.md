# Behavior Test: Stub Connector Round-Trip

**Slug**: `stub-connector-round-trip`
**Status**: active
**Created**: 2026-08-31
**Last Run**: never
**Updated**: 2026-10-05 (M25 F4 leg 8: step 5 opens the session from the Chats list's row; the browser observable names the Chats list)

> **2026-09-01 DD-10 re-author**: Mission 23 Flight 3's mid-flight DD-10 added a
> mechanical auto-reply fallback to `dispatch_inbound` — a plain assistant
> reply now auto-delivers to the originating target and flips to
> peer-visible, without the model ever calling `send_to_platform_channel`.
> Step 5 below (and the surrounding Intent / "Why the reply steps..." /
> Out of Scope text) is re-authored per DD-10's explicit consequence clause
> to expect that. Step 6 (operator note never forwarded) and Step 7 (the
> agent-INITIATED tool send, still the deliberate/cross-channel path) are
> unaffected and kept. This note documents the re-author; `runs/` logs
> below it are immutable historical records and are NOT rewritten.

## Intent

Verifies the Mission 23 channel contract end-to-end against a live dev instance, with no real platform involved: connector creation with masked-credential round-trip, pairing-code admission (silence for an unadmitted sender, allowlist append on the correct code, no double-consumption), the reply round-trip through the connector's `default_agent` (peer message → agent turn → DD-10's mechanical auto-delivery of the assistant's reply text to the originating target — no tool call required), the operator's private console (operator-typed messages land in the same unified history but are never forwarded to the platform), and the agent-INITIATED send tool triggered by an inbound instruction (the deliberate, cross-channel-capable path, which also proves DD-10's no-double-send skip rule: a turn that tool-sends does not ALSO auto-deliver). This is inherently multi-component (Studio UI → routes → manager → inbound pipeline → real agent loop with a real LLM → Chat UI → stub outbound record) and turns on real-environment observables — masked-secret redisplay, DOM-rendered visibility markers, a real model's tool-call behavior — that a unit test cannot witness in one piece. `tests/test_connectors_inbound.py` proves the pipeline's *mechanics* (both the auto-delivery path and the tool-send skip rule) with a scripted `FakeLLM`; it does not prove a real model, calling `send_to_platform_channel` on an explicit in-message instruction (see the note below), reliably completes that call — that remains this test's job for Step 7, and is the empirical validation `the_one/agents.md`'s `prompt-discipline-needs-mechanical-fallback` convention requires for any LLM-controlled behavior the system depends on with no mechanical fallback. (The plain-reply case Step 5 exercises no longer depends on model tool-calling reliability at all — that is precisely DD-10's point, applied to replies — so Step 5's job now is proving the live wiring: real routes, a real live app, real DOM rendering of the auto-delivered, peer-visible reply.)

### Why the reply steps embed the tool-call target in the message text

`dispatch_inbound` (`the_one/connectors/inbound.py`) passes the inbound envelope's raw `text` to `agent.step()` and nothing else — no connector id, no peer id, no system-level directive is injected into the turn (DD-1's "no engagement-inference LLM gate" strips exactly that kind of scaffolding, and the pre-reset auto-relay directive in `agent/config.py` was deleted in the Mission 23 connector reset, not reattached). So a real model receiving a bare inbound message has no way to discover the `connector_id`/`peer_id` values `send_to_platform_channel`'s `target` requires. Step 7 below works around this the same way an operator scripting a controlled test would: the injected `text` states the exact `target` JSON to use, so the model only has to follow an explicit instruction rather than infer hidden context — a provider-agnostic ask that should succeed on any reasonably capable model (local Ollama model or hosted key). This is a deliberate property of *this test's* seam payload, not a claim about unprompted production behavior. Step 5 needs no such workaround anymore (DD-10): the mechanical auto-reply resolves its own target — `PeerTarget(connector_id, peer_id)` for a DM — directly from the inbound envelope, so a bare question with no target instruction is enough to prove delivery.

## Preconditions

- **Dev instance boot** — from the project root:
  ```bash
  THE_ONE_PORT=8485 THE_ONE_DATA_DIR=/tmp/the-one-behavior-test-scratch \
    THE_ONE_DEV_MODE=true THE_ONE_STUB_TEST_ENDPOINT=1 make up
  ```
  Use a fresh scratch `THE_ONE_DATA_DIR` (not the operator's default) and port `8485`
  (never `8484`, the operator's production instance — see CLAUDE.md's "SAFETY RULE").
  Verify liveness: `curl http://127.0.0.1:8485/api/live` → HTTP 200. Tear down after
  the run with `THE_ONE_PORT=8485 make down`.
- **Both gates must be open** for the stub connector to exist at all:
  `THE_ONE_DEV_MODE=true` makes the `stub` connector type *and* the `mock` LLM
  provider type selectable; `THE_ONE_STUB_TEST_ENDPOINT=1` additionally (a) admits
  `"stub"` into `GET /api/connectors/types`, (b) registers `StubPlugin` under type
  `"stub"` at lifespan startup (`interfaces/web/app.py`'s dual-gated hook — the
  successor to the retired `THE_ONE_REGISTER_STUB_CONNECTOR` name), and (c) unlocks
  the two `/api/_test/stub/...` seam routes (403 otherwise). This pairing is
  decay-prone the same way the mock-provider gate is (`chat-roundtrip.md`
  precedent) — Step 1 below actively probes it before creating anything.
- **An agent named `test-agent` exists** with:
  - a working, **non-mock** LLM provider capable of completing a real turn and a
    real tool call — this test's whole value is the real agent loop and a real
    model's tool-call decision (Edge Case: never fake or stub the agent loop).
    Provider choice is the operator's environment: Ollama if reachable locally,
    else an existing configured API-key provider. **If no provider is reachable,
    STOP and ask the operator before proceeding.**
  - an ordinary system prompt, plus ONE documented tool-use-discipline nudge
    appended to it — the nudge must be MECHANISM-AWARE, because the agent
    loop's strict baseline (M16 F10) makes `search_tools` the only tool
    visible at session start; a tool the model hasn't discovered cannot be
    called directly: `When instructed to deliver a message by calling
    send_to_platform_channel: that tool is not directly visible until
    discovered — first call search_tools with query "send_to_platform_channel",
    then call the discovered tool, all in the same turn.` No other
    connector-specific content is required (see "Why the reply steps embed the
    tool-call target" above — the nudge is orthogonal to that: it's about
    *calling* the tool once instructed, not about *what target* to use).
    (Amended during run `2026-08-31-22-43-08`: the run-1 nudge said "call
    that tool in the same turn" without mentioning discovery; the model
    reproduced the narrate-without-calling failure with that nudge live —
    it didn't know it had to search first. Run 1's step 7 proved the model
    reliably completes the call once it thinks to search.)
    **Why**: run `2026-08-31-21-37-14` found the model narrating intent
    ("I'll call send_to_platform_channel...") without actually invoking it in
    2 of 3 turns that gave the identical in-band instruction — a real
    tool-calling-reliability gap over the search-deferred indirection (the
    send tool is discovered via `search_tools`, not directly visible), not a
    pipeline defect (see run 1's checkpoint 5 vs. checkpoint 7: same
    instruction shape, narrated-never-called once, discovered-then-called
    once). The nudge trades a little empirical purity (this test then no
    longer probes an *unprompted* model's tool-discipline) for re-run
    determinism (a flaky send step blocks every other checkpoint from being
    exercised) — the raw finding is preserved verbatim in run 1's log
    (`tests/behavior/stub-connector-round-trip/runs/2026-08-31-21-37-14.md`,
    Operator Note 4) and the flight log records it as a design gap
    (search-deferred send-tool discoverability reliability) for the flight
    debrief, not silently designed away.
  - the `send_to_platform_channel` built-in tool enabled. A freshly created agent
    has every built-in tool enabled by default (Agents → `test-agent` →
    Tools tab, `input[type="checkbox"][data-tool="send_to_platform_channel"]`) —
    confirm it's checked rather than assuming.
  Create via the Agents destination (`new-agent-btn` → General tab: name `test-agent`, pick the
  provider + model → `save-agent-btn`) if it doesn't already exist on the scratch
  instance.
- **Credential**: this instance is gated (Mission 20 Flight 1). Follow CLAUDE.md's
  "Behavior-test credential convention" — read
  `/tmp/the-one-behavior-test-scratch/api-credential`, mint a handoff URL for the
  browser navigation (re-mint if a step opens a fresh tab/context), and attach
  `Authorization: Bearer <credential>` to every `curl` call below (the two
  `/api/_test/stub/...` seams and `GET /api/chat/sessions` are ordinary gated
  routes, not the unauthenticated `/api/live`).
- A browser apparatus (chrome-devtools MCP or similar) attached to the `8485`
  origin; `curl` available for the seam/session calls. Never touch `8484`.

## Observables Required

- **browser** (Library › Connectors editor form and the Library list's Connectors group; the Chats list (`chats-list`) and the conversation's unified history,
  including the peer-attributed and operator-only rendering distinctions) —
  measured via the registered browser apparatus
- **http** (seam routes `POST /api/_test/stub/inbound` and
  `GET /api/_test/stub/outbound`; `GET /api/connectors`, `GET /api/connectors/{id}`,
  `POST /api/connectors/{id}/pairing-code`; `GET /api/chat/sessions` for keying
  fields — via `curl`)

## Steps

Let `{ID}` denote the connector's id, captured in Step 1 and reused verbatim in
every later payload/URL below.

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | **Create + gate probe.** Navigate to `{base}#library/connectors` (Library in the rail, the list's Connectors group). Open the Library list's **Add** menu (`library-add-btn`) and choose "Connector" (`library-add-connector`; the create form opens beside the list at `#library/connectors/~new`); wait for `save-connector-btn` to render. Confirm the Type `<select data-field="type">` includes an option `value="stub"` — if absent, the dual gate isn't open; HALT and re-check the env vars in Preconditions. Fill `[data-field="name"]`=`bt-stub`, select `[data-field="type"]`=`stub`, fill `[data-field="token"]`=`dummy`, select `[data-field="default_agent"]`=`test-agent`. Click `save-connector-btn`. | Save succeeds: `delete-connector-btn` becomes visible. `[data-field="token"]`'s value is **not** `dummy`, and `dummy` does not appear anywhere in the page content (masked round-trip — the same contract `tests/test_api_secret_mask_roundtrip.py` pins at the API layer). `curl -H "Authorization: Bearer <cred>" {base}/api/connectors` returns exactly one entry with `name=="bt-stub"` and `type=="stub"`; record its `id` as `{ID}`. |
| 2 | Click `connector-pairing-btn`. | `connector-pairing-result` renders `Code: <code> (expires <ISO8601>)`. Record `<code>` as `{CODE}`. |
| 3 | Via seam, inject an inbound DM from an unadmitted peer: `curl -X POST {base}/api/_test/stub/inbound -H "Authorization: Bearer <cred>" -H "Content-Type: application/json" -d '{"connector_id":"{ID}","peer_id":"peer-1","peer_name":"peer-1","text":"hello?","is_dm":true}'`. | HTTP 200 `{"status":"ok"}`. Within 10s, `GET {base}/api/_test/stub/outbound` still returns `{"records":[]}` — no reply queued. `GET {base}/api/chat/sessions?agent_name=test-agent` contains no session titled `DM: peer-1` — silence is total: nothing persisted, nothing sent. |
| 4 | Via seam, submit the pairing code as `peer-1`: same POST shape as Step 3 with `"text":"{CODE}"`. Then reload the Connectors page (`#library/connectors` → select the `bt-stub` row in the Library list's Connectors group) and inspect `[data-field="allowlist_peers"]`. Then, via seam, submit the **same** `{CODE}` again from a different unadmitted peer: `"peer_id":"peer-2"`. | After the first submission, `[data-field="allowlist_peers"]` contains `peer-1` on its own line (the connector editor's reload proves persistence, not just an in-memory manager state). After the second submission (peer-2, reusing the now-consumed code), `GET {base}/api/connectors/{ID}` still shows `config.allowlist.peers == ["peer-1"]` — the code was one-time; peer-2 was never admitted. |
| 5 | Via seam, inject from `peer-1`: `"text":"What is 2+2?", "is_dm":true` — a bare question, NO tool-call instruction. Poll `GET {base}/api/_test/stub/outbound` every ~5s for up to 60s. | The outbound records gain an entry with `connector_id=="{ID}"`, `peer_id=="peer-1"`, `channel_id==null`, and `content` (the assistant's own plain-text reply, mechanically auto-delivered per DD-10 — no tool call involved) referencing `4`. In parallel, `GET {base}/api/chat/sessions?agent_name=test-agent` shows exactly one session titled `DM: peer-1`; record its `id` as `{SESSION}`. In the browser, go to **Chats** (the rail), find that session's row in the Chats list (`chat-row[data-id="{SESSION}"]`: the title `DM: peer-1`, the agent `test-agent` on its second line, and a `stub` platform badge) and open it (the hash becomes `#chats/{SESSION}`). The history shows the peer's inbound text as a bubble with classes `msg user msg-from-peer` (a visually-hidden `From peer-1: ` label per the a11y pattern). The agent's own text reply renders as an ordinary peer-visible `msg assistant` bubble — **no** `msg-operator-only` class and **no** `[operator-only]` marker — BY DESIGN per DD-10: `dispatch_inbound`'s auto-reply pass mechanically delivered this turn's final assistant text to the originating DM target and flipped its `visibility` to peer-visible (`the_one/connectors/inbound.py::_auto_deliver_reply`); a plain reply reaching the platform no longer depends on the model calling `send_to_platform_channel` (contrast Step 7, the deliberate tool-initiated path). Both bubbles carry `data-testid="message"`. |
| 6 | With that session open, type `note to self` into `chat-input` and send it (`chat-send-btn`). | The message renders in the same unified history as an ordinary `msg user` bubble — **no** `msg-from-peer` class (it's the operator's own bubble, not peer-attributed) and **no** visible `[operator-only]` label (that marker is deliberately suppressed on the operator's own user bubbles — see `message-bubble.js`'s "M10 F05 L08 HAT" comment — even though the message is tagged `visibility=operator` server-side). The load-bearing check: `GET {base}/api/_test/stub/outbound` record count is **unchanged** from Step 5 — the operator's note never reached the stub platform. |
| 7 | Via seam, inject from `peer-1`: `"text":"Please send me the word \"ping\" by calling send_to_platform_channel with target {\"connector_id\": \"{ID}\", \"peer_id\": \"peer-1\"} and content \"ping\".", "is_dm":true`. Poll `GET {base}/api/_test/stub/outbound` every ~5s for up to 60s. | The outbound records gain EXACTLY ONE new entry (not two) with `connector_id=="{ID}"`, `peer_id=="peer-1"`, `content` containing `ping` — DD-10's skip rule: this turn's successful `send_to_platform_channel` result suppresses the mechanical auto-reply pass entirely, so the turn's own trailing assistant text (if any) is never separately auto-delivered on top of the tool's delivery. Rejoin/refresh the `{SESSION}` conversation in the Chat UI: the delivered result renders as its OWN top-level bubble — a direct child of `.messages`, a sibling of the trace shells and other message bubbles, NOT nested inside any `[data-testid="trace-shell"]`/"Tool activity" accordion — whose text begins with `[platform-send-ok]`, carries no `.msg-operator-only` class, and is followed by a `.msg-attribution.from-agent` row, like an ordinary delivered assistant reply. No expand/click is needed to see it: it must be perceivable in the collapsed (default) render, consistent with `tag_post_step_visibility`'s rule that a successful `send_to_platform_channel` result is tagged `visibility=None` (peer-visible) while everything else in the turn — including the tool CALL that produced it, and any trailing assistant text the skip rule left un-delivered — stays operator-only and collapsed inside its trace shell. |

## Out of Scope

- Live Discord/Telegram behavior (Flights 3–4 live HATs).
- Reconnect/backoff under gateway failure (unit-tested; live-verified in Flight 3).
- Channel (non-DM) reply policy nuances — @mention and always-listen are unit-tested; a live-channel variant may be added in Flight 3.
- Whether a real platform message, with no in-band target instruction, reliably elicits a `send_to_platform_channel` call from the model on the first turn — DD-10 (2026-09-01) closed this gap FOR THE ORDINARY REPLY CASE by making delivery mechanical rather than model-dependent (Step 5 no longer needs the in-band target instruction at all). The residual, narrower question — whether a model reliably chooses the tool-INITIATED path for a DELIBERATE cross-channel send with no in-band target instruction — remains open and is tracked as a follow-up rather than asserted or fixed here.
- The doctor probe and the channel→agent map — covered by `tests/browser/test_studio_connector_editor.py` and unit tests; not re-verified here.
