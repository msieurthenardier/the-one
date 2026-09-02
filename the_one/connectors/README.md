# Connectors

Bridges external chat platforms to the agent loop. Mission 23 Flight 1 removed
the pre-reset framework (a ~430-line message-routing layer, per-agent ACLs,
manual peer-approval flows, a slash-command surface, the Discord plugin)
wholesale; Flight 2 rebuilt a small, platform-agnostic core from scratch.
This file is the contract — not a tutorial on the pre-reset design, which is
gone.

Flight 3 ships the first real plugin, Discord (`discord/`) — registered
unconditionally at lifespan startup, unlike `stub.py`'s in-process
`StubPlugin`, which stays a test/dev fixture registered only by tests or by
the dual-gated startup hook described under "Test seams" below, never in a
real deployment. See "Discord (Flight 3)" below for the plugin's own
contract.

## Protocol (`base.py`)

Two structural `Protocol`s (`the_one/agents.md`'s
`structural-Protocol-satisfaction` convention — no inheritance required):

- **`ConnectorPlugin`** — the type-level adapter for a platform. `connect(account, encryptor, on_inbound) -> ConnectorClient` returns once the plugin's gateway listener is live; it does not block for the connection's lifetime. `disconnect(client)` is idempotent teardown. `doctor(account, encryptor) -> DoctorReport` is a cheap health probe.
- **`ConnectorClient`** — one instance per running listener. `is_alive()` is polled by the manager's supervisor loop. `send(target, content) -> SendResult` delivers outbound content. `history(target, limit) -> list[HistoryMessage]` is OPTIONAL (DD-8) — discovered via `getattr(client, "history", None)`, not declared on the Protocol, so a plugin that doesn't support history carries no stub method. `sever_for_test()` is another OPTIONAL hook, same discovery pattern (DD-7, Mission 23 Flight 3 Leg 3) — the Discord client's controlled-disconnect test seam; see "Test seams" below.

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
`visibility="operator"` — console-only, not yet forwarded.

**DD-10 auto-reply mechanical fallback**: for an inbound turn dispatched
through `dispatch_inbound` (i.e. a peer's own message, not the operator's
console), that "everything else" tagging is not the end of the story. Right
after `tag_post_step_visibility` runs, `dispatch_inbound`'s
`_auto_deliver_reply` pass mechanically delivers the turn's FINAL assistant
message text to the ORIGINATING target — `PeerTarget(connector_id, peer_id)`
for a DM, `ChannelTarget(connector_id, channel_id, thread_id)` for a channel
— via `manager.client_for(connector_id).send()`, then flips that message's
`visibility` back to `None` (peer-visible), since it genuinely reached the
peer. **Skip rule (no double-send)**: if the turn already contains a
successful `send_to_platform_channel` result, the agent spoke to the
platform deliberately — auto-delivery is skipped entirely for that turn
(even when the tool-send targeted a *different* channel; the agent's own
plain text then stays operator-only, by design). Delivery failure (no live
client, `ConnectorClientError`, or any other exception from `send()`) is
logged and the message's visibility is left as `tag_post_step_visibility`
tagged it (operator-only) — no retry, no crash; the turn is still persisted.

The operator's own typed message in the same session is unaffected: it is
tagged `visibility="operator"` at construction time by the WS handler and
never runs through `dispatch_inbound` at all, so it is never auto-delivered
— **an operator's console note never reaches the platform**. What DD-10
changes is narrower and specific: a peer's inbound message that gets a
plain-text reply now has that reply mechanically delivered back to the same
peer/channel, independent of whether the model chose to call
`send_to_platform_channel`. The send tool remains the agent-INITIATED path
(speak-first, cross-channel, or a deliberate re-send) — this fallback only
ever fires for the turn's own reply-in-kind.

## Send-tool target defaulting (DD-11)

