# Connectors

Bridges external chat platforms to the agent loop. Mission 23 Flight 1 removed
the pre-reset framework (a ~430-line message-routing layer, per-agent ACLs,
manual peer-approval flows, a slash-command surface, the Discord plugin)
wholesale; Flight 2 rebuilt a small, platform-agnostic core from scratch.
This file is the contract — not a tutorial on the pre-reset design, which is
gone.

No production plugin ships yet. Discord lands Flight 3. The only registered
plugin today is `stub.py`'s in-process `StubPlugin` — a test/dev fixture,
registered only by tests or by the dual-gated startup hook described under
"Test seams" below, never in a real deployment.

## Protocol (`base.py`)

Two structural `Protocol`s (`the_one/agents.md`'s
`structural-Protocol-satisfaction` convention — no inheritance required):

- **`ConnectorPlugin`** — the type-level adapter for a platform. `connect(account, encryptor, on_inbound) -> ConnectorClient` returns once the plugin's gateway listener is live; it does not block for the connection's lifetime. `disconnect(client)` is idempotent teardown. `doctor(account, encryptor) -> DoctorReport` is a cheap health probe.
- **`ConnectorClient`** — one instance per running listener. `is_alive()` is polled by the manager's supervisor loop. `send(target, content) -> SendResult` delivers outbound content. `history(target, limit) -> list[HistoryMessage]` is OPTIONAL (DD-8) — discovered via `getattr(client, "history", None)`, not declared on the Protocol, so a plugin that doesn't support history carries no stub method.

`InboundCallback = Callable[[InboundEnvelope], Awaitable[None]]` — the
callback a plugin invokes (from inside its own gateway-listener task) for
every inbound message. `ConnectorManager` threads this callback into every
`plugin.connect()` call; plugins never import `the_one.connectors.inbound`
directly (that would invert the dependency direction — plugins are leaves,
the manager wires them up).

## Envelope flags (`InboundEnvelope`, `base.py`)

A normalized inbound message: `platform`, `connector_id`, `channel_id`,
`thread_id`, `peer_id`, `peer_name`, `text`, `is_dm`, `mentions_bot`. `is_dm`
and `mentions_bot` are set by the *platform client's own translation layer* —
the inbound pipeline never infers them from `channel_id` shape.

`SendTarget = ChannelTarget | PeerTarget` — a channel-keyed or peer-keyed
(DM) send destination. `channel_map` (below) never applies to a `PeerTarget`
(DD-4).

## Manager lifecycle (`manager.py`)

One `ConnectorManager` instance is installed at lifespan startup
(`set_manager`/`get_manager`, mirroring `agent.factory.set_factory`/
`get_factory`). It owns one supervised listener task per connector:

- `start(account, encryptor, repo=None)` spawns a supervisor task
  (`_run`) that connects, holds while `client.is_alive()`, and
  reconnects with exponential backoff (`backoff_base` → `backoff_max`,
  ±25% jitter) on disconnect or a failed connect.
- The **first** connect attempt uses the `account` snapshot passed to
  `start()`. Every attempt **after** that — every reconnect — re-fetches a
  fresh row from `repo` (when supplied) before reconnecting, so a listener
  that outlives a `PUT`-driven config change or an encryption-key rotation
  never reconnects on stale credentials.
- `stop(connector_id)` cancels the task and awaits it; idempotent on an
  unknown id. `drain()` stops everything (lifespan shutdown).
- Pairing codes (below) live in the same instance, keyed by connector id.

## Inbound pipeline (`inbound.py`)

`dispatch_inbound(connector_id, envelope, manager=...)` runs one inbound
envelope through, in order:

1. **Admission** — `is_admitted`: flat allowlist check (peer OR channel).
   Unadmitted → silent drop, with one exception: a DM whose body is the
   live pairing code consumes it and appends the sender to
   `allowlist.peers`. Nothing else persists for an unadmitted sender.
2. **`/new` interception** — an admitted DM/channel message that is exactly
   `/new` writes an `ended_at` sentinel on the matching session (if any) and
   returns; no agent turn runs. Any other `/foo` command is not
   intercepted — it reaches the agent as ordinary text.
3. **Reply policy** — `should_reply`: DM, `@mention`, or an
   `always_listen` channel. Otherwise the message is admitted (and could
   pair/append to history) but gets no agent turn.
4. **Session resolution** — `resolve_session`: keyed on
   `(platform, connector_id, channel_id, thread_id)` — **not** `peer_id`,
   which is stored on the row but not part of the lookup. Reuses the most
   recent matching row within the continuation window
   (`session_continuation_seconds` override, else
   `THE_ONE_SESSION_CONTINUATION_SECONDS` env var, else 24h) unless it
   carries a `/new`-written `ended_at` sentinel, else creates a fresh row
   titled `f"DM: {peer_name}"` (DM) or the channel id.
5. **Dispatch** — under a per-session lock (`the_one.sessions.session_locks`),
   rebuilds the agent from the session's stored history, runs
   `agent.step(envelope.text)`, tags post-step message visibility (see
   "Reply visibility" below), and persists the updated history. Errors at
   any stage are logged and swallowed — a connector-layer failure never
   takes the agent runtime down.