`send_to_platform_channel`'s `target` argument is OPTIONAL (Mission 23
Flight 3, mid-flight amendment — live-gate checkpoint 5 proved the DD-5
carve-out works (the model calls the tool by name, unprompted) but "send
to this channel" dead-ends: the session's connector/channel keying is
invisible to the model, so it asks the operator for platform ids). When
`target` is omitted, the tool resolves one from `current_chat_session_id`
(`agent/_context.py`) → that session's `chat_sessions` row → the row's
own keying columns, mirroring `resolve_session`'s keying (`channel_id`,
not `peer_id`, is the session's primary key, per "Session resolution"
above): a `channel_id`-bearing session resolves to
`ChannelTarget(connector_id, channel_id, thread_id)`; a session with no
`channel_id` but a `peer_id` resolves to `PeerTarget(connector_id,
peer_id)`. No active session context, or a session not bound to a
connector at all (both columns unset), is a clear `[error] [constraint]`
— never a guess. The resolved default is folded into the exact dict
shape an explicit `target` takes, so it is authorized by the SAME rule
below — a defaulted target that fails authorization errors identically
to an explicit one. Explicit `target` arguments are unaffected.

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

`enabled` (`bool`, default `true`, DD-6) pauses a connector without
deleting it: `false` stops the listener (and keeps it stopped across
restarts — `start_all` skips disabled rows) while the row, config, and
secrets stay intact. Absent key reads as enabled — no migration was
needed. A `PUT` branches on the NEW effective value only: `true` → stop
+ start, `false` → stop only, regardless of the prior value (so a
disabled→disabled save never accidentally restarts the listener). Doctor
reports `disabled` as a distinct top-level field, independent of the
plugin's own health status — a connector can be both disabled AND carry a
stale permanent-failure marker.

## Discord (Flight 3)

`discord/` (`_gateway.py`, `_rest.py`, `plugin.py`) — a hand-rolled Gateway
v10 client on `websockets` and a bot-only REST client on `httpx`; no
`discord.py`/`aiohttp` dependency (mission constraint). Registered
unconditionally at lifespan startup (`the_one/interfaces/web/app.py`) — a
real platform, not gated like the stub.

- **Gateway protocol scope**: hello → heartbeat loop (jittered first beat,
  ACK-watchdog — a missed ACK closes and lets the manager reconnect) →
  identify (`GUILDS | GUILD_MESSAGES | DIRECT_MESSAGES | MESSAGE_CONTENT`
  intents) → dispatch, handling `READY` (captures `session_id` +
  `resume_gateway_url`) and `MESSAGE_CREATE`. **No sharding, no zlib
  compression** — out of scope for a personal-bot deployment; a guild
  count that would require sharding is not this project's target shape.
- **Resume behavior**: a dropped connection resumes against the
  `resume_gateway_url` READY advertised, replaying `session_id` +
  `last_seq`; a stale/unreachable resume URL falls back to a fresh
  `Get Gateway Bot` lookup + identify within the same `connect()` call. Op
  7 (`RECONNECT`) triggers a prompt self-initiated close so the next
  attempt resumes normally.
- **Close-code policy**: Discord's non-reconnectable codes (`4004` auth
  failure; `4010`–`4014` shard/intent misconfiguration) raise a
  `PermanentConnectorFailure` (`connectors/base.py` — contract-level, so
  Telegram inherits it). The manager stops retrying and logs; the plugin
  records a per-account failure marker so `doctor()` short-circuits to
  `"permanently failed: <reason>"` without a REST round-trip. The marker
  clears unconditionally at the top of every fresh `connect()` — the only
  reset point, so a PUT-driven stop/start recovers a fixed token with no
  extra wiring. **Accepted trade-off**: the close-code check runs only
  pre-`READY`; a permanent code observed mid-session is not raised
  immediately — it surfaces at the *next* handshake instead (one backoff
  cycle of latency), deliberately, since the token is equally bad either
  way and an immediate-signal path would add machinery for no recovery
  benefit.
- **REST rate limiting**: per-bucket serialization keyed by
  `X-RateLimit-Bucket` (learned from the first response on a route) plus a
  global gate that a `429` with `global: true` engages across every
  bucket; `retry_after` is honored with bounded retries. No request
  queuing beyond per-bucket serialization — a personal bot's volume
  doesn't need it. ~10 endpoints: Get Gateway Bot, Get Current User,
  Create Message, Create DM, Get Channel, Get Channel Messages (powers
  `history`), Trigger Typing, Get Guild Channels. No webhooks, no
  interactions/slash surface.
- **Credential**: the bot token lives in `Connector.secrets["token"]`
  (`Authorization: Bot <token>` on every REST call and in the gateway
  identify payload) — the same masked-at-rest, Fernet-encrypted contract
  every connector's secrets follow.
- **Per-account state**: `registry` plugins are type-keyed singletons, so
  `DiscordPlugin` holds `session_id`/`resume_gateway_url`/live-connection
  state in an account-id-keyed dict (the shape `StubPlugin._live` already
  established) — one Discord connector's reconnect never touches another's
  state.
- **Envelope translation**: `MESSAGE_CREATE` → `InboundEnvelope` with
  `is_dm` from the channel type (resolved via the READY private-channels
  cache or a channel fetch, cached thereafter), `mentions_bot` from the
  mentions array containing the bot's own user id, `peer_name` from the
  author's global/display name, `thread_id` set for thread channel types.
  Messages authored by the bot itself, any other bot, or a webhook are
  dropped before the pipeline (loop prevention) — webhook-authored content
  is treated as bot-authored, a deliberate scope trade-off.
- **Controlled-disconnect test seam**: see "Test seams" below — this is a
  test-only hook, never reachable in production traffic.

## Test seams (DD-10, DD-7)

`POST /api/_test/stub/inbound` and `GET /api/_test/stub/outbound`
(`interfaces/web/api.py`) require **both** `settings.dev_mode` and
`THE_ONE_STUB_TEST_ENDPOINT=1` — the same dual gate that admits `"stub"`
into `GET /api/connectors/types` and drives the lifespan-startup hook that
registers `StubPlugin`. These seams inject free text into a live agent loop
with real LLM calls and tool execution (purge-sweep's risk profile, not the
inert-metadata OAuth-pending seam's) — never available outside a
dev/test instance. See `tests/behavior/stub-connector-round-trip.md` for the
end-to-end HAT that exercises them against a real agent loop.

`POST /api/_test/discord/sever` (Mission 23 Flight 3 Leg 3, DD-7) requires
**both** `settings.dev_mode` and `THE_ONE_DISCORD_TEST_ENDPOINT=1` — its own
gate name, not the stub gate above (`risk-tiered-test-seam-gating`,
`the_one/agents.md`). Abruptly severs a live connector's gateway websocket
via the OPTIONAL `sever_for_test` hook (`getattr(client, "sever_for_test",
None)`, discovered through `manager.client_for` — never a Discord-specific
import, so any future plugin that defines the hook gets this seam for
free). Body: `{"connector_id": "..."}`. Error taxonomy: unknown connector
→ 404; row exists but no live client (mid-backoff or never started) → 409;
client present but no hook (e.g. a stub-typed connector) → 501. Never a
production kill switch. See `tests/behavior/discord-live-round-trip.md`'s
step 6 for the end-to-end resume proof this seam drives.

## Known limitations

- **No in-band way for an agent to discover its own `connector_id`/`peer_id`,
  for a DELIBERATE (agent-initiated) send.** `dispatch_inbound` passes only
  the raw inbound `text` to `agent.step()` — no connector id, no peer id, no
  directive is injected into the turn (the pre-reset auto-relay
  system-prompt directive was deleted in the Mission 23 reset, not
  reattached). For the ORDINARY reply case this is no longer a live gap:
  Mission 23 Flight 3's DD-10 auto-reply mechanical fallback (see "Reply
  visibility" above) delivers a plain reply back to the originating target
  without the model ever needing to discover or call
  `send_to_platform_channel` — the mechanical fallback
  `the_one/agents.md`'s `prompt-discipline-needs-mechanical-fallback`
  convention calls for. DD-11's target defaulting (see "Send-tool target
  defaulting" above) narrows what remains further: a model that decides to
  proactively call the send tool for its OWN session's platform
  conversation — a deliberate re-send, or a reply the auto-fallback's skip
  rule suppressed — no longer needs to discover a target at all; omitting
  `target` reaches that same conversation mechanically. What is still open
  is narrower still: a model choosing to send to a *different*
  channel/DM than the one it's currently bound to, with no in-band
  instruction naming that other target, still has no way to discover an id
  it wasn't told. See `tests/behavior/stub-connector-round-trip.md`'s "Why
  the reply steps embed the tool-call target" note for the empirical read
  on this residual gap.