Explicitly **out of scope** (superseded by design, not a placeholder): no
per-agent ACL, no message-routing layer, no routing/audit log, no
command-handler protocol beyond `/new`, no LLM-inferred engagement filter.

## Pairing (DD-3)

`POST /api/connectors/{id}/pairing-code` (operator-only) mints a
`secrets.token_hex(4)` code with a 10-minute TTL
(`ConnectorManager.PAIRING_TTL_SECONDS`), replacing any prior code for that
connector. Consumption (`consume_pairing_code`) has no `await` between check
and delete, so concurrent submissions of the same code resolve atomically
under asyncio's cooperative scheduling — first caller wins. A second
submission (wrong, expired, or already-consumed) is a silent no-op, exactly
like any other unadmitted message.

## Reply visibility

Every message an `agent.step()` call appends is tagged by
`tag_post_step_visibility` (`the_one/llm/base.py`): a successful
`send_to_platform_channel` tool result (content starting with
`[platform-send-ok]`) gets `visibility=None` (peer-visible — the tool
already pushed it to the platform); everything else the turn produces
(plain assistant text, intermediate tool calls/results) is tagged
`visibility="operator"` — console-only, never forwarded. An operator's own
typed message in the same session is tagged `visibility="operator"` at
construction time by the WS handler, for the same reason: **plain-text
replies never auto-reach the platform** — only an explicit
`send_to_platform_channel` call delivers content to a peer or channel.

## Authorization rule (send tool + history tool)

`send_to_platform_channel` (`tools/connector_send.py`) and
`fetch_channel_history` (`tools/connector_history.py`, DD-8) share one
binding-derived authorization rule, re-checked against the live `Connector`
row at call time — a union across the two target shapes:

- **Channel target** — sendable/readable by `channel_map[channel_id]`'s
  agent if that channel has a mapping, else by `default_agent`: the same
  agent that would *receive* an inbound message on that channel.
- **DM (peer) target** — sendable/readable **only** by `default_agent` —
  `channel_map` never applies to DMs — and only to a peer already on
  `allowlist.peers`.

Any other calling agent, or a DM target outside the allowlist, gets an
`[error] [constraint] ...` string back — never an exception, never a
platform call.

## Config schema (DD-2)

`Connector.config` is a closed reserved-key dict — unknown top-level keys
are rejected at validation time:

| Key | Shape | Meaning |
|-----|-------|---------|
| `default_agent` | `str` | The DM recipient/sender; the channel fallback when no `channel_map` entry matches. A dangling reference (renamed/deleted agent) is a doctor-reported warning, not a validator error. |
| `channel_map` | `dict[str, str]` | `channel_id -> agent_name`, channel targets only. |
| `allowlist` | `{"peers"?: [str], "channels"?: [str]}` | Admission list (see above). |
| `always_listen` | `list[str]` | Channel ids that get a reply with no `@mention`. |

`Connector.secrets` is a free-form dict (the platform credential, e.g.
`{"token": "..."}"`), Fernet-encrypted at rest and masked on every API
response — see [SECURITY-MODEL.md](../../SECURITY-MODEL.md) "Connector
Channel Contract" for the masking/rotation contract.

## Test seams (DD-10)

`POST /api/_test/stub/inbound` and `GET /api/_test/stub/outbound`
(`interfaces/web/api.py`) require **both** `settings.dev_mode` and
`THE_ONE_STUB_TEST_ENDPOINT=1` — the same dual gate that admits `"stub"`
into `GET /api/connectors/types` and drives the lifespan-startup hook that
registers `StubPlugin`. These seams inject free text into a live agent loop
with real LLM calls and tool execution (purge-sweep's risk profile, not the
inert-metadata OAuth-pending seam's) — never available outside a
dev/test instance. See `tests/behavior/stub-connector-round-trip.md` for the
end-to-end HAT that exercises them against a real agent loop.

## Known limitations

- **No persisted `enabled` field.** `Connector.config`'s reserved-key set
  has no `enabled` key, and there is no top-level DB column for it either —
  adding one is a real schema migration, out of Flight 2's "routes +
  Studio form" scope. Every created connector starts listening immediately;
  `DELETE` stops it; `PUT` unconditionally stops and restarts the listener
  on every successful save (a strict superset of "credential/enabled/type
  change restarts the listener"). The Studio form has no "enabled"
  checkbox — an operator cannot pause a connector without deleting it.
  Tracked as an open item for Flight 3/4 design, not silently expanded into
  Flight 2.
- **No in-band way for an agent to discover its own `connector_id`/`peer_id`.**
  `dispatch_inbound` passes only the raw inbound `text` to `agent.step()` —
  no connector id, no peer id, no directive is injected into the turn (the
  pre-reset auto-relay system-prompt directive was deleted in the Mission 23
  reset, not reattached). A real platform message with no in-band target
  instruction has no reliable way to elicit a `send_to_platform_channel`
  call on the first turn from a general-purpose model. See
  `tests/behavior/stub-connector-round-trip.md`'s "Why the reply steps embed
  the tool-call target" note for the empirical read on this gap; closing it
  (a per-turn injected directive, mirroring the removed one, paired with a
  mechanical fallback per `the_one/agents.md`'s
  `prompt-discipline-needs-mechanical-fallback` convention) is Flight 3+
  scope, not fixed here.
